"""Check WarpX's gas ionisation against n*sigma*v and the ejected-electron energy spectrum.

Usage: check_ionization.py WARPX_3D_EXECUTABLE WORK_DIR

Runs `inputs_3d_ionization_check` (mono-energetic electrons in uniform H2, no fields) at three
energies and prints, for each: ions made against the expected number, electrons gained against ions
made, energy removed per ionisation, and the ejected-electron spectrum against the requested one.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
C_LIGHT, MC2_EV, Q_E, K_B = 299792458.0, 510998.95, 1.602176634e-19, 1.380649e-23
BINDING, SCALE, GAS, GAS_TEMPERATURE = 15.43, 8.3, 1.0e22, 300.0


def main() -> None:
    executable, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    table = np.loadtxt(HERE / "h2_ionization.dat")

    def rate(energy):
        """Ionisations per second per electron as WarpX computes it, with gamma*v where v belongs."""
        gamma = 1 + energy / MC2_EV
        return GAS * np.interp(energy, table[:, 0], table[:, 1]) * C_LIGHT * np.sqrt(gamma**2 - 1)

    for energy in (100.0, 1000.0, 8000.0):
        run = work / f"e{energy:.0f}"
        run.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / "h2_ionization.dat", run)
        subprocess.run(
            [executable, HERE / "inputs_3d_ionization_check", f"my_constants.ek={energy}",
             f"gas.ionization_secondary_energy_scale={SCALE}"],
            cwd=run, check=True, stdout=(run / "run.log").open("w"), stderr=subprocess.STDOUT,
        )
        reduced = run / "diags/reducedfiles"
        number = np.loadtxt(reduced / "number.txt", skiprows=1)
        total_energy = np.loadtxt(reduced / "energy.txt", skiprows=1)[:, 2]
        spectrum = np.loadtxt(reduced / "eall.txt", skiprows=1, ndmin=2)[-1, 2:]
        start, ions, gained = number[0, 3], number[-1, 4], number[-1, 3] - number[0, 3]
        weight = number[0, 6] / start

        # Incident electrons keep nearly all their energy, so they ionise at a steady rate.
        # Ejected electrons above the threshold add a little; a flat estimate of that is enough here.
        span = number[-1, 1]
        top = (energy - BINDING) / 2
        edges = np.arange(spectrum.size + 1) * 5.0
        expected_spectrum = np.diff(np.arctan(np.minimum(edges, top) / SCALE)) / np.arctan(top / SCALE)
        centres = edges[:-1] + 2.5
        second = (start * rate(energy) * span) * (expected_spectrum * rate(centres) * (centres > BINDING)).sum() * span / 2
        expected = start * rate(energy) * span + second

        ejected = spectrum[centres < top]
        measured_spectrum = ejected[:6] / ejected.sum()
        per_event = (total_energy[0] - total_energy[-1]) / (ions * weight * Q_E)
        thermal = 1.5 * K_B * GAS_TEMPERATURE / Q_E
        print(f"{energy:6.0f} eV: ions {ions:.0f}, expected {expected:.0f} (ratio {ions / expected:.3f} +- {ions**-0.5:.3f}); "
              f"electrons gained {gained:.0f}; energy removed per ionisation {per_event:.3f} eV "
              f"(expected {BINDING - thermal:.3f})")
        print("           ejected share per 5 eV bin, measured:", np.round(measured_spectrum, 3))
        print("                                       expected:", np.round(expected_spectrum[:6] / expected_spectrum[centres < top].sum(), 3))
        assert gained == ions
        assert abs(ions / expected - 1) < 4 * ions**-0.5
        assert abs(per_event - (BINDING - thermal)) < 0.01
        assert np.abs(measured_spectrum - expected_spectrum[:6] / expected_spectrum[centres < top].sum()).max() < 0.02


if __name__ == "__main__":
    main()
