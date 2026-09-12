import type { CaseProgress, JobsResponse, SimulationJob } from "./job-types";

const escape = (value: string): string => value.replace(/[&<>"']/g, character =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]!);
const age = (value: string | null): string => {
  if (!value) return "not checked yet";
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(value)) / 1000));
  if (!Number.isFinite(seconds)) return "unknown";
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
};
const casePurpose: Record<string, string> = {
  vacuum: "Magnetic-only control",
  "1uA": "Low beam current",
  "10uA": "Reference beam current",
  "100uA": "Higher beam current",
  "10uA_grid": "65³ mesh · spatial resolution",
  "10uA_dt": "Half timestep · orbit accuracy",
  "10uA_particles": "4,096 particles · sampling",
  "10uA_duration": "400 ns window · cutoff sensitivity",
  "30kAt_vacuum": "30 kA-turn · magnetic-only control",
  "30kAt_1A": "30 kA-turn · 1 A electron beam",
  "100kAt_vacuum": "100 kA-turn · magnetic-only control",
  "100kAt_1A": "100 kA-turn · 1 A electron beam",
  broad_vacuum: "30 kA-turn · broad 3 cm / 0° vacuum control",
  broad_1A: "30 kA-turn · broad 3 cm / 0° · 1 A electron beam",
  compact_vacuum: "30 kA-turn · compact 50 µm / 10° vacuum control",
  compact_1A: "30 kA-turn · compact 50 µm / 10° · 1 A electron beam",
  pic_vacuum: "Transient magnetic-only control",
  pic_1mA: "Transient 1 mA beam",
  pic_1A: "Transient 1 A beam",
  pic_1A_dt: "Half timestep · matched macroparticle weight",
};
const caseLabel: Record<CaseProgress["status"], string> = {
  pending: "Awaiting snapshot",
  running: "Computing",
  completed: "Completed",
  timed_out: "Time limit",
  failed: "Failed",
};
function resultLabel(job: SimulationJob): string {
  if (job.launchError) return job.submissionState === "unknown" ? "Submission uncertain" : "Launch failed";
  if (["FAILED", "STOPPED", "CANCELLED"].includes(job.phase)) return `Scheduler ${job.phase.toLowerCase()}`;
  if (!job.progress) return job.phase || "Awaiting progress";
  if (job.progress.cases.some(item => item.status === "failed")) return "Case failed";
  if (job.progress.cases.some(item => item.status === "timed_out")) return "Partial results";
  if (job.progress.done && job.progress.cases.every(item => item.status === "completed")) return "Results ready";
  return "Computing";
}
function completed(job: SimulationJob): number {
  return job.progress?.cases.filter(item => item.status === "completed").length ?? 0;
}
function caseRow(item: CaseProgress, progressUnit: "iterations" | "steps"): string {
  const fraction = item.target > 0 ? Math.min(1, item.iteration / item.target) : 0;
  const unitLabel = progressUnit === "steps" ? "Steps" : "Iterations";
  const physicalTime = progressUnit === "steps" && item.physicalTimeS !== undefined
    ? ` · ${(item.physicalTimeS * 1e9).toLocaleString("en-US", { maximumSignificantDigits: 6 })} ns`
    : "";
  return `<tr><th scope="row">${escape(item.name)}</th>
    <td>${escape(casePurpose[item.name] ?? "Recorded variant")}</td>
    <td><div class="iteration-progress"><progress max="1" value="${fraction}" aria-label="${escape(item.name)} ${unitLabel}"></progress>
      <span>${item.iteration}/${item.target}${physicalTime}</span></div></td>
    <td><span class="case-status case-${item.status}">${caseLabel[item.status]}</span></td>
    <td class="muted" title="${escape(item.updatedAt ?? "No published snapshot")}">${escape(age(item.updatedAt))}</td></tr>`;
}
function jobArticle(job: SimulationJob, open: boolean): string {
  const progress = job.progress;
  const caseless = job.profile === "pic-cuda-validation";
  const progressUnit = progress?.progressUnit ?? (job.profile === "transient-pic" ? "steps" : "iterations");
  const errors = [job.launchError, job.brokerError && `Scheduler: ${job.brokerError}`,
    job.progressError && `Results: ${job.progressError}`].filter((error): error is string => Boolean(error));
  const pending = progress?.cases.length ?? 0;
  const source = job.sourceRevision ?? progress?.sourceRevision;
  const values = (key: string, scale = 1): string => [...new Set(progress?.cases.map(item =>
    (Number(item.settings[key]) * scale).toLocaleString()))].join(" / ");
  const setup = progress?.cases.length ? `${values("energy-ev")} eV · ${values("radius", 100)} cm coils · ${values("coil-current")} A-turn · ${values("aim-deg")}° aim` : caseless ? progress?.statusText || job.brokerMessage : "Settings will appear when the runner publishes its manifest.";
  const stale = !job.brokerCheckedAt || Date.now() - Date.parse(job.brokerCheckedAt) > 120_000;
  return `<article class="job-record" id="job-${escape(job.id)}">
    <div class="job-heading"><div><h2>${escape(job.title)}</h2><p>${escape(setup)}</p></div>
      <span class="job-result">${escape(resultLabel(job))}</span></div>
    <p class="job-purpose">${escape(progress?.purpose ?? job.purpose)}</p>
    <div class="job-facts">${caseless ? "" : `<span><b>${completed(job)}${pending ? `/${pending}` : ""}</b> cases completed</span>`}
      <span>${job.nodes} node · ${job.gpus} GPUs · priority ${job.priority}</span>
      <span>Scheduler: <b>${escape(job.phase)}</b>${stale ? " · last known" : ""}</span>
      ${job.restartCount || job.preemptedCount ? `<span>${job.restartCount} restarts · ${job.preemptedCount} preemptions</span>` : ""}
      ${job.campaignId ? `<a href="#campaign/${encodeURIComponent(job.campaignId)}">Open saved report →</a>` : ""}</div>
    ${errors.length ? `<p class="job-warning" role="status">${errors.map(escape).join("<br>")}<br>Previously saved state is retained; no automatic resubmission.</p>` : ""}
    ${progress
      ? caseless && !progress.cases.length
        ? `<p class="job-empty">${escape(progress.statusText ?? job.brokerMessage)}</p>`
        : `<div class="table-scroll"><table class="job-cases"><thead><tr><th>Variant</th><th>What it tests</th><th>${progressUnit === "steps" ? "Steps" : "Iterations"}</th><th>Result</th><th>Last snapshot</th></tr></thead>
      <tbody>${progress.cases.map(item => caseRow(item, progressUnit)).join("")}</tbody></table></div>
      <p class="job-footnote">${progressUnit === "steps" ? "Steps advance physical time. A completed startup run does not establish physical convergence." : "Iterations are stationary field updates, not elapsed physical time. Completing them does not establish convergence."}</p>`
      : `<p class="job-empty">Waiting for a published progress snapshot. Scheduler status is tracked separately.</p>`}
    <div class="job-timestamps"><span>Scheduler checked ${escape(age(job.brokerCheckedAt))}</span>
      <span>Progress checked ${escape(age(job.progressCheckedAt))}</span></div>
    <details data-job-details="${escape(job.id)}" ${open ? "open" : ""}><summary>Provenance & configuration</summary>
      <dl class="job-provenance"><dt>Broker job</dt><dd>${escape(job.brokerJobId ?? "Not assigned")}</dd>
        <dt>Source revision</dt><dd>${escape(source ?? "Not captured")}</dd>
        <dt>Output directory</dt><dd>${escape(job.runDirectory)}</dd>
        <dt>Attempt</dt><dd>${escape(progress?.attempt ?? "Not started")}</dd>
        <dt>Created</dt><dd>${escape(job.createdAt)}</dd></dl>
      ${progress?.statusText ? `<p>${escape(progress.statusText)}</p>` : ""}
      ${progress ? `<div class="job-command-settings">${progress.cases.map(item => `<h3>${escape(item.name)}</h3>
        <pre>${escape(Object.entries(item.settings).map(([key, value]) => `${key}: ${value}`).join("\n"))}</pre>`).join("")}</div>` : ""}
    </details></article>`;
}

