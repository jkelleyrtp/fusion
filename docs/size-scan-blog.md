# Does the leak grow with the bottle? Chasing one number through a hundred simulations

*Work in progress, 17 October 2026. Numbers are from finished 2D WarpX runs. There is no final answer yet, and
the caveats at the end matter.*

## The question

A magnetic cusp is a bottle with holes. Coils make a field that is weak in the middle and strong at the edge,
so plasma sits in the middle. But the field lines have to go somewhere, and where they lead out between the
coils, plasma follows them out. Every cusp leaks; what matters is how wide the leaks are.

There is an old hope about this, called cusp plugging. Fill the bottle until the plasma pushes back as hard as
the field does. The plasma then shoves the field out of its interior and the boundary between the two becomes
sharp. The claim is that the leaks then narrow to slits a few electron orbits wide (an electron orbit is the
small circle an electron makes in the field, a fraction of a millimetre here).

The hope only pays off if it survives scale-up. There are two ways it could go:

- **The slit stays a few electron orbits wide however big the device is.** Then a bigger device holds its
  plasma longer in proportion to its size, and cusps get good quickly.
- **The slit grows with the device.** Then a bigger device holds its plasma no longer than a small one,
  counted in the time an electron takes to cross it, and plugging buys little.

I could not find a published simulation that measures the leak against device size with the pressure held high
and the plasma continuously fed. That measurement is what this project is after.

## How we ask it

The tool is WarpX, an open particle-in-cell code that runs on GPUs. It follows millions of simulated electrons
and ions and solves the electric and magnetic fields they make at every step. Nothing about the boundary or
the leak is assumed. The coils' own field is put in by formula; the plasma's push on it is computed.

The device is the simplest one that has the leak in question: a stack of ring coils, called a picket fence,
simulated in 2D (everything is assumed the same all the way around the axis). Plasma leaks only through the
ring-shaped gaps between coils. One published simulation (Park and others, 2019) used this shape, which gives
us something to compare with.

Each run feeds hot plasma into the middle, waits for it to push the field out, and keeps feeding to replace
what leaks. Then we read off two numbers:

- **Holding time:** plasma held divided by plasma lost per second, counted in electron crossings of the device.
- **Leak height:** how tall a slot would have to be to pass the same stream of plasma at the inside density.

To change the size we do not make the box bigger. We make the field stronger and the plasma denser to match,
which shrinks every microscopic length together. The device is then larger measured in electron orbits, which
is the size that matters here. "1×" is the size Park used. Finished runs span an eighth of it to twice it, and
four times is still running. Larger sizes need finer meshes: the smallest takes ten minutes on one GPU, 2× takes
ten hours or more.

All of this goes through a small job runner that starts cases on GPU nodes, restarts them from saved states,
boils each one down to a line of numbers on the node, and brings back only that line. The current campaign has
96 finished runs.

## The first answer was wrong

The first size scan gave a clean power law. Then a check of the charge near the metal walls showed that every
run had been leaving charge stuck there, a fault in two settings. Fixing it lowered holding times by 14 to 43%
where the pressure was high. Those exponents are withdrawn and everything below is from reruns.

## Then the repeats disagreed

With the fix in, the middle size (0.5×) gave 71 crossings. The same case with four times the particles gave 52.
Two runs differing only in their random numbers gave 58 and 67.

A result that changes by a third between repeats is not a result. So most of the last two days went into
finding out why:

| Suspect | Test | Verdict |
|---|---|---|
| Time step too long | Half the step | No: 71 and 71 |
| Mesh too coarse | Twice as fine | No: same holding time, same leak |
| Simulated particles bumping into each other | Add real collisions | No: it moves the wrong way |
| Too few particles | 2×, 4×, 16× | Partly: helps, but 16× still splits by seed |
| Smooth the noise away | 1, 4, 16 smoothing passes | No: the answer keeps falling with more smoothing |

## The culprit: a current that should not be there

The simulated stack of coils repeats forever along its axis: what leaves the top comes back in at the bottom.
That is a standard way to model a long row, and it is what Park did. But it lets a current flow along the axis
and close on itself through the repeat. A real, finite row of coils has nowhere for that current to go.

