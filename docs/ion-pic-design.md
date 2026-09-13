# Coupled electron–ion PIC with gas ionization: design

Scope: the next fidelity step after frozen test ions (`src/ion_orbits.py`). Ions carry charge,
the field is solved from electrons plus ions, and ions are produced by electron-impact
ionization of a uniform background gas. Implemented in `src/ion_pic.py`.

## Why a two-timescale scheme

For the 1 A casing case (`pic_1A_casing_r015`, 300 ns snapshot) the live electron population is
about 4.2e11 electrons with mean kinetic energy 2.8 keV. With a Lotz H2 cross section the
ionization rate scales as 3e14 ions/s at 1e-4 Pa, so the neutralization time
`|Q_e| / (e S)` is about 1.3 ms at 1e-4 Pa and 130 µs at 1e-3 Pa. Electron residence is
about 66 ns and the explicit electron step is 4 ps; an H2+ bounce through a 4 kV well
takes about a microsecond. Explicitly resolving 130 µs of electrons would take ~3e7 steps.

The electron population relaxes in ~1e-7 s, far faster than the ion density changes, so the
coupling is operator-split into cycles:

1. **Electron window** (`--electron-window`, default 40 ns): continue the same external-gun
   electron PIC with the current ion charge as a frozen background. The gun injects at its
   normal rate; secondary electrons from ionization are injected at the current rate. Over the
   second half of the window, average the deposited electron charge and the ionization rate,
   and draw birth positions for new ions weighted by each electron's `n_gas σ(E) |v| w`.
2. **Ion cycle** (`--cycle-duration`, default 10 µs): push ions with an explicit Boris step
   (ion charge-to-mass ratio) in the window-mean electron charge plus the live ion charge,
   re-solved every `--ion-field-every` ion steps with the same conductors and grounded box.
   New ions are created in equal batches across the cycle at the window-mean rate.

The electron window is sub-sampled physical time: electrons are advanced for 40 ns per 10 µs
cycle. This is valid while the ion charge changes by a small fraction per cycle and the
electron population relaxes within the window; the cycle and window lengths are campaign
sensitivity parameters. It is not a resolution of electron–ion instabilities or
of ion-acoustic dynamics faster than the cycle.

## Physics

- Gas: uniform H2 at `--gas-pa` and `--gas-temperature-k`, not depleted.
- Ionization: electron-impact, Lotz form `σ = a q ln(E/P) / (E P)`, `a = 4.5e-18 m² eV²`,
  `q = 2`, `P = 15.43 eV`, scaled by `--ionization-scale`. Within ~10% of measured H2 totals
  at 0.1–1 keV. Primary electrons lose no energy to ionization (~5e-4 events per electron
  lifetime at 1e-3 Pa).
- Ion species: H2+ (`--ion-mass-amu 2.016`), born with `--ion-temperature-ev` Maxwellian
  velocity. Dissociative ionization and H3+ formation are omitted.
- Secondary electrons: injected into the electron PIC at the ionization rate from the same
  birth pool, Maxwellian at `--secondary-temperature-ev`; `--no-secondaries` disables them.
  Their population is only captured when their lifetime is short compared with the window.
- Charge exchange: constant cross section `--cx-cross-section` (default 5e-20 m²) against the
  gas; an exchanged ion is replaced by a thermal gas ion at the same position (charge unchanged,
  kinetic energy removed by the fast neutral and counted). No elastic scattering.
- Boundaries: ions are absorbed at the box faces, the gun barrel and the casings, using the
  same endpoint classification as electrons.

## Numerical checks

- Electron window: the existing electron checks (gyration, 0.2-cell drift, omega_p).
- Ions: at least 80 steps per gyration at the table maximum, 0.2-cell drift bound at every
  field update, and `omega_pi dt <= 0.1` from the peak ion nodal charge.
- Accounting: ion created charge = lost + alive; electron charge balance as before; deposited
  ion charge equals live ion charge.

## Not modelled

Collisions between charged particles, ion–ion or electron–ion instabilities faster than the
cycle, gas depletion and neutral transport, recombination, wall secondary emission, ion
sputtering, magnetic field from plasma currents, and fusion reactions. The two-coil
axisymmetric field remains imposed.

## Campaign

Eight cases on one node, casing geometry `pic_1A_casing_r015` (1 A, 5 keV, 65-node reference
cells, 1.2a box, 0.06a barrel, 0.15a grounded casings):

| case | change |
|---|---|
| `ions_p1e-3` | 1e-3 Pa, 40 × 10 µs cycles |
| `ions_p1e-3_nocx` | charge exchange off |
| `ions_p1e-3_nosec` | secondary electrons off |
| `ions_p1e-2` | 1e-2 Pa, 40 × 1 µs cycles |
| `ions_p1e-3_dt05` | ion step 0.5 ns |
| `ions_p1e-3_cycle5` | 80 × 5 µs cycles |
| `ions_p1e-3_window80` | 80 ns electron windows |
| `ions_p1e-3_ions2x` | twice the ion macroparticles per cycle |

## Campaign record

**Failed attempt.** Job `jonathan-pic-ed7b7f62b292` at source `06a0f7a`, output
`/public/jonathan/cusp/runs/pic-ed7b7f62b292/attempt-20260913-095532-962632006/`. Preflight
controls passed; seven of eight cases stopped in the first ionization sample with the CUDA
assertion `!(val < zero)` inside `torch.multinomial`, before writing any history. The
secondaries-off case was still running when the job was stopped through the broker CLI.
The Lotz cross section was evaluated on energies clamped to the threshold and then multiplied
by a logarithm that rounds to a tiny negative number just below threshold, so some electrons
contributed negative rates. The output is kept unchanged as evidence.

**Fix.** Source `05e2f69` returns exactly zero below threshold with `torch.where` and rejects
negative rates on the host before sampling. Corrected job `jonathan-pic-267721c0347e`, output
`/public/jonathan/cusp/runs/pic-267721c0347e/attempt-20260913-101913-995265517/`; preflight
passed and all eight cases are advancing cycles with charge balances at 1e-22 C.
