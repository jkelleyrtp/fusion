import "./style.css";
import { DataStore, parseChunk } from "./data";
import { Chamber, COLORS } from "./scene";
import { SweepPlot } from "./sweep";
import type { Catalog, Meta, Run, TrajectoryChunk } from "./types";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element: ${id}`);
  return element as T;
};
const escape = (text: string): string => text.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const fmt = (value: number | null | undefined, digits = 3): string =>
  value == null || !Number.isFinite(value) ? "—" : Number(value.toPrecision(digits)).toLocaleString("en-US", { maximumFractionDigits: 6 });
const bytes = (value: number): string => value < 1024 * 1024 ? `${fmt(value / 1024)} KB` : `${fmt(value / 1024 / 1024)} MB`;
const scientific = (value: number | undefined): string => value == null || !Number.isFinite(value) ? "—" : value.toExponential(2);
const channelNames = ["At window end", "−z cusp", "+z cusp", "Radial wall"];
const store = new DataStore();
let catalog: Catalog;
let selected: Run | undefined;
let meta: Meta | undefined;
let chamber: Chamber | undefined;
let revision = 0;
let playing = false;
let cursor = 1;
let lastFrame = 0;
let loaded: TrajectoryChunk[] = [];
let loadedName = "No trajectories loaded";
const metadata = new Map<string, Meta>();
const comparisons = new Map<string, { run: Run; meta: Meta }>();

$("app").innerHTML = `
  <header class="topbar">
    <a class="brand" href="./" aria-label="Fusion control room">
      <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true"><ellipse cx="16" cy="11" rx="12" ry="5"/><ellipse cx="16" cy="21" rx="12" ry="5"/><path d="M16 3v26M4 11l24 10M28 11L4 21"/></svg>
      Fusion
    </a>
    <div class="top-context">Fixed fields · no Poisson feedback</div>
  </header>
  <div class="workspace">
    <aside class="sidebar">
      <div class="sidebar-heading"><span>Campaigns · newest first</span><b id="run-count">—</b></div>
      <label class="search"><span>⌕</span><input id="search" placeholder="Find a run…" aria-label="Find a run"/></label>
      <select id="study" aria-label="Campaign"><option value="">All campaigns</option></select>
      <div class="filter-row"><select id="energy" aria-label="Energy"><option value="">All energies</option></select>
      <select id="radius" aria-label="Radius"><option value="">All sizes</option></select></div>
      <div class="run-list" id="run-list" aria-label="Simulation runs"></div>
    </aside>
    <main>
      <section id="sweep-explorer" class="panel sweep-panel" hidden></section>
      <section class="run-heading" id="selected-run"><div><div class="eyebrow" id="campaign-name">LOADING EXPERIMENTS</div>
        <h1 id="run-title">Electron residence study</h1><div id="run-subtitle" class="muted">Summary-first exploration</div></div>
        <div class="run-actions"><button id="back-sweep" class="secondary" hidden>↑ Sweep</button><button id="pin" class="secondary">+ Compare run</button></div></section>
      <div id="error" class="error" role="alert" hidden></div>
      <div class="console-grid">
        <div class="primary-column">
          <section class="panel chamber-panel">
            <div class="panel-heading"><h2>Trajectories</h2>
              <div class="view-buttons"><button data-view="iso" class="active" title="Isometric view">ISO</button><button data-view="side">SIDE</button><button data-view="top">AXIAL</button></div></div>
            <div id="viewport">
              <div class="view-info"><span id="view-mode">PRESCRIBED-FIELD MODEL</span><small id="view-scale">Coordinates scaled by coil radius</small></div>
              <div id="render-status" class="render-status">Connecting renderer…</div>
              <div class="view-hint">Drag to orbit · scroll to zoom</div>
              <div id="viewport-empty" class="viewport-empty">Loading run summary…</div>
            </div>
            <div class="legend" id="legend">${channelNames.map((name, i) =>
              `<label><input type="checkbox" data-channel="${i}" checked/><i style="background:${COLORS[i]}"></i>${name}</label>`).join("")}
              <label class="sphere-toggle"><input id="sphere" type="checkbox" checked/>Proxy sphere</label></div>
            <div class="playback"><button id="play" class="play-button" aria-label="Play trajectories">▶</button><output id="time">0 µs</output>
              <input id="scrub" type="range" min="0" max="1000" value="1000" aria-label="Trajectory playback time"/>
              <span id="time-end">—</span><select id="speed" aria-label="Playback duration"><option value="12">Slow</option><option value="6" selected>1×</option><option value="3">2×</option></select></div>
            <div class="stream-controls">
              <label>Detail<select id="detail"><option value="0">Preview · stride 24</option><option value="1">Standard · stride 6</option><option value="2">Full stored samples</option></select></label>
              <label>Start<select id="first"><option>0</option></select></label>
              <label>Paths<select id="amount"><option value="16" selected>16</option><option value="32">32</option><option value="64">64</option><option value="128">128</option></select></label>
              <button id="load" class="accent">Load selection</button>
            </div>
            <div class="sample-note"><span id="loaded">No trajectories loaded</span><span id="sample-note">Stored paths are a subset of the ensemble.</span></div>
          </section>
          <div class="plots">
            <section class="panel survival-panel"><div class="panel-heading"><h2>Residence / survival</h2>
              <label class="inline-toggle"><input id="log-time" type="checkbox" checked/>Log-like time</label></div>
              <div id="survival-chart"></div><div id="chart-hover" class="chart-note">Fraction not yet lost by time t</div>
              <div class="loss-strip" id="loss-strip"></div></section>
            <section class="panel occupancy-panel"><div class="panel-heading"><h2>Occupancy samples</h2><span class="tiny-label">r–z</span></div>
              <div class="heatmap-wrap"><canvas id="heatmap" width="220" height="175" aria-label="Axisymmetric occupancy sample histogram"></canvas><div id="heatmap-empty" hidden>Not recorded</div></div>
              <div id="core-share" class="chart-note">—</div><div class="plot-note">Sample counts, not charge density</div></section>
          </div>
          <section class="metrics" aria-label="Run metrics">
            <article class="metric primary"><div>Mean dwell <span id="dwell-badge"></span></div><strong id="dwell">—</strong><small id="dwell-note">All simulated particles</small></article>
            <article class="metric"><div>Observation window</div><strong id="window">—</strong><small id="survivors">—</small></article>
            <article class="metric"><div>Coil radius</div><strong id="coil">—</strong><small id="coil-note">Opposed circular coils</small></article>
            <article class="metric"><div>Prescribed φ(0)</div><strong id="potential">—</strong><small>Fixed charge proxy</small></article>
          </section>
          <section class="panel compare-panel" id="compare-panel" hidden><div class="panel-heading"><h2>Pinned comparisons</h2><button id="clear-comparisons" class="text-button">Clear</button></div><div id="comparison-table"></div></section>
        </div>
        <aside class="instrument-column">
          <section class="panel injection-panel"><div class="panel-heading"><h2>Electron inventory</h2><span class="tag">estimate</span></div>
            <label class="current-input" for="current">Beam current <span><input id="current" type="number" min="0" step="0.1" value="1"/> mA</span></label>
            <div class="inventory"><strong id="inventory">—</strong><small id="charge">—</small></div>
            <p class="caution">I⟨τ⟩/e · includes time outside the core.<br>Not a virtual-cathode prediction.</p>
          </section>
          <section class="panel bandwidth-panel"><div class="panel-heading"><h2>Data</h2><span id="cache-hits" class="tag">0 cached</span></div>
            <div class="download-total"><strong id="downloaded">0 KB</strong><span>this session</span></div><div class="budget-track"><i id="budget-fill"></i></div>
            <label class="budget-label">Limit<select id="budget"><option value="1">1 MiB</option><option value="5" selected>5 MiB</option><option value="20">20 MiB</option><option value="100">100 MiB</option></select></label>
            <label class="offline-label"><input id="offline" type="checkbox"/>Offline · cached data only</label>
            <div class="connection-actions"><button id="reload" class="text-button">Refresh</button><button id="clear-cache" class="text-button">Clear cache</button></div>
            <p id="cache-note">Result data only; excludes app shell.</p>
          </section>
          <details class="panel"><summary>Source & geometry</summary><dl id="geometry" class="readouts"></dl></details>
          <details class="panel"><summary>Numerical quality <span class="tag">FP64</span></summary><dl id="quality" class="readouts"></dl>
            <p class="quality-note" id="quality-note"></p></details>
        </aside>
      </div>
    </main>
  </div>`;

function showError(error: unknown): void {
  $("error").textContent = error instanceof Error ? error.message : String(error);
  $("error").hidden = false;
}
function clearError(): void { $("error").hidden = true; }
function stop(): void { playing = false; $("play").textContent = "▶"; $("play").setAttribute("aria-label", "Play trajectories"); }
function label(run: Run): string {
  return run.sweep ? `${fmt(run.energyEV)} eV · ${fmt(run.sweep.coilCurrentA / 1000)} kA-turn · ${run.sweep.aimDeg}° aim · ${run.sweep.coneDeg}° cone` :
    `${fmt(run.energyEV)} eV · ${fmt(run.radiusM * 100)} cm · ${run.chargeC < 0 ? "negative proxy" : run.chargeC > 0 ? "positive proxy" : "neutral"}`;
}
const sweepPlot = new SweepPlot($("sweep-explorer"), id => {
  void selectRun(id);
  $("selected-run").scrollIntoView({ block: "start" });
});
function renderSweep(): void {
  const study = $<HTMLSelectElement>("study").value || selected?.study || catalog.studies[0]?.id;
  sweepPlot.render(filteredRuns(), study, catalog.studies.find(s => s.id === study)?.label ?? study, selected?.id);
  $("back-sweep").hidden = $("sweep-explorer").hidden;
}
$("back-sweep").onclick = () => $("sweep-explorer").scrollIntoView({ block: "start" });
function readouts(id: string, rows: [string, string][]): void {
  $(id).innerHTML = rows.map(([name, value]) => `<div><dt>${escape(name)}</dt><dd>${escape(value)}</dd></div>`).join("");
}
function finishTime(study: Catalog["studies"][number]): number {
  const time = Date.parse(study.finishedAt ?? "");
  return Number.isFinite(time) ? time : -Infinity;
}
function finishedAgo(study: Catalog["studies"][number]): string {
  const time = finishTime(study);
  if (!Number.isFinite(time)) return "Time unknown";
  const seconds = Math.max(0, (Date.now() - time) / 1000);
  if (seconds < 60) return "Just finished";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function filteredRuns(): Run[] {
  const query = $<HTMLInputElement>("search").value.toLowerCase();
  const study = $<HTMLSelectElement>("study").value;
  const energy = $<HTMLSelectElement>("energy").value;
  const radius = $<HTMLSelectElement>("radius").value;
  return catalog.runs.filter(run => (!study || run.study === study) &&
    (!energy || run.energyEV === Number(energy)) && (!radius || run.radiusM === Number(radius)) &&
    `${run.tag} ${label(run)} ${run.study}`.toLowerCase().includes(query));
}
function renderLibrary(): void {
  const query = $<HTMLInputElement>("search").value;
  const runs = filteredRuns();
  $("run-count").textContent = String(runs.length);
  $("run-list").innerHTML = catalog.studies.map(campaign => {
    const members = runs.filter(run => run.study === campaign.id);
    if (!members.length) return "";
    const sweep = members.some(run => run.sweep);
    return `<button class="campaign-card ${selected?.study === campaign.id ? "selected" : ""}" data-campaign="${escape(campaign.id)}">
      <strong>${escape(campaign.label)}</strong><span>${members.length} runs · ${finishedAgo(campaign)}${sweep ? " · heatmaps" : ""}</span></button>
      <details class="campaign-members" ${query || (!sweep && selected?.study === campaign.id) ? "open" : ""}><summary>Browse ${members.length} runs</summary>` +
    members.map(run => `<button class="run-card ${selected?.id === run.id ? "selected" : ""}" data-run="${escape(run.id)}" aria-pressed="${selected?.id === run.id}">
    <div class="run-card-top"><strong>${fmt(run.energyEV)} <span>eV</span></strong><span class="run-size">${fmt(run.radiusM * 100)} cm</span></div>
    ${run.sweep ? `<div class="run-card-bottom">${fmt(run.sweep.coilCurrentA / 1000)} kA · ${run.sweep.aimDeg}° aim · ${run.sweep.coneDeg}° cone</div>` : ""}
    <div class="run-card-bottom"><span><i class="${run.chargeC === 0 ? "neutral" : "charged"}"></i>${run.chargeC === 0 ? "Neutral" : run.chargeC < 0 ? "Negative proxy" : "Positive proxy"}</span>
      <b>${run.meanDwellUs == null ? "Summary only" : `${run.dwellLowerBound ? "≥" : ""}${fmt(run.meanDwellUs)} µs`}</b></div>
    ${run.kind !== "external" ? `<span class="control-label">${run.kind === "control" ? "INSIDE-BORN CONTROL" : "LEGACY SOURCE"}</span>` : ""}
    </button>`).join("") + "</details>";
  }).join("") || '<p class="empty-list">No matching runs.</p>';
}

function renderMetrics(): void {
  if (!selected) return;
  $("campaign-name").textContent = catalog.studies.find(s => s.id === selected!.study)?.label ?? selected.study;
  $("run-title").textContent = label(selected);
  $("run-title").title = selected.tag;
  $("run-subtitle").textContent = `${fmt(selected.particles, 7)} particles · ${selected.kind === "external" ? "external gun" : selected.kind === "control" ? "inside-born numerical control" : "historical source"}`;
  $("dwell").innerHTML = `${selected.dwellLowerBound ? "≥ " : ""}${fmt(selected.meanDwellUs)} <em>µs</em>`;
  $("dwell-badge").textContent = selected.dwellLowerBound ? "lower bound" : "";
  const transit = selected.meanDwellUs == null ? null : selected.meanDwellUs * 1e-6 * Math.sqrt(2 * selected.energyEV * 1.602176634e-19 / 9.1093837e-31) / selected.radiusM;
  $("dwell-note").textContent = transit == null ? "Raw escape data unavailable" : `${fmt(transit)} × a/v₀ · launch-to-loss through T`;
  $("window").innerHTML = `${fmt(selected.windowUs)} <em>µs</em>`;
  $("survivors").textContent = `${fmt(selected.survivors, 7)} still present · ${fmt(selected.survivors / selected.particles * 100)}%`;
  $("coil").innerHTML = `${fmt(selected.radiusM * 100)} <em>cm</em>`;
  $("coil-note").textContent = meta ? `${fmt(meta.summary.current_A / 1000)} kA-turn · ${fmt(meta.summary.ring_half_sep_m * 200)} cm separation` : "Opposed circular coils";
  $("potential").innerHTML = `${fmt(meta?.summary.centre_potential_V)} <em>V</em>`;
  $("view-mode").textContent = selected.kind === "control" ? "Inside-born control" : "";
  $("view-scale").textContent = "Coil thickness schematic";
  const s = meta?.summary;
  readouts("geometry", [
    ["Energy", `${fmt(selected.energyEV)} eV`], ["Gun / B angle", `${fmt(selected.axisAngleDeg)}°`],
    ["Source RMS", s?.gun_source_sigma_m == null ? "—" : `${fmt(s.gun_source_sigma_m * 1e6)} µm`],
    ["Launch cone", s?.pitch_deg?.map(v => fmt(v)).join("–") ? `${s.pitch_deg.map(v => fmt(v)).join("–")}°` : "—"],
    ["Gun r / z", s?.gun_position_m ? `${fmt(Math.hypot(s.gun_position_m[0], s.gun_position_m[1]) * 1000)} mm / ${fmt(s.gun_position_m[2] * 100)} cm` : "—"],
    ["Charge proxy", `${scientific(selected.chargeC)} C`],
    ["Proxy radius", s?.space_charge_radius_m == null ? "—" : `${fmt(s.space_charge_radius_m * 100)} cm`],
  ]);
  readouts("quality", [
    ["Integrator", s ? `${s.integrator ?? "unknown"}${s.adaptive ? " · adaptive" : ""}` : "—"],
    ["Reference Δt", s?.dt_s == null ? "—" : `${fmt(s.dt_s * 1e12)} ps`],
    ["Maximum Δt", s?.dt_max_s == null ? "—" : `${fmt(s.dt_max_s * 1e12)} ps`],
    ["Max |ΔE/E|", scientific(s?.energy_drift_rel_max)],
    ["Energy diagnostic", `${selected.tracked} tracked particles`],
    ["Stored state", "FP32 positions · FP64 pusher"],
  ]);
  $("quality-note").textContent = selected.study.startsWith("conv")
    ? "Rare survival tails changed under timestep/grid refinement. Do not treat them as converged confinement."
    : "Dwell and core residence need convergence checks. Energy drift covers tracked particles, not the full ensemble.";
  $("sample-note").textContent = `${selected.tracked} paths / ${fmt(selected.particles, 7)} particles · first ${fmt(selected.trajectoryWindowUs)} µs · gyration may alias`;
  $("time-end").textContent = `${fmt(selected.trajectoryWindowUs)} µs`;
  renderInventory();
}

function renderInventory(): void {
  const current = Number($<HTMLInputElement>("current").value) * 1e-3;
  const dwell = selected?.kind === "control" ? undefined : selected?.meanDwellUs;
  const charge = dwell == null || !Number.isFinite(current) || current < 0 ? undefined : current * dwell * 1e-6;
  $("inventory").textContent = charge == null ? "—" : `${selected?.dwellLowerBound ? "≥ " : ""}${scientific(charge / 1.602176634e-19)}`;
  $("charge").textContent = charge == null ? "Inventory unavailable" : `${selected?.dwellLowerBound ? "|Q| ≥ " : "Q ≈ "}${selected?.dwellLowerBound ? "" : "−"}${fmt(charge * 1e9)} nC`;
}

function renderPlots(): void {
  if (!selected) return;
  const curves = [...(meta ? [{ run: selected, meta }] : []), ...[...comparisons.values()].filter(c => c.run.id !== selected!.id)];
  const curveColor = (id: string): string => id === selected?.id ? COLORS[0] :
    [COLORS[2], COLORS[3], COLORS[1]][[...comparisons.keys()].indexOf(id) % 3];
  const W = 530, H = 176, left = 40, right = 14, top = 12, bottom = 30;
  const maxT = Math.max(selected.windowUs, ...curves.map(c => c.run.windowUs));
  const log = $<HTMLInputElement>("log-time").checked;
  const norm = (t: number): number => log ? Math.log1p(t / (maxT / 1000)) / Math.log(1001) : t / maxT;
  const x = (t: number): number => left + norm(t) * (W - left - right);
  const y = (n: number): number => top + (1 - n) * (H - top - bottom);
  const ticks = log ? [0, maxT / 1000, maxT / 100, maxT / 10, maxT] : [0, maxT / 4, maxT / 2, maxT * 0.75, maxT];
  const svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Survival curves by physical time">
    ${[0, 0.5, 1].map(n => `<line x1="${left}" x2="${W - right}" y1="${y(n)}" y2="${y(n)}" stroke="#24313d"/><text x="${left - 7}" y="${y(n) + 4}" text-anchor="end">${n * 100}%</text>`).join("")}
    ${ticks.map(t => `<text x="${x(t)}" y="${H - 10}" text-anchor="middle">${fmt(t)}${t === maxT ? " µs" : ""}</text>`).join("")}
    ${curves.map((curve, ci) => {
      const points = curve.meta.survival.tUs.map((t, i) => `${i === 0 ? "M" : "H"}${x(t)}${i === 0 ? "," : "V"}${y(curve.meta.survival.counts[i] / curve.run.particles)}`).join("");
      return `<path d="${points}" stroke="${curveColor(curve.run.id)}" fill="none" stroke-width="2" ${ci ? 'stroke-dasharray="4 3"' : ""}/>`;
    }).join("")}</svg>`;
  $("survival-chart").innerHTML = curves.length ? svg : '<div class="plot-empty">Raw survival data not available for this archive.</div>';
  $("survival-chart").onpointermove = event => {
    if (!meta) return;
    const box = $("survival-chart").getBoundingClientRect();
    const fraction = Math.max(0, Math.min(1, ((event.clientX - box.left) / box.width * W - left) / (W - left - right)));
    const t = log ? (Math.exp(fraction * Math.log(1001)) - 1) * maxT / 1000 : fraction * maxT;
    let index = 0;
    while (index + 1 < meta.survival.tUs.length && meta.survival.tUs[index + 1] <= t) index++;
    $("chart-hover").textContent = `Saved curve at ${fmt(meta.survival.tUs[index])} µs · ${fmt(meta.survival.counts[index], 7)} present (${fmt(meta.survival.counts[index] / selected!.particles * 100)}%)`;
  };
  $("loss-strip").innerHTML = meta ? meta.lossCounts.map((count, i) =>
    `<span style="width:${count / selected!.particles * 100}%;background:${COLORS[i]}" title="${channelNames[i]}: ${count}"></span>`).join("") : "";
  const canvas = $<HTMLCanvasElement>("heatmap"), ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const occupancy = meta?.occupancy;
  $("heatmap-empty").hidden = !!occupancy;
  $("core-share").textContent = occupancy ? `${fmt((occupancy.coreSampleFraction ?? 0) * 100)}% of samples inside proxy-radius sphere` : "Occupancy unavailable";
  if (occupancy) {
    const maximum = Math.max(...occupancy.counts, 1);
    for (let z = 0; z < occupancy.height; z++) for (let r = 0; r < occupancy.width; r++) {
      const value = Math.log1p(occupancy.counts[z * occupancy.width + r]) / Math.log1p(maximum);
      ctx.fillStyle = `rgb(${Math.round(10 + 91 * value ** 2)},${Math.round(22 + 207 * value)},${Math.round(31 + 182 * value)})`;
      ctx.fillRect(r * 220 / occupancy.width, (occupancy.height - 1 - z) * 175 / occupancy.height, 220 / occupancy.width + 0.2, 175 / occupancy.height + 0.2);
    }
    ctx.strokeStyle = "#e4eef366"; ctx.setLineDash([3, 3]); ctx.beginPath();
    ctx.ellipse(0, occupancy.zMaxM / (occupancy.zMaxM - occupancy.zMinM) * 175,
      occupancy.coreRadiusM / occupancy.rMaxM * 220, occupancy.coreRadiusM / (occupancy.zMaxM - occupancy.zMinM) * 175, 0, 0, Math.PI * 2); ctx.stroke();
  }
  $("compare-panel").hidden = comparisons.size === 0;
  $("comparison-table").innerHTML = `<table><thead><tr><th>Run</th><th>Mean dwell</th><th>Window</th><th>Remaining</th></tr></thead><tbody>${[...comparisons.values()].map(c =>
    `<tr><td><i style="background:${curveColor(c.run.id)}"></i>${escape(label(c.run))}<small>${escape(catalog.studies.find(s => s.id === c.run.study)?.label ?? c.run.study)}</small></td><td>${c.run.dwellLowerBound ? "≥ " : ""}${fmt(c.run.meanDwellUs)} µs</td><td>${fmt(c.run.windowUs)} µs</td><td>${fmt(c.run.survivors / c.run.particles * 100)}%</td></tr>`).join("")}</tbody></table>`;
  $("pin").textContent = comparisons.has(selected.id) ? "Unpin run" : "+ Compare run";
}

