import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from field_diagnostics import E_CHARGE, build_field_data


class FieldDiagnosticsTest(unittest.TestCase):
    def test_axes_units_and_iteration_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            case = Path(directory)
            lower = np.array([-0.3, -0.3, -0.65])
            upper = -lower
            axes = [np.linspace(lo, hi, 5) for lo, hi in zip(lower, upper, strict=True)]
            x, y, z = np.meshgrid(*axes, indexing="ij")
            phi = 2 * x + 3 * y + 4 * z
            volume = np.prod((upper - lower) / 4)
            charge = np.full(phi.shape, -7 * E_CHARGE * volume)
            config = dict(
                radius=0.5,
                field_grid_rz=[256, 512],
                coil_current=0,
                source_revision="analytic-test",
                source_position_m=[0, 0, -0.65],
                iterations=2,
            )
            (case / "config.json").write_text(json.dumps(config))
            (case / "history.json").write_text(
                json.dumps([{"iteration": 0}, {"iteration": 1}])
            )
            for iteration in [1, 2]:
                snapshot = case / "viewer" / f"iteration-{iteration:04d}"
                snapshot.mkdir(parents=True)
                np.savez_compressed(
                    snapshot / "state.npz",
                    lower_m=lower,
                    upper_m=upper,
                    orbit_potential_V=phi,
                    deposited_potential_V=phi,
                    relaxed_potential_V=phi,
                    deposited_charge_C=charge,
                    relaxed_charge_C=charge,
                )
            data = build_field_data(case, max_iteration=1)
            self.assertEqual([row["iteration"] for row in data["snapshots"]], [1])
            self.assertEqual(len(data["history"]), 1)
            result = data["snapshots"][0]
            self.assertAlmostEqual(result["depositedCentreV"], 0)
            self.assertAlmostEqual(result["chargeC"] / (-E_CHARGE * volume), 7 * 125)
            coefficients = {"x": 2, "y": 3, "z": 4}
            for plane in result["fields"]["orbit"].values():
                u, v = np.meshgrid(plane["u"], plane["v"])
                expected = (
                    coefficients[plane["uAxis"]] * u + coefficients[plane["vAxis"]] * v
                )
                expected += coefficients[plane["fixedAxis"]] * plane["fixedM"]
                np.testing.assert_allclose(
                    plane["values"], expected.ravel(), atol=1e-14
                )
            for plane in result["fields"]["electric"].values():
                np.testing.assert_allclose(plane["values"], np.sqrt(29), atol=1e-13)
            for plane in result["fields"]["density"].values():
                np.testing.assert_allclose(plane["values"], 7, atol=1e-13)
            for plane in result["fields"]["magnetic"].values():
                np.testing.assert_array_equal(plane["values"], 0)


if __name__ == "__main__":
    unittest.main()
