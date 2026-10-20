import type { Meta, Run } from "./types";

const escape = (text: string): string => text.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const number = (value: number | null | undefined): string =>
  value == null || !Number.isFinite(value) ? "Not recorded" : Number(value.toPrecision(5)).toLocaleString("en-US", { maximumFractionDigits: 8 });
const colors = ["#83dfbd", "#65c6ee", "#b99aff", "#f4b275"];
const channels = ["Present at window end", "−z exit", "+z exit", "Radial boundary"];

const reportStyle = `
  :root{color-scheme:dark}body{background:#0b1219;color:#dae5ed;font:14px/1.6 system-ui,sans-serif;margin:0 auto;padding:32px;max-width:1040px}
  h1{font-size:24px}h2{font-size:17px;margin:28px 0 10px}p{max-width:85ch}small,footer{color:#8ea2b3}
  svg{width:100%;height:auto;max-height:360px}svg text{fill:#8ea2b3;font:11px system-ui,sans-serif}
  table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:8px;border-bottom:1px solid #263642}
  .report-charts{display:grid;grid-template-columns:1.6fr 1fr;gap:24px}.table-scroll{overflow-x:auto}
  footer{margin-top:32px;padding-top:14px;border-top:1px solid #263642;font-size:11px;overflow-wrap:anywhere}
  @media(max-width:650px){body{padding:16px}.report-charts{grid-template-columns:1fr}}
  @media print{body{background:white;color:#111}small,footer{color:#444}section{break-inside:avoid}}
`;