function updateStream(): void {
  const level = meta?.trajectory.levels[Number($<HTMLSelectElement>("detail").value)];
  const first = Number($<HTMLSelectElement>("first").value);
  const count = Number($<HTMLSelectElement>("amount").value);
  const refs = level?.chunks.filter(c => c.first >= first && c.first < first + count) ?? [];
  $<HTMLButtonElement>("load").disabled = !refs.length;
  $("load").textContent = `Load · ${bytes(refs.reduce((n, c) => n + c.bytes, 0))}`;
}

async function loadPaths(): Promise<void> {
  if (!meta || !selected) return;
  const currentRevision = revision;
  const currentMeta = meta;
  const level = currentMeta.trajectory.levels[Number($<HTMLSelectElement>("detail").value)];
  const first = Number($<HTMLSelectElement>("first").value);
  const count = Number($<HTMLSelectElement>("amount").value);
  const refs = level.chunks.filter(c => c.first >= first && c.first < first + count);
  clearError(); $<HTMLButtonElement>("load").disabled = true;
  $("loaded").textContent = "Fetching compressed chunks…";
  const chunks: TrajectoryChunk[] = [];
  try {
    for (const ref of refs) {
      if (revision !== currentRevision) return;
      chunks.push(parseChunk(await store.bytes(ref), ref));
    }
    if (revision !== currentRevision) return;
    loaded = chunks;
    chamber?.setChunks(chunks);
    const n = chunks.reduce((sum, c) => sum + c.count, 0);
    loadedName = `${n} paths · particles ${first}–${first + n - 1} · ${level.name.toLowerCase()}`;
    $("loaded").textContent = loadedName;
    $("viewport-empty").hidden = !!chamber;
    if (!chamber) $("viewport-empty").textContent = "WebGL2 is unavailable. Metrics and downloads still work.";
    $<HTMLButtonElement>("play").disabled = false;
    setCursor(1);
  } catch (error) {
    if (revision === currentRevision) { showError(error); $("loaded").textContent = loadedName; }
  } finally { if (revision === currentRevision) updateStream(); }
}

