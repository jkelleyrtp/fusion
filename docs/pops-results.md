# POPS in WarpX: results so far

All runs: deuterons, 1 cm grounded sphere, WarpX 26.10 electrostatic, 64³ mesh unless noted.
Decks and reductions are in `warpx/pops/`, case lists in `warpx/campaigns/`.
Status: in progress. Sections are added as campaigns finish.

## Stage A: imposed harmonic well, no electrons (CPU)

10 kV well, cloud prepared to compress 10× if ions did not repel each other, two ion periods.

- Breathing period at fill 1e-6: 32.0947473 ns measured, 32.0947473 ns from π/ω with ω = √(2eφ₀/Ma²).
- Compression at the first and fourth collapse, by ion fill (ions per electron of the cloud the well stands for):

| fill | first | fourth | period (ns) |
|---|---|---|---|
| 1e-6 | 8.31 | 8.31 | 32.09 |
| 1e-3 | 8.40 | 9.24 | 32.09 |
| 1e-2 | 7.31 | 4.99 | 33.4 |
| 3e-2 | 4.29 | 3.98 | 34.7 |
| 1e-1 | 1.92 | 1.93 | 36.4 |
| 3e-1 | no collapse | | |

These runs sampled the radius every 10 steps, so the 8.3 at low fill understates the minimum.
With nothing cancelling the ion charge, the collapse stalls near fill × compression ≈ 0.1–0.2.
The same fill 1e-2 case on a B200 gives 7.31 and 5.01.

## Campaign b1: electrons injected from the wall, no ions (one B200 node)

10 keV electrons injected inward over the whole wall, 4 ns. The depth is the uniform-ball estimate
Q/(8πε₀a) from the charge induced on the wall, averaged after 3 ns; it underestimates a centrally
peaked cloud.

| current (A) | tangential spread | electrons | depth estimate (kV) | electron rms radius (mm) |
|---|---|---|---|---|
| 5 | 0.02 | 1.15e10 | 0.85 | 5.61 |
| 10 | 0.02 | 2.79e10 | 2.07 | 5.26 |
| 20 | 0.02 | 5.66e10 | 4.21 | 5.63 |
| 40 | 0.02 | 9.94e10 | 7.37 | 6.40 |
| 20 | 0.1 | 5.15e10 | 3.82 | 5.77 |
| 20 | 0.3 | 3.80e10 | 2.79 | 6.52 |
| 20, 96³ mesh | 0.02 | 5.71e10 | 4.20 | 5.65 |

A uniform ball has an rms radius of 7.7 mm, so the electrons are centrally peaked. The 96³ run
agrees with 64³. Speed: 4000 steps with 1.8e7 macro-electrons took 84 s on one B200.

## Campaign b2: injected electrons and ions together (one B200 node)

40 A unless noted, 160 ns (about five or six collapses). "Shape" is φ(a/2)/φ(0) with the ions
out (0.75 for a harmonic well) and "misfit" is the rms difference from a parabola over radius, in
units of the depth. Both are medians over the 1 ns field samples where the ion cloud is expanded.
"Shallowest centre" is the least negative centre potential among the samples, reached during a
collapse.

| case | compression per collapse | centre (kV) | shape | misfit | shallowest centre (kV) |
|---|---|---|---|---|---|
| fill 1e-3 | 2.45, 2.28, 1.97, 1.66, 1.48, 1.51 | −10.2 | 0.93 | 0.09 | −10.1 |
| fill 1e-2 | 2.30, 1.60, 1.77, 1.73, 1.52, 1.64 | −10.0 | 0.94 | 0.10 | −9.0 |
| fill 3e-2 | 2.17, 1.63, 1.83, 1.79, 1.59, 1.87 | −9.9 | 0.95 | 0.10 | −7.9 |
| fill 1e-1 | 2.22, 1.78, 1.88, 1.96, 1.79, 1.87 | −9.8 | 0.94 | 0.10 | −6.7 |
| fill 1e-2, spread 0.1 | 2.96, 2.29, 1.86, 1.78, 1.71, 1.77 | −10.0 | 0.89 | 0.08 | −9.4 |
| fill 1e-2, spread 0.3 | 12.34, 7.19, 4.75, 3.93, 4.00 | −8.3 | 0.75 | 0.04 | −5.2 |
| fill 1e-2, 20 A | 3.54, 1.72, 1.70, 1.78, 1.73, 1.80, 1.76 | −10.0 | 0.59 | 0.13 | −8.7 |
| fill 1e-2, 4× electron particles | 2.29, 1.59, 1.78, 1.72, 1.51, 1.66 | −10.0 | 0.94 | 0.10 | −8.9 |

