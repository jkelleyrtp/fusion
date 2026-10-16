import unittest
from pathlib import Path

from run_pic_campaign import commands
from run_transient_pic import parser, validate


class RefinementTests(unittest.TestCase):
    def test_refinement_holds_physical_source_and_output_times(self) -> None:
        configurations = [
            parser().parse_args(command[2:])
            for command in commands(Path("/campaign"), "b" * 40, "refinement", "cuda")
        ]
        baseline, timestep, mesh, particles = configurations
        self.assertEqual(
            [validate(item) for item in configurations], [7500, 15000, 7500, 7500],
        )
        self.assertEqual([item.nodes for item in configurations], [33, 33, 65, 33])
        self.assertEqual(
            [item.inject_per_step for item in configurations], [8, 8, 8, 16],
        )
        source_keys = (
            "current_a", "coil_current", "radius", "energy_ev", "temperature_ev",
            "aim_deg", "source_sigma", "divergence_deg", "duration", "seed",
        )
        for item in configurations:
            self.assertEqual(
                {key: vars(item)[key] for key in source_keys},
                {key: vars(baseline)[key] for key in source_keys},
            )
            self.assertEqual(item.kernels, "cuda")
            self.assertEqual(item.dt * item.inject_every, 4e-12)
            self.assertEqual(item.dt * item.save_every, baseline.dt * baseline.save_every)
            pulses = validate(item) // item.inject_every
            self.assertEqual(pulses, 7500)
            self.assertAlmostEqual(
                pulses * item.dt * item.inject_every * item.current_a, 3e-8, delta=1e-22,
            )
            self.assertLessEqual(pulses * item.inject_per_step, item.max_live_particles)
            self.assertLessEqual(1 + validate(item) // item.save_every, item.max_snapshots)
        self.assertEqual(timestep.dt, baseline.dt / 2)
        self.assertEqual(mesh.nodes - 1, 2 * (baseline.nodes - 1))
        self.assertEqual(particles.inject_per_step, 2 * baseline.inject_per_step)


if __name__ == "__main__":
    unittest.main()
