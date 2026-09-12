import math
import tempfile
import unittest
from pathlib import Path

import torch

from electrostatic import ElectrostaticMesh
from pic_cuda import CUDAKernels
from pic_kernels import ReferenceKernels
from run_transient_pic import inject_packet, parser, validate
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
            for step in range(validate(args)):
                simulation.time = step * dt
                inject_packet(simulation, args, step)
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
