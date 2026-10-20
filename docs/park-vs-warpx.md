# How Park et al. 2019's simulation differs from ours

Written 17 October 2026. Compares Park, Lapenta, Gonzalez-Herrero & Krall (arXiv:1901.08041) with our WarpX
picket-fence runs (`warpx/cusp/inputs_rz_picket_fed`, campaign `pw1`, cases `pfw_…` and `pk_…`). The item-by-item
arithmetic is in [park-comparison-audit.md](park-comparison-audit.md); the run tables are in
[picket-park.md](picket-park.md). No new runs were made for this document. The interval table in section 4 is a
new reduction of finished runs.

Every statement carries its source:

- **[P]** read in Park's paper (full text, 29 pages with the supplement; figures 1, 6, S1, S2, S3 viewed).
- **[E]** read in the two papers that describe Park's code: Lapenta 2017 (arXiv:1602.06326) and Gonzalez-Herrero
  et al. 2018 (arXiv:1810.08433). I searched both for the topics below and read those sections, not every page.
- **[W]** our deck or reducer. **[R]** a finished run of ours. **[A]** my arithmetic. **[I]** my inference.

## 1. Summary

- Both simulations are of the same device: a row of alternating ring coils that repeats along the axis, in 2D
  with symmetry around the axis, ions 64 times the electron mass, filled over 10 electron crossings and then
  topped up. Our geometry and fill were converted from the paper's units and agree with it to 2% [A]. The
  paper does not state its coil current; the field in our boundary layer is 7.4 T against 8.1 T converted from
  the paper [R, A].
- **The boundary layer roughly agrees.** Park: 2.1 electron orbits thick (0.6 ion inertial lengths) [P]. Ours:
  2.3 to 2.7 orbits (0.75 ion inertial lengths in the baseline), counting the orbit at the fed temperature as
  Park does [R, A]. Our electrons have cooled by then, so counted with the momentum they actually have, ours is
  3.2 to 4.4 orbits [R]. Park's are held at their fed energy, so the two counts are the same there [P, I].
- **The holding time does not.** Park: 135 electron crossings as stated, 174 from the paper's own injection
  figures [P, A]. Ours, measured over the same part of the run as Park's (crossings 10 to 28): 56 to 62 at
  100 keV at Park's fill or below, and 61 at Park's temperature [R]. That is a factor of 2.2 to 3.
- **Park's result is not assumed correct.** It is one simulation with a different method, with no repeat seeds
  reported, and its own numbers disagree with each other by 29%. Ours is not assumed correct either: it has
  known faults at other sizes and run lengths.
- **What we changed on our side without closing the gap** [R]: the outer boundary for waves, the deposition
  method at that boundary, 8 times the particles, holding the number of particles constant as Park does, and
  Park's own temperature. In Park's window none of them moves our number by more than 15%.
- **What is left** is listed in section 5. The largest untested items are the method itself (Park's code
  conserves energy exactly, ours conserves charge exactly), that Park re-heats the plasma and we let it cool,
  and the shape of the particle source. I cannot rank them by size without runs.

## 2. The two codes

Both follow electrons and ions as sample particles through fields on a mesh. They differ in how a time step is
taken, and so in what each one conserves exactly.

