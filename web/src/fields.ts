import type { DataStore } from "./data";
import type { Run } from "./types";

type Field = "deposited" | "orbit" | "relaxed" | "density" | "relaxedDensity" | "magnetic" | "electric";
type Plane = "yz" | "xz" | "xy";
interface Slice { u: number[]; v: number[]; uAxis: string; vAxis: string; fixedAxis: string; fixedM: number; values: number[] }
interface Snapshot { iteration: number; fields: Record<Field, Record<Plane, Slice>> }
interface FieldData {
  version: number; coreRadiusM: number; snapshots: Snapshot[]; requestedIterations: number;
  history: { iteration: number; core_centre_potential_V: number; deposited_potential_min_V: number }[];
}
const labels: Record<Field, [string, string]> = {
  deposited: ["Deposited potential", "V"], orbit: ["Orbit potential", "V"],
  relaxed: ["Relaxed potential", "V"], relaxedDensity: ["Relaxed electron density", "m⁻³"],
  density: ["Electron density", "m⁻³"], magnetic: ["Magnetic |B|", "T"], electric: ["Orbit |E|", "V/m"],
};
const number = (n: number): string => n === 0 ? "0" : Math.abs(n) < 0.001 || Math.abs(n) >= 1e5 ? n.toExponential(2) : Number(n.toPrecision(4)).toString();
const color = (t: number): string => `rgb(${Math.round(24 + 215 * t)},${Math.round(45 + 175 * t)},${Math.round(90 + 25 * t)})`;

export class FieldView {
  private data?: FieldData;
  private run?: Run;
  private request = 0;
  private field: Field = "deposited";
  private plane: Plane = "yz";
  private index = 0;
  private visible = false;

  constructor(private host: HTMLElement, private store: DataStore) {}

  setRun(run: Run): void {
    this.run = run; this.data = undefined; this.request++;
    this.host.textContent = run.fields ? "Open Fields to load compressed maps." : "Field grids were not recorded for this run.";
    if (this.visible) void this.show();
  }

  hide(): void { this.visible = false; }

  async show(): Promise<void> {
    this.visible = true;
    if (!this.run?.fields) return;
    if (this.data) { this.render(); return; }
    const request = ++this.request;
    this.host.textContent = "Loading compressed field slices…";
    try {
      const data = await this.store.json<FieldData>(this.run.fields);
      if (request !== this.request) return;
      if (data.version !== 1 || !data.snapshots.length) throw new Error("Unsupported field archive");
      this.data = data; this.index = data.snapshots.length - 1; this.render();
    } catch (error) {
      if (request === this.request) this.host.textContent = error instanceof Error ? error.message : String(error);
    }
  }

