import unittest
from pathlib import Path

from ion_pic import parser as ion_parser
from ion_pic import validate_coupled
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

    def test_domain_study_varies_only_the_box(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "domain")
        configurations = [parser().parse_args(command[2:]) for command in argv]
        window = parser().parse_args(commands(Path("/campaign"), "a" * 40, "window")[2][2:])
        self.assertEqual(len(configurations), 8)
        self.assertEqual([item.device for item in configurations], [f"cuda:{i}" for i in range(8)])
        boxes = {(item.box_half_width, item.box_bottom, item.box_top) for item in configurations}
        self.assertEqual(len(boxes), 8)
        self.assertIn((0.6, 1.3, 1.3), boxes)
        box_options = ("out", "device", "box_half_width", "box_bottom", "box_top")
        expected = {key: value for key, value in vars(window).items() if key not in box_options}
        for item in configurations:
            validate(item)
            self.assertEqual(
                {key: value for key, value in vars(item).items() if key not in box_options}, expected,
            )

    def test_gun_study_varies_box_barrel_seed_and_mesh(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "gun")
        configurations = [parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 8)
        self.assertEqual([item.device for item in configurations], [f"cuda:{i}" for i in range(8)])
        wall, *barrels = configurations
        self.assertEqual((wall.box_bottom, wall.gun_radius), (1.3, 0))
        self.assertTrue(all(item.box_bottom > 1.3 and item.gun_radius > 0 for item in barrels))
        self.assertEqual([item.nodes for item in configurations], [65] * 7 + [97])
        self.assertEqual([item.seed for item in configurations], [1234] * 6 + [2345, 1234])
        for item in configurations:
            validate(item)
            self.assertEqual((item.current_a, item.duration, item.kernels), (1, 3e-7, "cuda"))

    def test_casing_study_encloses_the_coils(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "casing")
        configurations = [parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 8)
        control, *cased = configurations
        self.assertEqual((control.box_half_width, control.casing_radius), (0.6, 0))
        self.assertTrue(all(item.casing_radius > 0 and item.box_half_width > 1 for item in cased))
        self.assertEqual(sorted({item.casing_voltage for item in cased}), [-1000, 0, 1000])
        for item in configurations:
            validate(item)
            self.assertEqual((item.gun_radius, item.box_bottom, item.kernels), (0.06, 1.95, "cuda"))

    def test_ion_study_uses_the_casing_geometry(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "ions")
        self.assertTrue(all(command[1].endswith("ion_pic.py") for command in argv))
        configurations = [ion_parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 8)
        self.assertEqual([item.device for item in configurations], [f"cuda:{i}" for i in range(8)])
        for item in configurations:
            validate_coupled(item)
            self.assertEqual(
                (item.box_half_width, item.casing_radius, item.gun_radius, item.current_a, item.kernels),
                (1.2, 0.15, 0.06, 1, "cuda"),
            )
        base, nocx, nosec, dense, *_ = configurations
        self.assertEqual((base.gas_pa, base.cycles, base.cx_cross_section, base.secondaries), (1e-3, 40, 5e-20, True))
        self.assertEqual((nocx.cx_cross_section, nosec.secondaries), (0, False))
        self.assertEqual((dense.gas_pa, dense.cycle_duration), (1e-2, 1e-6))

    def test_six_coil_study_matches_packets_and_encloses_the_coils(self) -> None:
        argv = commands(Path("/campaign"), "a" * 40, "six-coil")
        configurations = [parser().parse_args(command[2:]) for command in argv]
        self.assertEqual(len(configurations), 8)
        control, *six = configurations
        self.assertEqual((control.coils, control.coil_offset), (2, 0.5))
        self.assertTrue(all(item.coils == 6 and item.coil_offset >= 1.2 for item in six))
        self.assertEqual(sorted({item.current_a for item in six}), [1e-3, 1])
        for item in configurations:
            validate(item)
            self.assertEqual(
                (item.dt, item.inject_every, item.inject_per_step, item.duration, item.casing_radius),
                (2e-12, 2, 8, 3e-7, 0.1),
            )


if __name__ == "__main__":
    unittest.main()
