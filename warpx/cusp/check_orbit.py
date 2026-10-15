"""Compare the test electron of inputs_3d_orbit_check with an independent integration in the same coil field.

Usage: check_orbit.py RUN_DIR [RUN_DIR ...]

The reference uses SciPy's elliptic integrals and an adaptive Runge-Kutta integrator, so it shares neither
the field expression nor the particle push with WarpX. Prints the position error at 50, 100 and 150 ps.
"""
import sys

import numpy as np
from scipy.integrate import solve_ivp

from vacuum_dwell import C, Q_OVER_M, field

START = np.array([0.002, 0.001, 0.0005])
U0 = np.array([0.12, -0.1, 0.123])
GAMMA = np.sqrt(1 + U0 @ U0)
COIL_AT = 16000.0


def rhs(_, state):
    velocity = state[3:] * C / GAMMA
    return np.concatenate([velocity, Q_OVER_M * np.cross(velocity, field(state[None, :3], COIL_AT)[0]) / C])


if __name__ == "__main__":
    reference = solve_ivp(rhs, (0, 2e-10), np.concatenate([START, U0]), rtol=1e-11, atol=1e-14, dense_output=True)
    for run in sys.argv[1:]:
        data = np.loadtxt(f"{run}/diags/reducedfiles/ext.txt", skiprows=1)
        alive = data[:, 16] < 1e300
        time, position = data[alive, 1], data[alive][:, [2, 4, 6]]
        error = np.linalg.norm(position - reference.sol(time)[:3].T, axis=1)
        marks = [f"{error[np.searchsorted(time, t) - 1]:.2e}" for t in (5e-11, 1e-10, 1.5e-10)]
        print(f"{run}: position error (m) at 50, 100, 150 ps = {marks}; "
              f"gamma drift = {np.ptp(data[alive, 14]):.1e}")