- With electrons aimed straight at the centre (spread 0.02) compression is about 1.5–2.5 and does
  not depend on ion fill over a factor of 100. The well is the limit: the centre sits at the full
  electron energy, so the electrons stagnate there and the well is flat-bottomed with a steep edge
  at 40 A and peaked at the centre at 20 A.
- A tangential spread of 0.3 makes the well harmonic and lifts the first collapse to 12×. It then
  fades to 4× by the fourth collapse.
- All ions stay in the sphere. Four times as many electron particles changes nothing.

## Campaign b3: tangential spread against current (one B200 node)

Fill 1e-2, 120 ns. Same columns as b2, plus the fraction of ions still in the sphere at the end.

| spread | current (A) | compression per collapse | centre (kV) | shape | misfit | shallowest centre (kV) | ions kept |
|---|---|---|---|---|---|---|---|
| 0.02 | 5 | 1.83, 1.38, 1.56 | −4.5 | 0.22 | 0.39 | −3.8 | 1.00 |
| 0.02 | 10 | 1.88, 1.38, 1.32 | −10.1 | 0.28 | 0.32 | −10.0 | 1.00 |
| 0.3 | 10 | 4.93, 5.18 | −2.3 | 0.63 | 0.10 | −0.4 | 1.00 |
| 0.5 | 20 | 5.35, 5.51 | −2.7 | 0.73 | 0.02 | −0.8 | 1.00 |
| 0.5 | 40 | 8.26, 7.12, 5.28 | −5.3 | 0.76 | 0.01 | −2.6 | 1.00 |
| 0.8 | 40 | 4.15, 3.33 | −2.9 | 0.81 | 0.05 | −1.5 | 0.96 |
| 0.8 | 80 | 5.40, 2.62, 1.63 | −5.4 | 0.82 | 0.05 | −3.6 | 0.99 |
| 1.2 | 80 | 3.59, 2.26 | −3.1 | 0.85 | 0.09 | −1.9 | 0.99 |

![Well shape, ion radius and centre potential at 40 A for five spreads](images/pops-well-shape.png)

- The spread sets the shape. At 40 A the well goes from flat-bottomed (0.02, 0.1) through harmonic
  (0.3, 0.5: within 1–4% of a parabola) to too shallow in the middle (0.8). A larger spread also
  costs depth: −10, −8.3, −5.3 and −2.9 kV at 40 A for spreads 0.02, 0.3, 0.5 and 0.8.
- In the harmonic wells the limit is the ion charge at the focus. Each collapse lifts the centre
  potential by 2–3 kV (right panel), and at fill 1e-2 that is a third to nearly all of the depth.
  The number of electrons in the sphere does not change during a collapse: electrons with keV
  energies at the centre barely respond to the ion charge.
- Mesh caveat: at 12× the ion cloud's rms radius is 0.42 mm and a cell is 0.35 mm, so the deepest
  collapses are not resolved on 64³.

## Campaign b4: ion fill in the harmonic well, mesh, and a centre-aimed beam (one B200 node)

40 A, spread 0.3 (the harmonic well of b2), 120 ns. "Ideal well" is a CPU control with the same ions
in an imposed 8.277 kV parabola and no electrons.

| case | compression per collapse | ideal well, first → last collapse |
|---|---|---|
| fill 1e-3 | 15.16, 5.66, 3.58, 2.75 | 35.2 → 9.8 (8 collapses) |
| fill 1e-2 (b2) | 12.34, 7.19, 4.75, 3.93, 4.00 | 12.2 → 2.1 (12 collapses) |
| fill 1e-2 on 128³ (60 ns) | 10.69, 10.02 | |
| fill 3e-2 | 5.89, 5.75, 5.06 | 4.43 → 3.78 (7 collapses) |
| fill 1e-1 | 2.53, 2.57, 2.52 | 1.72 → 1.73 (7 collapses) |
| fill 1e-2, steady 3 A beam at the centre | 10.57, 4.24, 3.01, 2.54 | |
| fill 1e-2, 5 A pulses at each collapse | 13.52, 5.75, 3.34 | |
| fill 1e-2, 15 A pulses | 13.96, 5.68, 3.54, 3.19 | |
| fill 1e-2, 40 A pulses | 14.15, 5.66, 3.66 | |

