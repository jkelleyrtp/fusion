# Coupled electron–ion PIC with gas ionization: design

Scope: the next fidelity step after frozen test ions (`src/ion_orbits.py`). Ions carry charge,
the field is solved from electrons plus ions, and ions are produced by electron-impact
ionization of neutral gas, either a uniform fill or a pumped background plus an inlet plume.
Implemented in `src/ion_pic.py`.

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

- Fuel: `--fuel H2` or `D2` (molecular mass 2.016 or 4.028 amu, ionization energy 15.43 or
  15.47 eV). Isotopes share the Lotz form; `--ion-mass-amu` overrides the ion mass.
- Gas: static and not depleted, at `--gas-temperature-k`. The background is
  `(--gas-pa + Q/S) / kT`: residual pressure plus inlet throughput `Q`
  (`--gas-inlet-throughput`, Pa m³/s) over pump speed `S` (`--pump-speed`, m³/s). An inlet at
  `--gas-inlet` adds a free-molecular cosine-law plume `n = (Q/kT) cos θ / (π v̄ r²)`, with
  `v̄ = sqrt(8kT/πm)`, `θ` from `--gas-inlet-direction` (default: toward the origin) and `r`
  clamped to `--gas-inlet-radius`. The plume flux over any enclosing hemisphere equals the
  throughput. It ignores shadowing by the casings and wall reflection.
  In steady state the pumped background `Q/S` usually exceeds the core plume density: a 1 m³/s
  pump and an inlet 0.7 m from the centre give a background ~2000 times the plume at the
  centre. A plume-dominated gas distribution therefore only represents an early-time puff
  (`t < V/S`, before the vessel fills) or strong differential pumping, which the campaign
  approximates with a large `S`. Ionization and charge exchange use the local density.
- Ionization: electron-impact, Lotz form `σ = a q ln(E/P) / (E P)`, `a = 4.5e-18 m² eV²`,
  `q = 2`, `P = 15.43 eV`, scaled by `--ionization-scale`. Within ~10% of measured H2 totals
  at 0.1–1 keV. Primary electrons lose no energy to ionization (~5e-4 events per electron
  lifetime at 1e-3 Pa).
- Ion species: the fuel molecular ion (H2+ or D2+, species 0) and the atomic ion (H+ or D+,
  species 1). Each ionization produces the atomic ion with probability `--dissociative-fraction`
  (default 0), carrying `--dissociation-energy-ev` (default 5 eV) in an isotropic direction; the
  molecular ion is born with `--ion-temperature-ev` Maxwellian velocity. This is a fixed branching
  ratio: measured H+/H2+ production by 100 eV–1 keV electrons is a few percent, so the campaign uses
  0.05. The companion neutral atom is not tracked. Electron-impact dissociation of trapped D2+,
  D3+ formation and recombination are omitted. The Boris push scales E and B by each ion's
  charge-to-mass ratio relative to the molecular ion, which leaves single-species runs unchanged
  bit for bit.
- Ion gun: `--ion-gun-current` injects `--ion-gun-species` (molecular or atomic) from `--ion-gun-position`
  along `--ion-gun-direction` (default toward the origin), monoenergetic at `--ion-gun-energy-ev`
  with Gaussian spot `--ion-gun-radius` and RMS divergence `--ion-gun-divergence-deg` per
  transverse axis, in the same batches as ionization ions. The energy is the kinetic energy at
  the emission point, whatever the local potential there. No extraction optics are modelled, so
  place the gun where the potential is near the intended source reference.
- Secondary electrons: injected into the electron PIC at the ionization rate from the same
  birth pool, Maxwellian at `--secondary-temperature-ev`; `--no-secondaries` disables them.
  Their population is only captured when their lifetime is short compared with the window.
- Charge exchange: constant cross section `--cx-cross-section` (default 5e-20 m²) against the
  gas for both species; an exchanged ion is replaced by a thermal molecular gas ion at the same
  position (charge unchanged, kinetic energy removed by the fast neutral and counted). D+ on D2
  uses the same cross section as D2+ on D2. No elastic scattering.
- Boundaries: ions are absorbed at the box faces, the gun barrel and the casings, using the
  same endpoint classification as electrons.

## Numerical checks

