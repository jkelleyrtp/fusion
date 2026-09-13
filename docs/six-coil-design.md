# Six-coil imposed field

`run_transient_pic.py --coils 6` replaces the two-coil axisymmetric cusp with a cube of six
circular coils, one per face (commits `1136c7c`, `d1ee9af`). The default remains `--coils 2`.
This is an imposed vacuum field from fixed coil currents. It is not a validated Polywell
model: there is no plasma current, diamagnetic modification or high-beta feedback, and the
coils are ideal filaments of radius a inside toroidal casings.

## Geometry

- Coils of radius a = 0.5 m sit in the planes x, y, z = ±`--coil-offset`·a. The two coils on
  each axis carry opposite currents, so every coil's on-axis field points to the centre and the
  centre is a null.
- The field is the sum of one single-loop (r, z) table (720 radial points, same elliptic
  integral field as the two-coil table), permuted and translated onto each coil, then sampled
  on a refined mesh excluding the casing interiors.
- Casings are solid tori around each winding (`Torus.axis` = 0, 1, 2), fixed potential,
  absorbing, reported as six conductor-loss channels after the gun barrel.
- Validation requires every casing inside the box on each axis and a gap between adjacent
  casings: windings on neighbouring faces are closest where they approach the shared cube
  edge, at distance √2·(offset − 1)·a between tube centres, which must exceed two casing radii.
  Offsets of 1.0a with any casing and 1.2a with 0.15a casings are rejected.
- The gun stays on the z axis at z = −0.65 m, 30° from +z. It fires through the −z coil
  opening. Local field at the source: 17.6 mT, nominal pitch 30.0° (offset 1.2a) and
  20.7 mT, 30.1° (offset 1.3a), versus 13.6 mT, 29.7° for the two-coil cusp.

## Checks

- Direct single-loop superposition over random interior points: relative error 1.1e-3 from the
  table interpolation.
- Central field below 1e-16 T; 90° rotations about the cube axes and inversion reproduce the
  field to roundoff.
- Every casing has resolved nodes at the test mesh and holds its fixed potential in a short
  reference PIC run.
- `validate_pic_gpu.py` preflight: CUDA field lookup against the reference superposition at
  65,536 seeded box points excluding casings, `rtol=1e-10`. The CPU reference side passes
  (62,721 points, maximum 0.159 T, below the 0.223 T allowed by 80 steps per gyration at 2 ps),
  and the CUDA lookup matched it on a B200 in the campaign preflight (job
  `jonathan-pic-e169c8cb23b9`, source `23e5800`).

## Conductor memory

The electrostatic boundary uses a dense capacitance matrix over all conductor surface nodes,
so storage grows with the square of the node count (8 bytes per entry). At the 65-node
reference cell size:

| Geometry | Conductor nodes | Dense matrix |
|---|---:|---:|
| two coils, 0.15a casings | 30,227 | 7.3 GB |
| two coils, 0.10a casings | 19,595 | 3.1 GB |
| six coils, offset 1.0a, 0.15a casings (overlapping, rejected) | 60,283 | 29.1 GB |
| six coils, offset 1.2a or 1.3a, 0.10a casings | 52,500–52,900 | ~22 GB |

Setup holds the matrix and its Cholesky factor, frees the matrix, then forms the inverse, so the
peak is two to three matrices (44–66 GB with workspace), within a 180 GB B200. Symmetrization is done in 4096-row blocks to avoid a
fourth copy. The two-coil casing campaign built 30k-node matrices in 10–18 s.

## Campaign

`run_pic_campaign.py --study six-coil`: CUDA electron-only PIC, 1 A, 5 keV, 300 ns at 2 ps
with packets of 8 every 2 steps (same injected current per unit time as 4 ps), 65-node
reference cells, 0.06a grounded barrel, lower wall at 1.95a, 0.10a grounded casings.

| Case | Coils | Offset | Box half-width / top | Change |
|---|---:|---:|---|---|
| `pic_1A_two_coil_c010` | 2 | 0.5a | 1.425a / 1.4625a | two-coil control in the same box |
| `pic_1A_six_d120` | 6 | 1.2a | 1.425a / 1.4625a | reference |
| `pic_1A_six_d120_1mA` | 6 | 1.2a | 1.425a / 1.4625a | 1 mA, vacuum-orbit control |
| `pic_1A_six_d130` | 6 | 1.3a | 1.5a / 1.54375a | coil spacing |
| `pic_1A_six_d120_w1575` | 6 | 1.2a | 1.575a / 1.4625a | wider box |
| `pic_1A_six_d120_t195` | 6 | 1.2a | 1.425a / 1.95a | farther top wall |
| `pic_1A_six_d120_p1kV` | 6 | 1.2a | 1.425a / 1.4625a | casings at +1 kV |
| `pic_1A_six_d120_s2345` | 6 | 1.2a | 1.425a / 1.4625a | seed 2345 |

Questions: does the six-coil field turn the beam channel into a more central well, how does
core dwell compare with the two-coil cusp at the same current, and are the box and seed
sensitivities as small as in the two-coil casing study. Results are not evidence about ion
confinement or fusion performance.
