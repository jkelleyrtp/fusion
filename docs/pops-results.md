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