- Electron window: the existing electron checks (gyration, 0.2-cell drift, omega_p).
- Ions: at least 80 steps per gyration of the lightest enabled species at the table maximum,
  0.2-cell drift bound at every field update, and `omega_pi dt <= 0.1` from the peak ion nodal
  charge at the lightest enabled species.
- Accounting: ion created charge = lost + alive; electron charge balance as before; deposited
  ion charge equals live ion charge.

## Not modelled

Collisions between charged particles, ion–ion or electron–ion instabilities faster than the
cycle, gas depletion, neutral transport beyond the free-molecular plume, recombination, wall secondary emission, ion
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
secondaries-off case, which samples fewer births, wrote partial cycle history before the job ended.
The Lotz cross section was evaluated on energies clamped to the threshold and then multiplied
by a logarithm that rounds to a tiny negative number just below threshold, so some electrons
contributed negative rates. The output is kept unchanged as evidence.

**Fix.** Source `05e2f69` returns exactly zero below threshold with `torch.where` and rejects
negative rates on the host before sampling. Corrected job `jonathan-pic-267721c0347e`, output
`/public/jonathan/cusp/runs/pic-267721c0347e/attempt-20260913-101913-995265517/`; preflight
passed and all eight cases completed (exit code 0, `DONE` in every case).

## Results

`src/analyze_ion_pic.py`, data `docs/data/pic-ions-05e2f69.json`. 400 µs at 1e-3 Pa and 40 µs at
1e-2 Pa. "Neutralization" is live ion charge over window-mean electron charge in the whole box;
"core" is the 0.125 m sphere. Last-quarter means (cycles 31–40, or 61–80 for `cycle5`); origin
potential is the snapshot potential at the centre. Ion charge balance stayed below 1.1e-19 C.

| Case | Neutralization time | Neutralization | Core neutralization | Origin | Min potential | Core ion KE | Ions lost (final) | Electron charge |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `ions_p1e-3` | 147 µs | 1.009 | 0.992 | −38 V | −137 V | 7.8 eV | 64% | −95 nC |
| `ions_p1e-3_nocx` | 147 µs | 1.008 | 0.991 | −41 V | −152 V | 8.7 eV | 64% | −95 nC |
| `ions_p1e-3_nosec` | 147 µs | 1.008 | 0.991 | −39 V | −147 V | 8.0 eV | 64% | −94 nC |
| `ions_p1e-3_dt05` | 147 µs | 1.007 | 0.993 | −31 V | −137 V | 6.7 eV | 64% | −95 nC |
| `ions_p1e-3_cycle5` | 147 µs | 1.010 | 0.993 | −26 V | −116 V | 6.6 eV | 63% | −96 nC |
| `ions_p1e-3_window80` | 147 µs | 1.009 | 0.990 | −39 V | −139 V | 9.1 eV | 64% | −96 nC |
| `ions_p1e-3_ions2x` | 147 µs | 1.007 | 0.993 | −31 V | −137 V | 6.6 eV | 64% | −96 nC |
| `ions_p1e-2` | 14.5 µs | 1.203 | 0.973 | +60 V | −239 V | 23.9 eV | 56% | −98 nC |

Before ions, the same geometry has origin potential −3.97 kV and −66 nC of live electrons.

![Coupled ion evolution](images/pic-ions-evolution.png)
![Coupled ion fields](images/pic-ions-fields.png)

### Interpretation

- **The electron well does not survive the gas.** Ions accumulate in the well until they cancel
  the electron charge. The origin potential rises from −3.6 kV to about −40 V and the core ion
  energy falls from ~450 eV to ~8 eV. Neutralization time is 147 µs at 1e-3 Pa and 14.5 µs at
  1e-2 Pa, inversely proportional to pressure and within 15% of the 130 µs estimate above.
  Extrapolating, 1e-5 Pa gives ~15 ms. A well used for ion acceleration therefore needs pulses
  shorter than the neutralization time, much lower pressure, or an ion loss or electron supply
  that this model lacks.
- **After neutralization the plasma is quasi-neutral and leaks ions.** Neutralization settles at
  1.01 and ion loss rises from a few percent of created ions at neutralization to 64% by 400 µs. About half the losses go to the gun
  barrel along the beam channel, most of the rest to the top and side faces; no ion reached a
  casing. At 1e-2 Pa the ions overshoot to 1.2, the centre becomes +60 V, and more ions leave
  through the box faces.