async function selectRun(id: string): Promise<void> {
  const run = catalog.runs.find(r => r.id === id);
  if (!run) return;
  const request = ++revision;
  stop(); clearError(); selected = run; meta = undefined; loaded = [];
  loadedName = "No trajectories loaded";
  $("loaded").textContent = loadedName;
  $("viewport-empty").hidden = false; $("viewport-empty").textContent = "Loading compact summary…";
  $<HTMLButtonElement>("play").disabled = true;
  $<HTMLSelectElement>("detail").value = "0"; $<HTMLSelectElement>("amount").value = "16";
  chamber?.setRun(run);
  renderLibrary(); renderSweep(); renderMetrics(); renderPlots(); updateStream();
  if (!run.meta) {
    $("viewport-empty").textContent = "Summary-only archive · raw trajectories unavailable";
    return;
  }
  try {
    const data = metadata.get(id) ?? await store.json<Meta>(run.meta);
    if (data.version !== 1) throw new Error("Unsupported run format.");
    metadata.set(id, data);
    if (request !== revision) return;
    meta = data; chamber?.setRun(run, data);
    chamber?.showSphere($<HTMLInputElement>("sphere").checked);
    $<HTMLSelectElement>("first").innerHTML = data.trajectory.levels[0].chunks.map(c => `<option value="${c.first}">${c.first}</option>`).join("");
    renderMetrics(); renderPlots(); updateStream();
    await loadPaths();
  } catch (error) { if (request === revision) { showError(error); $("viewport-empty").textContent = "Could not load run data"; } }
}

