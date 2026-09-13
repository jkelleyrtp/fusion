import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from ion_pic import (
    AMU,
    K_B,
    CoupledPIC,
    ionization_cross_section,
    parser,
    run,
    validate_coupled,
)


def arguments(path: Path, *extra: str):
    return parser().parse_args([
        "--out", str(path), "--current-a", "1e-3", "--dt", "1e-11", "--inject-per-step", "4",
        "--nodes", "9", "--coil-current", "3000", "--max-live-particles", "20000",
        "--electron-startup", "2e-10", "--electron-window", "2e-10", "--electron-samples", "4",
        "--gas-pa", "1", "--ion-dt", "1e-9", "--cycle-duration", "1e-7", "--cycles", "2",
        "--ions-per-cycle", "64", "--ion-batches", "8", "--save-every-cycles", "1", "--secondary-every", "4", *extra,
    ])


class IonPICTests(unittest.TestCase):
    def test_lotz_cross_section(self):
        sigma = ionization_cross_section(torch.tensor([10.0, 15.43, 100.0, 1000.0], dtype=torch.float64))
        self.assertEqual(sigma[:2].tolist(), [0.0, 0.0])
        self.assertAlmostEqual(float(sigma[2]), 1.09e-20, delta=0.01e-20)
        self.assertAlmostEqual(float(sigma[3]), 2.43e-21, delta=0.01e-21)

    def test_coupled_cycles_account_for_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root))
            self.assertEqual((root / "DONE").read_text(), "complete\n")
            self.assertEqual(len(history), 2)
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["model"], "coupled-electron-ion-pic-v1")
            final = history[-1]
            self.assertEqual(final["ion_created_count"], 128)
            self.assertAlmostEqual(final["time_s"], 2e-7, delta=1e-15)
            self.assertAlmostEqual(final["electron_time_s"], 6e-10, delta=1e-18)
            created = final["ion_created_charge_C"]
            self.assertGreater(created, 0)
            self.assertLess(abs(final["ion_charge_balance_C"]), 1e-9 * created)
            self.assertLess(abs(final["ion_deposition_error_C"]), 1e-9 * created)
            self.assertGreater(final["neutralization_fraction"], 0)
            self.assertLess(final["secondary_injected_charge_C"], 0)
            self.assertEqual(sum(final["ion_exit_counts"]), final["ion_created_count"] - final["ion_count"])
            with np.load(root / final["snapshot"]) as state:
                self.assertEqual(len(state["ion_count"]), final["ion_count"])
                np.testing.assert_allclose(state["ion_charge_C"].sum(), final["ion_alive_charge_C"], rtol=1e-9)
                self.assertEqual(state["electron_position_m"].shape, state["electron_velocity_m_s"].shape)
                self.assertEqual(len(state["electron_count"]), final["electrons"]["alive_count"])

    def test_inlet_plume_carries_the_throughput(self):
        args = arguments(Path("unused"), "--gas-pa", "0", "--gas-inlet", "0.1", "0", "0",
                         "--gas-inlet-throughput", "2e-3", "--pump-speed", "0.5", "--fuel", "D2")
        simulation = CoupledPIC(args, validate_coupled(args))
        kt = K_B * args.gas_temperature_k
        self.assertAlmostEqual(simulation.gas_density, 4e-3 / kt, delta=1e-9 / kt)
        generator = torch.Generator().manual_seed(1)
        directions = torch.randn((200_000, 3), generator=generator, dtype=torch.float64)
        directions /= directions.norm(dim=1, keepdim=True)
        radius = 0.05
        plume = simulation.neutral_density(torch.tensor([0.1, 0.0, 0.0]) + radius * directions) - simulation.gas_density
        self.assertEqual(float(plume[directions[:, 0] > 0].max()), 0.0)
        mean_speed = math.sqrt(8 * kt / (math.pi * 4.028 * AMU))
        emitted = float(plume.mean()) * mean_speed * 4 * math.pi * radius**2
        self.assertAlmostEqual(emitted * kt / 2e-3, 1.0, delta=0.01)

    def test_deuterium_inlet_run_accounts_for_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--fuel", "D2", "--gas-pa", "0", "--gas-inlet", "0.1", "0", "0",
                                        "--gas-inlet-throughput", "1"))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual((configuration["ion_species"], configuration["ion_mass_amu"]), ("D2+", 4.028))
            self.assertGreater(configuration["gas_density_at_origin_m3"], configuration["gas_density_m3"])
            final = history[-1]
            self.assertGreater(final["ion_created_charge_C"], 0)
            self.assertLess(abs(final["ion_charge_balance_C"]), 1e-9 * final["ion_created_charge_C"])

    def test_ion_gun_beam_energy_direction_and_spread(self):
        args = arguments(Path("unused"), "--fuel", "D2", "--ion-gun-current", "1e-3", "--ion-gun-position", "0", "0",
                         "0.05", "--ion-gun-energy-ev", "200", "--ion-gun-divergence-deg", "3")
        simulation = CoupledPIC(args, validate_coupled(args))
        simulation.inject_gun_ions(20_000, simulation.mesh.lower.new_zeros(tuple(simulation.mesh.shape)))
        ions = simulation.ions
        kinetic = simulation.ion_kinetic_ev()
        self.assertLess(float((kinetic - 200).abs().max()), 1e-9)
        direction = ions.velocity / ions.velocity.norm(dim=1, keepdim=True)
        self.assertLess(float(direction[:, :2].mean(dim=0).norm()), 2e-3)
        self.assertLess(float(direction[:, 2].max()), -0.9)
        self.assertAlmostEqual(float(direction[:, 0].std()), math.sin(math.radians(3)), delta=2e-3)
        self.assertAlmostEqual(simulation.ion_gun_charge, 1e-3 * 1e-7 * 20_000 / 64, delta=1e-20)

    def test_ion_gun_run_accounts_for_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--gas-pa", "1e-6", "--ion-gun-current", "1e-3", "--ion-gun-position",
                                        "0", "0", "0.05", "--cx-cross-section", "0"))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["ion_gun"]["direction"], [0.0, 0.0, -1.0])
            final = history[-1]
            self.assertAlmostEqual(final["ion_gun_injected_charge_C"] / (1e-3 * 2 * 1e-7), 1.0, delta=1e-12)
            self.assertGreaterEqual(final["ion_created_charge_C"], final["ion_gun_injected_charge_C"])
            self.assertLess(abs(final["ion_charge_balance_C"]), 1e-9 * final["ion_created_charge_C"])

    def test_atomic_ion_gun_run_accounts_for_charge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--fuel", "D2", "--gas-pa", "1e-6", "--ion-gun-current", "1e-3",
                                        "--ion-gun-species", "atomic", "--ion-gun-position", "0", "0", "0.05",
                                        "--cx-cross-section", "0"))
            configuration = json.loads((root / "configuration.json").read_text())
            self.assertEqual(configuration["ion_gun"]["species"], "D+")
            final = history[-1]
            self.assertGreater(final["atomic_ion_count"], 0)
            self.assertLess(abs(final["ion_charge_balance_C"]), 1e-9 * final["ion_created_charge_C"])
            with np.load(root / final["snapshot"]) as state:
                self.assertEqual(int(state["ion_species"].sum()), final["atomic_ion_count"])

    def test_atomic_gun_speed_and_gyration(self):
        args = arguments(Path("unused"), "--fuel", "D2", "--ion-gun-current", "1e-3", "--ion-gun-species", "atomic",
                         "--ion-gun-position", "0", "0", "0.05", "--ion-gun-energy-ev", "200")
        simulation = CoupledPIC(args, validate_coupled(args))
        potential = simulation.mesh.lower.new_zeros(tuple(simulation.mesh.shape))
        simulation.inject_gun_ions(2, potential)
        self.assertEqual(simulation.ions.species.tolist(), [1, 1])
        self.assertLess(float((simulation.ion_kinetic_ev() - 200).abs().max()), 1e-9)
        speed = float(simulation.ions.velocity[0].norm())
        self.assertAlmostEqual(speed, math.sqrt(2 * 200 * 1.602176634e-19 / (2.014 * AMU)), delta=1e-6 * speed)
        ions = simulation.ions
        ions.position = torch.tensor([[0.02, 0.01, 0.03]] * 2, dtype=torch.float64)
        ions.velocity = torch.tensor([[1e4, 2e4, -3e4]] * 2, dtype=torch.float64)
        ions.species = torch.tensor([0, 1])
        before = ions.velocity.clone()
        simulation.accelerate(potential, 1e-11)
        change = (simulation.ions.velocity - before).norm(dim=1)
        self.assertGreater(float(change[0]), 0)
        self.assertAlmostEqual(float(change[1] / change[0]), 4.028 / 2.014, delta=1e-6)

    def test_dissociative_ionization_and_exchange_species(self):
        args = arguments(Path("unused"), "--fuel", "D2", "--dissociative-fraction", "0.25",
                         "--dissociation-energy-ev", "4", "--cx-cross-section", "1e-12")
        simulation = CoupledPIC(args, validate_coupled(args))
        potential = simulation.mesh.lower.new_zeros(tuple(simulation.mesh.shape))
        simulation.pool = torch.zeros((1, 3), dtype=torch.float64)
        simulation.create_ions(40_000, 1.0, potential, 0)
        atomic = simulation.ions.species == 1
        self.assertAlmostEqual(float(atomic.double().mean()), 0.25, delta=0.01)
        self.assertLess(float((simulation.ion_kinetic_ev()[atomic] - 4).abs().max()), 1e-9)
        self.assertLess(float(simulation.ion_kinetic_ev()[~atomic].mean()), 0.1)
        simulation.exchange(1e-6)
        self.assertEqual(int(simulation.ions.species.sum()), 0)
        self.assertEqual(int(simulation.ion_exchanges), 40_000)

    def test_charge_exchange_thermalizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--cx-cross-section", "1e-12", "--no-secondaries", "--cycles", "1"))
            final = history[-1]
            self.assertGreaterEqual(final["ion_exchange_events"], final["ion_count"])
            self.assertLess(final["ion_mean_kinetic_eV"], 1)
            self.assertEqual(final["secondary_injected_charge_C"], 0)

    def test_population_limit_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "case"
            with contextlib.redirect_stdout(io.StringIO()):
                history = run(arguments(root, "--max-live-particles", "60"))
            self.assertEqual(history, [])
            self.assertIn("max-live-particles", (root / "DONE").read_text())

    def test_invalid_plans(self):
        root = Path("unused")
        with self.assertRaisesRegex(ValueError, "Invalid cycle"):
            validate_coupled(arguments(root, "--ion-batches", "7"))
        with self.assertRaisesRegex(ValueError, "integer multiple"):
            validate_coupled(arguments(root, "--cycle-duration", "1.5e-9"))
        with self.assertRaisesRegex(ValueError, "positive"):
            validate_coupled(arguments(root, "--gas-pa", "0"))


if __name__ == "__main__":
    unittest.main()
