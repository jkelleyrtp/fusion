# A magnetic cage for electrons: what a day of cusp simulations showed

*Work in progress. Numbers are from 3D WarpX runs of a 1 cm device. Several batches are still running, and the caveats at the end matter.*

## Why a cusp

The POPS work ended on one awkward fact. The electron cloud that makes the voltage well was being thrown away: every electron crossed the sphere once and hit the wall. The best well needed 68 A of 10 keV electrons, which is 680 kW through a sphere the size of a marble. Any real device has to keep its electrons.

The oldest idea for doing that is the Polywell. Put six ring-shaped coils on the faces of a cube, each pushing its field toward the centre. The fields cancel in the middle and get strong near the coils, so an electron in the middle sees a magnetic wall in every direction. The wall has holes: one through the middle of each coil, and weaker spots along the edges and corners between coils. Electrons leak through the holes. The whole question is how fast.

There is a hopeful theory about that. If the trapped plasma gets dense enough that its pressure matches the magnetic pressure, it should push the field outward and squeeze the holes down to the width of one electron orbit. That would be thousands of times better than holes one ion orbit wide. One experiment in 2015 saw signs of it. Nobody has simulated it in 3D with real electron mass. That is the target.

## The device we built

In WarpX: six coils, each inside a metal ring held at +10 kV, inside an outer wall. Six small electron emitters sit on the wall facing the coils. The rings pull electrons in, so they arrive at the centre with about 8.5 keV. The electrons' own charge is solved every step, so the well they dig is real, not assumed.

The magnetic field in these first runs is fixed. The plasma feels the coils but cannot push back on them. So these runs can show trapping, but they cannot show the hole-squeezing effect.

Before trusting anything, I followed one electron through the coil field in WarpX and in a separate calculation. After 150 picoseconds they agreed to 84 nanometres.

## Finding 1: the coils keep electrons off the rings

The rings are the obvious place to lose electrons. They are at +10 kV and electrons want to go there.

With the coils off, that is exactly what happens: 0.99 A goes in and 0.98 A lands on the rings. The well is 0.8 kV deep and each electron lasts a few nanoseconds.

With the coils on, the current to the rings reads zero. I first got this by subtraction, then measured it directly with a thin shell around each ring. It is zero at 8, 16 and 32 thousand ampere-turns. The magnetic field wraps around the rings and electrons follow it past them.

That changes the power bill. Electrons landing on a +10 kV ring cost 10 kW per amp. Electrons that go back to where they started cost almost nothing.

## Finding 2: the losses go to the outer wall, and a voltage stops most of them

With the coils on, the electrons that leave go out through the holes to the outer wall. Making the wall more negative turns them around. Going from −300 V to −1 kV cut the wall loss from 0.28 A to 0.07 A at the same moment in the run.

This is the "recirculation" that Polywell designs count on: an electron that leaks out through a hole is pushed back in through the same hole. It works here, at least for electrons that have not picked up much extra energy.

## Finding 3: the well gets nearly as deep as it can

With stronger emitters and the wall at −1.5 kV, after 30 ns:

| Coil current (kA-turns) | Well depth | To rings | To wall |
|---|---|---|---|
| off | 1.8 kV | 2.10 A | 0 |
| 8 | 6.8 kV | 0 | 0.21 A |
| 16 | 7.8 kV | 0 | 0.18 A |
| 32 | 8.6 kV | 0 | 0.09 A |

The deepest possible well with these emitters is 8.8 kV. At 32 kA-turns the device reaches 8.6 kV. So in this small device the trap is no longer what limits the well. The emitters are.

The emitters turned out to be the fussy part. Weak ones (50 eV) choke on their own charge: ask for 3 A or 10 A and only about 1 A gets in. Stronger ones (500 eV) get the current in, but their electrons have enough energy to reach the wall.

## Finding 4: switch the emitters off and the electrons stay