export function downloadStaticReport(html: string, title: string, filename: string): void {
  const document = `<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
    <title>${escape(title)} · Fusion report</title><style>${reportStyle}</style></head><body>${html}</body></html>`;
  const url = URL.createObjectURL(new Blob([document], { type: "text/html" }));
  const link = window.document.createElement("a");
  link.href = url;
  link.download = `${filename.replace(/[^a-z0-9_-]/gi, "_")}-report.html`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function survivalPlot(run: Run, meta: Meta): string {
  if (!meta.survival.tUs.length) return "<p>Survival curve not recorded.</p>";
  const x = (t: number): number => 45 + t / run.windowUs * 480;
  const y = (count: number): number => 20 + (1 - count / run.particles) * 195;
  const path = meta.survival.tUs.map((t, i) => `${i ? "H" : "M"}${x(t)}${i ? "V" : ","}${y(meta.survival.counts[i])}`).join("");
  return `<svg viewBox="0 0 550 265" role="img" aria-label="Survival fraction versus physical time, linear scale">
    ${[0, 0.5, 1].map(f => `<line x1="45" x2="525" y1="${y(f * run.particles)}" y2="${y(f * run.particles)}" stroke="#263642"/><text x="37" y="${y(f * run.particles) + 4}" text-anchor="end">${f * 100}%</text>`).join("")}
    ${[0, 0.25, 0.5, 0.75, 1].map(f => `<text x="${x(f * run.windowUs)}" y="237" text-anchor="middle">${number(f * run.windowUs)}</text>`).join("")}
    <path d="${path}" fill="none" stroke="#83dfbd" stroke-width="2"/>
    <text x="280" y="259" text-anchor="middle">Time (µs) · linear scale</text></svg>`;
}

function occupancyPlot(meta: Meta): string {
  const occupancy = meta.occupancy;
  if (!occupancy) return "<p>Occupancy histogram not recorded.</p>";
  const { width, height, counts } = occupancy;
  const maximum = Math.max(1, ...counts);
  return `<svg viewBox="0 0 310 265" role="img" aria-label="Axisymmetric occupancy sample counts, log color scale">
    ${counts.flatMap((count, i) => {
      if (!count) return [];
      const f = Math.log1p(count) / Math.log1p(maximum);
      const color = `rgb(${Math.round(10 + 91 * f ** 2)},${Math.round(22 + 207 * f)},${Math.round(31 + 182 * f)})`;
      return [`<rect x="${60 + (i % width) * 215 / width}" y="${20 + (height - 1 - Math.floor(i / width)) * 195 / height}"
        width="${215 / width + 0.1}" height="${195 / height + 0.1}" fill="${color}"/>`];
    }).join("")}
    <text x="52" y="27" text-anchor="end">${number(occupancy.zMaxM)}</text>
    <text x="52" y="215" text-anchor="end">${number(occupancy.zMinM)}</text>
    <text x="60" y="237">0</text><text x="275" y="237" text-anchor="end">${number(occupancy.rMaxM)}</text>
    <text x="167" y="259" text-anchor="middle">r (m) · z (m), bottom to top</text></svg>
    <small>log(1 + sample count), 0–${maximum}. Sample counts are not time-weighted charge density.</small>`;
}

function contents(run: Run, meta: Meta | undefined, campaign: string): string {
  const lower = run.dwellLowerBound ? "≥ " : "";
  const summary = meta?.summary;
  const poisson = run.poisson;
  const outcomes = poisson ? ["Present at window end", "−z box face", "+z box face", "Side box face"] : channels;
  const remaining = run.survivors / run.particles * 100;
  const escaped = meta?.lossCounts.slice(1) ?? [];
  const dominant = escaped.length && Math.max(...escaped) > 0 ? escaped.indexOf(Math.max(...escaped)) + 1 : null;
  const findings = [
    run.meanDwellUs == null ? "Mean residence was not recorded." :
      `Mean launch-to-loss residence is ${lower}${number(run.meanDwellUs)} µs over an observation window of ${number(run.windowUs)} µs.`,
    `${number(run.survivors)} of ${number(run.particles)} particles (${number(remaining)}%) remain at the cutoff.${
      run.dwellLowerBound ? " The recorded mean dwell is a lower bound; longer observation is needed to measure the tail." : ""}`,
    dominant !== null ? `${outcomes[dominant]} is the largest recorded escape channel: ${number(meta!.lossCounts[dominant] / run.particles * 100)}% of all launched particles.` :
      meta ? "No escaped particles were recorded in the channel counts." : "Detailed metadata is not loaded. Loss-channel and raw curve data are unavailable in this report.",
    poisson ? `Replay uses orbit iteration ${poisson.iteration}/${poisson.requestedIterations}, with the electric field frozen during each particle packet. Iteration number is not physical time.` :
      run.kind === "control" ? "Inside-born control: this run does not measure capture from an external electron gun." :
      "This fixed-field run measures residence under the prescribed fields. It does not predict a self-consistent electron well.",
  ];
  const setup: [string, string][] = [
    ["Particles", number(run.particles)], ["Launch energy (eV)", number(run.energyEV)],
    ["Coil radius (m)", number(run.radiusM)], ["Coil current (A-turn)", number(run.sweep?.coilCurrentA ?? summary?.current_A)],
    ["Coil half-separation (m)", number(summary?.ring_half_sep_m)],
    ["Gun position x, y, z (m)", summary?.gun_position_m?.map(number).join(", ") ?? "Not recorded"],
    ["Gun direction unit vector", summary?.gun_direction_unit?.map(number).join(", ") ?? "Not recorded"],
    ["Injection aim (degrees)", number(poisson?.aimDeg ?? run.sweep?.aimDeg)], ["Cone half-angle (degrees)", poisson ? "Thermal velocity distribution" : number(run.sweep?.coneDeg)],
    ["Source RMS width (m)", number(summary?.gun_source_sigma_m)], [poisson ? "Injected current (A)" : "Prescribed proxy charge (C)", (poisson?.currentA ?? run.chargeC).toExponential(5)],
    ["Integrator", summary?.integrator ?? "Not recorded"],
    ["Adaptive timestep", summary?.adaptive == null ? "Not recorded" : summary.adaptive ? "Yes" : "No"],
    ["Magnetic field grid (r × z)", poisson ? "256 × 512" : run.sweep ? `${run.sweep.gridR} × ${run.sweep.gridZ}` : "Not recorded"],
    ["Gyroperiod timestep fraction", number(run.sweep?.gyroFraction)],
    ["Reference timestep (ps)", number(summary?.dt_s == null ? null : summary.dt_s * 1e12)],
    [poisson ? "Maximum ensemble |ΔE/E|" : "Maximum tracked |ΔE/E|", summary?.energy_drift_rel_max == null ? "Not recorded" : summary.energy_drift_rel_max.toExponential(4)],
    ["Stored trajectories / ensemble", `${run.tracked} / ${run.particles}`],
    ["Trajectory observation window (µs)", number(run.trajectoryWindowUs)],
  ];
  if (poisson) setup.push(
    ["Electrostatic mesh", `${poisson.nodes}³ · grounded box`],
    ["Source temperature (eV)", number(poisson.temperatureEV)],
    ["Orbit field centre φ (V)", number(poisson.orbitCentreV)],
    ["Deposited-charge centre φ (V)", number(poisson.depositedCentreV)],
    ["Fixed-point relative mismatch", number(poisson.fixedPointMismatch)],
    ["Poisson relative residual", poisson.poissonResidual.toExponential(4)],
    ["Mean core dwell (µs)", number(poisson.meanCoreDwellUs)],
    ["Mean core entries", number(poisson.meanCoreEntries)],
  );
  return `<article class="analysis-article run-report">
    <small>${escape(campaign)}</small><h1>${number(run.energyEV)} eV · ${number(run.radiusM * 100)} cm${run.sweep ? ` · ${number(run.sweep.coilCurrentA / 1000)} kA-turn · ${run.sweep.aimDeg}° aim` : ""}</h1>
    <p class="analysis-lead">${poisson ? `${escape(run.tag)} · stationary trajectory–Poisson reference` : "Fixed-field electron residence report"}</p>
    <section><h2>Findings</h2>${findings.map(f => `<p>${escape(f)}</p>`).join("")}</section>
    ${meta ? `<div class="report-charts"><section><h2>Residence / survival</h2>${survivalPlot(run, meta)}</section>
      <section><h2>Occupancy samples</h2>${occupancyPlot(meta)}</section></div>
      <section><h2>Outcomes at the observation cutoff</h2><div class="table-scroll"><table><thead><tr><th>Outcome</th><th>Particles</th><th>Ensemble share</th></tr></thead><tbody>
      ${meta.lossCounts.map((count, i) => `<tr><td><span style="color:${colors[i]}">●</span> ${outcomes[i]}</td><td>${number(count)}</td><td>${number(count / run.particles * 100)}%</td></tr>`).join("")}</tbody></table></div></section>` :
      "<p>This report currently has only the catalog summary. Static diagnostic plots require this run’s detailed metadata.</p>"}
    <section><h2>Run configuration & numerical diagnostics</h2><div class="table-scroll"><table><tbody>
      ${setup.map(([key, value]) => `<tr><th>${escape(key)}</th><td>${escape(value)}</td></tr>`).join("")}</tbody></table></div></section>
    <section><h2>Interpretation limits</h2><p>Energy diagnostics cover ${poisson ? "the entire ensemble" : "tracked particles, not the entire ensemble"}.
      Stored paths may undersample gyration. A small energy error alone does not establish orbit or loss convergence.
      Check timestep, field grid, sample size and observation window before interpreting rare surviving tails.</p>
      <p>${poisson ? "The charge and Poisson field are iterated from current-weighted residence. A small Poisson residual does not establish nonlinear convergence or a useful ion well. Refine the orbit cutoff, mesh, timestep and particle count." :
        "A prescribed charge sphere is an external proxy. This run contains no self-consistent space-charge feedback."}
        There are no ions, collisions, or fusion power balance. Dwell divided by a transit time is not a bounce count.</p></section>
    <footer class="analysis-source">Run ID: ${escape(run.id)}<br>Campaign: ${escape(run.study)}
      ${run.meta ? `<br>Metadata: ${escape(run.meta.path)} · SHA-256: ${escape(run.meta.sha256)}` : "<br>Source: catalog summary only"}
      <br>Report plots use saved diagnostics; no trajectory chunks are needed. Static HTML export contains no external assets.</footer>
  </article>`;
}

export function renderReport(host: HTMLElement, run: Run, meta: Meta | undefined, campaign: string): void {
  const report = contents(run, meta, campaign);
  host.innerHTML = `<div class="report-actions"><span>Selected run · static analysis</span>
    <button id="download-report">Download HTML</button><button id="print-report">Print / PDF</button></div>${report}`;
  host.querySelector<HTMLButtonElement>("#print-report")!.onclick = () => window.print();
  host.querySelector<HTMLButtonElement>("#download-report")!.onclick = () => {
    downloadStaticReport(report, run.tag, run.tag);
  };
}
