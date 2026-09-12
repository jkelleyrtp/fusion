import math
import unittest
from itertools import pairwise

import torch

from cusp_sim import E_CHARGE
from electrostatic import ElectrostaticMesh
from transient_pic import PIC


def mesh(nodes: int = 17) -> ElectrostaticMesh:
    lower = torch.full((3,), -1.0, dtype=torch.float64)
    return ElectrostaticMesh(lower, -lower, (nodes,) * 3)


def zero_field(position: torch.Tensor) -> torch.Tensor:
    return torch.zeros_like(position)


def closed_pair() -> PIC:
    simulation = PIC(mesh(), zero_field, 0.2, 10)
    position = torch.tensor(
        [[0.21, 0.17, 0.13], [-0.23, -0.19, -0.11]], dtype=torch.float64,
    )
    simulation.inject(
        position, torch.zeros_like(position), position.new_full((2,), 1e7),
    )
    return simulation


def energy(simulation: PIC) -> float:
    _, potential = simulation.fields()
    return float(simulation.kinetic_energy() + simulation.mesh.field_energy(potential))


class TransientPICTests(unittest.TestCase):
    def test_half_step_losses_and_residence(self):
        simulation = PIC(mesh(), zero_field, 0.2, 10, track=3)
        position = torch.tensor(
            [[0.999, 0, 0], [0.993, 0, 0], [0, 0, 0]], dtype=torch.float64,
        )
        velocity = position.new_tensor([[1e6, 0, 0], [1e6, 0, 0], [0, 0, 0]])
        simulation.inject(position, velocity, position.new_tensor([0, 0, 0]))
        simulation.advance(1e-8)
        self.assertEqual(simulation.particles.ids.tolist(), [2])
        self.assertEqual(simulation.lost_count, 2)
        self.assertAlmostEqual(simulation.lost_dwell, 8e-9, delta=1e-21)
        torch.testing.assert_close(
            simulation.tracked_exit_time[:2], position.new_tensor([1e-9, 7e-9]),
            rtol=0, atol=1e-21,
        )
        self.assertEqual(simulation.exit_counts.tolist(), [0, 2, 0, 0, 0, 0])
        self.assertAlmostEqual(float(simulation.particles.core_dwell[0]), 1e-8)

    def test_empty_population(self):
        simulation = PIC(mesh(), zero_field, 0.2, 10)
        simulation.advance(1e-8)
        charge, potential = simulation.fields()
        self.assertEqual(float(charge.abs().sum()), 0)
        self.assertEqual(float(potential.abs().sum()), 0)
        self.assertEqual(simulation.diagnostics(charge, potential)["alive_count"], 0)

    def test_magnetic_rotation_preserves_speed(self):
        def uniform_field(position):
            result = torch.zeros_like(position)
            result[:, 2] = 0.001
            return result

        simulation = PIC(mesh(), uniform_field, 0.2, 10)
        position = torch.tensor([[0.123, 0, 0]], dtype=torch.float64)
        simulation.inject(
            position, position.new_tensor([[1e5, 0, 0]]), position.new_zeros(1),
        )
        for _ in range(100):
            simulation.advance(1e-11)
        squared_speed = float(simulation.particles.velocity.square().sum())
        self.assertLess(abs(squared_speed / 1e10 - 1), 5e-13)

    def test_closed_energy_time_refinement(self):
        errors = []
        for h in (1e-8, 5e-9, 2.5e-9):
            simulation = closed_pair()
            initial = energy(simulation)
            for _ in range(round(1e-7 / h)):
                simulation.advance(h)
            errors.append(abs(energy(simulation) - initial))
        for coarse, fine in pairwise(errors):
            self.assertGreater(coarse / fine, 3)
            self.assertLess(coarse / fine, 5)

    def test_closed_time_reversal(self):
        simulation = closed_pair()
        position = simulation.particles.position.clone()
        velocity = simulation.particles.velocity.clone()
        simulation.advance(1e-8)
        simulation.particles.velocity.neg_()
        simulation.advance(1e-8)
        simulation.particles.velocity.neg_()
        torch.testing.assert_close(
            simulation.particles.position, position, rtol=0, atol=2e-15,
        )
        torch.testing.assert_close(
            simulation.particles.velocity, velocity, rtol=0, atol=1e-8,
        )

    def test_instantaneous_charge_and_loss_accounting(self):
        simulation = PIC(mesh(), zero_field, 0.2, 10)
        position = torch.tensor([[0.999, 0, 0], [0, 0, 0]], dtype=torch.float64)
        simulation.inject(
            position, position.new_tensor([[1e6, 0, 0], [0, 0, 0]]),
            position.new_tensor([2, 3]),
        )
        charge, _ = simulation.fields()
        self.assertAlmostEqual(float(charge.sum()), -5 * E_CHARGE, delta=1e-33)
        simulation.advance(1e-8)
        charge, potential = simulation.fields()
        diagnostics = simulation.diagnostics(charge, potential)
        self.assertAlmostEqual(float(charge.sum()), -3 * E_CHARGE, delta=1e-33)
        self.assertAlmostEqual(simulation.lost_charge, -2 * E_CHARGE, delta=1e-33)
        self.assertAlmostEqual(diagnostics["charge_balance_C"], 0, delta=1e-33)
        self.assertLess(float(potential.min()), 0)

    def test_capacity_and_invalid_steps(self):
        simulation = PIC(mesh(), zero_field, 0.2, 1)
        position = torch.zeros((1, 3), dtype=torch.float64)
        simulation.inject(position, position, position.new_zeros(1))
        with self.assertRaisesRegex(ValueError, "max-live"):
            simulation.inject(position, position, position.new_zeros(1))
        self.assertEqual(simulation.injected_count, 1)
        for h in (0, -1, math.inf, math.nan):
            with self.assertRaisesRegex(ValueError, "Timestep"):
                simulation.advance(h)

    def test_resolution_guards(self):
        position = torch.tensor([[0.123, 0.17, 0.19]], dtype=torch.float64)
        fast = PIC(mesh(), zero_field, 0.2, 10)
        fast.inject(
            position, position.new_tensor([[1e6, 0, 0]]), position.new_zeros(1),
        )
        with self.assertRaisesRegex(ValueError, "drift bound"):
            fast.advance(1e-6)
        dense = PIC(mesh(), zero_field, 0.2, 10)
        dense.inject(position, torch.zeros_like(position), position.new_full((1,), 1e10))
        with self.assertRaisesRegex(ValueError, "omega_p"):
            dense.advance(1e-6)
        magnetic = PIC(
            mesh(), lambda p: p.new_tensor([0, 0, 1]).expand_as(p), 0.2, 10,
        )
        magnetic.inject(position, torch.zeros_like(position), position.new_zeros(1))
        with self.assertRaisesRegex(ValueError, "gyration"):
            magnetic.advance(1e-8)

    def test_all_absorbing_faces(self):
        simulation = PIC(mesh(), zero_field, 0.2, 10, track=6)
        direction = torch.tensor(
            [[-1, 0, 0], [1, 0, 0], [0, -1, 0],
             [0, 1, 0], [0, 0, -1], [0, 0, 1]], dtype=torch.float64,
        )
        simulation.inject(
            0.999 * direction, 1e6 * direction, direction.new_zeros(6),
        )
        simulation.advance(1e-8)
        self.assertEqual(len(simulation.particles.ids), 0)
        self.assertEqual(simulation.exit_counts.tolist(), [1] * 6)
        self.assertEqual(simulation.tracked_exit_face.tolist(), list(range(6)))


if __name__ == "__main__":
    unittest.main()
