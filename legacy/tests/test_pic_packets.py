import math
import tempfile
import unittest
from pathlib import Path

import torch

from cusp_sim import E_CHARGE, M_E
from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from pic_kernels import ReferenceKernels
from run_transient_pic import GUN_FACES, GUN_ROTATIONS, GunSource, parser, validate
from transient_pic import PIC
from validate_pic_gpu import compare_states, control


def mesh() -> ElectrostaticMesh:
    lower = torch.full((3,), -1.0, dtype=torch.float64)
    return ElectrostaticMesh(lower, -lower, (17, 17, 17))


class PacketTests(unittest.TestCase):
    def test_refinement_preserves_packets_and_partial_final_charge(self):
        simulations = []
        for dt, every in ((4e-12, 1), (2e-12, 2)):
            args = parser().parse_args([
                "--out", "unused", "--dt", str(dt), "--inject-every", str(every),
                "--duration", "1e-11", "--current-a", "1",
            ])
            simulation = PIC(mesh(), torch.zeros_like, 0.2, 100)
            source = GunSource(args)
            for step in range(validate(args)):
                simulation.time = step * dt
                source.inject(simulation, step)
            self.assertEqual(simulation.injected_count, 24)
            self.assertTrue(math.isclose(simulation.injected_charge, -1e-11, rel_tol=1e-15))
            simulations.append(simulation)
        coarse, fine = (simulation.particles for simulation in simulations)
        for actual, expected in (
            (fine.ids, coarse.ids), (fine.birth, coarse.birth),
            (fine.position, coarse.position), (fine.velocity, coarse.velocity),
            (fine.weight, coarse.weight),
        ):
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)

    def test_gun_blocks_are_independent_and_accounted(self):
        packets = {}
        for seed in (1234, 1235):
            args = parser().parse_args([
                "--out", "unused", "--dt", "4e-12", "--duration", "1.2e-9",
                "--current-a", "1", "--seed", str(seed), "--save-every", "100",
            ])
            simulation = PIC(mesh(), torch.zeros_like, 0.2, 10000)
            source = GunSource(args)
            for step in range(validate(args)):
                simulation.time = step * args.dt
                source.inject(simulation, step)
            p = simulation.particles
            self.assertEqual(simulation.injected_count, 2400)
            self.assertTrue(math.isclose(
                simulation.injected_charge, float(-E_CHARGE * p.weight.sum()), rel_tol=1e-12,
            ))
            self.assertTrue(math.isclose(
                simulation.injected_kinetic,
                float((0.5 * M_E * p.weight * p.velocity.square().sum(dim=1)).sum()),
                rel_tol=1e-12,
            ))
            packets[seed] = p.position.reshape(300, 8, 3)
        self.assertFalse(torch.equal(packets[1234][1], packets[1235][0]))
        self.assertFalse(torch.equal(packets[1234][255], packets[1234][256]))

    def test_extra_guns_are_rotated_copies_with_independent_streams(self):
        common = ["--out", "unused", "--coils", "6", "--current-a", "1", "--divergence-deg", "20"]
        single = GunSource(parser().parse_args([*common, "--inject-per-step", "2"]))
        several = GunSource(parser().parse_args([*common, "--inject-per-step", "12", "--guns", "6"]))
        single._sample(3)
        several._sample(3)
        assert single.cpu is not None and several.cpu is not None
        position, velocity = (value.reshape(256, 12, 3) for value in several.cpu)
        reference = single.cpu[0].reshape(256, 2, 3)
        torch.testing.assert_close(position[:, :2], reference, rtol=0, atol=0)
        torch.testing.assert_close(
            several.speed_square, [6 * value for value in single.speed_square], rtol=0.2, atol=0,
        )
        for index, (axis, sign) in enumerate(((2, -1), (2, 1), (0, -1), (0, 1), (1, -1), (1, 1))):
            gun = position[:, 2 * index:2 * index + 2].reshape(-1, 3)
            torch.testing.assert_close(gun[:, axis], torch.full_like(gun[:, axis], sign * 0.65), rtol=0, atol=1e-3)
            self.assertTrue(bool((sign * velocity[:, 2 * index:2 * index + 2, axis] < 0).all()))
            rotation = torch.tensor(GUN_ROTATIONS[GUN_FACES[6][index]], dtype=torch.float64)
            local = velocity[:, 2 * index:2 * index + 2].reshape(-1, 3) @ rotation
            self.assertEqual(torch.equal(local, single.cpu[1]), index == 0)
            torch.testing.assert_close(local.mean(dim=0), single.cpu[1].mean(dim=0), rtol=0.05, atol=2e6)

    def test_invalid_packet_interval(self):
        args = parser().parse_args(["--out", "unused", "--inject-every", "0"])
        with self.assertRaisesRegex(ValueError, "particle limits"):
            validate(args)

    def test_cuda_does_not_fall_back_on_cpu(self):
        with self.assertRaisesRegex(ValueError, "CUDA mesh"):
            CUDAKernels(mesh())

    def test_operator_mesh_must_match(self):
        with self.assertRaisesRegex(ValueError, "PIC mesh"):
            PIC(mesh(), torch.zeros_like, 0.2, 100, kernels=ReferenceKernels(mesh()))

    def test_state_and_diagnostic_comparator(self):
        expected, h = control("charged", torch.device("cpu"))
        actual, _ = control("charged", torch.device("cpu"))
        for simulation in (expected, actual):
            simulation.advance(h)
        with tempfile.TemporaryDirectory() as directory:
            compare_states(Path(directory), "control", expected, actual)
            actual.particles.velocity[0, 0] += 1
            with self.assertRaises(AssertionError):
                compare_states(Path(directory), "perturbed", expected, actual)


if __name__ == "__main__":
    unittest.main()