- **Neutralization pulls in electrons.** Live electron charge rises 43%, from −66 to −95 nC:
  the ion background lets the beam's own space charge hold more electrons.
- **Splitting and ion numerics are converged for these observables.** Halving the ion step or
  the cycle, doubling the electron window or the ion macroparticles changes neutralization,
  core neutralization, electron charge and loss fraction by at most 1%. The residual origin
  potential varies from −26 to −41 V and core ion energy from 6.6 to 9.1 eV; these are small
  differences between large cancelling charges and should be read as uncertain at the ~10 V and
  ~2 eV level. Turning off charge exchange or secondary electrons changes those quantities by under 1% at
  1e-3 Pa.
- **Missing physics limits the steady state, not the neutralization time.** Neutralization time
  is set by ionization rate and electron inventory. The quasi-neutral state depends on processes
  not modelled: Coulomb collisions, recombination, neutral depletion, wall emission and plasma
  magnetic fields. These results are for the two-coil field with a single beam.

## Six-coil results (job `jonathan-pic-1a0b057287d8`, source `b1809b3`)

`run_pic_campaign.py --study six-coil-ions`: the six-coil trap (30 kA-turn, 0 V casings, 5 keV gun)
with the same ion model. Cases: 1 A at 1e-3 Pa with a second seed, 300 mA, 1e-2 Pa (40 × 1 µs
cycles), and the four splitting controls (0.5 ns ion step, 5 µs cycles, 80 ns electron windows,
twice the ion macroparticles). All eight cases exited 0 with `DONE` and every requested cycle.
Raw output: `/public/devcontainer-shared/jonathan/cusp/runs/pic-1a0b057287d8/attempt-20260913-135600-865199098`.
Summary: `docs/data/pic-six-coil-ions-b1809b3.json` (`analyze_ion_pic.py --study six-coil`). Ion
charge balance stayed below 1.7e-19 C. Columns as in the two-coil table; last-quarter means, ions
lost is the final lost / created fraction.

| Case | Neutralization time | Neutralization | Core neutralization | Origin | Min potential | Core ion KE | Ions lost (final) | Electron charge |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `ions6_p1e-3` | 148 µs | 1.020 | 0.982 | −9 V | −161 V | 12.3 eV | 65% | −162 nC |
| `ions6_p1e-3_s2345` | 148 µs | 1.021 | 0.984 | −4 V | −141 V | 11.9 eV | 65% | −161 nC |
| `ions6_p1e-3_300mA` | 148 µs | 1.039 | 0.994 | +5 V | −39 V | 2.0 eV | 61% | −51 nC |
| `ions6_p1e-3_dt05` | 148 µs | 1.020 | 0.986 | −3 V | −139 V | 9.9 eV | 65% | −163 nC |
| `ions6_p1e-3_cycle5` | 148 µs | 1.020 | 0.990 | 0 V | −111 V | 8.7 eV | 63% | −165 nC |
| `ions6_p1e-3_window80` | 148 µs | 1.021 | 0.984 | −5 V | −143 V | 11.7 eV | 64% | −162 nC |
| `ions6_p1e-3_ions2x` | 148 µs | 1.019 | 0.989 | −2 V | −127 V | 8.0 eV | 64% | −165 nC |
| `ions6_p1e-2` | 14.6 µs | 1.295 | 0.985 | +162 V | −85 V | 9.9 eV | 53% | −174 nC |

At the first 10 µs cycle the 1 A origin potential is −2.6 kV with −157 nC of live electrons.

![Six-coil coupled ion evolution](images/pic-six-coil-ions-evolution.png)
![Six-coil coupled ion fields](images/pic-six-coil-ions-fields.png)

### Six-coil interpretation

- **The six-coil well is neutralized on the same clock as the two-coil well.** 148 µs at 1e-3 Pa
  and 14.6 µs at 1e-2 Pa, against 147 µs and 14.5 µs in the two-coil field. The centre rises from
  −2.6 kV to within ~10 V of ground and the core ion energy falls from ~780 eV to ~10 eV.
