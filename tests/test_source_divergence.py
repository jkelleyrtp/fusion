import math
import sys
import unittest
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steady_space_charge import parser, thermal_source


ORIGIN = [0.0, 0.0, -1.0]
AIM = [0.0, -0.5, math.sqrt(0.75)]
DEVICE = torch.device("cpu")


class SourceDivergenceTests(unittest.TestCase):
    def call(self, temperature: float, divergence: float = 0.0, count: int = 32, sigma: float = 5e-5):
        return thermal_source(ORIGIN, AIM, 5000.0, temperature, sigma, count, DEVICE, 44, divergence)

    def test_omitted_and_explicit_zero_are_bitwise_identical(self):
        for temperature in (0.0, 0.2):
            implicit = self.call(temperature)
            explicit = self.call(temperature, 0.0)
            for actual, expected in zip(implicit, explicit, strict=True):
                torch.testing.assert_close(actual, expected, rtol=0, atol=0)
            torch.manual_seed(44)
            self.call(temperature)
            implicit_draws = torch.rand(10, dtype=torch.float64)
            torch.manual_seed(44)
            self.call(temperature, 0.0)
            explicit_draws = torch.rand(10, dtype=torch.float64)
            torch.testing.assert_close(implicit_draws, explicit_draws, rtol=0, atol=0)

    def test_divergence_preserves_positions_and_speed_but_changes_direction(self):
        for temperature in (0.0, 0.2):
            positions, baseline = self.call(temperature)
            rotated_positions, rotated = self.call(temperature, 10.0)
            torch.testing.assert_close(positions, rotated_positions, rtol=0, atol=0)
            np.testing.assert_allclose(
                rotated.square().sum(dim=1).numpy(),
                baseline.square().sum(dim=1).numpy(),
                rtol=2e-14,
                atol=0,
            )
            self.assertFalse(torch.equal(rotated, baseline))

    def test_nonzero_divergence_is_reproducible(self):
        first = self.call(0.2, 10.0)
        second = self.call(0.2, 10.0)
        for actual, expected in zip(first, second, strict=True):
            torch.testing.assert_close(actual, expected, rtol=0, atol=0)

    def test_cold_source_cone_distribution(self):
        count = 20_000
        positions, velocity = self.call(0.0, 20.0, count, sigma=0)
        np.testing.assert_array_equal(positions.numpy(), np.tile(ORIGIN, (count, 1)))
        direction = torch.as_tensor(AIM, dtype=torch.float64)
        direction /= direction.norm()
        unit_velocity = velocity / velocity.norm(dim=1, keepdim=True)
        cosine = unit_velocity @ direction
        bound = math.cos(math.radians(20.0))
        self.assertGreaterEqual(float(cosine.min()), bound - 1e-14)
        self.assertLessEqual(float(cosine.max()), 1 + 1e-14)
        expected_mean = (1 + bound) / 2
        tolerance = 5 * (1 - bound) / math.sqrt(12 * count)
        self.assertLess(abs(float(cosine.mean()) - expected_mean), tolerance)
        transverse = unit_velocity - cosine[:, None] * direction
        self.assertLess(float(transverse.mean(dim=0).norm()), 5 * math.sin(math.radians(20)) / math.sqrt(count))

    def test_invalid_sigma_and_divergence_rejected(self):
        for sigma in (-1.0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                thermal_source(ORIGIN, AIM, 5000, 0.2, sigma, 32, DEVICE, 44)
        for divergence in (-1.0, 90.0, math.nan, math.inf):
            with self.assertRaises(ValueError):
                self.call(0.2, divergence)

    def test_parser_default_and_value(self):
        self.assertEqual(parser().parse_args(["--out", "out"]).divergence_deg, 0)
        self.assertEqual(parser().parse_args(["--out", "out", "--divergence-deg", "10"]).divergence_deg, 10)


if __name__ == "__main__":
    unittest.main()
