// The Runs page: every WarpX case dispatched, its state on the cluster and what it measured.
// The data is the file warpx/runs_feed.py keeps, served at /api/runs.

type Measured = Record<string, unknown>;
type RunState = "running" | "queued" | "complete" | "failed" | "unfinished" | "not started" | "unknown";
interface Run {
  campaign: string; case: string; deck: string; changes: string[]; thread: string; state: RunState;
  done?: string; wall_s?: string; tries?: string; last_try?: string; finished?: number;
  step?: [number, number, number] | null; try_started?: number; stop_time?: number; max_step?: number; measured?: Measured | null;
}
interface Campaign { name: string; question: string; jobs: { job: string; submitted: string; gpus_per_case?: number }[]; busy: Record<string, number[]> }
interface Pod { pod: string; state: string; age: string; role: "node" | "launcher" }
interface Feed { written_at: number; cluster: { reachable: boolean; note: string; read_at: number; pods: Pod[] }; campaigns: Campaign[]; runs: Run[] }

const escape = (text: string): string => text.replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
const number = (value: unknown, digits = 3): string => typeof value === "number" && Number.isFinite(value)
  ? Number(value.toPrecision(digits)).toLocaleString("en-US", { maximumFractionDigits: 6 }) : "—";
const ago = (seconds: number): string => seconds < 90 ? `${Math.max(0, Math.round(seconds))} s ago`
  : seconds < 5400 ? `${Math.round(seconds / 60)} min ago` : seconds < 172800 ? `${(seconds / 3600).toFixed(1)} h ago` : `${Math.round(seconds / 86400)} d ago`;
const span = (seconds: number): string => seconds < 90 ? `${Math.round(seconds)} s` : seconds < 5400 ? `${Math.round(seconds / 60)} min` : `${(seconds / 3600).toFixed(1)} h`;
const first = (measured: Measured | null | undefined, keys: string[]): number | undefined => {
  for (const key of keys) if (typeof measured?.[key] === "number") return measured[key] as number;
  return undefined;
};
// Headline columns. Each takes the first of these measurements a run has, because the reducers name them by deck.
const holdingCrossings = (run: Run): number | undefined => first(run.measured, ["electrons_holding_time_in_electron_crossings"]);
const holdingNs = (run: Run): number | undefined => first(run.measured, ["electrons_holding_time_ns", "electrons_holding_time_in_feed_ns", "electron_loss_time_ns"]);
const energyKeV = (run: Run): number | undefined => { const eV = first(run.measured, ["electrons_mean_energy_eV"]); return eV === undefined ? undefined : eV / 1000; };
const leakMm = (run: Run): number | undefined => first(run.measured, ["electron_stream_half_height_in_gap_mm", "electron_stream_half_width_mm"]);
const fraction = (run: Run): number | undefined => !run.step ? undefined
  : run.stop_time ? Math.min(1, run.step[1] / run.stop_time) : run.max_step ? Math.min(1, run.step[0] / run.max_step) : undefined;
const stateLabel: Record<RunState, string> = { running: "Running", queued: "Queued", complete: "Complete", failed: "Failed",
  unfinished: "Left unfinished", "not started": "Not started", unknown: "Unknown" };
const order: RunState[] = ["running", "queued", "failed", "unfinished", "not started", "unknown", "complete"];

export class RunsPage {
  private feed?: Feed;
  private error = "";
  private timer = 0;
  private filter = "";
  private show: "all" | RunState = "all";
  private readonly open = new Set<string>();
  private readonly openThreads = new Set<string>();
  private threadsTouched = false;

