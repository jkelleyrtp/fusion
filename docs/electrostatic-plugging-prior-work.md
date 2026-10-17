# Prior work on charged cages and electrostatic plugging of cusp leaks

What has been published on putting voltage on the coils or electrodes of a cusp, and on plugging cusp leaks with
electric fields. It checks four statements made from memory after the 3D six-coil run where floating rings
charged positive and the electron holding time rose about 10% (2.02 ns with rings, 1.84 ns without; pressure
ratio about 0.3 at the edge). Searched and read on 2026-10-17. Each source says what was read: **full text**,
**part of the full text**, **abstract**, or **title only**.

## Answer first

Making the cage positive is not new. Bussard put high positive voltage on the coil casings in the 2000s, and his
company dropped the idea in 2012 after WB-8. Plugging cusp leaks with charged electrodes has been studied since
the late 1960s in Japan, the UK, the US and the USSR. Dolan reviewed it in 1977 and again in 1994. Measured gains
are modest: density or decay time up by a factor of 2 to 3 in low-pressure laboratory plasmas. The best-known
cost is electron current to the positive electrodes, which the power supply has to pay for at the full electrode
voltage. Our floating rings have a close published match: Hershkowitz, Smith and Kozima (1979) measured
positive "potential islands" forming by themselves in front of the conductors of a picket fence, and called it
electrostatic self-plugging. I found no self-consistent 3D kinetic simulation of a six-coil cusp with electrodes
held at set voltages near pressure ratio 1. That is a search result, not proof that none exists.

## Terms

- **Electrostatic plugging:** using an electric field to push back the particles that would otherwise escape
  through a cusp. A positive electrode at the leak pushes ions back. Electrons are held in by the magnetic field.
- **Bias:** a voltage applied to a metal part from a power supply, measured against the grounded vacuum chamber.
  A **floating** part has no supply connected. It charges up from whatever particles land on it.
- **Magnetically insulated grid (MIG), "MaGrid":** Bussard's name for coil casings held at high voltage while
  their own magnetic field keeps plasma off the metal.
- **Hybrid orbit:** the geometric mean of the electron and ion orbit radii, \(\sqrt{r_e r_i}\). At a fixed
  temperature it grows as ion mass^0.25. The ion orbit grows as ion mass^0.5.
- **Te:** electron temperature, in volts here, so that it can be compared with an electrode voltage.

## The four statements

