import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { mkdir, chmod, readFile, readdir, rename, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import type { CaseProgress, JobsResponse, RunProgress, SimulationJob } from "../src/job-types.ts";
import { POISSON_PROFILE, PROFILES, poissonEntrypoint } from "./profile.ts";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const CLUSTER = "aws-usw2";
const RESEARCH_DIR = process.env.FUSION_RESEARCH_DIR ?? "/home/ubuntu/repos/research";
const KUBECTL_CONTEXT = process.env.FUSION_KUBECTL_CONTEXT ?? "cog-usw2-b200-ml-dev-devin";
const WRITE_POD = process.env.FUSION_WRITE_POD ?? "devin-public-aws";
const READ_POD = process.env.FUSION_READ_POD ?? "alex-aws-ckpt-helper";
const REMOTE_SOURCE_ROOT = "/public/devcontainer-shared/jonathan/cusp/sources";
const POLL_INTERVAL_MS = 60_000;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const NAME_RE = /^[A-Za-z0-9_-]+$/;
const BROKER_ID_RE = /^[A-Za-z0-9_.-]+$/;

type CommandResult = { stdout: Buffer; stderr: Buffer; code: number };
type CommandRunner = (argv: string[], input?: Buffer, timeoutMs?: number, cwd?: string) => Promise<CommandResult>;
type StoredJob = SimulationJob & {
  requestId: string | null;
  dispatchStarted?: boolean;
  templateYaml: string | null;
  templatePath: string | null;
  sourcePath: string | null;
  capacityAudit: { checkedAt: string; gpus: string; jobs: string } | null;
};

type ServiceOptions = {
  root?: string;
  stateDir?: string;
  command?: CommandRunner;
  now?: () => Date;
  poll?: boolean;
};

function commandRunner(defaultCwd: string): CommandRunner {
  return (argv, input, timeoutMs = 30_000, cwd = defaultCwd) => new Promise((resolvePromise, reject) => {
    const [file, ...args] = argv;
    const child = execFile(file, args, { cwd, encoding: "buffer", maxBuffer: 32 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (error && typeof (error as NodeJS.ErrnoException).code !== "number") {
        reject(error);
        return;
      }
      const code = error ? Number((error as NodeJS.ErrnoException).code) || 1 : 0;
      resolvePromise({ stdout: Buffer.from(stdout as Buffer), stderr: Buffer.from(stderr as Buffer), code });
    });
    if (input) child.stdin?.end(input);
    const timer = setTimeout(() => child.kill("SIGTERM"), timeoutMs);
    child.once("close", () => clearTimeout(timer));
  });
}

function text(result: CommandResult): string {
  return result.stdout.toString("utf8");
}

function fail(message: string): never {
  throw new Error(message);
}

function validateUuid(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !UUID_RE.test(value)) fail(`Invalid ${label}`);
}

function validateName(value: unknown, label: string): asserts value is string {
  if (typeof value !== "string" || !NAME_RE.test(value) || value.length > 160) fail(`Invalid ${label}`);
}

function validateBrokerId(value: unknown): asserts value is string {
  if (typeof value !== "string" || !BROKER_ID_RE.test(value) || value.length > 200) fail("Invalid brokerJobId");
}

