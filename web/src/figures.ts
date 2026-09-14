const DOCS = "https://github.com/jkelleyrtp/fusion/blob/devin/1789237491-pic-research/docs";

interface Figure { image: string; title: string }
interface Study { id: string; title: string; summary: string; doc: string; figures: Figure[] }

const pair = (name: string, what: string): Figure[] => [
  { image: `pic-${name}-evolution.png`, title: `${what}: time histories` },
  { image: `pic-${name}-fields.png`, title: `${what}: final potential and density` },
];

const studies: Study[] = [
  {
    id: "six-coil-tracks", title: "Settled-electron paths (six-coil)",
    summary: "64 electrons injected after 500 ns in eight 300 ns runs (0 V, second seed, −1 kV, +5 kV, +10 kV, 3 A, +5 kV with a 2 keV gun, 60 kA-turn), sampled every 2 ps. 61–87% of wall exits leave along a face-axis point cusp; each electron passes through the core about once (42% re-enter at +5 kV). At 3 A, 58% return into the gun barrel. Phase-space slices, not whole-population lifetimes.",
    doc: "six-coil-design.md", figures: [
      { image: "pic-six-coil-tracks-paths.png", title: "Paths of the 4 most-entering electrons per case (y–z projection)" },
      { image: "pic-six-coil-tracks-statistics.png", title: "Survival, core entries and exit channels" },
    ],
  },
  {
    id: "six-coil-ions", title: "Coupled electrons + H2+ ions (six-coil)",
    summary: "Six-coil trap, 0 V casings, H2 at 1e-3 Pa (and 1e-2 Pa), ionization, ion space charge and charge exchange; 400 µs, all 8 cases complete. Ions cancel the well in 148 µs at 1e-3 Pa and 14.6 µs at 1e-2 Pa, the same clock as the two-coil field; the centre rises from −2.6 kV to within ~10 V of ground. 300 mA neutralizes in the same 148 µs as 1 A: pressure sets the time, current does not.",
    doc: "ion-pic-design.md", figures: pair("six-coil-ions", "Six-coil coupled ions"),
  },
  {
    id: "six-coil-feed-fine", title: "High electron feed: 10–100 A with H2 ions (six-coil)",
    summary: "10 keV gun at 10–100 A, H2 at 1e-3 Pa (320 µs) and 1e-2 Pa (32 µs, transient), all 8 cases complete. At 1e-3 Pa, 10 A levels off at 0.76 neutralization with the centre at −2.7 kV and ~0.8 keV core ions; 30 A holds −5.7 kV but is still settling. 1 A at the same pressure lost its well. 100 A chokes: a −15 to −23 kV virtual cathode forms at the gun mouth and 99.8% of lost ions fall into the gun barrel. Coils are a weak knob: 60 kA-turn at 30 A (1e-2 Pa) is no deeper than 30 kA-turn. One seed, no cycle-duration control yet.",
    doc: "ion-pic-design.md", figures: pair("six-coil-feed-fine", "High feed"),
  },
  {
    id: "six-coil-sustain", title: "High-feed controls: current threshold, seed, D2, 1e-4 Pa, cycle length (six-coil)",
    summary: "10 keV gun, 30 kA-turn, H2 at 1e-3 Pa unless noted, all 8 cases complete. 10 A holds 0.75 neutralization and −2.9 kV for 640 µs; the seed repeat agrees within 2%. 1 A and 3 A lose the well. 30 A relaxes between −3.8 and −6.6 kV. 1e-4 Pa settles at −5.5 kV with 0.16 neutralization and 1.3 keV core ions over 3.2 ms. D2 is still rising. A 5 µs ion cycle gives 0.88 and −1.5 kV at 320 µs, so the 10 µs splitting is not converged and every 1e-3 Pa neutralization is provisional until the splitting study finishes.",
    doc: "ion-pic-design.md", figures: pair("six-coil-sustain", "High-feed controls"),
  },
  {
    id: "six-coil-gun-limit", title: "Single-gun limit: 30–300 A at 10–20 keV (six-coil)",
    summary: "One external gun, H2 at 1e-3 Pa, 320 µs, all 8 cases complete. The choke follows gun perveance I/V^1.5: 100 A at 10 keV and 300 A at 20 keV (~1e-4 A/V^1.5) both choke, with the centre within 270 V of ground and 99.8% of lost ions returning into the gun. 100 A at 20 keV (3.5e-5) reaches the centre: −13.8 kV, neutralization 0.50, 2.5 keV core ions. 30° divergence and +5 kV casings do not unchoke the 10 keV gun. 30 A at 20 keV is still drifting (seed repeat within 3%).",
    doc: "ion-pic-design.md", figures: pair("six-coil-gun-limit", "Single-gun limit"),
  },
  {
    id: "six-coil-multi-gun", title: "Multiple external guns: 30–1000 A split over 2, 3 or 6 guns (six-coil)",
    summary: "H2 at 1e-3 Pa, 320 µs, all 8 cases complete. Sharing the current removes the single-gun choke: at 100 A and 10 keV one gun leaves the centre at −0.1 kV, two guns give −8.2 kV, three −9.0 kV and six −10.1 kV (second seed within 0.4%). Two guns stay choked for ~60 µs and 60% of lost ions still return into the barrels. Six guns fill the coil interior with a broad well. Depth follows gun energy: six guns give −8.1 to −10.6 kV at 30–300 A and 10 keV, −18.4 kV at 300 A and −23.3 kV at 1000 A with 20 keV. Neutralization 0.60–0.79. Only the three-gun case has settled, and all use 10 µs ion cycles, so results are provisional until the splitting study finishes.",
    doc: "multi-gun-design.md", figures: pair("six-coil-multi-gun", "Multi-gun"),
  },
  {
    id: "six-coil-gas", title: "D2 fuel delivery: uniform fill, inlets and puffs (six-coil)",
    summary: "1 A 5 keV gun, D2 and D2+ ions, 400 µs, all 8 cases complete. A steady inlet with a normal pump matches uniform gas within 0.1%. Pressure sets the neutralization clock linearly: 148 µs at 1e-3 Pa, 1.36 ms at 1e-4 Pa, ~7.9 ms at 1e-5 Pa, where the well holds −3.0 kV and core ions carry ~770 eV. A puff at the same background speeds ionization by 19–61% because the plume overlaps the electrons; ions are still born deep in the well.",
    doc: "ion-pic-design.md", figures: pair("six-coil-gas", "D2 fuel delivery"),
  },
  {
    id: "six-coil-ion-gun", title: "D2+ ion gun at a cusp (six-coil)",
    summary: "1 A 5 keV electron gun, D2 at 1e-5 Pa, D2+ gun at the top point cusp, 400 µs, all 8 cases complete. At 10 mA and above a 10–100 eV gun chokes: its space charge builds a +0.7 to +1.6 kV hill at the mouth and 96–99% of gun ions leave back through the top. Unchoked beams (1 mA at 100 eV, 10 mA at 1 keV) fall through the −3 kV well, reach ~1.3 keV in the core and mostly leave through the opposite face; 1–3% are retained. Core neutralization stays at the no-gun 0.10–0.14.",
    doc: "ion-pic-design.md", figures: pair("six-coil-ion-gun", "D2+ ion gun"),
  },
  {
    id: "six-coil-deuteron", title: "Atomic D+ ion gun at a cusp (six-coil)",
    summary: "Same setup as the D2+ gun, 400 µs, 7 of 8 cases complete (100 mA failed the ion-step check and is rerun at 0.2 ns). A 10 mA, 100 eV D+ beam builds a +425 V mouth hill (D2+: +798 V) and still chokes: 97% leave through the top. At 1 keV D+ transits, 62% out the opposite face, 0.87% retained. +5 kV casings remove the well. 60 kA-turn deepens the centre 19% but leaves the mouth hill and 0.29% retention unchanged. Changing species does not trap gun ions in a static well.",
    doc: "ion-pic-design.md", figures: pair("six-coil-deuteron", "D+ ion gun"),
  },
  {
    id: "six-coil-deuteron-fine", title: "D+ ion gun at 30–300 mA, 0.2 ns ion steps (six-coil)",
    summary: "Same setup as the D+ gun study, 400 µs, all 8 cases complete. 30–300 mA builds a +0.56 to +1.05 kV mouth hill and 93–99.7% of gun ions leave back through the top, even at 1 keV. D+ alive / injected is 0.02–0.14%; core ions (~700 eV) and core neutralization (0.10) match the no-gun case. Seed repeat and a 0.1 ns ion-step control agree within seed noise.",
    doc: "ion-pic-design.md", figures: pair("six-coil-deuteron-fine", "D+ gun at 0.2 ns"),
  },
  {
    id: "six-coil-pulse", title: "Pulsed electron gun with D2 ions (six-coil)",
    summary: "1 A 5 keV gun switched on and off in 10 µs cycles, D2 at 1e-4 Pa, 600 µs, all 8 cases complete. Gas ions drain out while the gun is off and the trap reaches a periodic state: 150 µs on / 50 off averages −2.0 kV at the centre (−2.6 kV while on) with 510 eV core ions, against −1.4 kV and still-rising neutralization for continuous injection. 150 / 20 gives −2.3 kV. At 1e-3 Pa pulsing leaves 0.67 neutralization. Seed repeat within 1%; the period-end ion inventory changes 2.5× with the switch-on settle time, so only potentials are quoted.",
    doc: "ion-pic-design.md", figures: pair("six-coil-pulse", "Pulsed gun"),
  },
  {
    id: "six-coil-capture", title: "Phase-gated D+ capture (six-coil)",
    summary: "1 A electron gun pulsed 10 µs on / 2 off, 10 mA 1 keV D+ gun gated to the off, on or both phases, D2 at 1e-5 Pa, 48 µs, all 8 cases complete. A continuous well binds no gun ions. Injecting while the well is down leaves 1.6 nC (2% of gun charge) energetically bound when it rebuilds, and the inventory is re-bound every period; seed and ion-step repeats agree within 2% and 9%. Captured charge is ~1% of the trapped electrons and still growing.",
    doc: "ion-pic-design.md", figures: [
      ...pair("six-coil-capture", "Phase-gated capture"),
      { image: "pic-six-coil-capture-bound.png", title: "Alive and bound D+ per injected gun charge" },
    ],
  },
  {
    id: "six-coil-bias", title: "Six-coil casing (magrid) bias sweep",
    summary: "1 µs, 1 A, 5 keV gun, casings at +1 to +10 kV, with a second seed, a 1 mA control, 3 A and a 2 keV gun at +5 kV. Electrons only; imposed vacuum field. Positive casings raise repeated core entries from 26% to 37%, but the ion escape barrier (lowest path from the centre to the grounded walls) falls from 3.1 kV at 0 V to 338 V at +5 kV and 96 V at +10 kV.",
    doc: "six-coil-design.md", figures: pair("six-coil-bias", "Bias sweep"),
  },
  {
    id: "six-coil-long", title: "Six-coil saturation (1 µs)",
    summary: "Trap fills by ~450 ns. 1 A gives about −3.1 kV at the centre; 3 A is choked by gun-mouth space charge; 60 kA-turn was still drifting.",
    doc: "six-coil-design.md", figures: pair("six-coil-long", "Saturation"),
  },
  {
    id: "six-coil", title: "Six-coil geometry (first runs)",
    summary: "Six coils on cube faces with grounded casings; central field cancels. Short windows used to set up the long study.",
    doc: "six-coil-design.md", figures: pair("six-coil", "Six-coil"),
  },
  {
    id: "ions", title: "Coupled electrons + H2+ ions (two-coil)",
    summary: "H2 gas, electron-impact ionization, ion space charge and charge exchange. Ions cancel the electron well within 147 µs at 1e-3 Pa.",
    doc: "ion-pic-design.md", figures: pair("ions", "Coupled ions"),
  },
  {
    id: "test-ions", title: "Test ions in the settled electron well",
    summary: "Frozen-field test ions (no ion space charge): births weighted by electron density versus uniform births.",
    doc: "pic-window-evidence.md", figures: [
      { image: "pic-test-ions-density.png", title: "Density-weighted births" },
      { image: "pic-test-ions-uniform.png", title: "Uniform births" },
    ],
  },
  {
    id: "casing", title: "Coil casings inside the domain",
    summary: "Grounded housings let the box widen past the coils; box size is settled to ~1%. Casing voltage is a real design knob.",
    doc: "pic-window-evidence.md", figures: pair("casing", "Casings"),
  },
  {
    id: "gun", title: "Grounded gun barrel",
    summary: "Replaces the grounded inlet so moving the bottom wall no longer shifts the beam energy.",
    doc: "pic-window-evidence.md", figures: pair("gun", "Gun barrel"),
  },
  {
    id: "domain", title: "Box-size study",
    summary: "Top wall has <1% effect; side-wall distance changed the core potential by ~17% before casings were added.",
    doc: "pic-window-evidence.md", figures: pair("domain", "Box size"),
  },
  {
    id: "window", title: "Long-window runs",
    summary: "Longer physical-time runs of the transient PIC model to check whether the electron population settles.",
    doc: "pic-window-evidence.md", figures: pair("window", "Long window"),
  },
  {
    id: "refinement", title: "Mesh, timestep and particle refinement",
    summary: "Mesh resolution materially changes losses; timestep sensitivity is much smaller.",
    doc: "pic-refinement-evidence.md", figures: pair("refinement", "Refinement"),
  },
  {
    id: "startup", title: "Physical-time startup",
    summary: "First transient PIC campaign: the strongest negative potential forms near the inlet, not the centre.",
    doc: "pic-startup-evidence.md", figures: pair("startup", "Startup"),
  },
];

export function renderFigures(host: HTMLElement): void {
  host.innerHTML = `<div class="page-title"><div><h1>PIC results</h1>
      <p>Time-dependent electrostatic PIC · newest first · click a figure for full size</p></div><span>${studies.length} studies</span></div>
    <nav class="figure-index">${studies.map(s => `<a href="#pic" data-target="figures-${s.id}">${s.title}</a>`).join("")}</nav>
    ${studies.map(s => `<section class="figure-study" id="figures-${s.id}"><h2>${s.title}</h2>
      <p>${s.summary} <a href="${DOCS}/${s.doc}" target="_blank" rel="noreferrer">Write-up →</a></p>
      <div class="figure-grid">${s.figures.map(f => `<figure><a href="figures/${f.image}" target="_blank" rel="noreferrer">
        <img src="figures/${f.image}" alt="${f.title}" loading="lazy"/></a><figcaption>${f.title}</figcaption></figure>`).join("")}</div>
    </section>`).join("")}`;
  for (const link of host.querySelectorAll<HTMLAnchorElement>(".figure-index a")) {
    link.onclick = event => {
      event.preventDefault();
      document.getElementById(link.dataset.target!)?.scrollIntoView({ behavior: "smooth" });
    };
  }
}
