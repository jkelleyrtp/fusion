import unittest
from pathlib import Path

from run_pic_campaign import commands
from run_transient_pic import parser, validate


class CampaignTests(unittest.TestCase):
    def test_matched_weight_and_bounded_output(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40)
        configurations = [parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 4)
        self.assertEqual([validate(item) for item in configurations], [7500, 7500, 7500, 15000])
        self.assertEqual([item.current_a for item in configurations], [0, 1e-3, 1, 1])
        baseline, refined = configurations[-2:]
        self.assertEqual(
            baseline.dt * baseline.inject_every / baseline.inject_per_step,
            refined.dt * refined.inject_every / refined.inject_per_step,
        )
        self.assertEqual(
            validate(baseline) // baseline.inject_every * baseline.inject_per_step,
            validate(refined) // refined.inject_every * refined.inject_per_step,
        )
        self.assertEqual(
            baseline.save_every * baseline.dt, refined.save_every * refined.dt,
        )
        for item in configurations:
            self.assertEqual(item.duration, 3e-8)
            self.assertEqual(item.nodes, 33)
            self.assertEqual(item.source_sigma, 5e-5)
            self.assertEqual(item.divergence_deg, 10)
            self.assertEqual(item.source_revision, "a" * 40)
            self.assertEqual(1 + validate(item) // item.save_every, 13)

    def test_long_window_study_is_bounded_and_matched(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "window")
        configurations = [parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 8)
        self.assertEqual([item.device for item in configurations], [f"cuda:{i}" for i in range(8)])
        self.assertEqual([item.nodes for item in configurations], [33, 49, 65, 97, 129, 65, 65, 65])
        baseline = configurations[2]
        for item in configurations:
            steps = validate(item)
            self.assertEqual(item.kernels, "cuda")
            self.assertEqual(item.duration, 3e-7)
            self.assertEqual(1 + steps // item.save_every, 11)
            self.assertEqual(item.save_every * item.dt, baseline.save_every * baseline.dt)
            self.assertEqual(
                item.diagnostic_every * item.dt, baseline.diagnostic_every * baseline.dt,
            )
            self.assertEqual(item.diagnostic_every * item.dt, 1e-9)
            self.assertLessEqual(
                steps // item.inject_every * item.inject_per_step, item.max_live_particles,
            )
            self.assertEqual(item.source_sigma, 5e-5)
            self.assertEqual(item.current_a, 1)
        refined = configurations[6]
        self.assertEqual(
            baseline.dt * baseline.inject_every / baseline.inject_per_step,
            refined.dt * refined.inject_every / refined.inject_per_step,
        )


if __name__ == "__main__":
    unittest.main()