- The ion charge sets the first collapse: fill × compression is 0.12, 0.18 and 0.25 at fills 1e-2,
  3e-2 and 1e-1. Real electrons give 1.3–1.5 times the ideal-well compression at the two highest
  fills, so they cancel little of the ion charge.
- The fade over successive collapses is strongest at the lowest fill, so it is not the ion charge.
  It is the well shape (next section).
- A 10 keV beam pulsed onto the centre at each collapse adds 10–15% to the first collapse whatever
  its current, and does nothing for the fade. A steady one deepens the centre to −10 kV and makes
  the well less harmonic.
- Mesh: at fill 1e-2 the first collapse is 10.7 on 128³ against 12.3 on 64³, and the second is 10.0
  against 7.2. Numbers at this fill carry that uncertainty.

## Well-shape search (campaigns b5, b7, b8, b10: 168 electron-only runs, 70–180 s each)

`warpx/pops/analyze_well_scan.py` fits the time-averaged well of an electron-only run and follows
6000 chargeless test ions in it. That predicts the compression at each collapse in seconds.

- **The prediction matches the full simulation at low fill.** For the 40 A, spread 0.3 well it
  gives 14.9, 5.4, 3.4, 2.6; the fill 1e-3 run gave 15.16, 5.66, 3.58, 2.75. So the fade is ions of
  different amplitude drifting out of step in a slightly non-harmonic well: there the bounce period
  varies by 4.3% (rms) across the cloud.
- **The well shape does not depend on the numerics.** For the best b7 well the predicted five
  collapses are 32.0, 27.2, 21.8, 17.6, 14.6 on 64³; 31.8, 26.0, 20.1, 15.9, 13.0 on 96³ and 128³;
  32.0, 27.5, 22.2, 18.0, 15.0 with four times the particles; 31.9, 27.8, 22.9, 18.9, 15.8 at half
  the time step.
- **Two electron populations make a much more harmonic well than one.** A broad main beam leaves
  the centre slightly too flat; a few amps with a narrower spread fill it in.

| electrons (current, spread) | centre (kV) | period variation (rms) | predicted compression, collapses 1–5 |
|---|---|---|---|
| 40 A, 0.3 (b2/b4 well) | −8.7 | 4.3% | 15.5, 5.6, 3.6, 2.7, 2.3 |
| 40 A, 0.45 | −6.2 | 2.0% | best single beam at 40 A |
| 20 A, 0.6 | −2.4 | 0.9% | 20.4, 16.3, 12.4, 9.7, 7.9 |
| 40 A, 0.6 + 10 A, 0.3 | −6.7 | 1.6% | 28.9, 15.4, 9.9, 7.3, 5.7 |
| 50 A, 0.7 + 5 A, 0.25 | −5.9 | 0.65% | 32.0, 27.2, 21.8, 17.6, 14.6 |
| 60 A, 0.9 + 5 A, 0.25 | −5.3 | 0.31% | 30.1, 26.5, 22.0, 18.2, 15.2 |
| 60 A, 0.8 + 8 A, 0.25 | −6.6 | 0.66% | 34.0, 30.6, 26.0, 21.9, 18.6 |
| 70 A, 0.9 + 8 A, 0.25 | −6.5 | 0.60% | 33.6, 30.5, 26.3, 22.3, 19.0 |

- Wells deeper than about 70% of the electron energy are not harmonic in any run: at 80 A with a
  single beam the centre saturates at the full 10 kV and flattens.

## Ions in the searched wells (campaigns b6, b9: electrons and ions together, fill 1e-3, 64³)

![Full runs against the test-ion prediction](images/pops-prediction-check.png)