The field snapshots show exactly such a current. It starts at zero and points either way depending on the random
numbers. Most of it is a thin sheet on the plasma's boundary:

![Maps of electron density, the field around the axis and the current along the axis in two runs](images/picket-axial-current-map.png)

The numbers below are the net current. The maps show that a run with no net current still carries layers of
current that cancel; what it lacks is the sheet on the boundary. At the middle size the net current sorts the
repeats:

| Current along the axis ÷ coil current | Holding time (crossings), 15 repeats at 0.5× |
|---|---|
| under 0.15 | 52 to 58 |
| 0.2 to 0.35 | 55 to 57 |
| 0.45 to 0.6 | 60 to 62 |
| 0.65 to 0.8 | 67 to 73 |

Runs with few particles always grow it. Runs with many grow it in some seeds. So "too few particles" was really
"more noise to start the current".

This is a correlation. To show the current is the cause, I replaced the repeat with mirror planes at the end
coils, which cannot pass a net current. At the smallest size, where the current had been several times the
coil current and the plasma looked nothing like the others, the mirrors removed it and the normal sharp
boundary came back. There, the current was the cause.

## The cure had its own disease

The mirrors were meant to become the new standard. They will not, as they stand. In mirrored runs, charge
slowly gathers in the single column of cells on the axis. Run long enough, the electric field there grows
past anything a plasma could hold, the electrons heat up, and the plasma drains. Runs with the repeat show no
such pile-up over the same length.

I had told myself the mirrors passed the same check that caught the wall fault. That check skipped the inner
tenth of the radius, which is where this is. Every run now carries a measure of it, so a spoiled run shows up
in its own line of the table.

So neither treatment of the ends is right yet. The repeat allows a current a real device cannot carry. The
mirrors forbid it and break something on the axis.

## Where the answer stands

Taking the repeating runs that ended with little current:

| Size | Holding time (electron crossings) | If the slit stayed fixed in orbits | If the slit grew with the device | Leak height (electron orbits) |
|---|---|---|---|---|
| 0.25× | 34 | 34 | 34 | 1.2 |
| 0.375× | 45 | 51 | 34 | 1.3 |
| 0.5× | 52 | 68 | 34 | 1.4 |
| 0.75× | 73 | 103 | 34 | 1.7 |
| 1× | 91 | 137 | 34 | 2.1 |

The holding time goes up about as size to the power 0.7. Plugging that scales perfectly would give a power
of 1; a leak that grows with the device would give 0. The leak, counted in electron orbits, widens 1.7 times
while the device grows 4 times. So the answer so far is in between, nearer the hopeful side, and getting less
hopeful toward the large end.

That is not a final exponent. The two largest rows are single runs, none of the rows is free of the current,
and the mirrored runs (now in doubt) read lower, near a power of 0.5.

## Two things that did come out clean

- **How full the bottle is does not matter**, at the three sizes where runs settle. The holding time is the
  same at three fills.
- **Heavier ions help.** Plasma leaves at the speed of its ions through a hole whose size barely depends on
  ion mass. An earlier result of mine, that the leak widens like an ion orbit, was the particle-count problem
  in disguise and is withdrawn. Our ions are 64 electron masses and real deuterium is 3,670, so this is a long
  reach.

## What comes next

1. Find out whether the pile-up on the axis is a mesh artefact (a run on a finer mesh is queued).
2. If it is not, model what a device actually is: a finite row of coils with real end walls. Our two-coil
   runs have end walls and never showed the repeat problem.
3. Redo the size scan in whichever model survives, with enough particles at 1× and 2×.
4. Only then go back to 3D and to charged coils, which is where this started.

## Caveats

- 2D only. Anything that varies around the axis cannot appear.
- Light ions (64 electron masses), hot electrons (100 keV), no collisions in the main runs.
- Our holding times are about half of what Park's paper reports for the same case, and I have not found why.
  The boundary thickness matches theirs.
- WarpX is used with three patches of mine that nobody else has reviewed.
- The tables with case names are in [cusp-results.md](cusp-results.md); the run-by-run log, including my
  mistakes, is in [progress-2026-10-17.md](progress-2026-10-17.md).
