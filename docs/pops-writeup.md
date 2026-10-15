# POPS in WarpX: techniques, runs, and what hasn't been tried

A longer companion to `pops-blog.md`. Full tables are in `pops-results.md`.

## 1. The simulated device, and what is idealised

- **Geometry.** A grounded conducting sphere, 1 cm in radius, cut out of a 3D Cartesian mesh
  (64³ cells by default, so one cell is about 0.3 mm). No magnetic field.
- **Solver.** WarpX 26.10 in electrostatic mode: every time step it deposits the charge of all
  particles on the mesh, solves for the voltage, and pushes the particles. Electrons and deuterons
  both have their real masses and are advanced on the same 1 ps step.
- **Electrons that make the well.** 10 keV electrons enter uniformly over the whole wall, cross
  the sphere and are absorbed where they land. Two knobs per population: current, and "spread"
  (sideways speed over inward speed).
- **Ions.** A cloud of deuterons released at rest (1 eV) with a set size and count. "Fill" is the
  ion count against the 1.39×10¹¹ electrons of an ideal 10 kV cloud.
- **Cost.** A 60 ns run (two collapses) takes about 15 minutes on one B200 GPU at 64³; a node
  runs 8 at once. About 400 runs in 33 campaigns.

Three idealisations matter for reading the results:

1. **The electrons come from the whole wall evenly.** A real device has a few guns.
2. **The electrons make one pass.** The best well uses 68 A of 10 keV electrons, which is 680 kW
   passing through a 1 cm sphere. A real POPS device has to trap its electrons (a magnetic field,
   or grids) so the well costs far less to hold. So these runs answer "what does the ion cloud do
   in a well like this", not "what does the well cost". I haven't flagged this before and should
   have.
3. **No collisions and no fusion reactions** are computed. Everything is one to eight
   oscillations (30–300 ns).

## 2. Techniques

**Checking the setup against theory.** In a perfect bowl the collapse period depends only on the
well depth, the ion mass and the radius. With almost no ions the simulated period matched that
formula to nine digits. The no-electron runs (bowl imposed by hand) then gave the baseline: the
ions' own charge stalls the collapse at fill × compression of 0.1–0.2.

**Shaping the well with sideways spread.** Electrons aimed straight at the centre pile up there
and give a flat-floored well; compression is 1.5–2.5× at every fill. A spread of 0.3 gives a
bowl within 4% of ideal and 12×. More spread rounds the well further but makes it shallower.

**A fast predictor, so the search could be automated.** A full run takes tens of minutes. An
electron-only run takes 70–180 seconds, and from its time-averaged well I follow 6,000 test ions
with no charge, which takes seconds. That predicts the compression at each collapse. Checked
against 11 full runs, it ranks wells correctly and is within about 10% for most. With it I
searched 168 wells.

**Two electron populations.** The search showed a broad population leaves the centre slightly too
flat, and a few amps of a narrow one fill it in. The best well (60 A at spread 0.8 plus 8 A at
0.25) holds the bounce period constant to 0.7% across the cloud. Full runs: 30.5× on the first
collapse and 9.5× on the fifth, against 15× and 2.5× for one population. The ion temperature
caps the first collapse at about 35×, so at low fill the well is no longer the limit.

**The slow wall beam.** A third electron population from the wall, with its energy set a few
hundred volts above the well depth (6.2–7 keV against a 6.5 kV well). Those electrons reach the
centre nearly stopped and stay there. Below the well depth they never arrive; well above it they
pass straight through. This is what lifted fill × compression from 0.15 to 1.6.

**Seeing inside the collapse.** Three measurements I added along the way:
- counts of each species in radial shells, every 0.25–0.5 ns, which give how much electron charge
  sits inside the ion cloud;
- the energy distribution of the slow electrons within 1 mm of the centre;
- the voltage rebuilt from those shell counts, compared with the voltage on the mesh. This is
  what exposed the resolution problem at the centre.

**Controls.** Each claim about the beam has a matching run without it. Also: 10 keV currents
raised 1.5–2× with no slow beam (no gain), slow electrons created at the centre by hand (a
numerical test, not a real gun), finer meshes, a half time step, and four times the particles.

## 3. The runs, by stage

| Campaigns | Question | Outcome |
|---|---|---|
| Stage A (CPU) | Is the setup right? What do ions do with no electrons? | Period matches to 9 digits. Stalls at fill × compression 0.1–0.2. |
| b1 | What well do wall-injected electrons make? | 4 kV at 20 A, 7 kV at 40 A; same on a finer mesh. |
| b2–b4 | Ions in a real electron well | Straight-in: 2×. Spread 0.3: 12×, fading to 4×. Pulsed 10 keV beams at the centre: +10–15% only. |
| b5, b7, b8, b10 | Which wells are closest to a perfect bowl? | 168 electron-only runs; two populations win. |
| b6, b9, b12 | Do full runs confirm the predictor? | Yes within ~10%. Best: 30.5× first, 9.5× fifth. |
| b11 | Slow beam below the well depth | Nothing, except one run at 6 keV that gave the clue. |
| b13, b14 | Radio-frequency drive on a warm cloud | Pumps the oscillation 6–30% per cycle until ions hit the wall. No steady state. |
| b15, b16, b18, b21 | Slow electrons created at the centre (numerical test) | 20.7× at 1 per 100, but only on the first collapse. They heat to 110–140 eV whatever their birth energy. |
| b17, b19 | Slow beam energy scan, 3 per 100 | Peak 12.9× at 6.7 keV; useful window about 0.6 keV wide. |
| b20–b26 | Other fills, finer meshes, long runs | Works at every fill; compression holds on 96³ and 128³; fades over eight collapses. |
| b27, b28 | How much ion charge is cancelled? Lowest current that works? | Sharp current threshold: 2.5 A does nothing where 3 A works. |
| b29 | Fine scan above the threshold | Best: 4.9× at 30 per 100 (5.4× on 96³), fill × compression 1.6. |
| b30 | Second slow beam fired during the collapse | Its electrons replace the first beam's one for one. No gain. |
| b31 | Bigger or smaller starting cloud | Bigger compresses more: 11.8× at 10 per 100, 21.7× at 3 per 100. |
| b32, b33 (running) | Is the centre resolved? Later collapses at high fill? | Early: a bigger cloud with 8 A at 6.5 keV gives 6.0× at 30 per 100 (1.8), 64³ only. |

