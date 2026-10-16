import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ion_orbits import load_run, parser, simulate


def write_run(root: Path) -> None:
    """Two snapshots of a quadratic bowl, -1 kV at the origin and 0 V at the transverse face centres."""
    (root / "snapshots").mkdir(parents=True)
    (root / "configuration.json").write_text(json.dumps({
        "nodes": 17, "radius": 0.5, "coil_current": 0.0, "gun_radius": 0, "casing_radius": 0,
    }))
    lower, upper = np.array([-0.3, -0.3, -0.65]), np.array([0.3, 0.3, 0.65])
    axes = [np.linspace(lower[axis], upper[axis], 17) for axis in range(3)]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    potential = -1000 + 1000 * (x ** 2 + y ** 2 + z ** 2) / 0.09
    charge = np.exp(-(x ** 2 + y ** 2 + z ** 2) / 0.01)
    for step, time in ((1, 1e-7), (2, 2e-7), (3, 3e-7)):
        np.savez(
            root / "snapshots" / f"step-{step:08d}.npz", time_s=time, potential_V=potential * time / 2e-7,
            charge_C=-charge, lower_m=lower, upper_m=upper,
        )


class IonOrbitTests(unittest.TestCase):
    def test_window_mean_and_confinement(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "case"
            write_run(run)
            _, mesh, potential, charge, times = load_run(run, 1.5e-7)
            self.assertEqual(times, [2e-7, 3e-7])
            self.assertEqual(mesh.shape, (17, 17, 17))
            self.assertAlmostEqual(float(potential[8, 8, 8]), -1250, delta=1e-9)
            self.assertAlmostEqual(float(charge[8, 8, 8]), 1, delta=1e-12)
            out = Path(directory) / "ions"
            options = parser().parse_args([
                "--run", str(run), "--out", str(out), "--birth", "uniform", "--ions", "128",
                "--dt", "1e-9", "--duration", "5e-6", "--window-start", "1.5e-7",
            ])
            with contextlib.redirect_stdout(io.StringIO()):
                summary = simulate(options)
            ions = np.load(out / "ions.npz")
            confined = ions["total_energy_eV"] < 0
            self.assertTrue(confined.any() and (~confined).any())
            self.assertTrue((ions["exit_index"][confined] == -1).all())
            self.assertAlmostEqual(
                sum(summary["exit_fractions"].values()), summary["lost_fraction"], delta=1e-12,
            )
            self.assertGreater(summary["entered_core_fraction"], 0)
            self.assertLess(summary["surviving_max_energy_drift_eV"], 25)
            self.assertTrue((out / "ions.png").exists())

    def test_timestep_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "case"
            write_run(run)
            options = parser().parse_args([
                "--run", str(run), "--out", str(Path(directory) / "ions"), "--dt", "1e-7",
            ])
            with self.assertRaisesRegex(ValueError, "drift bound"):
                simulate(options)


if __name__ == "__main__":
    unittest.main()
