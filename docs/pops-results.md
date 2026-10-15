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

40 A unless noted, 160 ns (about six collapses). "Shape" is φ(a/2)/φ(0), which is 0.75 for a
harmonic well.

| case | compression per collapse | centre (kV) | shape |
|---|---|---|---|
| fill 1e-3 | 2.45, 2.28, 1.97, 1.66, 1.48, 1.51 | −10.2 | 0.92 |
| fill 1e-2 | 2.30, 1.60, 1.77, 1.73, 1.52, 1.64 | −10.0 | 0.94 |
| fill 1e-1 | 2.22, 1.78, 1.88, 1.96, 1.79, 1.87 | −9.9 | 0.92 |
| fill 1e-2, spread 0.1 | 2.96, 2.29, 1.86, 1.78, 1.71, 1.77 | −10.0 | 0.89 |
| fill 1e-2, 20 A | 3.54, 1.72, 1.70, 1.78, 1.73, 1.80, 1.76 | −10.0 | 0.60 |
| fill 1e-2, 4× electron particles | 2.29, 1.59, 1.78, 1.72, 1.51, 1.66 | −10.0 | 0.94 |

- Compression is about 1.5–3.5 and does not depend on ion fill over a factor of 100, so ion space
  charge is not what limits it here. The well shape is: at 40 A it is flat-bottomed with a steep
  edge, at 20 A it is peaked at the centre, and neither is a parabola.
- The centre sits at the full electron energy in every case, so the electrons stagnate there.
- All ions stay in the sphere. Four times as many electron particles changes nothing.
