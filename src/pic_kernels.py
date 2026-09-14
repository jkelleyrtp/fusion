"""Local FP64 particle operators for the transient PIC integrator."""

import torch

from cusp_sim import QM
from electrostatic import ElectrostaticMesh, clip_segment, sphere_segment_fraction


class ReferenceKernels:
    def __init__(self, mesh: ElectrostaticMesh) -> None:
        self.mesh = mesh

    def deposit(self, position: torch.Tensor, charge: torch.Tensor) -> torch.Tensor:
        return self.mesh.deposit(position, charge)

    def potential(self, charge: torch.Tensor) -> torch.Tensor:
        return self.mesh.potential(charge)

    def gather(self, potential: torch.Tensor, position: torch.Tensor) -> torch.Tensor:
        return self.mesh.gather(potential, position)[1]

    def drift(
        self, position: torch.Tensor, velocity: torch.Tensor, h: float, core_radius: float,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        end, fraction, hit = clip_segment(position, position + h * velocity, self.mesh)
        inside, entered = sphere_segment_fraction(position, end, core_radius)
        return end, fraction, hit, inside, entered

    def boris(
        self, velocity: torch.Tensor, electric: torch.Tensor, magnetic: torch.Tensor, h: float,
        qm: float = QM,
    ) -> torch.Tensor:
        minus = velocity + 0.5 * h * qm * electric
        t = 0.5 * h * qm * magnetic
        s = 2 * t / (1 + t.square().sum(dim=1, keepdim=True))
        prime = minus + torch.linalg.cross(minus, t)
        return minus + torch.linalg.cross(prime, s) + 0.5 * h * qm * electric