| # | Statement | Verdict | Basis |
|---|---|---|---|
| 1 | A positively biased coil cage is the original Polywell design (Bussard ran the coils at high positive voltage to draw electrons in) | **Partly.** Bussard did run the coils positive, but in later machines, not in the original design | See below |
| 2 | Electrostatic plugging goes back to Soviet work in the 1960s–70s (Lavrentiev's electromagnetic traps), reviewed by Dolan in 1994 | **Partly.** The Dolan review is real and covers this. Lavrent'ev's traps are real, but I could not read his papers, and the field was not only Soviet: Japanese (1968), UK (1969) and US (1970s) work came at the same time | See below |
| 3 | Electrons that reach a positive electrode are lost at high energy, so power balance can get worse even if holding time rises | **Confirmed** as a recognised cost, in the Polywell literature and in IEC critiques. I found no published number for the net trade-off in a high-pressure cusp | See below |
| 4 | No published self-consistent 3D kinetic simulation of a six-coil cusp with electrodes at set voltages near pressure ratio 1 | **Could not find one.** The closest are a 1980 2D axisymmetric electrostatic particle code with electrodes in a spindle cusp, single-particle orbit studies, and Park et al. 2025 (3D at high pressure, but with no electrode bias and equal masses) | See below |

### 1. Positive coil cage and the original Polywell

- **Original design, 1985 (Bussard, US patent 4,826,646, filed 1985-10-29; [Google Patents](https://patents.google.com/patent/US4826646A/en);
  full text fetched and keyword-searched, not read end to end).** The potential well comes from injected
  electrons. Each electron injector has an emitter and an accelerating grid "held at an electric potential +V
  above that of the emitter... thus producing a central potential well depth of −V". High positive potential is
  proposed only for the *outer walls*, to recover energy from escaping fusion products. My keyword search found
  no positive bias on the coils.
- **Bussard 1991, Fusion Technol. 19, 273 ([doi](https://doi.org/10.13182/fst91-a29364); abstract).** Describes
  the concept as magnetic fields that "contain energetic electrons that are injected to form a negative
  potential well". The abstract says nothing about coil bias.
- **Krall 1992, Fusion Technol. 22, 42 ([doi](https://doi.org/10.13182/fst92-a30052); abstract).** The same
  description: electrons held magnetically, ions held by the well. Nothing on coil bias.
- **Bussard, US patent application 2008/0187086 A1 (continuation-in-part of an application filed 2006-09-27;
  [Google Patents](https://patents.google.com/patent/US20080187086A1/en); full text fetched and
  keyword-searched).** This is where coil bias appears: the machine sits on "insulated supports... through
  which power is supplied to the machine to keep it at high positive potential", and "the machine coils may be
  at high positive potential and the emitters at ground potential". It reports WB-4 at "12 kV drive" and WB-6
  at "10 kV well depth (with a 12.5 kV drive)". It also states that "cross-field transport constitutes an
  unavoidable loss to coil structure". It cites Bussard's 57th IAC paper of 2006
  ([doi](https://doi.org/10.2514/6.iac-06-d2.8.05); not read).
- **Park, Krall, Lapenta, Ono, "Polywell Revisited", J. Fusion Energy 45 (2026), [arXiv:2508.06761](https://arxiv.org/abs/2508.06761)
  (part of the full text: sections 1–2 and the mass-ratio discussion).** Calls coil bias a *supplementary*
  mechanism ("M6"): "As an alternative to electron beam injectors, Bussard proposed forming the potential well
  by charging the magnet coils... high positive voltages are applied to the metal casing of the cusp coils while
  electron emitters at ground potential provide the excess negative charge... the positively biased grids may
  provide an attractive force to facilitate recirculation of escaping electrons". EMC2 worked on it from 1992
  to 2012 and then suspended it (results under statement 3).

So: "Bussard ran the coils at high positive voltage to draw electrons in" is confirmed for the WB series of the
2000s (WB-6 to WB-8). "Original design" is wrong. In the 1985 patent and the 1991/1992 papers, electron guns
make the well, and the people who ran the programme describe coil bias as an add-on they later dropped.

### 2. Origins of electrostatic plugging, and the Dolan review

- **Dolan 1994, "Magnetic electrostatic plasma confinement", Plasma Phys. Control. Fusion 36, 1539–1593
  ([doi](https://doi.org/10.1088/0741-3335/36/10/001); abstract only, and the copy I could get is cut off part way).**
  Exists as described. The abstract says the field has been studied "for four decades", that "electrostatic
  plugging of magnetic cusps evolved to a similar configuration" to magnetically shielded IEC grids, and that
  early experiments used spindle cusps, "which are poor for plasma confinement", and later ones multipole or
  ring cusps. I could not read the body, so I cannot say what it reports about Lavrent'ev.
- **Dolan 1977, "Review of electrostatic plugging", OSTI report 7297331 ([doi](https://doi.org/10.2172/7297331);
  abstract; the full text is on osti.gov, which is not reachable from this machine).** An earlier review by the
  same author. Numbers under Results.
- **Lavrent'ev.** Verified to exist (titles and citations only): O. A. Lavrent'ev, Ukr. Fiz. Zh. 8, 440 (1963),
  cited as an early IEC scheme by Hedditch et al. 2015; Lavrent'ev, "Electrostatic and electromagnetic
  high-temperature plasma traps", Ann. N.Y. Acad. Sci. 251, 152 (1975)
  ([doi](https://doi.org/10.1111/j.1749-6632.1975.tb00089.x); no abstract available); Georgievskii, Ziser,
  Lavrent'ev, Nozdrachev, "Investigation and test of the magnetic system of the Jupiter-1M electromagnetic
  trap", Sov. At. Energy 36, 408 (1974) ([doi](https://doi.org/10.1007/bf01229366); title only). I did not
  read any of them. What these traps contained and what they measured is **not verified here**.
- **Not only Soviet.** Over the same years: Sugisaki 1968 (Japan) on a cusp combined with an electrostatic
  field; Ware and Faulkner 1969 (Nucl. Fusion) on the theory of electrostatic plugging of cusps and mirrors;
  and US experiments and reactor studies by Dolan and co-workers from 1976 to 1977. Details are in the table.

### 3. The cost: electron current to positive electrodes

- **Park et al. 2025/2026 (part of the full text).** The only measured numbers I found from a six-coil cage.
  WB-7 drew about 40 A of grid current at about 13 kV (about 0.5 MW). WB-8, with full magnetic insulation, drew
  about 6 A at about 13 kV (about 80 kW) at 10 to 20 times the plasma density. After the plasma source was
  switched off, 130 to 200 kW into the biased casings "could not sustain even modestly dense plasma"
  (0.1–1 × 10^19 m^-3). The density decayed with a time constant of about 180 µs for every bias from 0.7 to
  12 kV. The emissive probe showed 2.2 kV at a coil centre with 7.2 kV on the casings and no plasma. Once
  plasma was present the plasma potential fell to near ground. Their interpretation is that the bias was
  screened within a thin layer next to the metal ("magnetically modified Debye shielding"). So in this device
  bias cost power and did not lengthen confinement at all.
- **Bussard 2008 patent application (full text, keyword-searched).** "Electron surface losses through the
  confining magnetic field will limit the power balance performance (i.e., the system power gain) of such
  devices."
- **Rider 1995, Phys. Plasmas 2, 1853 ([doi](https://doi.org/10.1063/1.871273); abstract).** Even with a
  polyhedral cusp and "exceedingly optimistic assumptions", electron losses "prove to be intolerable for all
  fuels except perhaps DT". This is about cusp losses in general, not electrodes specifically.
- **Hedditch, Bowden-Reid, Khachan 2015, Phys. Plasmas 22, 102705 ([arXiv:1510.01788](https://arxiv.org/abs/1510.01788);
  introduction read).** On schemes that put a positive bias on an inner grid: "electron loss to the grid limits
  the attainable efficiency". Their own proposal biases the coils *negative* (−100 kV in their example), so
  that the magnetic field shields the grid from ions.
- **Hershkowitz, Hendricks, Carpenter 1982, J. Appl. Phys. 53, 4105 ([doi](https://doi.org/10.1063/1.331277);
  abstract).** With positively biased electrodes at the line cusps of a multidipole source, the main electron
  loss at high bias is diffusion across the cusp field onto the electrodes.

The physics behind "lost at high energy" (an electron arriving at an electrode at +V gains eV from the
potential drop, and the supply delivers current × V) is textbook. The sources above confirm that it is the
recognised cost and give one measured scale (tens to hundreds of kW for a 40 cm cage at 13 kV). None of them
gives a net energy balance for plugging at high pressure.

### 4. Is there a 3D kinetic simulation with set electrode voltages at high pressure?

What I found that comes closest:

| Work | What it is | Why it is not the missing study |
|---|---|---|
| Shoucri, Matte, Gregory 1980, Can. J. Phys. 58, 1216 ([doi](https://doi.org/10.1139/p80-161); abstract) | Particle code, axisymmetric (2D), electrostatic only, actual walls and electrodes of a plugged spindle-cusp experiment | 2D, no plasma current or field changes (so no high pressure), spindle cusp. Finds electrons "extremely well confined" and ions leaking slowly through the point cusps "due to electron shielding of the electrode potential" |
| Hedlof and Ordonez 2017, AIP Adv. 7 ([doi](https://doi.org/10.1063/1.5008673); abstract) | Single-particle Monte Carlo orbits, planar row of cusps with plugging electrodes | No plasma, no self-consistency |
| Gummersall et al. 2013; Carr et al. 2011 (abstracts) | Single-electron orbits in a six-coil cage | Zero pressure, no electrodes |
| Park et al. 2025/2026 (part of the full text) | 3D implicit particle code (ECsim), six-coil cage at high pressure; 2D picket fence with an electron beam | No electrode bias. 3D run uses equal electron and ion masses |
| Carr and Khachan 2013; Cornish et al. 2014 (abstracts) | *Experiments* in a small Sydney Polywell with a "Polywell bias" scan | Low pressure, measurements not simulation |

Searches: Crossref, OpenAlex and the arXiv API, for combinations of polywell, magnetic cusp, particle-in-cell,
kinetic simulation, biased coils/electrodes and electrostatic plugging. Google Scholar, OSTI and IOP full text
were not reachable from this machine, and I could not read the body of the Dolan 1994 review. A thesis or
conference paper could have escaped this search.

## Key papers and numbers

| Who, year | Device or simulation | What was measured | Number | Read |
|---|---|---|---|---|
| Sugisaki 1968, Jpn. J. Appl. Phys. 7, 1387 ([doi](https://doi.org/10.1143/jjap.7.1387)) | Cusp plus applied electric field, experiment and theory | Light decay with and without field | "Decayed more slowly" with the right field strength; no number in the abstract | Abstract |
| Ware, Faulkner 1969, Nucl. Fusion 9, 353 ([doi](https://doi.org/10.1088/0029-5515/9/4/009)) | Theory | Leak width achievable with electrostatic fields plus beam injection | Cusps "with a width of 4 ρe" (4 electron orbits); stability of the electron sheath in the leak left open | Abstract |
| Hayward, Dolan 1977, Phys. Fluids 20, 646 ([doi](https://doi.org/10.1063/1.861923)) | Plugged spindle cusp, R = 0.16 m, 0.3–0.5 T, 1 keV electron beam | Density and confinement time | n ≈ 2 × 10^16 m^-3, τ ≈ 50 µs | Abstract |
| Dolan 1977 review ([doi](https://doi.org/10.2172/7297331)) | Survey of plugged-cusp experiments | Best plasma reported | n = 5 × 10^12 cm^-3, Ti = 1 keV, τ = 5 ms, at about 1 T and about 10 kV applied | Abstract |
| Blondin, Dolan 1976, J. Appl. Phys. 47, 2903 ([doi](https://doi.org/10.1063/1.323069)); Dolan 1976 design study ([doi](https://doi.org/10.2172/7132575)) | Reactor estimates | Voltage needed for gain | Q favourable above 250 kV; Q ≈ 5 at 8 T, 300 kV, *assuming* the electron layer at the anodes is 2 electron orbits wide | Abstracts |
| Hershkowitz, Smith, Kozima 1979, Phys. Fluids 22, 122 ([doi](https://doi.org/10.1063/1.862450)) | Picket fence, no applied bias | Plasma potential near the conductors | Positive potential "islands" in front of the conductors confine ions ("self-plugging"); channel width of order the hybrid leak width | Abstract |
| Shoucri et al. 1980 ([doi](https://doi.org/10.1139/p80-161)) | 2D electrostatic particle code, plugged spindle cusp | Where particles leak | Electrons well held; electrode potential screened by electrons, ions leak via point cusps | Abstract |
| Hershkowitz, Hendricks, Carpenter 1982 ([doi](https://doi.org/10.1063/1.331277)) | Multidipole source with positive electrodes beside each line cusp | Density against bias | About ×2, and the plasma potential follows the electrode; the gain shrinks at higher neutral pressure or narrower electrode gap | Abstract |
| Fujita, Ohnuma, Adachi 1983, IEEE TPS 11, 53 ([doi](https://doi.org/10.1109/tps.1983.4316220)) | Cusp end of a surface-magnet device, barrier made by a second plasma | Afterglow decay time | 2 to 3 times longer with the barrier | Abstract |
| Couture, Stansfield 1983, Plasma Phys. 25, 1001 ([doi](https://doi.org/10.1088/0032-1028/25/9/004)) | Double-cusp "electromagnetic trap" with electrodes | Where the ion barrier forms | Potential well forms, but "a significant ion-confining barrier is not formed in the electrode region" | Abstract |
| Park et al. 2025/2026 ([arXiv:2508.06761](https://arxiv.org/abs/2508.06761)) | WB-8 six-coil cage, casings biased 0.7–13.2 kV, 2 kG | Grid current, density decay, plasma potential | About 6 A at 13 kV; decay time about 180 µs at every bias; plasma potential falls to near ground once plasma is present | Part of the full text |

None of these gives the electrode voltage *relative to Te* in the abstract, which is what you asked for. The only
case where both are given is the reactor study: 300 kV against a fusion plasma of tens of keV, i.e. about
10 Te. That is my arithmetic, not a number from the paper.

## Leak width against ion mass

| Who, year | Pressure | Result | Read |
|---|---|---|---|
| Leung, Hershkowitz, MacKenzie 1976, Phys. Fluids 19, 1045 ([doi](https://doi.org/10.1063/1.861575)) | Low, multidipole, He/Ar/Xe | Plasma leak half-width = 2 hybrid orbits; fast primary electrons leak at 1 electron orbit | Abstract |
| Christensen, Hershkowitz, Leung 1977, IEEE TPS 5, 23 ([doi](https://doi.org/10.1109/tps.1977.4316999)) | Low, permanent-magnet line cusps | Leak ∝ ion mass^0.25, "consistent with hybrid... but not with ion gyroradius" | Abstract |
| Knorr, Merlino 1984, Plasma Phys. Control. Fusion 26, 433 ([doi](https://doi.org/10.1088/0741-3335/26/2/004)) | Low, theory | Ion-orbit width without fast electrons, hybrid width with them | Abstract |
| Bosch, Merlino 1986, Phys. Fluids 29, 1998 ([doi](https://doi.org/10.1063/1.865628)) | Low, spindle cusp | Between hybrid and ion orbit, set by neutral collisions | Abstract |
| Park et al. 2019 / 2025 | High, picket-fence simulation, mass ratio set by changing the *electron* mass | Loss rate ∝ (mass ratio)^-0.28, read as hybrid scaling; Park et al. *hypothesise* 1.5 hybrid orbits for deuterium holes in a six-coil cage and say this needs testing | Part of the full text (2025) |
| Pechacek et al. 1980; Kitsunezaki et al. 1974 | High, pellet-filled cusps | One ion orbit, against "much smaller than" one ion orbit | Abstracts (already in [prior-work.md](prior-work.md)) |

How ours compares: our gap stream goes as ion mass^0.46 (0.040, 0.066, 0.146 mm at 16, 64, 256 electron masses,
with the electron mass fixed). That is close to ion-orbit scaling (0.5) and far from the low-pressure hybrid
result (0.25). Our holding time goes as mass^0.29 (49, 71, 110 crossings). That is numerically close to Park's
0.28, but Park changes the electron mass and measures loss rate, so the two exponents are not the same quantity,
and the match may be coincidence. I found no published high-pressure measurement of leak *width* against ion
mass. Our data would be new, but they are three masses at one size.

## What is and is not published

**Published:**
- Positive coil bias in a six-coil cage: tried in experiments (WB-6 to WB-8), and suspended in 2012 because the
  bias was screened close to the casings and did not sustain plasma.
- Plugging cusp leaks with biased electrodes, at low pressure: factor 2 to 3 gains in density or decay time,
  plus reactor studies that assume a 2-electron-orbit layer.
- Positive charge building up by itself on picket-fence conductors and plugging ions (1979).
- At high pressure, a picket-fence simulation mass scan and a 3D six-coil run, both without electrodes.

**Not found:**
- Any simulation that solves for the plasma and its fields together (self-consistent), with electrodes at set
  voltages, at pressure ratio near 1, in 2D or 3D.
- Any scan of leak width or holding time against electrode voltage in units of Te, at any pressure.
- A net energy account (electrode current × voltage, against the confinement gained) for plugging a
  high-pressure cusp.
- High-pressure leak width against ion mass (our 0.46 has no published counterpart).

## Is the 10% from charged rings a discovery?

No, not as stated. Positive charge on conductors next to a cusp plugging ions is in the 1979 paper, and making
the cage positive on purpose is Bussard's MaGrid. It is also a single pair of runs at pressure ratio about 0.3,
with no seed or resolution repeat of the difference. Our rings charged positive because they collected *more ions than
electrons*. The 1979 abstract does not say what charges the conductors in that experiment, so I cannot say
whether the mechanism is the same.

## What a new simulation would have to show to be worth writing up

1. **Electrodes at set voltages, not floating rings.** A scan of voltage in units of Te (for example 0, 1, 3 and
   10 Te), with the electrode current recorded.
2. **Pressure ratio near 1.** At low pressure the result would repeat the 1970s–80s experiments.
3. **The potential reaches the leak.** Park et al. saw the bias screened in a thin layer next to the metal once
   plasma was present. A simulation has to show the potential where the plasma leaves, not just on the metal.
4. **Leak width in electron orbits against device size, with and without bias.** Does bias keep the leak at a
   fixed number of electron orbits (the 4 ρe of Ware and Faulkner), or does it only change the prefactor?
5. **Energy account.** Electrode current × voltage, plus the gun power, against the holding time gained. A
   longer holding time that costs more power than it saves is the known failure.
6. **Ion mass.** At least three masses, to see whether bias moves the scaling from ion-orbit-like (our 0.46)
   toward hybrid or electron scaling.
7. **Usual convergence checks.** Particle number, mesh, time step, seed, and the wall fix. The particle-count
   problem in [cusp-results.md](cusp-results.md) section 3 already moves holding times by 26%, more than the
   10% effect here.

A 3D six-coil run that passed points 1 to 5 would, as far as this search found, be the first of its kind. A 2D
picket fence with biased electrodes in the gaps would be cheaper and would already go beyond what is published
(the 1980 simulation was electrostatic and at low pressure).

## Not checked

- The body of Dolan 1994 and Dolan 1977, and every Lavrent'ev paper: not readable from this machine.
- Bussard's 2006 IAC paper and the WB-6/WB-7 reports: not read. WB-6 numbers here come from the 2008 patent
  application.
- The full text of every paper marked "abstract" above. Numbers in the abstracts were not checked against the
  papers' tables.