- **Beam current does not change the neutralization time.** 300 mA neutralizes in exactly the same
  148 µs as 1 A with a third of the electron charge: each electron ionizes at the same rate, so
  pressure sets the time and current only sets how deep the well was.
- **Most lost ions leave through the box faces, not the beam channel.** At 1e-3 Pa 86% of ion losses
  reach the grounded walls, 14% the gun barrel and 55 of ~208,000 a casing. The −z face below
  the gun takes about half as many as each other face.
- **At 1e-2 Pa the ions overshoot** to 1.3 of the electron charge and the centre sits at +162 V.
- **Splitting controls agree.** Neutralization, core neutralization, electron charge and loss
  fraction change by at most 3%; origin potential (−10 to 0 V) and core ion energy (8–12 eV) are
  small differences of large cancelling charges and uncertain at that level.
- The same missing physics as the two-coil study limits the post-neutralization state.

## High-feed results (job `jonathan-pic-98784dc572d0`, source `0efa509`)

`run_pic_campaign.py --study six-coil-feed-fine`: the six-coil trap with H2 and H2+, 10 keV gun at
10–100 A, 10/30/60 kA-turn. Two groups: 1e-2 Pa for 32 × 1 µs cycles with a 0.2 ns ion step (the
1 ns cases of `six-coil-feed` failed the `omega_pi * dt` check), and 1e-3 Pa for 32 × 10 µs cycles
(320 µs, 0.5–1 ns ion step). All eight cases have `DONE` and every cycle; ion charge balance
stayed below 3e-19 C.
Raw output: `/public/jonathan/cusp/runs/pic-98784dc572d0/attempt-20260913-194000-421552263`.
Summary: `docs/data/pic-six-coil-feed-fine-0efa509.json` (`analyze_ion_pic.py --study
six-coil-feed-fine`). Last-quarter means; "gun" is the share of lost ions absorbed by the
gun barrel.

| Case | Gas | Neutralization | Origin | Gun-mouth minimum | Electron charge | Core ion KE | Ions lost | Gun |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `feed_10A_10keV_p1e-3` | 1e-3 Pa | 0.760 ± 0.005 | −2722 V | −6.2 kV | −954 nC | 765 eV | 42% | 3% |
| `feed_30A_10keV_p1e-3` | 1e-3 Pa | 0.707 ± 0.033 | −5718 V | −11.3 kV | −2080 nC | 1137 eV | 13% | 20% |
| `feed_100A_10keV_p1e-3` | 1e-3 Pa | 0.111 | −98 V | −23.2 kV | −151 nC | 100 eV | 92% | 99.8% |
| `feed_10A_10keV_idt2` | 1e-2 Pa | 1.057 | −251 V | −1.5 kV | −963 nC | 202 eV | 19% | 6% |
| `feed_30A_10keV_idt2` | 1e-2 Pa | 0.777 | −3903 V | −8.6 kV | −2240 nC | 742 eV | 2% | 30% |
| `feed_100A_10keV_idt2` | 1e-2 Pa | 0.424 | −6283 V | −15.4 kV | −1090 nC | 1458 eV | 27% | 99.8% |
| `feed_100A_10keV_10kAt_idt2` | 1e-2 Pa | 0.496 | −5434 V | −14.4 kV | −1650 nC | 1211 eV | 20% | 98% |
| `feed_30A_10keV_60kAt_idt2` | 1e-2 Pa | 0.889 ± 0.059 | −2178 V | −9.3 kV | −2005 nC | 571 eV | 5% | 15% |

For comparison, 1 A and 300 mA at 5 keV and 1e-3 Pa neutralize to 1.02–1.04 with the centre within
10 V of ground (`six-coil-ions` above).

![Six-coil high-feed evolution](images/pic-six-coil-feed-fine-evolution.png)
![Six-coil high-feed fields](images/pic-six-coil-feed-fine-fields.png)

### High-feed interpretation

