# Prior work on cusp leaks at high pressure

What has been measured and simulated before, and what is left open. Every claim below was checked
against the paper or its abstract on 2026-10-16; where only an abstract was read, that is stated.

## What is open

- **Leak size against device size at a fixed pressure ratio, with particles for both species.** No
  published scan. Lockheed's 2017 abstract says they ran one; no results were published.
- **A six-coil cage at high pressure with ions heavier than electrons.** The only published 3D run
  uses equal masses and about 100 cells a side.
- **Leak width through the holes, in electron orbits, against pressure.** The picket-fence paper
  reports the thickness of the boundary layer, not the width of the leak.

## Simulations

| Work | What was run | Result |
|---|---|---|
| Park, Lapenta, Gonzalez-Herrero, Krall 2019, [arXiv:1901.08041](https://arxiv.org/abs/1901.08041), Front. Astron. Space Sci. 6, 74 | 2D axisymmetric picket fence (ring cusps only, periodic along the axis), plasma fed near the axis and topped up to a steady state. Ions 64 electron masses (1 to 1836 scanned), electrons at 0.0735 of light speed, one device size (coil radius about 107 electron orbits at the boundary, from their table), four pressures. Implicit energy-conserving code; 10,000 to 150,000 CPU hours a run. | Boundary layer about 2 electron orbits thick (a quarter of an ion orbit), set by an electric field that holds the ions back. Particle holding time about 135 electron crossings of the coil diameter (17 ion crossings). At a pressure 40% above their baseline the wall fails in the gap and plasma leaks fast. Needs cells below one electron orbit; coarser meshes overstate the layer. |
| Park, Krall, Lapenta, Ono 2025, [arXiv:2508.06761](https://arxiv.org/abs/2508.06761) | 3D six-coil cage, same code, about 100 cells a side, equal electron and ion mass, about a million CPU hours. Also the picket-fence mass scan above. | Loss through the six coil centres and the eight corners, each a hole of radius about 1.5 orbits; little loss along the edges. Picket-fence loss rate falls as (mass ratio)^-0.28, between ion-orbit (0) and electron-orbit (0.5) scaling. Their reactor estimate assumes holes of 1.5 times the geometric mean of the two orbits and says this needs testing. |
| Font, Welch, Mitchell, McGuire, APS DPP 2017, BP11.102 (abstract only) | Implicit particle runs of scaled-down Lockheed cusp geometries "to determine particle loss scaling with reactor size, plasma conditions, and gyro radii". | No published numbers found. |
| Gummersall, Carr, Cornish, Khachan 2013, Phys. Plasmas 20, 102701 (abstract only) | Single-electron orbits in a six-coil cage with no plasma pressure. | Holding time against coil current and size, valid only at zero pressure. |

## Experiments

| Work | Plasma | Leak width |
|---|---|---|
| Hershkowitz, Leung, Romesser 1975, Phys. Rev. Lett. 35, 277 (abstract) | Low pressure, line cusp | Half-width twice the geometric mean of the electron and ion orbits |
| Kitsunezaki, Tanimoto, Sekiguchi 1974, Phys. Fluids 17, 1895 (abstract) | Laser-heated pellet at the centre of a two-coil cusp, high pressure | Ring leak "much smaller than" the ion orbit |
| Pechacek et al. 1980, Phys. Rev. Lett. 45, 256 (abstract) | Laser-heated pellet filling a cusp to pressure ratio 1 | Ring leak one ion orbit wide, contradicting the narrower results |
| Haines 1977, Nucl. Fusion 17, 811 (abstract) | Review | Layer thickness "possibly" the geometric mean; earlier results nearer the ion orbit |
| Park et al. 2015, Phys. Rev. X 5, 021024 | Gun-filled six-coil cage, one device, one field | X-ray signal from fast electrons rises when the plasma pushes the field out. No leak width, no scaling. |

## How our runs compare

- Our two-coil 2D runs are fed and reach pressure ratios from 0.1 to 37, like the 2019 paper, but in a
  geometry with holes through the coils as well as a ring gap, and at 15 to 120 orbits rather than one size.
- That paper's failure of the wall just above its baseline pressure matches what we see: leaks widen
  once the pressure ratio in the gap passes about 1, and the holding time peaks and then falls.
- Its 135 electron crossings at about 107 orbits is a number to reproduce. Our 30-orbit baseline holds
  for about 35 electron crossings of the coil diameter (5.4 ns, electrons at 56 keV), in a different shape.
