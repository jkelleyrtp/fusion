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


if __name__ == "__main__":
    unittest.main()