| | Park: ECsim-CYL | Ours: WarpX 26.10 |
|---|---|---|
| Time step | Semi-implicit: the fields for the next step are solved together with the plasma's response to them [P, E] | Explicit: fields and particles are advanced from the previous step [W] |
| Total energy | Conserved to machine precision at any mesh and time step [P, E] | Not conserved exactly. Plasma on a mesh coarser than the screening length heats or cools numerically |
| Charge (Gauss's law) | Not exact. The mesh operators do not make it hold; the code paper reports the error as small in one test (about 1e-6 in its normalised measure) [E]. Lapenta 2017 lists exact charge and momentum conservation as work still to do [E] | Exact, from the deposition method, once the fault at the conducting wall is removed ([wall-charge.md](wall-charge.md)) [W, R] |
| Fields on the mesh | Finite-volume: electric field at mesh nodes, magnetic field at cell centres [E] | Staggered (Yee) mesh [W] |
| Particle shape | First-order spline [E] | Second-order spline [W] |
| Smoothing | None [P] | None [W] |
| Field components kept | All three, including the field around the axis [E, I] | All three [W] |
| Known weakness on the axis | Noisy in the first radial cells, because those cells are small and hold few particles [E] | Same kind of noise in our runs (section 6) [R] |

- The paper's argument for its code is that smoothing, which breaks energy conservation, thickens the boundary
  layer artificially [P]. We use no smoothing, and our layer is 25% thicker than Park's in absolute terms [R, A].
  I cannot tell from that whether our method thickens it.
- An explicit code needs a short step and a fine mesh. Park's step is 0.125/ωpi for Run 1 in the text and
  Table ST1, and 0.25 in Table ST2 [P]. Ours is 0.070/ωpi [A]. Light crosses 1.5 cells per step in Park's Run 1
  and 0.6 in ours [A]. Park's code does not follow light waves or the fastest plasma oscillation accurately
  and is built not to need to [P].
- Park's cell is 3.1 screening lengths, taken at the fed temperature and the density at the boundary (Table
  ST1: cell 0.083, screening length 0.027) [P, A]. Counted the same way, ours is 0.8 at 100 keV and 4.4 at
  2.76 keV [A]. Inside our plasma, at its measured density and temperature, it is 1.4 and 10 [R].
- The paper says its code stays correct on a mesh that does not resolve the screening length, and that
  resolving it would cost 100 times more [P]. An explicit code has no such guarantee: there it is a known
  source of numerical heating or cooling. That is why our baseline is 36 times hotter than Park's, and why our
  run at Park's temperature is the least trustworthy row in section 4.

## 3. The setup, side by side

Lengths are in Park's unit (the ion inertial length); our coil radius of 1 cm is 30 of them [A].

| Item | Park (Run 1) | Ours (`pfw_x1.0`) | Same? |
|---|---|---|---|
| Geometry | 2D, symmetric around the axis, repeating along it; 45 in radius, 30 long [P] | The same [W] | Yes |
| Coils | Radius 30, spacing 15, alternating; 27 coils supply the field [P] | Radius 30, spacing 15, alternating; 25 coils with half weight on the end pair [W] | Yes, to the accuracy that matters |
| Coil current | Not stated [P] | Read from the paper's figures; our field in the layer is 7.4 T against 8.1 T converted from the paper [R, A] | Within 9% |
| Ion mass | 64 electron masses [P] | 64 [W] | Yes |
| Temperature | 2.77 keV, electrons and ions [P] | 100 keV; a 2.76 keV case exists [W] | **No** |
| Mesh | 540 × 360, cell 0.30 electron orbits [P] | 384 × 256, cell 0.42 orbits [W] | Close |
| Particles per cell | 885 averaged over the mesh, 1000 to 1600 at the boundary [P, A] | 210 to 320 in the plasma; one case with 8 times as many [R] | **No** |
| Where particles are removed | A wall at radius 42 that absorbs particles and waves [P] | A conducting wall at radius 45: absorbs particles, reflects waves [W] | **No** |
| Charge of a particle absorbed at the wall | Not described in the paper or in either code paper [P, E] | Removed with it [W, R] | **Unknown** |
| Source | Fills the volume inside radius 9 over the whole length [P] | A disc of radius 9 in the plane of the middle coil, firing along the axis both ways [W] | **No** |
| Fill | 160 equal pulses over 9.8 electron crossings [P, A] | Continuous over 10.0 crossings [W] | Yes |
| Topping up: particles | Rate adjusted through the run to hold the charge constant; about 1/18 of the fill rate [P] | Fixed at 1/18 of the fill rate; one case fixed at a rate that holds the number constant [W] | **No** in the baseline |
| Topping up: energy | Adjusted to hold the total kinetic energy at its value at the end of the fill; injected particles carry 2.5 to 3 times the energy of those in the fill [P] | Injected at the fed temperature; the plasma cools [W, R] | **No** |
| Run length | 28 electron crossings in all, 18 after the fill [P, A] | 50 crossings; 400 in the size scan [W] | **No** |
| Repeats with other random numbers | None reported [P] | Several at other sizes; over 400 crossings they differ by up to a third [R] | |