function setCursor(fraction: number): void {
  cursor = fraction; $<HTMLInputElement>("scrub").value = String(Math.round(fraction * 1000));
  const time = fraction * (selected?.trajectoryWindowUs ?? 0);
  $("time").textContent = `${fmt(time)} µs`; chamber?.setTime(time);
}

store.onChange = () => {
  $("downloaded").textContent = bytes(store.spent);
  $("cache-hits").textContent = `${store.cacheHits} cached`;
  $("budget-fill").style.width = `${Math.min(100, store.spent / store.budget * 100)}%`;
  $("cache-note").textContent = store.cacheNotice || "Result data only; excludes app shell.";
};

for (const id of ["search", "study", "energy", "radius"]) $(id).addEventListener("input", () => { if (catalog) { renderLibrary(); renderSweep(); } });
$("run-list").onclick = event => {
  const campaign = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-campaign]")?.dataset.campaign;
  if (campaign) {
    $<HTMLSelectElement>("study").value = "";
    for (const id of ["search", "energy", "radius"]) $<HTMLInputElement | HTMLSelectElement>(id).value = "";
    const members = catalog.runs.filter(r => r.study === campaign);
    const preferred = [...members].sort((a, b) => (b.meanDwellUs ?? -1) - (a.meanDwellUs ?? -1))[0];
    if (preferred) void selectRun(preferred.id);
    $("sweep-explorer").scrollIntoView({ block: "start" });
    return;
  }
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-run]");
  if (button?.dataset.run) void selectRun(button.dataset.run);
};
$("load").onclick = () => { void loadPaths(); };
for (const id of ["detail", "first", "amount"]) $(id).onchange = updateStream;
$("current").oninput = renderInventory;
$("log-time").onchange = renderPlots;
$("legend").onchange = () => {
  chamber?.setChannels([...document.querySelectorAll<HTMLInputElement>("[data-channel]")].map(input => input.checked));
  chamber?.showSphere($<HTMLInputElement>("sphere").checked);
};
document.querySelectorAll<HTMLButtonElement>("[data-view]").forEach(button => {
  button.onclick = () => {
    chamber?.resetView(button.dataset.view!);
    document.querySelectorAll("[data-view]").forEach(b => b.classList.toggle("active", b === button));
  };
});
$("scrub").oninput = () => { stop(); setCursor(Number($<HTMLInputElement>("scrub").value) / 1000); };
$("play").onclick = () => {
  if (!loaded.length) return;
  if (playing) stop();
  else { if (cursor >= 1) setCursor(0); playing = true; $("play").textContent = "Ⅱ"; $("play").setAttribute("aria-label", "Pause trajectories"); }
};
$("pin").onclick = () => {
  if (!selected || !meta) return;
  if (comparisons.has(selected.id)) comparisons.delete(selected.id);
  else if (comparisons.size < 3) comparisons.set(selected.id, { run: selected, meta });
  else { showError(new Error("Three comparisons are pinned. Clear them before adding another.")); return; }
  renderPlots();
};
$("clear-comparisons").onclick = () => { comparisons.clear(); renderPlots(); };
$("budget").onchange = () => { store.budget = Number($<HTMLSelectElement>("budget").value) * 1024 * 1024; store.onChange(); };
$("offline").onchange = () => { store.offline = $<HTMLInputElement>("offline").checked; };
$("clear-cache").onclick = () => { void store.clear().catch(showError); };