## 4. What I think is true, and how sure I am

- **Well shaping works and is understood.** Confident: predictor and full runs agree, and it
  holds across mesh, time step and particle count.
- **The slow beam gives a tenfold gain in fill × compression.** Confident for the first collapse:
  it has matching controls and finer-mesh checks at all four fills.
- **Tuning the beam won't get much further.** Fairly confident. Current, energy, beam
  temperature, a second beam and timing were all tried.
- **Why it stops.** Not established. The slow electrons trapped with the ions heat to 650–740 eV
  as the cloud shrinks, and the charge they leave uncancelled is enough to stop the collapse. But
  a limit set by heating alone predicts the smallest size wouldn't depend on the starting size,
  and it does.
- **Density at the very centre.** Unknown at the lower fills until the mesh scan finishes.

## 5. Ideas not yet explored

Ranked by how much I think they could matter.

**A. Trap the electrons with a magnetic field.** This addresses the 680 kW problem and possibly
the limit too. A cusp field would let electrons recirculate, so the same well needs far less
current, and it changes how the slow electrons at the centre behave (they can't simply fly out
when heated). This is where POPS and the cusp work meet: a small cusp device with a POPS cloud
inside. Test: add a coil field to the existing setup, which WarpX supports directly. Cost: about
the same per run, but electrons take longer to settle, so maybe 3–10× longer runs. Unknown:
whether a cusp-confined well can still be shaped into a bowl.

**B. Measure reaction rate, not cloud size.** Fill × compression is a stand-in. What matters is
density squared, summed over the volume and the time of the collapse. Two clouds with the same
overall size can differ a lot in how peaked they are. I've written this measurement and it runs
in the mesh scan. WarpX also has a fusion-reaction module that would count neutrons directly,
which I haven't switched on. Cost: none beyond the finer mesh.

**C. A finer mesh at the centre only.** The collapse is now smaller than the mesh can show at low
fill. WarpX can refine a patch around the centre without paying for a fine mesh everywhere. Needed
before any claim above about 30× compression, and to find out whether the unresolved core helps
or hurts.

**D. Hold the oscillation with a controlled drive.** My radio-frequency runs used a fixed drive,
which pumps until ions are lost. Untried: a drive that backs off as the swing grows, or is
slightly off resonance so it saturates. This is what POPS actually proposes (a warm cloud in
steady oscillation), and nothing I've run tests it with the slow beam on. Cost: a few dozen
300–400 ns runs, about one node-day.

**E. Refresh the ions.** The squeeze fades because ions drift out of step. Feeding fresh cold
ions and letting stale ones leave could hold the first-collapse quality. Untried. Simple to set
up as a steady ion source at the right radius.

**F. A beam whose energy tracks the centre.** The centre voltage rises about 3.5 kV during a
collapse, so a beam tuned for the expanded cloud is mistuned at the collapse. I tried a second
beam at a fixed higher energy; I haven't tried sweeping the energy continuously. I rate this
lower: the second-beam result suggests the cloud holds a fixed share of electrons whatever is fed.

**G. Let an optimiser run the search.** My scans were one or two knobs at a time, chosen by hand.
There are about ten knobs (two well populations, beam energy, current and spread, cloud size,
timing). With 8 runs per node an optimiser could do a thousand runs a day. I'd expect a factor
of 2–3 from this, not 600, so it's worth doing only after A or D changes the picture.

**H. Real guns.** Replace the even wall source with 6–14 discrete beams. This is a robustness
test, not a way to gain: does the bowl survive a lumpy source? It needs doing before anyone
builds anything, and it reuses the old six-gun geometry.

**I. Scale.** Everything is one size and one voltage. Theory says smaller spheres give more power
per volume, and a deeper well raises the temperature cap on compression. A 100 kV well or a 3 mm
sphere might behave differently because the electrons do. Untested.

**J. Longer times with collisions.** Whether the ions stay cool over thousands of oscillations
decides if POPS really avoids Rider's cost. WarpX has collisions; nothing here has run long
enough to see them. Expensive: hundreds of GPU-hours per run.

## 6. What I'd do next

1. Finish the mesh scan and long runs (in flight), and switch the headline number to the
   reaction-rate measure (B, C).
2. One campaign on D with the slow beam on, since that's the actual POPS proposal and it's cheap.
3. Then A, as the first cusp experiment that also serves POPS: a small cusp with electrons
   trapped in it, checking what well it makes.
