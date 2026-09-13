"""FP64 particle-mesh electrostatics in a grounded rectangular conducting box."""

import itertools
import math
import weakref
from collections.abc import Callable
from dataclasses import dataclass

import torch

EPSILON_0 = 8.8541878128e-12


def dst1(values: torch.Tensor, axis: int) -> torch.Tensor:
    size = list(values.shape)
    size[axis] = 1
    zero = values.new_zeros(size)
    extension = torch.cat((zero, values, zero, -values.flip((axis,))), dim=axis)
    return -torch.fft.fft(extension, dim=axis).imag.narrow(axis, 1, values.shape[axis])


@dataclass
class ElectrostaticMesh:
    lower: torch.Tensor
    upper: torch.Tensor
    shape: tuple[int, int, int]

    def __post_init__(self) -> None:
        if self.lower.dtype != torch.float64 or self.upper.dtype != torch.float64:
            raise ValueError("Reference mesh requires FP64 coordinates")
        if self.lower.shape != (3,) or self.upper.shape != (3,):
            raise ValueError("Box coordinates must have three components")
        if not torch.isfinite(self.lower).all() or not torch.isfinite(self.upper).all():
            raise ValueError("Box coordinates must be finite")
        if min(self.shape) < 3 or not (self.upper > self.lower).all():
            raise ValueError("Each axis needs at least three nodes and positive length")
        self.h = (self.upper - self.lower) / self.lower.new_tensor(self.shape).sub(1)
        self.volume = self.h.prod()
        self._checked: tuple[weakref.ref[torch.Tensor], int] | None = None
        self.corners = torch.tensor(list(itertools.product((0, 1), repeat=3)),
                                    device=self.lower.device, dtype=torch.long)
        eigenvalues = []
        for axis, count in enumerate(self.shape):
            k = torch.arange(1, count - 1, device=self.lower.device, dtype=torch.float64)
            eigenvalues.append(4 * torch.sin(math.pi * k / (2 * (count - 1))) ** 2 / self.h[axis] ** 2)
        self.eigenvalues = (eigenvalues[0][:, None, None] + eigenvalues[1][None, :, None]
                            + eigenvalues[2][None, None, :])

    def check_positions(self, positions: torch.Tensor) -> None:
        """Validate positions, skipping a tensor already validated and not modified since."""
        if (self._checked is not None and self._checked[0]() is positions
                and self._checked[1] == positions._version):
            return
        nonfinite, outside = torch.stack((
            ~torch.isfinite(positions).all(),
            ((positions < self.lower) | (positions > self.upper)).any(),
        )).tolist()
        if nonfinite:
            raise ValueError("Nonfinite particle position")
        if outside:
            raise ValueError("Deposit/gather requires positions inside the box")
        self._checked = (weakref.ref(positions), positions._version)

    def stencil(self, positions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        self.check_positions(positions)
        scaled = (positions - self.lower) / self.h
        base = torch.minimum(scaled.floor().long(),
                             self.corners.new_tensor(self.shape).sub(2))
        fraction = scaled - base
        coordinates = base[:, None, :] + self.corners[None, :, :]
        indices = ((coordinates[:, :, 0] * self.shape[1] + coordinates[:, :, 1])
                   * self.shape[2] + coordinates[:, :, 2])
        factors = torch.where(self.corners[None, :, :] == 1,
                              fraction[:, None, :], 1 - fraction[:, None, :])
        return indices, factors

    def deposit(self, positions: torch.Tensor, charge: torch.Tensor) -> torch.Tensor:
        indices, factors = self.stencil(positions)
        nodal_charge = positions.new_zeros(math.prod(self.shape))
        nodal_charge.index_add_(0, indices.flatten(),
                               (factors.prod(dim=2) * charge[:, None]).flatten())
        return nodal_charge.reshape(self.shape)

    def potential(self, charge: torch.Tensor) -> torch.Tensor:
        rhs = charge[1:-1, 1:-1, 1:-1] / (EPSILON_0 * self.volume)
        for axis in range(3):
            rhs = dst1(rhs, axis)
        rhs = rhs / self.eigenvalues
        for axis in range(3):
            rhs = dst1(rhs, axis) / (2 * (self.shape[axis] - 1))
        potential = torch.zeros_like(charge)
        potential[1:-1, 1:-1, 1:-1] = rhs
        return potential

    def gather(self, potential: torch.Tensor, positions: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        indices, factors = self.stencil(positions)
        vertices = potential.flatten()[indices]
        scalar = (vertices * factors.prod(dim=2)).sum(dim=1)
        gradient = []
        for axis in range(3):
            other = [i for i in range(3) if i != axis]
            derivative = (2 * self.corners[:, axis] - 1) / self.h[axis]
            gradient.append((vertices * factors[:, :, other].prod(dim=2) * derivative).sum(dim=1))
        return scalar, -torch.stack(gradient, dim=1)

    def negative_laplacian(self, potential: torch.Tensor) -> torch.Tensor:
        centre = potential[1:-1, 1:-1, 1:-1]
        result = torch.zeros_like(centre)
        for axis in range(3):
            low = [slice(1, -1)] * 3
            high = [slice(1, -1)] * 3
            low[axis], high[axis] = slice(0, -2), slice(2, None)
            result += (2 * centre - potential[tuple(low)] - potential[tuple(high)]) / self.h[axis] ** 2
        return result

    def field_energy(self, potential: torch.Tensor) -> torch.Tensor:
        energy = potential.new_zeros(())
        for axis in range(3):
            energy += (potential.diff(dim=axis) / self.h[axis]).square().sum()
        return 0.5 * EPSILON_0 * self.volume * energy

    def residual(self, potential: torch.Tensor, charge: torch.Tensor) -> torch.Tensor:
        rhs = charge[1:-1, 1:-1, 1:-1] / (EPSILON_0 * self.volume)
        return (self.negative_laplacian(potential) - rhs).abs().max() / rhs.abs().max().clamp_min(1e-30)


def clip_segment(start: torch.Tensor, end: torch.Tensor,
                 mesh: ElectrostaticMesh) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    delta = end - start
    limits = torch.where(delta > 0, (mesh.upper - start) / delta,
                         torch.where(delta < 0, (mesh.lower - start) / delta, torch.inf))
    fraction = limits.min(dim=1).values.clamp(0, 1)
    hit = ((end <= mesh.lower) | (end >= mesh.upper)).any(dim=1)
    endpoint = start + fraction[:, None] * delta
    return endpoint.clamp(mesh.lower, mesh.upper), fraction, hit


def sphere_segment_fraction(start: torch.Tensor, end: torch.Tensor,
                            radius: float) -> tuple[torch.Tensor, torch.Tensor]:
    delta = end - start
    a = delta.square().sum(dim=1)
    b = 2 * (start * delta).sum(dim=1)
    c = start.square().sum(dim=1) - radius * radius
    discriminant = b * b - 4 * a * c
    root = discriminant.clamp_min(0).sqrt()
    lo = (-b - root) / (2 * a).clamp_min(1e-300)
    hi = (-b + root) / (2 * a).clamp_min(1e-300)
    fraction = (hi.clamp(0, 1) - lo.clamp(0, 1)).clamp_min(0)
    fraction = torch.where(a == 0, (c < 0).to(start.dtype), fraction)
    entries = (a > 0) & (discriminant > 0) & (lo > 0) & (lo <= 1)
    return fraction, entries


@dataclass(frozen=True)
class Cylinder:
    """Solid cylinder of `radius` around the segment from `start` along unit `axis` for `length`."""

    start: tuple[float, float, float]
    axis: tuple[float, float, float]
    length: float
    radius: float
    voltage: float = 0.0

    def __post_init__(self) -> None:
        if abs(math.hypot(*self.axis) - 1) > 1e-12 or self.length <= 0 or self.radius <= 0:
            raise ValueError("Cylinder needs a unit axis and positive length and radius")

    def contains(self, points: torch.Tensor) -> torch.Tensor:
        relative = points - points.new_tensor(self.start)
        along = relative @ points.new_tensor(self.axis)
        radial = relative.square().sum(dim=1) - along.square()
        return (along >= 0) & (along <= self.length) & (radial <= self.radius ** 2)


@dataclass(frozen=True)
class Torus:
    """Solid torus around the z axis: tube of `minor_radius` about the circle of `major_radius` at `center_z`."""

    center_z: float
    major_radius: float
    minor_radius: float
    voltage: float = 0.0

    def __post_init__(self) -> None:
        if not 0 < self.minor_radius < self.major_radius:
            raise ValueError("Torus needs 0 < minor radius < major radius")

    def contains(self, points: torch.Tensor) -> torch.Tensor:
        radial = torch.hypot(points[:, 0], points[:, 1]) - self.major_radius
        return radial.square() + (points[:, 2] - self.center_z).square() <= self.minor_radius ** 2


Shape = Cylinder | Torus


class Conductors:
    """Conductor surface nodes held at fixed potentials by induced nodal charge (capacitance matrix).

    Only nodes inside a shape with a node outside every shape among their 26 neighbours are held;
    enclosed nodes then carry no charge and follow at the conductor voltage. Each solve adds the
    induced charge that restores the held potentials and solves again.
    """

    def __init__(
        self, mesh: ElectrostaticMesh, shapes: tuple[Shape, ...],
        potential: Callable[[torch.Tensor], torch.Tensor],
    ) -> None:
        self.mesh = mesh
        self.shapes = shapes
        self._potential = potential
        axes = [
            torch.linspace(float(mesh.lower[axis]), float(mesh.upper[axis]), count,
                           dtype=torch.float64, device=mesh.lower.device)
            for axis, count in enumerate(mesh.shape)
        ]
        grid = torch.meshgrid(*axes, indexing="ij")
        nodes = torch.stack(grid, dim=-1).reshape(-1, 3)
        interior = torch.zeros(mesh.shape, dtype=torch.bool, device=mesh.lower.device)
        interior[1:-1, 1:-1, 1:-1] = True
        owner = self.absorbing(nodes)
        outside = (owner < 0).reshape(1, 1, *mesh.shape).to(torch.float64)
        surface = torch.nn.functional.max_pool3d(outside, 3, stride=1, padding=1).flatten() > 0
        self.indices = torch.nonzero((owner >= 0) & surface & interior.flatten()).flatten()
        self.owner = owner[self.indices]
        self.node_counts = torch.bincount(self.owner, minlength=len(shapes)).tolist()
        self.voltage = mesh.lower.new_tensor([shape.voltage for shape in shapes])[self.owner]
        capacitance = mesh.lower.new_zeros((len(self.indices), len(self.indices)))
        unit = mesh.lower.new_zeros(math.prod(mesh.shape))
        for column, node in enumerate(self.indices.tolist()):
            unit[node] = 1.0
            capacitance[:, column] = potential(unit.reshape(mesh.shape)).flatten()[self.indices]
            unit[node] = 0.0
        capacitance = 0.5 * (capacitance + capacitance.T)
        self._inverse = torch.cholesky_inverse(torch.linalg.cholesky(capacitance))

    def absorbing(self, points: torch.Tensor) -> torch.Tensor:
        """Index of the first shape containing each point, or -1."""
        result = torch.full((len(points),), -1, dtype=torch.long, device=points.device)
        for index in reversed(range(len(self.shapes))):
            result = torch.where(self.shapes[index].contains(points), index, result)
        return result

    def potential(self, charge: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Potential with conductors held at their voltages, and induced charge per conductor."""
        free = self._potential(charge)
        induced_total = charge.new_zeros(len(self.shapes))
        if not len(self.indices):
            return free, induced_total
        induced = self._inverse @ (self.voltage - free.flatten()[self.indices])
        total = charge.flatten().index_add(0, self.indices, induced).reshape(self.mesh.shape)
        return self._potential(total), induced_total.index_add_(0, self.owner, induced)
