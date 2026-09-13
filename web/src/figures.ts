const DOCS = "https://github.com/jkelleyrtp/fusion/blob/devin/1789237491-pic-research/docs";

interface Figure { image: string; title: string }
interface Study { id: string; title: string; summary: string; doc: string; figures: Figure[] }

const pair = (name: string, what: string): Figure[] => [
  { image: `pic-${name}-evolution.png`, title: `${what}: time histories` },
  { image: `pic-${name}-fields.png`, title: `${what}: final potential and density` },
];

const studies: Study[] = [
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
    id: "six-coil-ions", title: "Coupled electrons + H2+ ions (six-coil, partial)",
    summary: "Six-coil trap at 1 A, 0 V casings with H2 gas at 1e-3 Pa (and 1e-2 Pa), ionization, ion space charge and charge exchange. Ions cancel the whole electron well within ~200 µs at 1e-3 Pa (~20 µs at 1e-2 Pa); the centre rises from −2.8 kV to ~0 V. Partial: 7 of 8 cases still running, 50–90% of cycles shown.",
    doc: "ion-pic-design.md", figures: pair("six-coil-ions", "Six-coil coupled ions"),
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
