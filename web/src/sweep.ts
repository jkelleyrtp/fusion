import type { Run } from "./types";

const format = (n: number): string => Number(n.toPrecision(3)).toLocaleString("en-US");
const escape = (s: string): string => s.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const unique = (values: number[]): number[] => [...new Set(values)].sort((a, b) => a - b);
const resolution = (run: Run): string =>
  `${run.sweep!.gridR}/${run.sweep!.gridZ}/${run.sweep!.gyroFraction}`;

export class SweepPlot {
  private campaign = "";
  private cone = "";
  private grid = "";
  private metric = "transit";

  constructor(private root: HTMLElement, private onSelect: (id: string) => void) {}

  render(runs: Run[], campaign: string, title: string, selected?: string): void {
    const members = runs.filter(r => r.study === campaign && r.sweep);
    this.root.hidden = !members.length;
    if (!members.length) return;
    const cones = unique(members.map(r => r.sweep!.coneDeg));
    const grids = [...new Map(members.map(r => [resolution(r), r.sweep!])).entries()]
      .sort((a, b) => a[1].gridR - b[1].gridR || a[1].gridZ - b[1].gridZ || b[1].gyroFraction - a[1].gyroFraction);
    if (this.campaign !== campaign) {
      this.campaign = campaign;
      this.cone = String(cones[0]); this.grid = grids[0][0];
    }
    if (!cones.some(c => String(c) === this.cone)) this.cone = String(cones[0]);
    if (!grids.some(([key]) => key === this.grid)) this.grid = grids[0][0];
    const filtered = members.filter(r => String(r.sweep!.coneDeg) === this.cone && resolution(r) === this.grid);
    const energies = unique(members.map(r => r.energyEV));
    const currents = unique(members.map(r => r.sweep!.coilCurrentA));
    const angles = unique(members.map(r => r.sweep!.aimDeg)).reverse();
    const value = (r: Run): number | null => {
      if (this.metric === "survival") return r.survivors / r.particles * 100;
      if (r.meanDwellUs == null) return null;
      if (this.metric === "dwell") return r.meanDwellUs;
      return r.meanDwellUs * 1e-6 * Math.sqrt(2 * r.energyEV * 1.602176634e-19 / 9.1093837e-31) / r.radiusM;
    };
    const values = filtered.map(value).filter((v): v is number => v !== null && Number.isFinite(v));
    const maximum = Math.max(0, ...values);
    const unit = this.metric === "survival" ? "%" : this.metric === "dwell" ? "µs" : "× a/v₀";
    const caption = this.metric === "survival" ? "Present at window end" : "Mean residence through T";
    this.root.innerHTML = `
      <div class="sweep-heading"><div><h2>Sweep explorer</h2><p>${escape(title)}</p></div>
        <span class="tiny-label">${filtered.length} cases · click a cell for its run report</span></div>
      <div class="sweep-controls">
        <label>Color<select data-control="metric" aria-label="Heatmap color metric">
          <option value="transit" ${this.metric === "transit" ? "selected" : ""}>Dwell / transit time</option>
          <option value="dwell" ${this.metric === "dwell" ? "selected" : ""}>Dwell (µs)</option>
          <option value="survival" ${this.metric === "survival" ? "selected" : ""}>Present at window end (%)</option>
        </select></label>
        <label>Beam cone<select data-control="cone" aria-label="Beam cone half-angle">${cones.map(c =>
          `<option value="${c}" ${String(c) === this.cone ? "selected" : ""}>${format(c)}° half-angle</option>`).join("")}</select></label>
        <label>Resolution<select data-control="grid" aria-label="Sweep resolution">${grids.map(([key, g]) =>
          `<option value="${key}" ${key === this.grid ? "selected" : ""}>${g.gridR} × ${g.gridZ} · gyro ${g.gyroFraction}</option>`).join("")}</select></label>
      </div>
      <div class="sweep-scale"><span>${caption} (${unit})</span><b>0</b><i></i><b>${format(maximum)} ${unit}</b><span>Shared linear scale</span></div>
      <div class="grouped-heatmap-scroll"><div class="grouped-heatmap" style="--columns:${currents.length}" role="group" aria-label="Sweep heatmap grouped by energy and injection angle">
        <span class="axis-corner">Energy / window</span><span class="axis-corner">Aim</span>
        ${currents.map(c => `<span class="axis-tick">${format(c / 1000)} kA-turn</span>`).join("")}
        ${energies.map((energy, energyIndex) => {
        const panelRuns = filtered.filter(r => r.energyEV === energy);
        const windows = unique(panelRuns.map(r => r.windowUs));
        return `${energyIndex ? `<div class="heat-group-gap"></div>` : ""}
          <div class="heat-energy" style="grid-row:span ${angles.length}"><strong>${format(energy)} eV</strong>
            <small>${windows.length === 1 ? `T = ${format(windows[0])} µs` : panelRuns.length ? "Multiple windows" : "Not sampled"}</small></div>
            ${angles.map(angle => `<span class="axis-tick">${angle}°</span>${currents.map(current => {
              const candidates = panelRuns.filter(r => r.sweep!.aimDeg === angle && r.sweep!.coilCurrentA === current);
              const run = candidates.length === 1 ? candidates[0] : undefined;
              const v = run ? value(run) : null;
              if (!run || v == null || !Number.isFinite(v)) {
                return `<span class="heat-missing" title="${candidates.length > 1 ? "Multiple cases; refine the filters" : "No measured case"}">${candidates.length > 1 ? "Multiple" : "—"}</span>`;
              }
              const t = maximum > 0 ? v / maximum : 0;
              const color = `rgb(${Math.round(19 + 112 * t)},${Math.round(42 + 181 * t)},${Math.round(62 + 127 * t)})`;
              const censored = this.metric !== "survival" && run.dwellLowerBound;
              const description = `${format(current / 1000)} kA-turn, ${angle}° aim, ${format(energy)} eV: ${format(v)} ${unit}${censored ? ", finite-window lower bound" : ""}`;
              return `<button class="heat-cell ${run.id === selected ? "selected" : ""}" style="background:${color};color:${t > 0.48 ? "#0b1219" : "#dae5ed"}"
                data-sweep-run="${escape(run.id)}" aria-label="${escape(description)}" aria-pressed="${run.id === selected}" title="${escape(description)}">
                ${format(v)}${censored ? "<sup>†</sup>" : ""}</button>`;
            }).join("")}`).join("")}
          `;
      }).join("")}</div></div><div class="heat-axis">Coil current (kA-turn) · sampled settings</div>
      <p class="sweep-footnote">† Survivors are censored at T; dwell is a lower bound. a/v₀ normalizes the launch-speed scale, not a bounce count. — = no sample.</p>`;
    this.root.querySelectorAll<HTMLSelectElement>("select[data-control]").forEach(select => {
      select.onchange = () => {
        if (select.dataset.control === "metric") this.metric = select.value;
        if (select.dataset.control === "cone") this.cone = select.value;
        if (select.dataset.control === "grid") this.grid = select.value;
        this.render(runs, campaign, title, selected);
      };
    });
    this.root.querySelectorAll<HTMLButtonElement>("[data-sweep-run]").forEach(button => {
      button.onclick = () => this.onSelect(button.dataset.sweepRun!);
    });
  }
}
