import math
import sys
import unittest
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from electrostatic import (
    EPSILON_0,
    Conductors,
    Cylinder,
    ElectrostaticMesh,
    clip_segment,
    sphere_segment_fraction,
)
from steady_space_charge import E_CHARGE, M_E, thermal_source, trace_packet


def zero_field(positions: torch.Tensor) -> torch.Tensor:
    return torch.zeros_like(positions)


class ElectrostaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        torch.set_num_threads(1)

    def mesh(self, nodes: int = 17) -> ElectrostaticMesh:
        lower = torch.tensor([-1, -1, -1], dtype=torch.float64)
        return ElectrostaticMesh(lower, -lower, (nodes,) * 3)

    def test_charge_conservation_including_boundary_shapes(self) -> None:
        mesh = self.mesh()
        torch.manual_seed(10)
        points = torch.rand(100, 3, dtype=torch.float64) * 2 - 1
        points[:2] = torch.stack((mesh.lower, mesh.upper))
        charges = torch.rand(100, dtype=torch.float64) * -1e-12
        deposited = mesh.deposit(points, charges)
        self.assertAlmostEqual(float(deposited.sum() / charges.sum()), 1, places=14)
        self.assertEqual(float(deposited[0, 0, 0]), float(charges[0]))
        with self.assertRaises(ValueError):
            mesh.deposit(points + 4, charges)

    def test_revalidates_positions_modified_after_a_check(self) -> None:
        mesh = self.mesh()
        points = torch.zeros(4, 3, dtype=torch.float64)
        mesh.check_positions(points)
        mesh.check_positions(points)
        points[0, 0] = 2
        with self.assertRaisesRegex(ValueError, "inside the box"):
            mesh.check_positions(points)
        points[0, 0] = math.nan
        with self.assertRaisesRegex(ValueError, "Nonfinite"):
            mesh.deposit(points, torch.ones(4, dtype=torch.float64))

    def test_poisson_discrete_manufactured_solution_and_energy(self) -> None:
        lower = torch.tensor([-1, -2, -3], dtype=torch.float64)
        mesh = ElectrostaticMesh(lower, -lower, (9, 13, 17))
        axes = [torch.arange(n, dtype=torch.float64) * math.pi / (n - 1) for n in mesh.shape]
        expected = -(axes[0].sin()[:, None, None] * (2 * axes[1]).sin()[None, :, None]
                     * axes[2].sin()[None, None, :])
        expected[[0, -1], :, :] = 0
        expected[:, [0, -1], :] = 0
        expected[:, :, [0, -1]] = 0
        charge = torch.zeros_like(expected)
        charge[1:-1, 1:-1, 1:-1] = mesh.negative_laplacian(expected) * EPSILON_0 * mesh.volume
        actual = mesh.potential(charge)
        self.assertLess(float((actual - expected).abs().max()), 3e-14)
        self.assertLess(float(mesh.residual(actual, charge)), 1e-13)
        energy = float(mesh.field_energy(actual))
        self.assertGreater(energy, 0)
        self.assertAlmostEqual(energy / float(0.5 * (actual * charge).sum()), 1, places=13)

    def test_poisson_continuum_second_order(self) -> None:
        errors = []
        for n in (9, 17, 33):
            mesh = self.mesh(n)
            axis = torch.arange(n, dtype=torch.float64) * math.pi / (n - 1)
            exact = -axis.sin()[:, None, None] * axis.sin()[None, :, None] * axis.sin()[None, None, :]
            charge = exact * (3 * (math.pi / 2) ** 2) * EPSILON_0 * mesh.volume
            errors.append(float((mesh.potential(charge) - exact).abs().max()))
        self.assertTrue(3.9 < errors[0] / errors[1] < 4.2)
        self.assertTrue(3.9 < errors[1] / errors[2] < 4.2)

    def test_gather_matches_particle_mesh_energy_gradient(self) -> None:
        mesh = self.mesh()
        points = torch.tensor([[0.123, 0.234, 0.345], [-0.37, -0.24, -0.19]], dtype=torch.float64)
        charges = torch.tensor([-1e-12, -2e-12], dtype=torch.float64)
        potential = mesh.potential(mesh.deposit(points, charges))
        force = charges[0] * mesh.gather(potential, points)[1][0, 0]
        displaced = points.clone()
        delta = 1e-6
        displaced[0, 0] += delta
        plus = mesh.field_energy(mesh.potential(mesh.deposit(displaced, charges)))
        displaced[0, 0] -= 2 * delta
        minus = mesh.field_energy(mesh.potential(mesh.deposit(displaced, charges)))
        self.assertAlmostEqual(float(force / (-(plus - minus) / (2 * delta))), 1, places=8)

    def test_negative_charge_has_negative_potential(self) -> None:
        mesh = self.mesh()
        points = torch.zeros(1, 3, dtype=torch.float64)
        potential = mesh.potential(mesh.deposit(points, points.new_tensor([-1e-12])))
        self.assertLess(float(potential.min()), 0)
        self.assertLess(float(potential.max()), 1e-14)
        self.assertEqual(float(potential[0].abs().sum()), 0)

    def test_conductors_hold_voltages_and_induce_charge(self) -> None:
        mesh = self.mesh(13)
        shapes = (
            Cylinder((0, 0, -0.5), (0, 0, 1), 1.0, 0.2),
            Cylinder((0.4, 0, -0.3), (1, 0, 0), 0.4, 0.25, voltage=-100.0),
        )
        conductors = Conductors(mesh, shapes, mesh.potential)
        self.assertTrue(all(count > 0 for count in conductors.node_counts))
        charge = mesh.deposit(
            torch.tensor([[-0.5, 0.4, 0.1]], dtype=torch.float64),
            torch.tensor([-1e-12], dtype=torch.float64),
        )
        potential, induced = conductors.potential(charge)
        torch.testing.assert_close(
            potential.flatten()[conductors.indices], conductors.voltage, rtol=0, atol=1e-9,
        )
        free = torch.ones(mesh.shape, dtype=torch.bool)
        free.view(-1)[conductors.indices] = False
        rhs = charge / (EPSILON_0 * mesh.volume)
        residual = (mesh.negative_laplacian(potential) - rhs[1:-1, 1:-1, 1:-1])[free[1:-1, 1:-1, 1:-1]]
        self.assertLess(float(residual.abs().max() / rhs.abs().max()), 1e-9)
        self.assertLess(float(potential.max()), 1e-9)
        self.assertGreater(float(potential.min()), -100 - 1e-9)
        self.assertLess(float(induced[1]), 0)
        grounded = Conductors(mesh, shapes[:1], mesh.potential)
        _, induced = grounded.potential(charge)
        self.assertGreater(float(induced[0]), 0)
        self.assertLess(float(induced[0]), 1e-12)
        points = torch.tensor([[0, 0, 0], [0.6, 0, -0.3], [0.9, 0.9, 0.9]], dtype=torch.float64)
        self.assertEqual(conductors.absorbing(points).tolist(), [0, 1, -1])

    def test_segment_absorption_and_core_crossing(self) -> None:
        mesh = self.mesh()
        start = torch.tensor([[0, 0, 0], [-0.8, 0, 0]], dtype=torch.float64)
        end = torch.tensor([[2, 0.5, 0], [0.8, 0, 0]], dtype=torch.float64)
        clipped, fraction, hit = clip_segment(start, end, mesh)
        self.assertEqual(hit.tolist(), [True, False])
        self.assertEqual(fraction.tolist(), [0.5, 1])
        self.assertEqual(clipped[0].tolist(), [1, 0.25, 0])
        core, entered = sphere_segment_fraction(start[1:], end[1:], 0.2)
        self.assertAlmostEqual(float(core[0]), 0.25, places=14)
        self.assertEqual(entered.tolist(), [True])

    def test_ballistic_residence_current_and_core_inventory(self) -> None:
        mesh = self.mesh()
        positions = torch.tensor([[0, 0, -0.8]], dtype=torch.float64)
        velocity = positions.new_tensor([[0, 0, 1]])
        packet = trace_packet(mesh, positions, velocity, positions.new_zeros(mesh.shape),
                              zero_field, 1e-6, 0.07, 3, 0.2)
        self.assertTrue(bool(packet.escaped[0]))
        self.assertAlmostEqual(float(packet.dwell[0]), 1.8, places=13)
        self.assertAlmostEqual(float(packet.core_dwell[0]), 0.4, places=13)
        self.assertEqual(int(packet.entries[0]), 1)
        self.assertAlmostEqual(float(packet.charge.sum()), -1.8e-6, places=19)

    def test_censored_residence_is_included(self) -> None:
        mesh = self.mesh()
        positions = torch.zeros(2, 3, dtype=torch.float64)
        velocity = positions.new_tensor([[0, 0, 1], [0, 0, -1]])
        packet = trace_packet(mesh, positions, velocity, positions.new_zeros(mesh.shape),
                              zero_field, 1e-6, 0.03, 0.1, 0.2)
        self.assertFalse(bool(packet.escaped.any()))
        self.assertLess(float((packet.dwell - 0.1).abs().max()), 1e-15)
        self.assertAlmostEqual(float(packet.charge.sum()), -1e-7, places=20)

    def test_recorded_orbits_preserve_ids_losses_and_physics(self) -> None:
        mesh = self.mesh()
        positions = torch.zeros(4, 3, dtype=torch.float64)
        velocity = positions.new_tensor([[0, 0, -1], [0, 0, 2], [1, 0, 0], [0, 0, 0.1]])
        potential = positions.new_zeros(mesh.shape)
        baseline = trace_packet(mesh, positions, velocity, potential, zero_field,
                                1e-6, 0.07, 3, 0.2)
        packet = trace_packet(mesh, positions, velocity, potential, zero_field,
                              1e-6, 0.07, 3, 0.2, track=4, frames=17)
        self.assertTrue(torch.equal(packet.charge, baseline.charge))
        self.assertTrue(torch.equal(packet.dwell, baseline.dwell))
        self.assertTrue(torch.equal(packet.core_dwell, baseline.core_dwell))
        self.assertTrue(torch.equal(packet.final_kinetic_energy, baseline.final_kinetic_energy))
        self.assertEqual(packet.exit_codes.tolist(), [1, 2, 3, 0])
        self.assertIsNotNone(packet.trajectory)
        assert packet.trajectory is not None
        self.assertEqual(packet.trajectory.shape, (4, 17, 3))
        times = torch.arange(17, dtype=torch.float64) * packet.trajectory_dt
        for particle in range(4):
            live = times <= packet.dwell[particle]
            torch.testing.assert_close(packet.trajectory[particle, live],
                                       times[live, None] * velocity[particle])
            self.assertTrue(torch.isnan(packet.trajectory[particle, ~live]).all())

    def test_recorded_orbits_cover_fractional_final_step(self) -> None:
        mesh = self.mesh()
        positions = torch.zeros(1, 3, dtype=torch.float64)
        velocity = positions.new_tensor([[0, 0, 1]])
        packet = trace_packet(mesh, positions, velocity, positions.new_zeros(mesh.shape),
                              zero_field, 0, 0.03, 0.11, 0.2, track=1, frames=12)
        assert packet.trajectory is not None
        torch.testing.assert_close(packet.trajectory[0, :, 2],
                                   torch.linspace(0, 0.11, 12, dtype=torch.float64))

    def test_uniform_electric_field_energy(self) -> None:
        mesh = self.mesh()
        x = torch.linspace(-1, 1, mesh.shape[0], dtype=torch.float64)
        potential = -x[:, None, None].expand(mesh.shape)
        positions = torch.tensor([[0.123, 0, 0]], dtype=torch.float64)
        velocity = positions.new_tensor([[1e5, 0, 0]])
        packet = trace_packet(mesh, positions, velocity, potential, zero_field,
                              0, 1e-10, 1e-9, 0.2)
        self.assertLess(float(packet.relative_energy_error.max()), 1e-10)

    def test_uniform_magnetic_field_preserves_speed(self) -> None:
        mesh = self.mesh()
        positions = torch.tensor([[0.123, 0, 0]], dtype=torch.float64)
        velocity = positions.new_tensor([[1e5, 0, 0]])

        def magnetic_field(points: torch.Tensor) -> torch.Tensor:
            field = torch.zeros_like(points)
            field[:, 2] = 0.02
            return field

        packet = trace_packet(mesh, positions, velocity, positions.new_zeros(mesh.shape), magnetic_field,
                              0, 1e-11, 1e-8, 0.2)
        self.assertLess(float(packet.relative_energy_error.max()), 1e-12)

    def test_flux_source_energy_moments_and_reproducibility(self) -> None:
        args = ([0, 0, -1], [0, 0, 1], 5.0, 0.2, 0.001, 100000, torch.device("cpu"), 44)
        positions, velocity = thermal_source(*args)
        energy = 0.5 * M_E / E_CHARGE * velocity.square().sum(dim=1)
        self.assertAlmostEqual(float(energy.mean()), 5.4, delta=0.004)
        self.assertAlmostEqual(float(energy.var()), 0.08, delta=0.003)
        self.assertAlmostEqual(float(positions[:, 0].std()), 0.001, delta=1e-5)
        self.assertTrue(bool((velocity[:, 2] > 0).all()))
        repeated_pos, repeated_vel = thermal_source(*args)
        self.assertTrue(torch.equal(positions, repeated_pos))
        self.assertTrue(torch.equal(velocity, repeated_vel))


if __name__ == "__main__":
    unittest.main()