- **At 10–30 A the well survives 1e-3 Pa for 320 µs.** Ions do not cancel the electron charge. At
  10 A neutralization levels off at 0.76 from ~200 µs and the centre holds −2.7 kV with ~0.8 keV core
  ions; ion losses balance production before the well is gone. At 30 A the centre holds −5.7 kV
  but neutralization is still rising (0.76 at 320 µs), so that case is not yet settled. At 1 A the
  same pressure removed the well. This corrects the earlier estimate that current cannot keep a
  well alive: the neutralization *time* is still ~180 µs for every current, but the endpoint
  depends on current. The live electron charge also grows as ions arrive (−0.33 to −0.95 µC at
  10 A), so ions let the trap hold more electrons.
- **100 A chokes at the gun.** The beam's own charge makes a −15 to −23 kV virtual cathode at the gun
  mouth. At 1e-3 Pa the beam never reaches the centre (−98 V, −151 nC, no core ions) and 99.8% of lost
  ions fall back into the gun barrel. At 1e-2 Pa ions born near the mouth partly neutralize the choke
  within ~15 µs and a −6.3 kV spherical well forms, but ions still stream into the gun. More current
  needs a lower-perveance gun (larger emitter or several guns), not a single brighter one.
- **The 1e-2 Pa runs are transient.** Neutralization is still rising at 32 µs in every case and
  10 A has already overshot to 1.06; treat them as the fast-pressure limit, not an equilibrium.
- **Coil current is a weak knob here.** 100 A at 10 kA-turn is within ~15% of 30 kA-turn. At 30 A,
  60 kA-turn neutralizes further (0.89 vs 0.78) and leaves the centre shallower (−2.2 vs −3.9 kV);
  both differences are about one last-quarter spread (±0.06, ±0.8–0.9 kV) in a transient run, so
  stronger coils do not preserve the well against 1e-2 Pa.
- Limits: two-timescale splitting, no gas depletion (the 100 A ion inventory is below 1e-5 of the
  gas), no plasma magnetic field, one seed, and no cycle-duration control at 10–30 A yet. The
  plateau needs those controls and a longer run before it is a design number.

## D2 fuel-delivery results (job `jonathan-pic-f74373c4cc21`, source `09f2191`)

`run_pic_campaign.py --study six-coil-gas`: the six-coil trap (30 kA-turn, 0 V casings, 1 A 5 keV
gun) with D2 and D2+ ions, 40 × 10 µs cycles (400 µs). Inlets aim at the centre from a face axis
(0.7, 0, 0), a corner (0.68, 0.68, 0.68) and beside the gun (0.1, 0, −0.95). "Puff" cases use a
1000 m³/s pump, far larger than a real pump, to approximate an early-time puff or strong
differential pumping in this static-gas model. All eight cases exited 0 with `DONE` and every
requested cycle; ion charge balance stayed below 1e-19 C.
Raw output: `/public/devcontainer-shared/jonathan/cusp/runs/pic-f74373c4cc21/attempt-20260913-170701-271575149`.
Summary: `docs/data/pic-six-coil-gas-09f2191.json` (`analyze_ion_pic.py --study six-coil-gas`).
Neutralization time is live electron charge over the ion production rate at the last cycle; the
other columns are last-quarter means.

| Case | Background | Gas at centre | Neutralization time | Neutralization (400 µs) | Origin | Core ion KE | Ions lost |
|---|---:|---:|---:|---:|---:|---:|---:|
| `d2_uniform_p1e-3` | 1e-3 Pa | 2.41e17 m⁻³ | 148 µs | 1.034 | +3 V | 9 eV | 59% |
| `d2_inlet_face_Q1e-3_S1` | 1e-3 Pa | 2.42e17 m⁻³ | 148 µs | 1.034 | +5 V | 8 eV | 59% |
| `d2_uniform_p1e-4` | 1e-4 Pa | 2.41e16 m⁻³ | 1.36 ms | 0.271 | −1.93 kV | 323 eV | 2% |
| `d2_inlet_face_Q1e-4_S1` | 1e-4 Pa | 2.42e16 m⁻³ | 1.36 ms | 0.271 | −1.93 kV | 323 eV | 2% |
| `d2_puff_face_Q1e-1_S1e3` | 1e-4 Pa | 3.66e16 m⁻³ | 845 µs | 0.422 | −1.35 kV | 247 eV | 6% |
| `d2_puff_gun_Q1e-1_S1e3` | 1e-4 Pa | 3.08e16 m⁻³ | 1.02 ms | 0.367 | −1.51 kV | 229 eV | 4% |
| `d2_puff_corner_Q1e-1_S1e3` | 1e-4 Pa | 2.86e16 m⁻³ | 1.15 ms | 0.322 | −1.71 kV | 290 eV | 3% |
| `d2_puff_face_Q1e-2_S1e3` | 1e-5 Pa | 3.66e15 m⁻³ | 7.9 ms | 0.043 | −3.03 kV | 770 eV | 0.1% |