export function parseBrokerShow(output: string): {
  jobId: string;
  phase: string;
  restartCount: number;
  preemptedCount: number;
  message: string;
} {
  const fields = new Map<string, string>();
  const plain = output.split(/^# template\.yaml/m)[0];
  for (const line of plain.split(/\r?\n/)) {
    const match = line.match(/^([a-z_]+)\s{2,}(.+?)\s*$/i);
    if (match) fields.set(match[1], match[2]);
  }
  const jobId = fields.get("job_id");
  const phase = fields.get("phase");
  if (!jobId || !phase) fail("Malformed broker show output: missing job_id or phase");
  const parseIntField = (name: string): number => {
    const raw = fields.get(name);
    if (!raw || !/^\d+$/.test(raw)) fail(`Malformed broker show output: invalid ${name}`);
    return Number(raw);
  };
  return {
    jobId,
    phase,
    restartCount: parseIntField("restart_count"),
    preemptedCount: parseIntField("preempted_count"),
    message: fields.get("message") ?? "",
  };
}

export function parseFreeNodes(output: string): number {
  const lines = output.split(/\r?\n/);
  const header = lines.find((line) => line.includes("FREE") && line.includes("HEALTHY"));
  if (!header) fail("Malformed capacity output: missing FREE column");
  const headerCells = header.split(/[│┃]/).map((cell) => cell.trim());
  const freeIndex = headerCells.findIndex((cell) => cell === "FREE");
  if (freeIndex < 0) fail("Malformed capacity output: missing FREE column");
  let rows = 0;
  let free = 0;
  for (const line of lines) {
    if (!line.includes("│") && !line.includes("┃")) continue;
    const cells = line.split(/[│┃]/).map((cell) => cell.trim());
    if (cells.length <= freeIndex || !/^ip-[A-Za-z0-9.-]+$/.test(cells[1] ?? "")) continue;
    if (!/^\d+$/.test(cells[freeIndex])) fail("Malformed capacity output: invalid FREE value");
    rows += 1;
    free += Number(cells[freeIndex]);
  }
  if (!rows) fail("Malformed capacity output: no clique rows");
  return free;
}

function parseRunProgress(value: unknown): RunProgress | null {
  if (value === null) return null;
  if (!value || typeof value !== "object") fail("Malformed progress response");
  const run = value as Record<string, unknown>;
  if (typeof run.attempt !== "string" || typeof run.sourceRevision !== "string" || typeof run.purpose !== "string") fail("Malformed progress identity");
  if (typeof run.done !== "boolean" || (run.statusText !== null && typeof run.statusText !== "string")) fail("Malformed progress status");
  if (run.progressUnit !== undefined && !["iterations", "steps"].includes(String(run.progressUnit))) {
    fail("Malformed progress unit");
  }
  if (!Array.isArray(run.cases)) fail("Malformed progress cases");
  const cases: CaseProgress[] = run.cases.map((item) => {
    if (!item || typeof item !== "object") fail("Malformed progress case");
    const row = item as Record<string, unknown>;
    if (typeof row.name !== "string" || typeof row.iteration !== "number" || typeof row.target !== "number") fail("Malformed progress case values");
    if (!["pending", "running", "completed", "timed_out", "failed"].includes(String(row.status))) fail("Malformed progress case status");
    if (row.exitCode !== null && typeof row.exitCode !== "number") fail("Malformed progress exit code");
    if (row.updatedAt !== null && typeof row.updatedAt !== "string") fail("Malformed progress timestamp");
    if (row.physicalTimeS !== undefined && (typeof row.physicalTimeS !== "number" || !Number.isFinite(row.physicalTimeS) || row.physicalTimeS < 0)) fail("Malformed progress physical time");
    if (!row.settings || typeof row.settings !== "object") fail("Malformed progress settings");
    return row as unknown as CaseProgress;
  });
  return { attempt: run.attempt, sourceRevision: run.sourceRevision, purpose: run.purpose, done: run.done, statusText: run.statusText as string | null, progressUnit: run.progressUnit as RunProgress["progressUnit"], cases };
}

function responseJob(job: StoredJob): SimulationJob {
  const publicJob = { ...job } as Partial<StoredJob>;
  delete publicJob.requestId;
  delete publicJob.dispatchStarted;
  delete publicJob.templateYaml;
  delete publicJob.templatePath;
  delete publicJob.sourcePath;
  delete publicJob.capacityAudit;
  return publicJob as SimulationJob;
}

export class JobService {
  readonly root: string;
  readonly stateDir: string;
  readonly jobsDir: string;
  readonly tokenPath: string;
  private readonly command: CommandRunner;
  private readonly now: () => Date;
  private readonly locks = new Map<string, Promise<void>>();
  private createLock = Promise.resolve();
  private timer: ReturnType<typeof setInterval> | null = null;
  private polling = false;
  private token: string | null = null;

  constructor(options: ServiceOptions = {}) {
    this.root = options.root ?? ROOT;
    this.stateDir = options.stateDir ?? process.env.FUSION_STATE_DIR ?? join(this.root, ".fusion");
    this.jobsDir = join(this.stateDir, "jobs");
    this.tokenPath = process.env.FUSION_CONTROL_TOKEN ?? join(this.stateDir, "control-token");
    this.command = options.command ?? commandRunner(this.root);
    this.now = options.now ?? (() => new Date());
    if (options.poll !== false) this.timer = setInterval(() => { this.pollAll().catch(() => undefined); }, POLL_INTERVAL_MS);
  }

  async initialize(): Promise<void> {
    await mkdir(this.jobsDir, { recursive: true, mode: 0o700 });
    this.token = await this.ensureToken();
    const names = await readdir(this.jobsDir).catch(() => []);
    for (const name of names.filter((entry) => entry.endsWith(".json"))) {
      const job = await this.readStored(name.slice(0, -5));
      if (job.submissionState === "preparing" || job.submissionState === "submitting") {
        job.submissionState = job.dispatchStarted || job.submissionState === "submitting" ? "unknown" : "failed";
        job.launchError = "Service restarted during submission; no automatic retry was attempted.";
        job.updatedAt = this.now().toISOString();
        await this.writeStored(job);
      }
    }
  }

  async close(): Promise<void> {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  getToken(): string {
    if (!this.token) fail("Job service has not been initialized");
    return this.token;
  }

  async jobs(): Promise<JobsResponse> {
    const names = await readdir(this.jobsDir).catch(() => []);
    const jobs: SimulationJob[] = [];
    for (const name of names.filter((entry) => entry.endsWith(".json"))) {
      jobs.push(responseJob(await this.readStored(name.slice(0, -5))));
    }
    jobs.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    return { jobs, pollIntervalMs: POLL_INTERVAL_MS };
  }

  async launch(requestId: string): Promise<SimulationJob> {
    validateUuid(requestId, "requestId");
    const prior = this.createLock;
    const created = prior.then(async () => {
      const existing = await this.findRequest(requestId);
      if (existing) return responseJob(existing);
      const now = this.now().toISOString();
      const job: StoredJob = {
        id: randomUUID(), profile: POISSON_PROFILE.id, title: POISSON_PROFILE.title, purpose: POISSON_PROFILE.purpose,
        createdAt: now, updatedAt: now, sourceRevision: null, brokerJobId: null, phase: "PREPARING",
        submissionState: "preparing", cluster: CLUSTER, priority: 1, nodes: 1, gpus: 8,
        runDirectory: "", campaignId: null, progress: null, brokerCheckedAt: null, progressCheckedAt: null,
        brokerError: null, progressError: null, launchError: null, restartCount: 0, preemptedCount: 0,
        brokerMessage: "", requestId, dispatchStarted: false, templateYaml: null, templatePath: null, sourcePath: null, capacityAudit: null,
      };
      await this.writeStored(job);
      void this.performLaunch(job.id).catch((error) => { console.error("launch dispatch failed", error); });
      return responseJob(job);
    });
    this.createLock = created.then(() => undefined, () => undefined);
    return created;
  }

  async register(brokerJobId: string, runDirectory: string, campaignId: string | null, title: string, profileId: string = POISSON_PROFILE.id): Promise<SimulationJob> {
    validateBrokerId(brokerJobId); validateName(runDirectory, "runDirectory");
    if (campaignId !== null) validateName(campaignId, "campaignId");
    if (typeof title !== "string" || !title.trim() || title.length > 200) fail("Invalid title");
    if (!Object.hasOwn(PROFILES, profileId)) fail("Invalid profile");
    const profile = PROFILES[profileId as keyof typeof PROFILES];
    if (!profile) fail("Invalid profile");
    const existing = (await this.jobs()).jobs.find((job) => job.brokerJobId === brokerJobId);
    if (existing) {
      await this.mutate(existing.id, (stored) => {
        stored.profile = profile.id;
        stored.title = title;
        stored.purpose = profile.purpose;
        stored.nodes = profile.nodes;
        stored.gpus = profile.gpus;
        stored.runDirectory = runDirectory;
        stored.campaignId = campaignId;
      });
      return (await this.jobs()).jobs.find((job) => job.id === existing.id) ?? existing;
    }
    const now = this.now().toISOString();
    const job: StoredJob = {
      id: randomUUID(), profile: profile.id, title, purpose: profile.purpose,
      createdAt: now, updatedAt: now, sourceRevision: null, brokerJobId, phase: "REGISTERED",
      submissionState: "submitted", cluster: CLUSTER, priority: 1, nodes: profile.nodes, gpus: profile.gpus,
      runDirectory, campaignId, progress: null, brokerCheckedAt: null, progressCheckedAt: null,
      brokerError: null, progressError: null, launchError: null, restartCount: 0, preemptedCount: 0,
      brokerMessage: "Registered existing broker job", requestId: null, templateYaml: null, templatePath: null,
      sourcePath: null, capacityAudit: null,
    };
    await this.writeStored(job);
    return responseJob(job);
  }

  private async findRequest(requestId: string): Promise<StoredJob | null> {
    const names = await readdir(this.jobsDir).catch(() => []);
    for (const name of names.filter((entry) => entry.endsWith(".json"))) {
      const job = await this.readStored(name.slice(0, -5));
      if (job.requestId === requestId) return job;
    }
    return null;
  }

  private async performLaunch(id: string): Promise<void> {
    try {
      await this.mutate(id, (job) => { job.submissionState = "preparing"; job.phase = "PREPARING"; });
      const revisionResult = await this.command(["git", "rev-parse", "HEAD"], undefined, 10_000);
      if (revisionResult.code !== 0) fail(`git rev-parse failed: ${revisionResult.stderr.toString()}`);
      const revision = text(revisionResult).trim();
      if (!/^[a-f0-9]{40}$/.test(revision)) fail("Invalid git revision");
      const clean = await this.command(["git", "status", "--porcelain", "--", "src", "jobs"], undefined, 10_000);
      if (clean.code !== 0 || text(clean).trim()) fail("src/ and jobs/ must be clean before launch");
      const archive = await this.command(["git", "archive", revision, "src"], undefined, 30_000);
      if (archive.code !== 0) fail(`git archive failed: ${archive.stderr.toString()}`);
      const destination = `${REMOTE_SOURCE_ROOT}/${revision}-${id}`;
      const stage = await this.command(["kubectl", "--context", KUBECTL_CONTEXT, "exec", "-i", "-n", "default", WRITE_POD, "--", "sh", "-c", `mkdir -p '${REMOTE_SOURCE_ROOT}' && test ! -e '${destination}' && mkdir '${destination}' && tar -xf - -C '${destination}'`], archive.stdout, 60_000);
      if (stage.code !== 0) fail(`source staging failed: ${stage.stderr.toString()}`);
      const template = JSON.parse(await readFile(join(this.root, "jobs", "poisson-server-template.json"), "utf8")) as Record<string, unknown>;
      const metadata = template.metadata as Record<string, unknown>;
      const spec = template.spec as Record<string, unknown>;
      const brokerName = `fusion-poisson-${id.replaceAll("-", "").slice(0, 12)}`;
      metadata.name = brokerName;
      spec.entrypoint = poissonEntrypoint(id, revision);
      const templateYaml = `${JSON.stringify(template, null, 2)}\n`;
      const templatePath = join(this.jobsDir, `${id}.yaml`);
      await writeFile(templatePath, templateYaml, { mode: 0o600 });
      const runDirectory = id;
      await this.mutate(id, (job) => {
        job.sourceRevision = revision; job.sourcePath = `${destination}/src`; job.templateYaml = templateYaml; job.templatePath = templatePath;
        job.runDirectory = runDirectory; job.submissionState = "submitting"; job.phase = "SUBMITTING";
      });
      const gpus = await this.command(["uv", "run", "train", "gpus", "--cluster", CLUSTER], undefined, 30_000, RESEARCH_DIR);
      const jobs = await this.command(["uv", "run", "train", "job", "list", "--show-all", "--cluster", CLUSTER], undefined, 30_000, RESEARCH_DIR);
      if (gpus.code !== 0 || jobs.code !== 0) fail("Capacity check command failed");
      if (parseFreeNodes(text(gpus)) < 1) fail("No free GPU node available; launch was not submitted");
      await this.mutate(id, (job) => { job.capacityAudit = { checkedAt: this.now().toISOString(), gpus: text(gpus), jobs: text(jobs) }; });
      this.validateTemplate(template);
      await this.mutate(id, (job) => { job.dispatchStarted = true; });
      const submitted = await this.command(["uv", "run", "train", "job", "submit", templatePath, "--cluster", CLUSTER, "--priority", "1"], undefined, 60_000, RESEARCH_DIR);
      const match = text(submitted).match(/submitted\s+([A-Za-z0-9_.-]+)\s+\(phase\s+([^\)]+)\)/);
      if (submitted.code !== 0 || !match) {
        await this.mutate(id, (job) => { job.submissionState = "unknown"; job.phase = "UNKNOWN"; job.launchError = `Submission outcome unknown: ${text(submitted)}${submitted.stderr.toString()}`; });
        return;
      }
      await this.mutate(id, (job) => { job.brokerJobId = match[1]; job.phase = match[2]; job.submissionState = "submitted"; job.brokerMessage = "Submitted by fusion control service"; });
    } catch (error) {
      await this.mutate(id, (job) => {
        const ambiguous = job.dispatchStarted || job.submissionState === "unknown";
        job.submissionState = ambiguous ? "unknown" : "failed";
        job.phase = ambiguous ? "UNKNOWN" : "FAILED";
        job.launchError = error instanceof Error ? error.message : String(error);
      });
    }
  }

  private validateTemplate(template: Record<string, unknown>): void {
    const spec = template.spec as Record<string, unknown>;
    const entrypoint = String(spec.entrypoint);
    if (spec.shutdownAfterJobFinishes !== true || spec.ttlSecondsAfterFinished !== 600) fail("Template violates shutdown/TTL policy");
    if (!entrypoint.includes("--actor-num-nodes 1") || !entrypoint.includes("--actor-num-gpus-per-node 8") || !entrypoint.includes("--rollout-num-gpus 0")) fail("Template violates one-node GPU policy");
  }

  async pollAll(): Promise<void> {
    if (this.polling) return;
    this.polling = true;
    try {
      const jobs = await this.jobs();
      for (const job of jobs.jobs.filter((item) => item.brokerJobId && item.submissionState === "submitted")) await this.pollJob(job.id);
    } finally { this.polling = false; }
  }

  private async pollJob(id: string): Promise<void> {
    const job = await this.readStored(id);
    if (!job.brokerJobId) return;
    try {
      const result = await this.command(["uv", "run", "train", "job", "show", job.brokerJobId, "--cluster", CLUSTER], undefined, 15_000, RESEARCH_DIR);
      if (result.code !== 0) fail(`broker show failed: ${result.stderr.toString() || text(result)}`);
      const status = parseBrokerShow(text(result));
      if (status.jobId !== job.brokerJobId) fail(`Broker returned ${status.jobId}, expected ${job.brokerJobId}`);
      await this.mutate(id, (current) => { current.phase = status.phase; current.restartCount = status.restartCount; current.preemptedCount = status.preemptedCount; current.brokerMessage = status.message; current.brokerError = null; current.brokerCheckedAt = this.now().toISOString(); });
    } catch (error) {
      await this.mutate(id, (current) => { current.brokerError = error instanceof Error ? error.message : String(error); });
    }
    try {
      const reader = await readFile(join(this.root, "src", "job_progress.py"));
      const result = await this.command(["kubectl", "--context", KUBECTL_CONTEXT, "exec", "-i", "-n", "default", READ_POD, "--", "python3", "-", job.runDirectory], reader, 30_000);
      if (result.code !== 0) fail(`progress reader failed: ${result.stderr.toString() || text(result)}`);
      const progress = parseRunProgress(JSON.parse(text(result)));
      await this.mutate(id, (current) => { current.progress = progress; current.progressError = null; current.progressCheckedAt = this.now().toISOString(); if (progress?.sourceRevision) current.sourceRevision = progress.sourceRevision; });
    } catch (error) {
      await this.mutate(id, (current) => { current.progressError = error instanceof Error ? error.message : String(error); });
    }
  }

  private async mutate(id: string, update: (job: StoredJob) => void | Promise<void>): Promise<void> {
    const prior = this.locks.get(id) ?? Promise.resolve();
    const next = prior.then(async () => { const job = await this.readStored(id); await update(job); job.updatedAt = this.now().toISOString(); await this.writeStored(job); });
    const queued = next.catch(() => undefined);
    this.locks.set(id, queued);
    await next;
    if (this.locks.get(id) === queued) this.locks.delete(id);
  }

  private async readStored(id: string): Promise<StoredJob> {
    return JSON.parse(await readFile(join(this.jobsDir, `${id}.json`), "utf8")) as StoredJob;
  }

  private async writeStored(job: StoredJob): Promise<void> {
    await mkdir(this.jobsDir, { recursive: true, mode: 0o700 });
    const path = join(this.jobsDir, `${job.id}.json`);
    const tmp = `${path}.${process.pid}.${randomUUID()}.tmp`;
    await writeFile(tmp, `${JSON.stringify(job, null, 2)}\n`, { mode: 0o600 });
    await rename(tmp, path);
  }

  private async ensureToken(): Promise<string> {
    try { return (await readFile(this.tokenPath, "utf8")).trim(); } catch { /* create below */ }
    const token = randomUUID().replaceAll("-", "") + randomUUID().replaceAll("-", "");
    await mkdir(dirname(this.tokenPath), { recursive: true, mode: 0o700 });
    await writeFile(this.tokenPath, `${token}\n`, { mode: 0o600 });
    await chmod(this.tokenPath, 0o600);
    return token;
  }
}

export async function createJobService(options: ServiceOptions = {}): Promise<JobService> {
  const service = new JobService(options);
  await service.initialize();
  return service;
}

export const jobConstants = { POLL_INTERVAL_MS, CLUSTER, RESEARCH_DIR, KUBECTL_CONTEXT, WRITE_POD, READ_POD };