The cleanest test of a trap is to stop feeding it. With coils off, 1% of the electrons are left after 10 ns. At 16 kA-turns, 78% are still there after 25 ns, and the loss rate at the end would take about 760 ns to empty the device, and was still slowing.

An electron crosses the device in about a third of a nanosecond. So these electrons are making thousands of passes.

## The wall we hit: electrons alone cannot reach the interesting regime

The hole-squeezing effect needs the plasma pressure to match the magnetic pressure. Our best run is at about 0.00002 of that. The reason is simple: electrons repel each other, and the well depth caps how many you can hold. To go further you need ions to cancel the charge.

That means gas. Real devices puff in hydrogen or deuterium, and the trapped electrons ionise it. WarpX has a model for this, but it splits the energy between the two outgoing electrons evenly, which is wrong at these energies. I patched it to use the measured split and checked it in a uniform box: the ionisation rate matches theory within 1.5% at 100 eV, 1 keV and 8 keV. Eight gas runs are on the cluster now. No result yet.

## Skipping ahead: let the plasma push on the field

While the gas runs cook, I jumped to the physics that matters most. A second set of runs drops a ready-made neutral plasma ball (10 keV electrons, cooler ions) into the centre of the coils and solves the plasma's own electric and magnetic fields with Maxwell's equations. There are no electrodes or emitters. This asks one question: how does a dense plasma leak out of this field, and does it bend the field?

After one ion crossing time (ions lighter than real, to save time; density 3e19 per m³):

| Coil current (kA-turns) | Ions lost |
|---|---|
| off | 49% |
| 8 | 26% |
| 16 | 22% |
| 32 | 17% |
| 64 | 14% |

Three things stand out, and two are not good news.

**Field strength helps only weakly.** Eight times the coil current roughly halves the loss. The hopeful scaling would give far more.

**The leak is not as narrow as the electron orbit.** The streams leaving through the coil openings are 1.4 to 2.2 mm in half-width across the whole scan, while the electron orbit there shrinks from 1.2 mm to 0.15 mm. In the best-case theory the width follows the electron orbit. Here it does not.

**The plasma does dent the field, a little.** At the highest density the field along one line through the device drops by up to 16%, and switching off the plasma's own magnetic field raises the electron loss from 19.5% to 25%. But the plasma's magnetic energy is under 0.1% of its particle energy. The field is being nudged, not pushed out.

Denser plasma is also held better: electron loss falls from 73% at 1e17 per m³ to 23% at 1e20. At low density the electrons run off alone. At high density they are tied to the ions and can only leave as fast as the ions do.

## What I would not conclude yet

- **One crossing time is a burst, not a leak rate.** The ball expands, cools sharply and sheds its fastest particles. Sixteen longer runs (5 to 10 crossing times) are going now to measure what happens after.
- **The plasma was born inside.** These runs say nothing about getting it there with guns. By our own rule, they are controls, not confinement evidence.
- **The coil field is still fixed.** The plasma's field is solved, but the coils do not respond.
- **The mesh is the weak point in the electrode runs:** going from 128³ to 192³ moves the electron count by +7% or −16% depending on the emitters. The electromagnetic runs are better: 17.3% against 17.4% lost.
- **No run has reached a steady state.** Every electrode run was still filling at 30 ns.
- **The energy balance is open.** Total energy holds to 0.3% until particles start leaving. After that the runs do not record the energy carried out.

## Where this is heading

The picture so far: a small six-coil cage holds electrons well, keeps them off the expensive electrodes, and builds a well to 98% of the available depth. That part of the Polywell story checks out in 3D. The part everything depends on, whether a dense plasma squeezes the holes shut, does not show up yet in the first electromagnetic runs. That is at one crossing time and modest size, so it is an early reading, not a verdict.

Next: the long runs for a real leak rate, the gas runs to see how dense the electrode device can get on its own, and then the two together, with the plasma fed by guns and gas while Maxwell's equations run.