![Six-coil D2 delivery evolution](images/pic-six-coil-gas-evolution.png)
![Six-coil D2 delivery fields](images/pic-six-coil-gas-fields.png)

### D2 delivery interpretation

- **A steady inlet into a normally pumped vessel is uniform fill.** With a 1 m³/s pump the inlet
  cases match uniform gas at the same background within 0.1% in every quantity, at both 1e-3 and
  1e-4 Pa. D2 neutralizes on the same 148 µs clock as H2 at 1e-3 Pa.
- **Background pressure sets the clock, linearly.** 148 µs at 1e-3 Pa, 1.36 ms at 1e-4 Pa and
  ~7.9 ms at 1e-5 Pa. At 1e-5 Pa the well stays at −3.0 kV for the whole 400 µs and core ions
  carry ~770 eV.
- **A puff adds ionization where the electrons are; it does not move birth to the walls.** At the
  same 1e-4 Pa background the face-axis puff raises the centre density by 52% and the ionization
  rate by 61%, the gun-side puff by 28% and 34%, the corner puff by 19% and 19%. The face inlet sits
  on a point-cusp axis, where most electrons leave, so its plume overlaps the electron flow. Alive
  ions are still born mostly 0.5–2.5 kV down in the well. The plume does make some wall-side ions:
  lost ions leave mainly along the inlet axis (both x faces take 4.5 times each y face for the face
  puff, the z faces most for the gun-side puff), but they are 3–6% of created ions.
- **Localized puffing is therefore a small knob in this model; pressure is the large one.** A
  puff that delivers fuel without adding core ionization would need the gas to be ionized away
  from the beam, which this static plume cannot represent: no neutral depletion, shadowing by the
  casings, wall reflection or time-dependent filling.

## D2+ ion-gun results (job `jonathan-pic-489401f39d77`, source `2ebefc8`)

`run_pic_campaign.py --study six-coil-ion-gun`: the same six-coil trap and 1 A 5 keV electron gun,
D2 at 1e-5 Pa (a slow 12.8 ms neutralization clock), plus a D2+ ion gun at the top point cusp
(0, 0, 0.7) m aimed at the centre, 5 mm RMS spot, 5° RMS divergence; one case uses the corner
(0.68, 0.68, 0.68) m. 40 × 10 µs cycles. All eight cases exited 0 with `DONE` and every requested
cycle. The analyzer's charge-balance gate is now 1e-9 of created charge: gun cases accumulate
~4e5 injected packets and reach 3.5e-12 relative FP64 accumulation roundoff, against 1e-12 before.
Raw output: `/public/devcontainer-shared/jonathan/cusp/runs/pic-489401f39d77/attempt-20260913-172701-598627424`.
Summary: `docs/data/pic-six-coil-ion-gun-2ebefc8.json`. Columns are last-quarter means except
retained, which is (final alive ion charge − the no-gun case) / injected gun charge; mouth is the
highest potential in the domain at 400 µs.

