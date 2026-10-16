# Plasma fired into the six-coil cusp from guns outside it

Status: first results, 2026-10-16. Every number here uses `flux-paired.patch`, which has not been reviewed
(`flux-injection-charge.md`). Gun runs made before it (`jet1`, `jet2`) are not usable.

## What is run

Deck `inputs_3d_cusp_jets`, campaign `jet3`. Nothing starts inside. Two guns sit on the z axis at 1.9 coil radii
from the centre, outside the coil planes at 1.3. Each mouth is a disc of radius 0.3 coil radii that sends out
neutral plasma toward the centre, along the coil field there (angle 0 degrees; the field at the coil opening is
1.52 times that at the mouth). Coil radius 1 cm, 10 keV electrons, 1 keV ions of 57 electron masses, 1e22
electrons and ions per second from the two guns together, fixed coil field, plasma fields from Maxwell's
equations, 128 cells across a 5 cm box. The guns fire for 60 ns and the run goes on to 80 ns.

"Held" is the number of electrons within 1.3 coil radii of the centre late in the firing, over the firing rate:
the time an average fired electron spends inside. The centre-fed column is the same count for plasma born on a
disc at the centre (`fed3`).

## Results

![Amount inside against time, and held time against coil current](images/guns_first.png)

| Case | Coils (kA-turns) | Held (ns) | Left 20 ns after the guns stop | Loss time after stop (ns) | Centre-fed held (ns) |
|---|---|---|---|---|---|
| `p_off` | 0 | 1.21 | 2% | 7.6 | 2.63 |
| `p_8k` | 8 | 2.17 | 8% | 9.1 | 4.29 |
| `p_32k` | 32 | 4.86 | 26% | 15.4 | 7.56 |
| `p_128k` | 128 | 6.96 | 48% | 27.0 | 11.92 |

- Plasma fired from outside gets in and is held 45 to 65% as long as plasma born at the centre.
- At 32 and 128 kA-turns the amount inside was still rising when the guns stopped, so those two are lower bounds.
- A second seed at 32 kA-turns gives 4.85 ns against 4.86.
- The streams leaving through the coil openings are 2.3 to 2.8 mm in half-width with the coils on, while the
  electron orbit there goes from 1.2 mm to 0.08 mm. As in the centre-fed runs, the width does not follow the orbit.

Other settings at 32 kA-turns unless said:

| Case | Change | Held (ns) | Left 20 ns after stop |
|---|---|---|---|
| `p_32k_v1e7` | directed speed 1e7 m/s toward the centre | 3.57 | 5% |
| `p_32k_v2e7` | directed speed 2e7 m/s | 1.80 | 2% |
| `p_128k_v1e7` | 128 kA-turns, 1e7 m/s | 7.60 | 21% |
| `p_off_v1e7` | coils off, 1e7 m/s | 1.62 | 0.2% |
| `p_32k_te1e3` | 1 keV electrons | 11.89, still rising | 52% |
| `p_off_te1e3` | 1 keV electrons, coils off | 2.24 | 4% |
| `p_32k_te1e3_v1e7` | 1 keV electrons, 1e7 m/s | 5.76 | 7% |
| `p_32k_f1e21` | a tenth of the firing rate | 4.38 | 28% |
| `p_32k_f1e23` | ten times the firing rate | 3.27 | 23% |

- A directed speed makes the jet pass straight through and out of the far opening: more is inside while the guns
  fire at 128 kA-turns, but less stays once they stop, at every field.
- Colder plasma is held longer, as in the centre-fed runs (time goes with size over sound speed).
- Ten times the firing rate holds a third less per particle.

## Limits

- Light ions, one device size, one gun position and mouth size. Heavier ions, longer firing, gun position and size,
  higher firing rates and a 192-cell repeat are running (second half of `jet3`).
- The coil field is fixed and there are no electrodes, gas or collisions.
- The pressure at the coil openings is far below the magnetic pressure in all of these, so they say nothing
  about plugging.
