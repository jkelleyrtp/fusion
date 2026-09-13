"""FP64 electron PIC with instantaneous charge and synchronized particle states."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import torch

from cusp_sim import E_CHARGE, M_E, QM
from electrostatic import (
    EPSILON_0,
    ElectrostaticMesh,
)
from pic_kernels import ReferenceKernels

MagneticField = Callable[[torch.Tensor], torch.Tensor]


@dataclass
class Particles:
    ids: torch.Tensor
    birth: torch.Tensor
    position: torch.Tensor
    velocity: torch.Tensor
    weight: torch.Tensor
    dwell: torch.Tensor
    core_dwell: torch.Tensor
    entries: torch.Tensor

    def select(self, keep: torch.Tensor) -> "Particles":
        if keep.dtype == torch.bool:
            keep = keep.nonzero().squeeze(1)
        return Particles(
            self.ids[keep], self.birth[keep], self.position[keep],
            self.velocity[keep], self.weight[keep], self.dwell[keep],
            self.core_dwell[keep], self.entries[keep],
        )


class PIC:
    def __init__(
        self, mesh: ElectrostaticMesh, magnetic_field: MagneticField,
        core_radius: float, max_live: int, track: int = 0,
        *, kernels: ReferenceKernels | None = None,
    ) -> None:
        if not math.isfinite(core_radius) or core_radius <= 0 or max_live < 1:
            raise ValueError("Positive core radius and live-particle limit required")
        if not 0 <= track <= 256:
            raise ValueError("Track count must be between 0 and 256")
        self.mesh = mesh
        self.kernels = ReferenceKernels(mesh) if kernels is None else kernels
        if self.kernels.mesh is not mesh:
            raise ValueError("Particle operators must use the PIC mesh")
        self.magnetic_field = magnetic_field
        self.core_radius = core_radius
        self.max_live = max_live
        empty = mesh.lower.new_empty(0)
        self.particles = Particles(
            empty.long(), empty.clone(), empty.reshape(0, 3),
            empty.reshape(0, 3), empty.clone(), empty.clone(),
            empty.clone(), empty.long(),
        )
        self.time = 0.0
        self.injected_count = 0
        self.lost_count = 0
        self.injected_charge = 0.0
        self.lost_charge = 0.0
        self.injected_kinetic = 0.0
        self.lost_kinetic = 0.0
        self.lost_dwell = 0.0
        self.lost_core_dwell = 0.0
        self.lost_electron_dwell = 0.0
        self.lost_electron_core_dwell = 0.0
        self.lost_entries = 0
        self.lost_repeated_entries = 0
        self.exit_counts = torch.zeros(6, device=empty.device, dtype=torch.int64)
        self.tracked_position = empty.new_full((track, 3), math.nan)
        self.tracked_birth = empty.new_full((track,), math.nan)
        self.tracked_exit_time = empty.new_full((track,), math.nan)
        self.tracked_exit_face = torch.full(
            (track,), -1, device=empty.device, dtype=torch.int64,
        )
        self._tracked_live = 0

    def _raise_first(
        self, checks: list[tuple[torch.Tensor, str]], *extra: torch.Tensor,
    ) -> list[float]:
        tensors = [flag for flag, _ in checks] + list(extra)
        if not tensors:
            return []
        flags = torch.stack(tensors).tolist()
        for flag, (_, message) in zip(flags, checks, strict=False):
            if flag:
                raise ValueError(message)
        return flags[len(checks):]

    def inject(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
    ) -> None:
        self._check_append(position, velocity, weight)
        charge, kinetic = self._raise_first([
            (~torch.isfinite(tensor).all(), "Particle arrays must be finite")
            for tensor in (position, velocity, weight)
        ] + [
            ((weight < 0).any(), "Represented electron counts must be nonnegative"),
            (((position < self.mesh.lower) | (position > self.mesh.upper)).any(),
             "Deposit/gather requires positions inside the box"),
        ], -E_CHARGE * weight.sum(), (0.5 * M_E * weight * velocity.square().sum(dim=1)).sum())
        self._append(position, velocity, weight, charge, kinetic)

    def append_validated_packet(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: float,
        kinetic_J: float,
    ) -> None:
        """Append equal-weight particles already checked finite and inside the box."""
        if not math.isfinite(weight) or weight < 0 or not math.isfinite(kinetic_J):
            raise ValueError("Represented electron counts must be finite and nonnegative")
        count = len(position)
        weights = torch.full((count,), weight, dtype=torch.float64, device=position.device)
        self._check_append(position, velocity, weights)
        self._append(position, velocity, weights, -E_CHARGE * weight * count, kinetic_J)

    def _check_append(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
    ) -> None:
        count = len(position)
        if len(self.particles.ids) + count > self.max_live:
            raise ValueError("Injection exceeds max-live-particles")
        if position.shape != (count, 3) or velocity.shape != (count, 3):
            raise ValueError("Particle positions and velocities must be N by 3")
        if weight.shape != (count,):
            raise ValueError("Particle weights must have length N")
        for tensor in (position, velocity, weight):
            if tensor.dtype != torch.float64 or tensor.device != self.mesh.lower.device:
                raise ValueError("Particle arrays must be FP64 on the mesh device")

    def _append(
        self, position: torch.Tensor, velocity: torch.Tensor, weight: torch.Tensor,
        charge: float, kinetic: float,
    ) -> None:
        count = len(position)
        ids = torch.arange(
            self.injected_count, self.injected_count + count, device=position.device,
        )
        birth = weight.new_full((count,), self.time)
        zeros = torch.zeros_like(weight)
        p = self.particles
        self.particles = Particles(
            torch.cat((p.ids, ids)), torch.cat((p.birth, birth)),
            torch.cat((p.position, position)), torch.cat((p.velocity, velocity)),
            torch.cat((p.weight, weight)), torch.cat((p.dwell, zeros)),
            torch.cat((p.core_dwell, zeros)), torch.cat((p.entries, zeros.long())),
        )
        start = self.injected_count
        tracked = max(0, min(count, len(self.tracked_birth) - start))
        self.injected_count += count
        self.injected_charge += charge
        self.injected_kinetic += kinetic
        self.tracked_birth[start:start + tracked] = self.time
        self.tracked_position[start:start + tracked] = position[:tracked]
        self._tracked_live += tracked

    def fields(self) -> tuple[torch.Tensor, torch.Tensor]:
        p = self.particles
        charge = self.kernels.deposit(p.position, -E_CHARGE * p.weight)
        return charge, self.kernels.potential(charge)

    def kinetic_energy(self) -> torch.Tensor:
        p = self.particles
        return (0.5 * M_E * p.weight * p.velocity.square().sum(dim=1)).sum()

    def _drift(
        self, h: float, start_time: float, checks: list[tuple[torch.Tensor, str]],
    ) -> None:
        p = self.particles
        if len(p.ids) == 0:
            self._raise_first(checks)
            return
        end, fraction, hit, inside, entered = self.kernels.drift(
            p.position, p.velocity, h, self.core_radius,
        )
        (lost_count,) = self._raise_first(checks, hit.sum())
        elapsed = h * fraction
        p.dwell += elapsed
        p.core_dwell += elapsed * inside
        p.entries += entered.long()
        live = self._tracked_live
        self.tracked_position[p.ids[:live]] = end[:live]
        p.position = end
        if not lost_count:
            return
        survivors = len(p.ids) - int(lost_count)
        order = torch.argsort(hit.to(torch.int8), stable=True)
        lost = p.select(order[survivors:])
        lost_end = end[order[survivors:]]
        stats = torch.stack((
            -E_CHARGE * lost.weight.sum(),
            (0.5 * M_E * lost.weight * lost.velocity.square().sum(dim=1)).sum(),
            lost.dwell.sum(),
            lost.core_dwell.sum(),
            (lost.weight * lost.dwell).sum(),
            (lost.weight * lost.core_dwell).sum(),
            lost.entries.sum().to(torch.float64),
            (lost.entries >= 2).sum().to(torch.float64),
            (lost.ids < len(self.tracked_birth)).sum().to(torch.float64),
        )).tolist()
        tracked = int(stats[8])
        self.lost_count += len(lost.ids)
        self.lost_charge += stats[0]
        self.lost_kinetic += stats[1]
        self.lost_dwell += stats[2]
        self.lost_core_dwell += stats[3]
        self.lost_electron_dwell += stats[4]
        self.lost_electron_core_dwell += stats[5]
        self.lost_entries += int(stats[6])
        self.lost_repeated_entries += int(stats[7])
        self._tracked_live = live - tracked
        distances = torch.stack((
            (lost_end - self.mesh.lower).abs() / self.mesh.h,
            (lost_end - self.mesh.upper).abs() / self.mesh.h,
        ), dim=2).flatten(start_dim=1)
        faces = distances.argmin(dim=1)
        self.exit_counts.index_add_(0, faces, torch.ones_like(faces))
        tracked_ids = lost.ids[:tracked]
        self.tracked_exit_time[tracked_ids] = start_time + elapsed[order[survivors:survivors + tracked]]
        self.tracked_exit_face[tracked_ids] = faces[:tracked]
        self.particles = p.select(order[:survivors])

    def _speed_checks(self, h: float) -> list[tuple[torch.Tensor, str]]:
        if len(self.particles.ids) == 0:
            return []
        speed = self.particles.velocity.norm(dim=1).max()
        return [
            (~torch.isfinite(speed), "Nonfinite particle velocity"),
            (speed * h > 0.2 * self.mesh.h.min(), "Timestep exceeds the 0.2-cell drift bound"),
        ]

    def advance(self, h: float) -> None:
        if not math.isfinite(h) or h <= 0:
            raise ValueError("Timestep must be finite and positive")
        self._drift(h / 2, self.time, self._speed_checks(h))
        charge, potential = self.fields()
        omega_p = torch.sqrt(
            charge.abs().max() * E_CHARGE / (self.mesh.volume * EPSILON_0 * M_E),
        )
        checks = [(omega_p * h > 0.1, "Timestep exceeds omega_p * dt <= 0.1")]
        p = self.particles
        if len(p.ids):
            electric = self.kernels.gather(potential, p.position)
            magnetic = self.magnetic_field(p.position)
            if (magnetic.shape != p.position.shape or magnetic.dtype != torch.float64
                    or magnetic.device != p.position.device):
                raise ValueError("Magnetic field must be finite FP64, N by 3 on the mesh device")
            checks += [
                (~torch.isfinite(magnetic).all(),
                 "Magnetic field must be finite FP64, N by 3 on the mesh device"),
                (abs(QM) * magnetic.norm(dim=1).max() * h > 2 * math.pi / 80,
                 "Timestep requires at least 80 steps per gyration"),
            ]
            p.velocity = self.kernels.boris(p.velocity, electric, magnetic, h)
        self._drift(h / 2, self.time + h / 2, checks + self._speed_checks(h))
        self.time += h

    def diagnostics(
        self, charge: torch.Tensor, potential: torch.Tensor,
    ) -> dict[str, float | int | list[int]]:
        p = self.particles
        alive_charge = float(-E_CHARGE * p.weight.sum())
        kinetic = float(self.kinetic_energy())
        field = float(self.mesh.field_energy(potential))
        in_core = p.position.square().sum(dim=1) < self.core_radius ** 2
        return {
            "time_s": self.time,
            "injected_count": self.injected_count,
            "lost_count": self.lost_count,
            "alive_count": len(p.ids),
            "injected_charge_C": self.injected_charge,
            "lost_charge_C": self.lost_charge,
            "alive_charge_C": alive_charge,
            "charge_balance_C": self.injected_charge - self.lost_charge - alive_charge,
            "deposition_error_C": float(charge.sum()) - alive_charge,
            "boundary_shape_charge_C": float(
                charge.sum() - charge[1:-1, 1:-1, 1:-1].sum(),
            ),
            "kinetic_J": kinetic,
            "field_energy_J": field,
            "injected_kinetic_J": self.injected_kinetic,
            "lost_kinetic_J": self.lost_kinetic,
            "open_energy_balance_J": (
                kinetic + field + self.lost_kinetic - self.injected_kinetic
            ),
            "total_dwell_particle_s": self.lost_dwell + float(p.dwell.sum()),
            "total_core_dwell_particle_s": (
                self.lost_core_dwell + float(p.core_dwell.sum())
            ),
            "total_dwell_electron_s": (
                self.lost_electron_dwell + float((p.weight * p.dwell).sum())
            ),
            "total_core_dwell_electron_s": (
                self.lost_electron_core_dwell + float((p.weight * p.core_dwell).sum())
            ),
            "core_entry_count": self.lost_entries + int(p.entries.sum()),
            "repeated_entry_count": (
                self.lost_repeated_entries + int((p.entries >= 2).sum())
            ),
            "core_particle_count": int(in_core.sum()),
            "core_electron_count": float(p.weight[in_core].sum()),
            "minimum_potential_V": float(potential.min()),
            "exit_counts_xlo_xhi_ylo_yhi_zlo_zhi": self.exit_counts.tolist(),
        }