| Case | Mouth potential | Gun ions leaving +z (back out) | leaving −z (transit) | Retained | Core neutralization | Origin | Core ion KE |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gun_none` | 0 V | — | — | — | 0.103 | −3.06 kV | 694 eV |
| `gun_1mA_100eV` | +68 V | 3% | 80% | 3.1% | 0.143 | −3.07 kV | 1288 eV |
| `gun_10mA_10eV` | +690 V | 98% | 1% | 0.5% | 0.104 | −3.04 kV | 737 eV |
| `gun_10mA_100eV` | +803 V | 99% | 1% | 0.3% | 0.103 | −3.04 kV | 726 eV |
| `gun_100mA_100eV` | +1.62 kV | 96% | 0% | 0.09% | 0.101 | −3.04 kV | 697 eV |
| `gun_10mA_1keV` | +790 V | 1% | 49% | 1.2% | 0.142 | −2.85 kV | 1284 eV |
| `gun_corner_10mA_100eV` | +984 V | 11% | 0% (87% sides) | 0.2% | 0.103 | −3.06 kV | 692 eV |
| `gun_10mA_100eV_bias5kV` | — | 75% | 0% | 0.03% | 0.078 | +154 V | 298 eV |

Exit fractions count all lost ions, so the `gun_none` row is gas ions only. The no-gun case loses
0.13% of created ions, mostly to the conductors.

![Six-coil D2+ ion gun evolution](images/pic-six-coil-ion-gun-evolution.png)
![Six-coil D2+ ion gun fields](images/pic-six-coil-ion-gun-fields.png)

### Ion-gun interpretation

- **At 10 mA and above a low-energy ion gun chokes on its own charge.** The beam's space charge
  builds a +0.7 to +1.6 kV potential hill at the mouth, above the 10–100 eV beam energy, and
  96–99% of gun ions turn around and leave through the top face. This is the ion analogue of the
  electron gun choke at 3 A. The mesh (9.4 × 9.4 × 20 mm cells) smears the 5 mm spot, so the real
  hill for this spot would be higher; a real gun needs extraction optics, a wider aperture or
  beam neutralization, none of which is modelled.
- **Unchoked gun ions transit and leave.** At 1 mA, 100 eV (hill +68 V) and 10 mA, 1 keV (hill
  +790 V) the ions pass the mouth, fall through the −3 kV well, gain ~1.3 keV in the core and 49–80%
  leave through the opposite face. This is energy conservation: an ion injected from a grounded
  wall with positive energy cannot be trapped by a static potential. Only charge exchange and the
  slowly changing well retain them, 1–3% of injected charge over 400 µs.
- **The gun barely touches the core well.** Core neutralization stays 0.10–0.14 in every case, the
  same as gas ionization alone; the larger volume-averaged neutralization (up to 0.31) is the
  choked or transiting beam near the axis. The 1 keV beam makes the centre 7% shallower.
- **Casing bias does not help injection.** At +5 kV the centre sits at +154 V, the gun ions see no
  well, and retention falls to 0.03%.
- **Consequence for fuelling.** A cusp ion gun adds energetic core transits but does not fill the
  well. Trapping injected ions needs a time-varying well (for example lowering the barrier during
  injection, then deepening it) or dissipation; the pulsed electron-gun campaign tests the first
  of these in a limited way.

## Atomic D+ ion-gun results (job `jonathan-pic-306fed43182f`, source `cf4fb70`)

Same setup as the D2+ gun study: 1 A / 5 keV electron gun, D2 at 1e-5 Pa, 400 µs, 1 ns ion step,
gun at the top point cusp (`0, 0, 0.7` m, aimed at the centre). Gas ionization makes D2+, with 5%
dissociative ionization to D+ (`diss5`). Seven of eight cases are complete. `dplus_100mA_100eV`
failed the `omega_pi * dt <= 0.1` ion-step check before writing a history and is rerun at 0.2 ns in
`jonathan-pic-a551941178c2`. Exit fractions count gun macroparticles. After the last case finished
the campaign exited non-zero because of the failed case and the broker restarted the whole sweep;
that second attempt was stopped and only the first attempt (`attempt-20260913-174029-877869917`)
is analysed.

| case | mouth hill | top face | opposite face | conductors | D+ alive / injected | core ion KE | origin |
|---|---|---|---|---|---|---|---|
| no gun (5% dissociative) | 0 V | 4% | 4% | 59% | — | 693 eV | −3057 V |
| D2+ 10 mA, 100 eV | +798 V | 98.7% | 0.6% | 0.4% | — | 728 eV | −3043 V |
| D+ 10 mA, 100 eV | +425 V | 96.9% | 1.3% | 0.7% | 0.29% | 796 eV | −3043 V |
| D+ 10 mA, 100 eV, seed 2345 | +432 V | 96.9% | 1.3% | 0.7% | 0.29% | 799 eV | −3045 V |
| D+ 10 mA, 100 eV, 60 kA-turn | +441 V | 95.7% | 2.8% | 0.3% | 0.29% | 669 eV | −3623 V |
| D+ 10 mA, 1 keV | +367 V | 1.0% | 62% | 23% | 0.87% | 1515 eV | −2902 V |
| D+ 10 mA, 100 eV, +5 kV casings | casings at +5 kV | 75% | 0.4% | 4% | 0.08% | 297 eV | +157 V |

The mouth hill is the last-quarter mean of the maximum potential; with +5 kV casings the maximum is
the casings themselves. Core ion KE is the core-time-weighted mean over all ions, gas-born included.

### D+ interpretation

- **D+ halves the mouth hill but a 100 eV gun still chokes.** At fixed current a lighter ion moves
  √2 faster, so beam density and the hill fall: +425 V for D+ against +798 V for D2+. That is still
  above 100 eV, and 97% of gun ions leave through the top face. The seed repeat agrees within 1%.
- **A 1 keV D+ beam transits.** It clears the hill, crosses the well and leaves mostly through the
  opposite face (62%) and the casings (23%). Retention is 0.87% of injected charge, against
  1–3% for the D2+ transit cases, and the centre is 5% shallower than with no gun.
- **Casing bias removes the well**, as with D2+: the centre sits at +157 V and retention is 0.08%.
- **Stronger coils deepen the well but do not open the gun.** At 60 kA-turn the centre is 19%
  deeper (−3623 V), the mouth hill is unchanged (+441 V) and retention stays 0.29%. Core ions are
  slower (669 eV) because more gas ions are born deep in the stronger electron channel.
- **Same conclusion as D2+.** Changing the ion species does not trap gun ions in a static well;
  the phase-gated capture campaign below tests injecting while the well is down.

![Six-coil D+ ion gun evolution](images/pic-six-coil-deuteron-evolution.png)
![Six-coil D+ ion gun fields](images/pic-six-coil-deuteron-fields.png)

## Phase-gated D+ capture campaign (job `jonathan-pic-7acf9e969fe4`, source `65d4592`)

This tests the time-varying well idea above. `--ion-gun-phase electron-off` injects gun ions only
in cycles where the pulsed electron gun is off, so ions enter while the well is decaying, and the
well rebuilds around them when the gun switches back on. `electron-on` and `always` are the
controls. Gun state switches at cycle boundaries; each switch-on is followed by `--gun-settle`
of electron-only advance against frozen ions before the next electron window.

Setup: six coils at 30 kA-turn, D2 at 1e-5 Pa, 1 A / 5 keV electron gun pulsed 10 µs on and 2 µs
off (12-cycle period, 1 µs cycles, 48 cycles), and an atomic D+ gun at 10 mA from the top cusp
(`0, 0, 0.7` m, aimed at the centre, 5 mm spot, 5° divergence).

| case | electron gun | ion gun | purpose |
|---|---|---|---|
| `capture_off_1keV` | 10 on / 2 off | off-phase, 1 keV | main case |
| `capture_on_1keV` | 10 on / 2 off | on-phase | control: same pulse, ions into a live well |
| `capture_always_1keV` | 10 on / 2 off | always | control: pulse without gating |
| `capture_continuous_1keV` | continuous | always | control: no time-varying well |
| `capture_off_300eV` | 10 on / 2 off | off-phase, 300 eV | lower injection energy |
| `capture_off_1keV_on4_off2` | 4 on / 2 off | off-phase | shorter period |
| `capture_off_1keV_s2345` | 10 on / 2 off | off-phase | seed |
| `capture_off_1keV_idt2` | 10 on / 2 off | off-phase, 0.2 ns ion step | timestep |

New per-cycle records: `electron_gun_on`, `ion_gun_on`, and `ion_bound_charge_C` /
`atomic_ion_bound_charge_C`, the charge of ions whose kinetic energy plus the potential at their
position is below zero on the end-of-cycle potential. That is a diagnostic of being energetically
below the grounded walls on a frozen field, not a confinement measurement: the potential keeps
changing with the pulse, and ions can still leave through lower paths between casings. The
capture figure plots alive and bound D+ per unit injected gun charge.

Limits: cycle-boundary switching only, frozen-ion electron windows, no induced fields, no gas
depletion, and no plasma magnetic field.
