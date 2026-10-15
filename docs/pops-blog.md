# We tried to revive a forgotten fusion idea in simulation. Here's how far it got.

## The idea

Most fusion schemes fight the same problem: to fuse, ions must be hot and dense, and hot dense
ions leak energy faster than they fuse unless the machine is huge. In the 1990s Todd Rider showed
that the usual escape route, keeping ions in some clever non-thermal state, costs more power than
the fusion gives back.

POPS (the periodically oscillating plasma sphere, from Los Alamos around 2000) is the one scheme
built to slip past that argument. Fill a small sphere with electrons so it becomes a
bowl-shaped voltage well. Drop a cloud of ions in. In a perfect bowl every ion takes the same time
to fall to the centre and come back, however far out it started. So the whole cloud collapses to a
point together, re-expands, and repeats, tens of millions of times a second. The ions stay an
ordinary thermal gas the whole time, so Rider's cost doesn't apply. All the fusion happens in the
brief, dense moment of collapse.

A small experiment confirmed the oscillation in 2005. Then the work stopped, because of one
question nobody could answer: how hard does the cloud really squeeze? The ions repel each other, and
that repulsion grows as they converge. The only simulations were 1D and 2D, and I found none since
2007.

## What we did

We built the device in WarpX, an open-source plasma simulator, in full 3D with real electrons and
real deuterium ions: a 1 cm sphere with a 10 kV well. Each run takes minutes to hours on one
GPU, so we could afford about 400 of them. The first run was a sanity check: with almost no ions,
the cloud's oscillation period matched the textbook formula to nine digits.

The number we track is how many times smaller the cloud gets at collapse (compression), and that
times how full of ions the sphere is. By my rough estimate, useful power needs that product near
1000.

## Step one: the shape of the bowl

Our first electron wells were bad. Fire electrons straight at the centre and you get a well with a
flat floor and steep walls, and the ions arrive at the centre at different times. Compression: about 2×.

Giving the electrons some sideways motion rounds the well out. Mixing two electron populations, one
broad and one narrow, rounds it further. That took compression from 2× to 30×, close to the
ceiling the ions' own temperature sets (about 35×). A cheap shortcut that predicts a well's
quality from an electron-only run let us search 168 candidate wells quickly.

So with very few ions, POPS works about as well as it possibly can.

## Step two: add ions, hit the wall

Then we added more ions, and the result fell apart exactly as the sceptics predicted. At 1 ion per
100 electrons, compression drops to 10×. At 10 per 100, 1.7×. At 30 per 100 the cloud doesn't
collapse at all. Fill × compression sat at about 0.15 however we shaped the well.

## Step three: the trick that helped

The fix proposed in 2005 was to bring extra electrons into the centre along with the ions, to
cancel their charge. Our first attempts did nothing. Then one worked: a slow electron beam from the
wall, with its energy tuned to just above the well's depth. Those electrons arrive at the centre
nearly stopped, linger there, and soak up the ions' charge.

It made a real difference:

| Ions per 100 electrons | Without the beam | With it |
|---|---|---|
| 3 | 4× | 13× |
| 10 | 1.7× | 7.5× |
| 30 | no collapse | 5× |

Fill × compression went from 0.15 to about 1.6, a tenfold gain. It's fussy: the beam energy has
to be right within a few hundred volts, and there's a sharp current threshold below which
nothing happens.

## Step four: trying to push further

Then we tried everything obvious to get past 1.6. More beam current made it worse. A colder beam
changed nothing. A second beam timed to fire during the collapse got its electrons in, but they
just displaced the first beam's, one for one. Starting from a bigger cloud helped slightly. Radio
waves to pump the oscillation, as the original proposal imagined, pump it until ions hit the wall.
And the squeeze fades with each bounce, typically by half over eight collapses.

The electrons at the centre get hot as the cloud collapses, up to several hundred electron-volts,
and hot electrons won't sit still to neutralise the ions. I think that's the heart of the limit, but
my simplest version of that explanation failed its own test, so it's not pinned down.

## Where that leaves it

POPS in this form falls short of a power source by a factor of several hundred. The honest summary:
shaping the well works beautifully, neutralising the ions gives a real tenfold gain, and then
you run into a ceiling that tuning doesn't move. Getting further would need a new idea for keeping
the central electrons cold, not more of the same.

The caveats matter. These are first collapses, mostly on a coarse mesh that we've found doesn't
resolve the very centre of the cloud; a finer-mesh study is running. The electrons come from an
idealised wall, not a real gun. The "1000" target is my own rough estimate. The ion counts are
quoted against an ideal electron cloud, and the real ratios are about 1.65× higher.

Still, as far as I can find, these are the first 3D numbers anyone has for this question. It cost
a day of GPU time to get an answer that the original team, working in 2007, couldn't reach.