export class JobMonitor {
  private jobs: SimulationJob[] = [];
  private error = "";
  private loading = false;
  private seen = false;
  private paused = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private campaignId: string | undefined;
  private readonly content: HTMLElement;
  private readonly status: HTMLElement;
  private readonly refreshButton: HTMLButtonElement;

  constructor(private readonly host: HTMLElement, private readonly home: HTMLElement,
    private readonly campaign: HTMLElement) {
    host.innerHTML = `<div class="page-title"><div><h1>Jobs</h1><p>Persistent scheduler state and published run progress</p></div>
      <button id="refresh-jobs" class="secondary">Refresh</button></div>
      <div class="job-service-status" role="status"></div><div class="job-records"></div>
      <p class="job-service-note">Updates every minute while this tab is visible. Only small status records are fetched.
        Reports contain separately imported trajectory snapshots. Launches use the server control CLI.</p>`;
    this.content = host.querySelector<HTMLElement>(".job-records")!;
    this.status = host.querySelector<HTMLElement>(".job-service-status")!;
    this.refreshButton = host.querySelector<HTMLButtonElement>("#refresh-jobs")!;
    this.refreshButton.onclick = () => { void this.refresh(); };
    document.addEventListener("visibilitychange", this.visibilityChanged);
    window.addEventListener("pagehide", () => this.dispose(), { once: true });
    void this.refresh();
  }

