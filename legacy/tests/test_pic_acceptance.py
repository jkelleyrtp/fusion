import unittest
from pathlib import Path

from accept_pic_cuda import evaluate, seconds_per_step
from run_pic_campaign import commands
from run_transient_pic import parser, validate


def summary(**overrides: float | list[int]) -> dict[str, object]:
    result: dict[str, object] = {
        "injected_particles": 60000,
        "minimum_potential_V": -967.6,
        "field_energy_J": 1.2e-3,
        "observed_dwell_s": 1.5e-9,
        "observed_core_dwell_s": 1.0e-10,
        "core_electron_count": 420.0,
        "loss_fraction": 0.0078,
        "core_entry_events_per_injected_particle": 0.30,
        "repeated_entry_particle_fraction": 0.011,
        "deposition_error_C": 1.7e-23,
        "charge_balance_C": 4.0e-23,
        "exit_counts_xlo_xhi_ylo_yhi_zlo_zhi": [0, 0, 0, 0, 0, 468],
    }
    result.update(overrides)
    return result


class AcceptanceCommandTests(unittest.TestCase):
    def test_paired_seeds_on_eight_devices(self) -> None:
        configurations = [
            parser().parse_args(command[2:])
            for command in commands(Path("/campaign"), "b" * 40, "acceptance", "reference")
        ]
        self.assertEqual(len(configurations), 8)
        self.assertEqual([validate(item) for item in configurations], [7500] * 8)
        self.assertEqual(
            [item.seed for item in configurations],
            [1234, 1234, 2345, 2345, 3456, 3456, 4567, 4567],
        )
        self.assertEqual(
            [item.kernels for item in configurations],
            ["reference", "cuda"] * 4,
        )
        self.assertEqual(
            [item.device for item in configurations], [f"cuda:{index}" for index in range(8)],
        )
        source_keys = (
            "current_a", "coil_current", "radius", "energy_ev", "temperature_ev",
            "aim_deg", "source_sigma", "divergence_deg", "duration", "nodes",
            "dt", "inject_per_step", "inject_every", "save_every",
        )
        baseline = configurations[0]
        for item in configurations:
            self.assertEqual(
                {key: vars(item)[key] for key in source_keys},
                {key: vars(baseline)[key] for key in source_keys},
            )


class AcceptanceEvaluateTests(unittest.TestCase):
    def test_identical_summaries_pass(self) -> None:
        reference = {seed: summary() for seed in (1234, 2345, 3456)}
        cuda = {seed: summary() for seed in (1234, 2345, 3456)}
        self.assertTrue(all(row["passed"] for row in evaluate(reference, cuda)))

    def test_shifted_minimum_potential_fails(self) -> None:
        reference = {seed: summary() for seed in (1234, 2345, 3456)}
        cuda = {seed: summary() for seed in (1234, 2345, 3456)}
        cuda[2345] = summary(minimum_potential_V=-967.6 + 1.0)
        rows = evaluate(reference, cuda)
        self.assertFalse(all(row["passed"] for row in rows))
        failing = [
            row for row in rows
            if row["metric"] == "minimum_potential_V" and not row["passed"]
        ]
        self.assertEqual(len(failing), 1)
        self.assertEqual(failing[0]["seed"], 2345)

    def test_exit_face_count_floor(self) -> None:
        reference = {seed: summary() for seed in (1234, 2345, 3456)}
        within = {seed: summary() for seed in (1234, 2345, 3456)}
        within[1234] = summary(exit_counts_xlo_xhi_ylo_yhi_zlo_zhi=[0, 0, 0, 0, 0, 470])
        self.assertTrue(all(row["passed"] for row in evaluate(reference, within)))
        beyond = {seed: summary() for seed in (1234, 2345, 3456)}
        beyond[1234] = summary(exit_counts_xlo_xhi_ylo_yhi_zlo_zhi=[0, 0, 0, 0, 0, 471])
        rows = evaluate(reference, beyond)
        failing = [row for row in rows if row["metric"] == "exit_zhi" and not row["passed"]]
        self.assertEqual(len(failing), 1)
        self.assertEqual(failing[0]["seed"], 1234)


class TimingTests(unittest.TestCase):
    def test_seconds_per_step(self) -> None:
        history = [
            {"step": 0, "wall_s": 0.0},
            {"step": 625, "wall_s": 2.0},
            {"step": 1250, "wall_s": 4.0},
        ]
        self.assertAlmostEqual(seconds_per_step(history), 0.0032)


if __name__ == "__main__":
    unittest.main()
