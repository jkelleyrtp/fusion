import type { Catalog, Run } from "./types";

const escape = (s: string): string => s.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const format = (n: number): string => Number(n.toPrecision(4)).toLocaleString("en-US");
export const campaignHref = (id: string): string => `#campaign/${encodeURIComponent(id)}`;
export const reportHref = (id: string): string => `#reports/${encodeURIComponent(id)}`;
const range = (values: number[]): string => {
  const lo = Math.min(...values), hi = Math.max(...values);
  return lo === hi ? format(lo) : `${format(lo)}–${format(hi)}`;
};
const runLabel = (run: Run): string => run.poisson
  ? `${run.tag} · ${format(run.poisson.currentA * 1e6)} µA · iteration ${run.poisson.iteration}/${run.poisson.requestedIterations}`
  : `${format(run.energyEV)} eV · ${format(run.radiusM * 100)} cm${
  run.sweep ? ` · ${format(run.sweep.coilCurrentA / 1000)} kA-turn · ${run.sweep.aimDeg}° aim · ${run.sweep.coneDeg}° cone` : ` · ${run.chargeC.toExponential(1)} C proxy`}`;

export function renderCampaignHome(host: HTMLElement, catalog: Catalog, age: (study: Catalog["studies"][number]) => string): void {
  const legacy = '<a class="campaign-row" href="#space-charge"><div><h2>Earlier Poisson pilot</h2><p>8 cases · partial results · no trajectory recording</p></div><span>View analysis →</span></a>';
  const hasPoisson = catalog.studies.some(study => study.model === "stationary-poisson");
  host.innerHTML = `<div class="page-title"><div><h1>Campaigns</h1><p>Poisson first · newest finished within each model</p></div><span>${catalog.runs.length} runs</span></div>
    ${hasPoisson ? "" : legacy}
    <div class="campaign-index">${catalog.studies.map(study => {
      const runs = catalog.runs.filter(run => run.study === study.id);
      if (!runs.length) return "";
      return `<a class="campaign-row" href="${campaignHref(study.id)}"><div><h2>${escape(study.label)}</h2>
        <p>${runs.length} runs · ${study.model === "stationary-poisson" ? "trajectory–Poisson feedback · " : ""}${range(runs.map(r => r.energyEV))} eV · ${range(runs.map(r => r.radiusM * 100))} cm coils</p></div>
        <span>${escape(age(study))} <b>→</b></span></a>`;
    }).join("")}</div>
    ${hasPoisson ? `<h2 class="reference-heading">Reference analyses</h2>${legacy}` : ""}`;
}

export function renderCampaignReport(heading: HTMLElement, details: HTMLElement, catalog: Catalog, run: Run, onPreview: (id: string) => void): void {
  const study = catalog.studies.find(s => s.id === run.study);
  const members = catalog.runs.filter(r => r.study === run.study);
  heading.innerHTML = `<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="#campaigns">Campaigns</a><span>/</span>${escape(study?.label ?? run.study)}</nav>
    <div class="page-title"><div><h1>${escape(study?.label ?? run.study)}</h1><p>${members.length} runs · campaign report</p></div></div>
    <div class="preview-picker"><label>Trajectory preview <select aria-label="Campaign trajectory preview">${members.map(r =>
      `<option value="${escape(r.id)}" ${r.id === run.id ? "selected" : ""}>${escape(runLabel(r))}${r.sweep ? ` · ${r.sweep.gridR}×${r.sweep.gridZ} · gyro ${r.sweep.gyroFraction}` : ""}</option>`).join("")}</select></label>
      <a href="${reportHref(run.id)}">Open this run’s report →</a></div>`;
  heading.querySelector<HTMLSelectElement>("select")!.onchange = event => onPreview((event.target as HTMLSelectElement).value);
  details.innerHTML = `${run.poisson ? '<p class="muted">Trajectories replay the latest saved orbit iteration in its frozen Poisson field. Solver iterations are not physical time. These reference cases require convergence checks.</p>' : ""}
    <h2>Individual runs</h2><p class="muted">Mean dwell is measured through each run’s observation window. † marks a censored lower bound.</p>
    <div class="table-scroll"><table><thead><tr><th>Run / settings</th><th>Mean dwell</th><th>Window</th><th>Remaining</th><th>Resolution</th></tr></thead>
    <tbody>${members.map(r => `<tr><td><a href="${reportHref(r.id)}">${escape(runLabel(r))}</a></td>
      <td>${r.meanDwellUs == null ? "—" : `${format(r.meanDwellUs)}${r.dwellLowerBound ? "†" : ""} µs`}</td>
      <td>${format(r.windowUs)} µs</td><td>${format(100 * r.survivors / r.particles)}%</td>
      <td>${r.poisson ? `${r.poisson.nodes}³ · ${r.particles} particles` : r.sweep ? `${r.sweep.gridR}×${r.sweep.gridZ} · gyro ${r.sweep.gyroFraction}` : "—"}</td></tr>`).join("")}</tbody></table></div>`;
}