| electrons (current, spread) | centre (kV) | compression per collapse | test-ion prediction |
|---|---|---|---|
| 40 A, 0.3 (b4) | −8.7 | 15.2, 5.7, 3.6, 2.8 | 14.9, 5.4, 3.4, 2.6 |
| 20 A, 0.5 | −3.0 | 18.2, 11.6, 8.6, 7.0 | 25.4, 12.8, 8.1, 5.9 |
| 20 A, 0.6 | −2.4 | 16.3, 10.9, 7.2, 5.3 | 20.4, 16.3, 12.4, 9.7 |
| 40 A, 0.45 | −6.2 | 23.0, 10.7, 6.7, 4.9 | |
| 20 A, 0.4 + 20 A, 0.5 | −6.3 | 23.2, 10.9, 6.9, 5.1 | 27.6, 15.2, 9.9, 7.3 |
| 40 A, 0.5 + 10 A, 0.2 | −8.3 | 21.2, 8.7, 5.5, 4.2 | |
| 40 A, 0.6 + 10 A, 0.3 | −6.6 | 26.2, 13.5, 8.5, 6.2 | 28.9, 15.4, 9.9, 7.3 |
| same, 128³ (70 ns) | −6.7 | 24.7, 12.4 | |
| 50 A, 0.5 + 5 A, 0.15 | −8.3 | 27.4, 13.1, 8.6, 6.5, 5.3 | 27.6, 12.2, 7.6, 5.6, 4.5 |
| 40 A, 0.6 + 5 A, 0.25 | −5.9 | 27.6, 18.1, 12.9, 10.0, 8.2 | 28.8, 16.7, 11.0, 8.2, 6.5 |
| 50 A, 0.7 + 5 A, 0.25 | −5.9 | 27.9, 19.9, 13.7, 10.0, 7.7 | 32.0, 27.2, 21.8, 17.6, 14.6 |
| 50 A, 0.7 + 8 A, 0.25 | −6.6 | 30.5, 22.2, 15.9, 12.0, 9.5 | 32.5, 22.3, 15.6, 11.8, 9.4 |

- Shaping the well with two electron populations doubles the first collapse (15 → 30) and raises
  the fifth from about 2.5 to 9.5.
- The test-ion prediction ranks the wells correctly and is within about 10% for most. It is too
  optimistic for the shallow wells and for the single most harmonic one, where the ions' own
  charge is no longer negligible at fill 1e-3.
- Mesh: 128³ gives 24.7, 12.4 where 64³ gives 26.2, 13.5.
- With more ions in the 50 A, 0.7 + 5 A, 0.25 well: fill 3e-3 gives 21.3, 11.1, 6.6, 5.0, 4.3;
  fill 1e-2 gives 9.1, 7.9, 6.0, then the oscillation turns irregular and 10% of the ions reach
  the wall by 220 ns.

## A low-energy electron beam as a neutraliser (campaign b11): no effect

Well: 60 A, 0.8 + 8 A, 0.25 (−6.6 kV). A third, steady beam of 4–6 keV electrons is turned back
short of the centre by the well, and should reach the centre only when the ion charge lifts it.

| fill | extra beam | compression per collapse | ions kept |
|---|---|---|---|
| 3e-2 | none | 4.07, 4.18, 4.16 | 1.00 |
| 3e-2 | 1 A, 5 keV | 3.99, 4.07, 4.06 | 1.00 |
| 3e-2 | 1 A, 6 keV | 6.94, 5.97, 4.07 | 0.97 |
| 3e-2 | 3 A, 4 keV | 3.91, 3.89, 3.74 | 0.96 |
| 3e-2 | 3 A, 5 keV | 3.80, 3.72, 3.42 | 0.95 |
| 3e-2 | 3 A, 6 keV | 3.81, 3.61, 3.77 | 0.99 |
| 1e-1 | none | 1.69, 1.71, 1.71 | 1.00 |
| 1e-1 | 3 A, 4 keV | 1.69, 1.67, 1.67 | 0.99 |

- The number of low-energy electrons in the sphere does not rise during a collapse (6.85e9 before,
  6.78e9 at the collapse, for 1 A at 6 keV), so they do not collect on the ion core.
- Fill × compression stays at 0.12–0.17 in this well, against 0.18–0.25 in the deeper 40 A,
  spread 0.3 well. A more harmonic well does not help once the ion charge is the limit.
- Electrons passing through speed up where the ions raise the potential, so their density there
  falls. None of the three injection schemes tried (10 keV pulses, a steady 10 keV beam, a steady
  low-energy beam) cancels the ion charge at the focus.