  setCampaign(id: string | undefined): void {
    this.campaignId = id;
    this.renderBanners();
  }

  setPaused(paused: boolean): void {
    this.paused = paused;
    if (paused) clearTimeout(this.timer);
    else void this.refresh();
    this.render();
  }

  private readonly visibilityChanged = (): void => {
    clearTimeout(this.timer);
    if (!document.hidden && !this.paused) void this.refresh();
  };

  dispose(): void {
    clearTimeout(this.timer);
    document.removeEventListener("visibilitychange", this.visibilityChanged);
  }

  private async refresh(): Promise<void> {
    if (this.loading || this.paused || document.hidden) return;
    clearTimeout(this.timer);
    this.loading = true;
    this.refreshButton.disabled = true;
    try {
      const response = await fetch("/api/jobs", { cache: "no-store", signal: AbortSignal.timeout(15_000) });
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) {
        throw new Error("Live job service unavailable. Saved reports remain accessible.");
      }
      const data: JobsResponse = await response.json();
      if (!Array.isArray(data.jobs)) throw new Error("Invalid job service response");
      this.jobs = data.jobs;
      this.error = "";
      this.seen = true;
    } catch (error) {
      this.error = error instanceof Error ? error.message : "Job service request failed";
    } finally {
      this.loading = false;
      this.refreshButton.disabled = this.paused;
      this.render();
      if (!this.paused && !document.hidden) this.timer = setTimeout(() => { void this.refresh(); }, 60_000);
    }
  }

  private render(): void {
    const open = new Set([...this.content.querySelectorAll<HTMLDetailsElement>("details[open]")]
      .map(element => element.dataset.jobDetails));
    this.status.textContent = this.paused ? "Offline mode · live updates paused" :
      this.error || (this.seen ? "Connected · server continues tracking when you leave this page" : "Connecting…");
    this.status.classList.toggle("job-warning", Boolean(this.error));
    this.content.innerHTML = this.jobs.length ? this.jobs.map(job => jobArticle(job, open.has(job.id))).join("") :
      `<p class="job-empty">${this.seen ? "No jobs registered yet. Launch or register a job through the server control CLI." : "No live job records loaded."}</p>`;
    this.renderBanners();
  }

  private renderBanners(): void {
    const latest = this.jobs[0];
    const banner = (job: SimulationJob): string => `<a class="job-banner" href="#jobs">
      <span><b>${escape(resultLabel(job))}</b> · ${escape(job.title)} · ${job.profile === "pic-cuda-validation" ? escape(job.phase || "Registered") : `${completed(job)}/${job.progress?.cases.length ?? "?"} cases`}</span>
      <span>${this.paused ? "Updates paused" : this.error ? "Connection lost · cached state" : `Scheduler ${escape(age(job.brokerCheckedAt))}`} · Job details →</span></a>`;
    this.home.innerHTML = latest ? banner(latest) :
      `<a class="job-banner muted" href="#jobs">${this.error ? "Live job service unavailable" : "Live jobs"} · View status →</a>`;
    const matching = this.jobs.find(job => job.campaignId === this.campaignId);
    this.campaign.innerHTML = matching ? banner(matching) : "";
    this.campaign.hidden = !matching;
  }
}