async function initialize(): Promise<void> {
  try {
    catalog = await store.catalog<Catalog>();
    if (catalog.version !== 1 || !catalog.runs.length) throw new Error("No supported runs in the catalog.");
    catalog.studies.sort((a, b) => finishTime(b) - finishTime(a));
    $("study").innerHTML = '<option value="">All campaigns</option>' + catalog.studies.map(s => `<option value="${escape(s.id)}">${escape(s.label)} · ${finishedAgo(s)}</option>`).join("");
    $("energy").innerHTML = '<option value="">All energies</option>' + [...new Set(catalog.runs.map(r => r.energyEV))].sort((a, b) => a - b).map(e => `<option value="${e}">${fmt(e)} eV</option>`).join("");
    $("radius").innerHTML = '<option value="">All sizes</option>' + [...new Set(catalog.runs.map(r => r.radiusM))].sort((a, b) => a - b).map(r => `<option value="${r}">${fmt(r * 100)} cm</option>`).join("");
    const latestRuns = catalog.runs.filter(r => r.study === catalog.studies[0]?.id);
    const preferred = catalog.runs.find(r => r.id === selected?.id)?.id ??
      latestRuns.find(r => r.energyEV === 5 && r.chargeC === 0)?.id ?? latestRuns[0]?.id ?? catalog.runs[0].id;
    await selectRun(preferred);
  } catch (error) { showError(error); }
}
$("reload").onclick = () => { metadata.clear(); void initialize(); };
try {
  chamber = new Chamber($("viewport"));
  const software = /swiftshader|llvmpipe|software/i.test(chamber.rendererName);
  $("render-status").textContent = software ? "WebGL2 · software renderer" : "WebGL2 · GPU buffers";
  $("render-status").title = chamber.rendererName;
  chamber.onStats = () => {
    $("render-status").textContent = `WebGL2 · ${software ? "software" : "GPU buffers"} · ${fmt(chamber!.segments, 5)} segments`;
  };
} catch {
  $("render-status").textContent = "WebGL2 unavailable";
  $("viewport-empty").textContent = "WebGL2 is unavailable. Metrics and downloads still work.";
}
function frame(now: number): void {
  const dt = lastFrame ? Math.min((now - lastFrame) / 1000, 0.1) : 0; lastFrame = now;
  if (playing) {
    setCursor(Math.min(1, cursor + dt / Number($<HTMLSelectElement>("speed").value)));
    if (cursor >= 1) stop();
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
void initialize();