  private render(): void {
    const data = this.data;
    if (!data) return;
    const snapshot = data.snapshots[this.index];
    const slice = snapshot.fields[this.field][this.plane];
    let lo = Infinity, hi = -Infinity;
    for (const step of data.snapshots) for (const plane of Object.values(step.fields[this.field])) {
      for (const value of plane.values) { lo = Math.min(lo, value); hi = Math.max(hi, value); }
    }
    const [title, unit] = labels[this.field];
    const left = 65, top = 22, width = 710;
    const height = Math.min(450, width * (slice.v.at(-1)! - slice.v[0]) / (slice.u.at(-1)! - slice.u[0]));
    const actualWidth = height * (slice.u.at(-1)! - slice.u[0]) / (slice.v.at(-1)! - slice.v[0]);
    const x = (u: number): number => left + (u - slice.u[0]) / (slice.u.at(-1)! - slice.u[0]) * actualWidth;
    const y = (v: number): number => top + height - (v - slice.v[0]) / (slice.v.at(-1)! - slice.v[0]) * height;
    const dx = actualWidth / (slice.u.length - 1), dy = height / (slice.v.length - 1);
    const cells = slice.values.map((value, i) => {
      const col = i % slice.u.length, row = Math.floor(i / slice.u.length);
      return `<rect x="${x(slice.u[col]) - dx / 2}" y="${y(slice.v[row]) - dy / 2}" width="${dx + 0.1}" height="${dy + 0.1}" fill="${color(hi === lo ? 0 : (value - lo) / (hi - lo))}"><title>${slice.uAxis}=${number(slice.u[col])} m, ${slice.vAxis}=${number(slice.v[row])} m: ${number(value)} ${unit}</title></rect>`;
    }).join("");
    const ticks = Array.from({ length: 5 }, (_, i) => {
      const u = slice.u[0] + i / 4 * (slice.u.at(-1)! - slice.u[0]);
      const v = slice.v[0] + i / 4 * (slice.v.at(-1)! - slice.v[0]);
      return `<text x="${x(u)}" y="${top + height + 22}" text-anchor="middle">${number(u)}</text><text x="${left - 10}" y="${y(v) + 4}" text-anchor="end">${number(v)}</text>`;
    }).join("");
    const coreRadius = Math.sqrt(Math.max(0, data.coreRadiusM ** 2 - slice.fixedM ** 2));
    this.host.innerHTML = `
      <div class="field-controls">
        <label>Field<select data-field aria-label="Field quantity">${Object.entries(labels).map(([key, value]) => `<option value="${key}" ${key === this.field ? "selected" : ""}>${value[0]}</option>`).join("")}</select></label>
        <label>Plane<select data-plane aria-label="Field plane">${(["yz", "xz", "xy"] as Plane[]).map(key => `<option ${key === this.plane ? "selected" : ""}>${key}</option>`).join("")}</select></label>
        <label>Solver iteration<select data-iteration aria-label="Field solver iteration">${data.snapshots.map((step, i) => `<option value="${i}" ${i === this.index ? "selected" : ""}>${step.iteration} / ${data.requestedIterations}</option>`).join("")}</select></label>
      </div>
      <p class="field-caption">${title} · ${slice.fixedAxis} = ${number(slice.fixedM)} m · shared color scale across saved field snapshots</p>
      <svg class="field-map" viewBox="0 0 900 ${height + 82}" role="img" aria-label="${title}, ${this.plane} slice at iteration ${snapshot.iteration}">
        <defs><clipPath id="field-clip"><rect x="${left}" y="${top}" width="${actualWidth}" height="${height}"/></clipPath>
        <linearGradient id="field-gradient" x1="0" y1="1" x2="0" y2="0"><stop stop-color="${color(0)}"/><stop offset="1" stop-color="${color(1)}"/></linearGradient></defs>
        <g clip-path="url(#field-clip)">${cells}<circle cx="${x(0)}" cy="${y(0)}" r="${coreRadius * actualWidth / (slice.u.at(-1)! - slice.u[0])}" fill="none" stroke="white" stroke-dasharray="4 4" opacity=".7"/>
        <path d="M${x(0) - 6},${y(0)}h12 M${x(0)},${y(0) - 6}v12" stroke="white"/></g>
        ${ticks}<text x="${left + actualWidth / 2}" y="${height + 68}" text-anchor="middle">${slice.uAxis} (m)</text><text transform="translate(18,${top + height / 2}) rotate(-90)" text-anchor="middle">${slice.vAxis} (m)</text>
        <rect x="810" y="${top}" width="14" height="${height}" fill="url(#field-gradient)"/>
        <text x="834" y="${top + 10}">${number(hi)}</text><text x="834" y="${top + height}">${number(lo)}</text><text x="810" y="${height + 50}">${unit}</text>
      </svg>
      <p class="field-caption">${this.description()} Dashed circle: diagnostic core; cross: geometric centre.</p>
      <p class="field-caption">${data.snapshots.length === 1 ? "Only the final field grid was retained for this run. " : ""}Solver iterations are not physical time.</p>
      ${this.historyPlot(data)}`;
    this.host.querySelector<HTMLSelectElement>("[data-field]")!.onchange = event => {
      this.field = (event.target as HTMLSelectElement).value as Field; this.render();
    };
    this.host.querySelector<HTMLSelectElement>("[data-plane]")!.onchange = event => {
      this.plane = (event.target as HTMLSelectElement).value as Plane; this.render();
    };
    this.host.querySelector<HTMLSelectElement>("[data-iteration]")!.onchange = event => {
      this.index = Number((event.target as HTMLSelectElement).value); this.render();
    };
  }

  private description(): string {
    if (this.field === "density") return "Residence-weighted deposition from all simulated particles, divided by −e × cell volume. No azimuthal averaging.";
    if (this.field === "relaxedDensity") return "Relaxed charge density carried into the next solver iteration, divided by −e.";
    if (this.field === "relaxed") return "Relaxed potential prepared for the next solver iteration.";
    if (this.field === "magnetic") return "Reconstructed imposed |B|. The central magnetic null does not imply an electrostatic well or particle capture.";
    if (this.field === "electric") return "Nodal finite-difference |E| from the orbit potential; a visualization diagnostic, not the exact particle gather.";
    if (this.field === "orbit") return "Frozen potential used to trace this iteration’s trajectories.";
    return "Potential generated by this iteration’s deposited electron charge. It may differ from the orbit potential until convergence.";
  }

  private historyPlot(data: FieldData): string {
    const minimum = Math.min(-1, ...data.history.map(row => row.deposited_potential_min_V));
    const series = (key: "core_centre_potential_V" | "deposited_potential_min_V"): string => data.history.map((row, i) =>
      `${65 + i / Math.max(1, data.history.length - 1) * 710},${20 + row[key] / minimum * 135}`).join(" ");
    return `<div class="field-history"><h3>Potential across solver iterations</h3>
      <svg viewBox="0 0 900 195" role="img" aria-label="Deposited centre and minimum potential across solver iterations">
      <path d="M65,20v135h710" stroke="#536574" fill="none"/>
      <polyline points="${series("core_centre_potential_V")}" fill="none" stroke="#83dfbd" stroke-width="2"/>
      <polyline points="${series("deposited_potential_min_V")}" fill="none" stroke="#e8a585" stroke-width="2"/>
      <text x="55" y="24" text-anchor="end">0 V</text><text x="55" y="155" text-anchor="end">${number(minimum)}</text>
      <text x="65" y="180">1</text><text x="775" y="180" text-anchor="end">${data.history.length}</text>
      <text x="420" y="180" text-anchor="middle">Solver iteration</text>
      <text x="810" y="50" fill="#83dfbd">Centre</text><text x="810" y="75" fill="#e8a585">Minimum</text></svg></div>`;
  }
}