## 4. How the holding time is measured, and what ours is in Park's window

- **Park:** charge held ÷ rate of injection, while the injection is adjusted to keep the charge constant [P].
  With the charge constant this equals charge held ÷ rate of loss [A].
- **Ours:** number held ÷ rate of loss, averaged over the last fifth of the run [W]. The table below instead
  uses the feed less the change in the number held as the rate of loss, over any interval
  (`warpx/cusp/holding_by_interval.py`). Over crossings 40 to 50 the two methods agree to 2% with the conducting
  wall and to 5% with the wave-absorbing boundary [R].
- The two definitions are the same quantity. The difference that matters is **when**: our usual window is
  crossings 40 to 50, by which time our number has risen. Park's whole run ends at 28.

Holding time in electron crossings at the fed temperature, by interval, all complete cases [R]:

| Case | What differs from `pfw_x1.0` | 10–20 | 20–28 | 10–28 (Park's) | 40–50 | Electron energy ÷ fed, 10–28 |
|---|---|---|---|---|---|---|
| `pfw_x1.0` | nothing | 55 | 63 | **58** | 84 | 0.68 |
| `pfw_x0.7` | 0.7 times the fill | 60 | 67 | **62** | 85 | 0.66 |
| `pfw_x1.4` | 1.4 times the fill | 40 | 60 | **47** | 87 | 0.67 |
| `pk_open_wall` | outer boundary absorbs waves | 54 | 65 | **58** | 96 | 0.62 |
| `pk_open_wall_esirkepov` | the same, with the deposition and wall settings that caused our wall fault | 56 | 68 | **60** | 98 | 0.61 |
| `pk_ppc_paper` | 8 times the particles | 56 | 65 | **60** | 75 | 0.61 |
| `pk_const_charge` | feed raised so the number held stays constant; ends at 28 | 53 | 60 | **56** | | 0.68 |
| `pfw_25keV_x1.0` | 25 keV | 65 | 83 | **72** | 116 | 0.70 |
| `pfw_2.76keV_x1.0` | Park's temperature | 55 | 72 | **61** | 111 | 0.72 |
| Park, Run 1 | | | | **135 stated, 174 implied** | | held constant |

- In Park's window everything of ours at 100 keV lies between 56 and 62, except the overfilled case, which
  sheds its excess first.
- The effects I reported before from the 40–50 window are smaller or absent in Park's window: Park's
  temperature gives +31% at 40–50 but +4% over 10–28; 8 times the particles gives −11% at 40–50 but +2% over
  10–28; the wave-absorbing boundary +14% and 0%.
- Our electrons are at 0.6 to 0.7 of their fed energy in Park's window and 0.4 to 0.5 by crossings 40–50 [R].
  Park's stay at their end-of-fill energy because the injection holds it there [P]. Counting our crossings at
  the electrons' actual speed would lower our 58 to about 48 [A].

**The paper's own numbers** [P, A]:

- "About 3 per 22.5/ωpi" sustaining a charge of 18,900 gives 174 crossings. The text says 135. To get 135 the
  rate must be 3.9.
- Figure S2 shows the injection rate wandering between about 2.7 and 3.8 over 6 ion crossings (read off the
  plot). That figure is from Run 4, on a mesh three times coarser than Run 1. At the same charge, that range is 137 to 193 crossings. So
  135 is the low end of a number that drifts by a third within one run.
- The paper does not say whether "total charge 18,900" counts one species or both. Our fill was matched to it
  as one species, which is consistent with the paper's pressure as far as I can check. If it counted both, the
  paper's own figures would give 87 crossings, and our runs would hold about twice Park's plasma. This is a
  reading I cannot exclude, not one I have evidence for [I].

## 5. Differences not yet tested, and which way each would push

| Difference | What correcting ours toward Park would do | Basis |
|---|---|---|
| **Energy-conserving implicit method against explicit** | Unknown, either way. Our plasma loses a third of its electron energy by crossing 28 with the same source; how much of that is the method is not known | [I]. WarpX has implicit schemes; whether they run in this geometry with our patches is unchecked |
| **Park re-heats the plasma, we do not** | Not established. If plasma leaves in proportion to its particles' speed, keeping ours at the fed energy lowers our number by up to 18% | [I, A]. Never run |
| **Source shape** (volume against a disc firing along the axis) | Unknown. A disc source drives flow along the axis that a volume source does not | [I]. Never run |
| **Charge of absorbed particles in Park's code** | In WarpX, leaving it behind at a conducting wall raised 85 to 141. With a wave-absorbing boundary it changes nothing (58 against 60). What ECsim does is not written down anywhere I have read | [R] ours; unknown theirs |
| **Wall at 42 against 45** | Probably lowers ours slightly: a nearer wall removes particles that might return | [I]. Never run |
| **Park's temperature at Park's mesh in screening lengths** | Unknown. Our 2.76 keV case has a cell of 10 screening lengths, so its 61 is not reliable | [R, I] |
| **First-order against second-order particle shape** | Unknown, expected small | [I] |
| **Mesh** (0.42 against 0.30 orbits per cell) | Expected small: at other sizes halving our cell did not change the holding time | [R] at 0.25× and 0.5× only |

Tested, and not the explanation at Park's run length: particle count, the definition of holding time, holding
the charge constant, the wave boundary in WarpX, the fill between 0.7 and 1.0.

## 6. Two things from our later work that bear on this

- **The current along the axis** that separates repeat runs in the size scan ([cusp-results.md](cusp-results.md))
  is not the explanation here. In every case in the table above it is under 8% of the coil current throughout
  [R]. It grows over hundreds of crossings, and these runs last 50. Park's code keeps the field component that
  such a current makes [E], so Park's runs could carry one. The paper does not show that component or mention
  it [P].
- **Noise on the axis.** In these runs the electric field energy density within four cells of the axis is about
  90 times its mean over the mesh from the first snapshot with plasma. With the conducting wall it stays between
  70 and 125; with the wave-absorbing boundary it falls to 35 by the end; with 8 times the particles it is 21 to
  29 throughout [R]. The 400-crossing runs at this size show the same: 28 to 47 at the standard
  particle count, 7 to 10 with 4 times, 5 with 16 times [R]. It falls with particle count and does not grow, unlike the pile-up
  between mirror ends (which reaches several hundred and keeps rising), so I read it as particle noise in the small cells on the axis [I]. It does not move the
  holding time in Park's window (58 against 60 with 8 times the particles). ECsim-CYL's own paper reports the
  same kind of noise [E]. Earlier notes of mine called the repeating runs clean on the axis; that was measured
  at the two smaller sizes and does not hold at this one.

## 7. What would settle it

In order of what each costs:

1. **Ask the authors** two questions the papers do not answer: what happens to the charge of a particle absorbed
   at the loss boundary, and whether 18,900 counts one species or both.
2. **Hold the energy as well as the number.** Top up with particles 2.5 to 3 times hotter, at the rate that
   keeps the number constant, to 28 crossings. Needs a small deck change and one run.
3. **A volume source** in place of the disc. Needs a deck change and a check that it stays neutral.
4. **The implicit scheme in WarpX** at Park's temperature and time step. Needs a check on a workstation first
   that it runs in this geometry.

If 2 to 4 leave ours near 60, the paper's holding time should not be used to validate anything, and its layer
thickness still can be.
