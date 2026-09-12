"""FP64 electron PIC with instantaneous charge and synchronized particle states."""

import math
from collections.abc import Callable
from dataclasses import dataclass

import torch

from cusp_sim import E_CHARGE, M_E, QM
from electrostatic import (
    EPSILON_0,
    ElectrostaticMesh,
    clip_segment,
    sphere_segment_fraction,
)

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
        return Particles(
            self.ids[keep], self.birth[keep], self.position[keep],
            self.velocity[keep], self.weight[keep], self.dwell[keep],
            self.core_dwell[keep], self.entries[keep],
        )


class PIC:
    def __init__(
        self, mesh: ElectrostaticMesh, magnetic_field: MagneticField,
        core_radius: float, max_live: int, track: int = 0,
    ) -> None:
        if not math.isfinite(core_radius) or core_radius <= 0 or max_live < 1:
            raise ValueError("Positive core radius and live-particle limit required")
        if not 0 <= track <= 256:
            raise ValueError("Track count must be between 0 and 256")
        self.mesh = mesh
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

    def inject(
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
            if not torch.isfinite(tensor).all():
                raise ValueError("Particle arrays must be finite")
        if (weight < 0).any():
            raise ValueError("Represented electron counts must be nonnegative")
        self.mesh.stencil(position)
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
        self.injected_count += count
        self.injected_charge += float(-E_CHARGE * weight.sum())
        self.injected_kinetic += float(
            (0.5 * M_E * weight * velocity.square().sum(dim=1)).sum(),
        )
        tracked = ids < len(self.tracked_birth)
        self.tracked_birth[ids[tracked]] = self.time
        self.tracked_position[ids[tracked]] = position[tracked]

    def fields(self) -> tuple[torch.Tensor, torch.Tensor]:
        p = self.particles
        charge = self.mesh.deposit(p.position, -E_CHARGE * p.weight)
        return charge, self.mesh.potential(charge)

    def kinetic_energy(self) -> torch.Tensor:
        p = self.particles
        return (0.5 * M_E * p.weight * p.velocity.square().sum(dim=1)).sum()

    def _drift(self, h: float, start_time: float) -> None:
        p = self.particles
        if len(p.ids) == 0:
            return
        end, fraction, hit = clip_segment(
            p.position, p.position + h * p.velocity, self.mesh,
        )
        elapsed = h * fraction
        inside, entered = sphere_segment_fraction(p.position, end, self.core_radius)
        p.dwell += elapsed
        p.core_dwell += elapsed * inside
        p.entries += entered.long()
        tracked = p.ids < len(self.tracked_birth)
        self.tracked_position[p.ids[tracked]] = end[tracked]
        if hit.any():
            lost = p.select(hit)
            self.lost_count += len(lost.ids)
            self.lost_charge += float(-E_CHARGE * lost.weight.sum())
            self.lost_kinetic += float(
                (0.5 * M_E * lost.weight * lost.velocity.square().sum(dim=1)).sum(),
            )
            self.lost_dwell += float(lost.dwell.sum())
            self.lost_core_dwell += float(lost.core_dwell.sum())
            self.lost_electron_dwell += float((lost.weight * lost.dwell).sum())
            self.lost_electron_core_dwell += float((lost.weight * lost.core_dwell).sum())
            self.lost_entries += int(lost.entries.sum())
            self.lost_repeated_entries += int((lost.entries >= 2).sum())
            distances = torch.stack((
                (end[hit] - self.mesh.lower).abs() / self.mesh.h,
                (end[hit] - self.mesh.upper).abs() / self.mesh.h,
            ), dim=2).flatten(start_dim=1)
            faces = distances.argmin(dim=1)
            self.exit_counts += torch.bincount(faces, minlength=6)
            tracked_hits = lost.ids < len(self.tracked_birth)
            self.tracked_exit_time[lost.ids[tracked_hits]] = (
                start_time + elapsed[hit][tracked_hits]
            )
            self.tracked_exit_face[lost.ids[tracked_hits]] = faces[tracked_hits]
        p.position = end
        self.particles = p.select(~hit)

    def _check_speed(self, h: float) -> None:
        if len(self.particles.ids) == 0:
            return
        speed = self.particles.velocity.norm(dim=1).max()
        if not torch.isfinite(speed):
            raise ValueError("Nonfinite particle velocity")
        if speed * h > 0.2 * self.mesh.h.min():
            raise ValueError("Timestep exceeds the 0.2-cell drift bound")

    def advance(self, h: float) -> None:
        if not math.isfinite(h) or h <= 0:
            raise ValueError("Timestep must be finite and positive")
        self._check_speed(h)
        self._drift(h / 2, self.time)
        charge, potential = self.fields()
        omega_p = torch.sqrt(
            charge.abs().max() * E_CHARGE / (self.mesh.volume * EPSILON_0 * M_E),
        )
        if omega_p * h > 0.1:
            raise ValueError("Timestep exceeds omega_p * dt <= 0.1")
        p = self.particles
        if len(p.ids):
            electric = self.mesh.gather(potential, p.position)[1]
            magnetic = self.magnetic_field(p.position)
            if (magnetic.shape != p.position.shape or magnetic.dtype != torch.float64
                    or magnetic.device != p.position.device
                    or not torch.isfinite(magnetic).all()):
                raise ValueError("Magnetic field must be finite FP64, N by 3 on the mesh device")
            if abs(QM) * magnetic.norm(dim=1).max() * h > 2 * math.pi / 80:
                raise ValueError("Timestep requires at least 80 steps per gyration")
            minus = p.velocity + 0.5 * h * QM * electric
            t = 0.5 * h * QM * magnetic
            s = 2 * t / (1 + t.square().sum(dim=1, keepdim=True))
            prime = minus + torch.linalg.cross(minus, t)
            p.velocity = minus + torch.linalg.cross(prime, s) + 0.5 * h * QM * electric
        self._check_speed(h)
        self._drift(h / 2, self.time + h / 2)
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