  constructor(private readonly root: HTMLElement) {
    root.innerHTML = `<header class="runs-header"><div><h1>Runs</h1>
        <p class="muted">Every WarpX case dispatched to the cluster, grouped by the question it serves. Refreshes every 30 s.</p></div>
        <div class="runs-status" id="runs-status" role="status">Connecting…</div></header>
      <div class="runs-tally" id="runs-tally"></div>
      <div class="runs-controls"><input id="runs-filter" placeholder="Filter by case or campaign…" aria-label="Filter runs"/>
        <select id="runs-state" aria-label="State"><option value="all">All states</option>${order.map(state =>
          `<option value="${state}">${stateLabel[state]}</option>`).join("")}</select></div>
      <section id="runs-now"></section><section id="runs-threads"></section>`;
    root.querySelector<HTMLInputElement>("#runs-filter")!.oninput = event => { this.filter = (event.target as HTMLInputElement).value.trim().toLowerCase(); this.render(); };
    root.querySelector<HTMLSelectElement>("#runs-state")!.onchange = event => { this.show = (event.target as HTMLSelectElement).value as "all" | RunState; this.render(); };
    root.addEventListener("click", event => {
      const row = (event.target as HTMLElement).closest<HTMLElement>("[data-run]");
      if (!row || (event.target as HTMLElement).closest("a")) return;
      const key = row.dataset.run!;
      if (this.open.has(key)) this.open.delete(key); else this.open.add(key);
      this.render();
    });
    root.addEventListener("keydown", event => {
      const row = event.target as HTMLElement;
      if ((event.key === "Enter" || event.key === " ") && row.matches("[data-run]")) { event.preventDefault(); row.click(); }
    });
    root.addEventListener("toggle", event => {
      const details = event.target as HTMLDetailsElement;
      if (!details.dataset.thread) return;
      this.threadsTouched = true;
      if (details.open) this.openThreads.add(details.dataset.thread); else this.openThreads.delete(details.dataset.thread);
    }, true);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) void this.refresh(); });
    void this.refresh();
    setInterval(() => this.renderStatus(), 5000);
  }

  private async refresh(): Promise<void> {
    clearTimeout(this.timer);
    try {
      const response = await fetch("/api/runs", { cache: "no-store", signal: AbortSignal.timeout(20_000) });
      if (!response.ok) throw new Error(response.status === 503 ? "The run feed is not running on the server." : `Run feed answered ${response.status}.`);
      this.feed = await response.json() as Feed;
      this.error = "";
    } catch (error) {
      this.error = error instanceof Error ? error.message : "Run feed request failed.";
    }
    this.render();
    if (!document.hidden) this.timer = window.setTimeout(() => { void this.refresh(); }, 30_000);
  }

  private renderStatus(): void {
    const status = this.root.querySelector<HTMLElement>("#runs-status")!;
    const feed = this.feed;
    if (!feed) { status.textContent = this.error || "Connecting…"; status.classList.toggle("job-warning", Boolean(this.error)); return; }
    const age = Date.now() / 1000 - feed.written_at;
    const stale = age > 300 || Boolean(this.error) || !feed.cluster.reachable;
    status.classList.toggle("job-warning", stale);
    status.innerHTML = `<b>${this.error ? "Connection lost, showing the last copy" : age > 300 ? "Feed stopped" : feed.cluster.reachable ? "Live" : "Cluster not readable"}</b>
      · cluster read ${escape(ago(Date.now() / 1000 - feed.cluster.read_at))}${feed.cluster.note ? `<br>${escape(feed.cluster.note)}` : ""}`;
  }

  private row(run: Run, now: number): string {
    const key = `${run.campaign}/${run.case}`;
    const done = fraction(run);
    const progress = run.state === "running" && done !== undefined
      ? `<div class="iteration-progress"><progress max="1" value="${done}" aria-label="${escape(run.case)} progress"></progress><span>${Math.round(done * 100)}%</span></div>`
      : run.state === "unfinished" && done !== undefined ? `<span class="muted">stopped at ${Math.round(done * 100)}%</span>` : "";
    const gpu = run.last_try?.match(/^(\S+) gpu (\S+)/);
    const running = run.state === "running";
    // A finished run shows its whole run time and when it ended; a running one, where it is and how long this try has run.
    const timing = running
      ? `${gpu ? `job ${escape(gpu[1].slice(0, 6))} · GPU ${escape(gpu[2])}` : ""}${run.try_started ? ` · ${span(now - run.try_started)} this try` : ""}${Number(run.tries) > 1 ? ` · try ${escape(run.tries!)}` : ""}`
      : `${run.wall_s ? span(Number(run.wall_s)) : ""}${run.finished && (run.state === "complete" || run.state === "failed") ? ` · ${ago(now - run.finished)}` : ""}`;
    const detail = this.open.has(key) ? `<tr class="run-detail"><td colspan="8">
        ${run.done && run.done !== "complete" ? `<p class="job-warning">${escape(run.done)}</p>` : ""}
        <p class="muted">Campaign ${escape(run.campaign)} · deck ${escape(run.deck)}${gpu ? ` · job ${escape(gpu[1])}, GPU ${escape(gpu[2])}` : ""}${run.tries ? ` · ${escape(run.tries)} ${run.tries === "1" ? "try" : "tries"}` : ""}</p>
        <p class="run-changes">${run.changes.map(change => `<code>${escape(change)}</code>`).join(" ") || "No changes against the deck."}</p>
        ${run.measured ? `<dl class="run-measured">${Object.entries(run.measured).filter(([, value]) => value !== null && typeof value !== "object")
          .map(([name, value]) => `<div><dt>${escape(name.replaceAll("_", " "))}</dt><dd>${typeof value === "number" ? number(value, 4) : escape(String(value))}</dd></div>`).join("")}</dl>`
          : run.state === "complete" ? `<p class="muted">Complete, but no reduced measurements have been fetched.</p>` : ""}</td></tr>` : "";
    return `<tr data-run="${escape(key)}" class="run-row" tabindex="0" aria-expanded="${this.open.has(key)}"><th scope="row">${escape(run.case)}</th>
      <td><span class="case-status run-${run.state.replace(" ", "-")}">${stateLabel[run.state]}</span></td><td>${progress}</td>
      <td>${number(holdingCrossings(run))}</td><td>${number(holdingNs(run))}</td><td>${number(energyKeV(run))}</td><td>${number(leakMm(run))}</td>
      <td class="muted">${timing}</td></tr>${detail}`;
  }

  private table(runs: Run[], now: number, active = false): string {
    return `<div class="table-scroll"><table class="runs-table"><thead><tr><th>Case</th><th>State</th><th>Progress</th>
      <th title="Electron holding time, in electron crossings of the device">Holding (crossings)</th><th title="Electron holding time">Holding (ns)</th>
      <th title="Mean electron energy at the end">Electron energy (keV)</th><th title="Half-width of the escaping electron stream">Leak half-width (mm)</th>
      <th>${active ? "Where · how long" : "Run time · finished"}</th></tr></thead><tbody>${runs.map(run => this.row(run, now)).join("")}</tbody></table></div>`;
  }

  private render(): void {
    this.renderStatus();
    const feed = this.feed;
    if (!feed) return;
    const now = Date.now() / 1000;
    const count = (state: RunState): number => feed.runs.filter(run => run.state === state).length;
    const nodes = feed.cluster.pods.filter(pod => pod.role === "node" && pod.state === "Running");
    const busy = feed.campaigns.reduce((sum, campaign) => sum + Object.entries(campaign.busy)
      .filter(([job]) => nodes.some(pod => pod.pod.includes(job))).reduce((inner, [, gpus]) => inner + gpus.length, 0), 0);
    this.root.querySelector("#runs-tally")!.innerHTML = [
      [count("running"), "running"], [count("queued"), "queued"], [count("complete"), "complete"], [count("failed"), "failed"],
      [count("unfinished"), "left unfinished"], [nodes.length, nodes.length === 1 ? "node held" : "nodes held"],
      [feed.cluster.reachable ? `${busy}/${nodes.length * 8}` : "—", "GPUs busy"],
    ].map(([value, label]) => `<div><b>${value}</b><span>${label}</span></div>`).join("");
    const wanted = (run: Run): boolean => (this.show === "all" || run.state === this.show)
      && (!this.filter || `${run.case} ${run.campaign} ${run.thread}`.toLowerCase().includes(this.filter));
    const active = feed.runs.filter(run => run.state === "running" || run.state === "queued").filter(wanted)
      .sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || (fraction(b) ?? 0) - (fraction(a) ?? 0));
    const recent = feed.runs.filter(run => (run.state === "complete" || run.state === "failed") && run.finished && now - run.finished < 6 * 3600).filter(wanted)
      .sort((a, b) => b.finished! - a.finished!);
    this.root.querySelector("#runs-now")!.innerHTML = `<h2 class="runs-section">On the cluster now</h2>
      ${active.length ? this.table(active, now, true) : `<p class="job-empty">${feed.cluster.reachable ? "Nothing is running or queued." : "The cluster cannot be read right now."}</p>`}
      <h2 class="runs-section">Finished in the last 6 hours</h2>
      ${recent.length ? this.table(recent, now) : `<p class="job-empty">Nothing finished in the last 6 hours.</p>`}`;
    const threads = new Map<string, Run[]>();
    for (const run of feed.runs.filter(wanted)) threads.set(run.thread, [...(threads.get(run.thread) ?? []), run]);
    const latest = (runs: Run[]): number => Math.max(...runs.map(run => run.state === "running" || run.state === "queued" ? now : run.finished ?? 0));
    const sorted = [...threads.entries()].sort((a, b) => latest(b[1]) - latest(a[1]));
    if (!this.threadsTouched) for (const [name, runs] of sorted) if (runs.some(run => run.state === "running" || run.state === "queued")) this.openThreads.add(name);
    this.root.querySelector("#runs-threads")!.innerHTML = `<h2 class="runs-section">All runs, by research thread</h2>` + sorted.map(([name, runs]) => {
      const tally = order.filter(state => runs.some(run => run.state === state))
        .map(state => `<span class="run-${state.replace(" ", "-")}">${runs.filter(run => run.state === state).length} ${stateLabel[state].toLowerCase()}</span>`).join(" · ");
      const questions = [...new Set(runs.map(run => run.campaign))].map(campaign => feed.campaigns.find(entry => entry.name === campaign)!)
        .map(campaign => `<p class="run-question"><b>${escape(campaign.name)}</b> ${escape(campaign.question)}</p>`).join("");
      const rows = [...runs].sort((a, b) => order.indexOf(a.state) - order.indexOf(b.state) || (b.finished ?? 0) - (a.finished ?? 0));
      return `<details class="run-thread" data-thread="${escape(name)}" ${this.openThreads.has(name) || this.filter ? "open" : ""}>
        <summary><span>${escape(name)}</span><small>${tally}</small></summary>${questions}${this.table(rows, now)}</details>`;
    }).join("") || `<p class="job-empty">No run matches this filter.</p>`;
  }
}
