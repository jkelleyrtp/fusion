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
