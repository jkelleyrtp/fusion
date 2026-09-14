import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { once } from "node:events";
import { jobsMiddleware } from "./middleware.ts";
import { JobService, parseBrokerShow, parseFreeNodes } from "./service.ts";
import config from "../vite.config.ts";

type Result = { stdout: Buffer; stderr: Buffer; code: number };
type Runner = (argv: string[], input?: Buffer, timeout?: number, cwd?: string) => Promise<Result>;
const ok = (stdout = ""): Result => ({ stdout: Buffer.from(stdout), stderr: Buffer.alloc(0), code: 0 });
const repoRoot = new URL("../..", import.meta.url).pathname;
const capacity = "┃ CLIQUE ┃ HEALTHY ┃ CLAIMED ┃ FREE ┃\n│ ip-test.example │ 1 │ 0 │ 1 │\n";
const commandFor = (overrides: (argv: string[]) => Result | undefined = () => undefined, seen: string[] = []): Runner => async (argv, _input, _timeout, cwd) => {
  seen.push(`${cwd ?? ""} ${argv.join(" ")}`);
  const custom = overrides(argv);
  if (custom) return custom;
  if (argv[0] === "git" && argv[1] === "rev-parse") return ok("0123456789abcdef0123456789abcdef01234567\n");
  if (argv[0] === "git" && argv[1] === "archive") return ok("archive");
  if (argv[0] === "kubectl") return ok();
  const op = argv.slice(0, 5).join(" ");
  if (op === "uv run train gpus --cluster") return ok(capacity);
  if (op === "uv run train job list") return ok("jobs");
  if (op === "uv run train job submit") return ok("submitted broker-123 (phase QUEUED)\n");
  if (op === "uv run train job show") return ok("job_id               broker-123\nphase                SUCCEEDED\nrestart_count        0\npreempted_count      0\nmessage              done\n# template.yaml\n");
  return ok();
};

async function fixture(command: Runner): Promise<{ root: string; service: JobService }> {
  const root = await mkdtemp(join(tmpdir(), "fusion-job-test-"));
  const service = new JobService({ root: repoRoot, stateDir: root, command, poll: false });
  await service.initialize();
  return { root, service };
}

async function settle(service: JobService): Promise<void> {
  for (let i = 0; i < 100; i++) {
    const job = (await service.jobs()).jobs[0];
    if (job.submissionState !== "preparing" && job.submissionState !== "submitting") return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  throw new Error("launch did not settle");
}

test("Vite preserves secret deny patterns and protects fusion state", () => {
  const deny = ((config as { server?: { fs?: { deny?: unknown[] } } }).server?.fs?.deny ?? []).map(String);
  assert(deny.includes(".env"));
  assert(deny.includes("**/.git/**"));
  assert(deny.includes("**/.fusion/**"));
  assert(deny.some((pattern) => pattern.endsWith("/.fusion")));
  assert(deny.some((pattern) => pattern.endsWith("/.fusion/**")));
});

test("parses broker and capacity output conservatively", () => {
  const status = parseBrokerShow("job_id               abc-1\nphase                RUNNING\nrestart_count        2\npreempted_count      1\nmessage              admitted\n# template.yaml\n");
  assert.deepEqual(status, { jobId: "abc-1", phase: "RUNNING", restartCount: 2, preemptedCount: 1, message: "admitted" });
  assert.equal(parseFreeNodes(capacity), 1);
  assert.throws(() => parseFreeNodes("broken"), /missing FREE/);
  assert.throws(() => parseBrokerShow("phase RUNNING"), /missing job_id/);
});

test("launch request id is persisted idempotently, including concurrent calls and cwd routing", async () => {
  const seen: string[] = [];
  const { root, service } = await fixture(commandFor(() => undefined, seen));
  try {
    const requestId = "11111111-1111-4111-8111-111111111111";
    const [first, second] = await Promise.all([service.launch(requestId), service.launch(requestId)]);
    assert.equal(first.id, second.id);
    assert.equal((await service.jobs()).jobs.length, 1);
    await settle(service);
    assert.equal(seen.filter((item) => item.includes(" job submit ")).length, 1);
    assert(seen.find((item) => item.includes(" job submit "))!.startsWith("/home/ubuntu/repos/research "));
    const template = JSON.parse(await readFile(join(root, "jobs", `${first.id}.yaml`), "utf8")) as { metadata: { name: string }; spec: { entrypoint: string } };
    assert.equal(template.metadata.name, `fusion-poisson-${first.id.replaceAll("-", "").slice(0, 12)}`);
    assert.match(template.spec.entrypoint, new RegExp(`sources/0123456789abcdef0123456789abcdef01234567-${first.id}/src`));
    assert.match(template.spec.entrypoint, /runs\/.+\/attempt-\$\(date \+%Y%m%d-%H%M%S-%N\)/);
    assert.match(template.spec.entrypoint, /--actor-num-nodes 1 --actor-num-gpus-per-node 8 --rollout-num-gpus 0/);
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});

test("malformed capacity prevents submit and remains failed", async () => {
  let submits = 0;
  const { root, service } = await fixture(commandFor((argv) => {
    const op = argv.slice(0, 5).join(" ");
    if (op === "uv run train gpus --cluster") return ok("┃ CLIQUE ┃ HEALTHY ┃ CLAIMED ┃ FREE ┃\n│ malformed │ x │ y │ z │\n");
    if (op === "uv run train job submit") submits += 1;
    return undefined;
  }));
  try {
    await service.launch("22222222-2222-4222-8222-222222222222");
    await settle(service);
    assert.equal(submits, 0);
    assert.equal((await service.jobs()).jobs[0].submissionState, "failed");
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});

test("thrown submission is unknown and never retried", async () => {
  let submits = 0;
  const { root, service } = await fixture(commandFor((argv) => {
    if (argv.slice(0, 5).join(" ") === "uv run train job submit") { submits += 1; throw new Error("process died"); }
    return undefined;
  }));
  try {
    await service.launch("33333333-3333-4333-8333-333333333333");
    await settle(service);
    assert.equal(submits, 1);
    assert.equal((await service.jobs()).jobs[0].submissionState, "unknown");
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});

test("unauthenticated mutating endpoint is rejected while list is read-only", async () => {
  const { root, service } = await fixture(commandFor());
  const listener = createServer((req: IncomingMessage, res: ServerResponse) => {
    void jobsMiddleware(service)(req, res, () => { res.statusCode = 404; res.end(); });
  });
  try {
    listener.listen(0, "127.0.0.1");
    await once(listener, "listening");
    const address = listener.address();
    if (!address || typeof address === "string") throw new Error("missing test listener address");
    const base = `http://127.0.0.1:${address.port}`;
    assert.equal((await fetch(`${base}/api/jobs`)).status, 200);
    const rejected = await fetch(`${base}/api/jobs/launch`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ profile: "poisson-reference", requestId: "44444444-4444-4444-8444-444444444444" }),
    });
    assert.equal(rejected.status, 401);
  } finally {
    listener.close();
    await service.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("transient progress failure retains the last successful snapshot", async () => {
  const progress = JSON.stringify({
    attempt: "attempt-1", sourceRevision: "0123456789abcdef0123456789abcdef01234567", purpose: "test", done: false, statusText: null,
    cases: [{ name: "case", iteration: 1, target: 12, status: "running", exitCode: null, updatedAt: null, settings: {} }],
  });
  let progressCalls = 0;
  const { root, service } = await fixture(commandFor((argv) => {
    if (argv[0] === "kubectl" && argv.includes("python3")) {
      progressCalls += 1;
      return progressCalls === 1 ? ok(progress) : { stdout: Buffer.alloc(0), stderr: Buffer.from("unreachable"), code: 1 };
    }
    return undefined;
  }));
  try {
    await service.register("broker-123", "run-1", "campaign-1", "Registered test");
    await service.pollAll();
    const checkedAt = (await service.jobs()).jobs[0].progressCheckedAt;
    await service.pollAll();
    const job = (await service.jobs()).jobs[0];
    assert.equal(job.progress?.attempt, "attempt-1");
    assert.equal(job.progressCheckedAt, checkedAt);
    assert(job.progressCheckedAt);
    assert.match(job.progressError ?? "", /unreachable/);
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});

test("registration preserves the selected profile and rejects unknown profiles", async () => {
  const { root, service } = await fixture(commandFor());
  try {
    const highVoltage = await service.register(
      "jonathan-cusp-poisson-5kev-1ce5bd",
      "poisson-5kev-070652d",
      null,
      "5 keV magnetic field and space charge",
      "poisson-high-voltage",
    );
    assert.equal(highVoltage.profile, "poisson-high-voltage");
    assert.equal(highVoltage.gpus, 4);
    assert.equal(highVoltage.campaignId, null);
    assert.equal(highVoltage.purpose, "Compare 30 and 100 kA-turn at 5 keV with vacuum controls and a 1 A electron beam.");
    const reregistered = await service.register(
      "jonathan-cusp-poisson-5kev-1ce5bd", "poisson-5kev-070652d", null, "5 keV", "poisson-high-voltage", 8,
    );
    assert.equal(reregistered.gpus, 8);
    await assert.rejects(
      service.register("broker-456", "run-3", null, "Too many", "poisson-high-voltage", 9),
      /Invalid GPU count/,
    );
    await assert.rejects(
      service.register("unknown-profile", "run-2", null, "Unknown", "unknown"),
      /Invalid profile/,
    );
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});

test("restart marks submitting records unknown without retry", async () => {
  const root = await mkdtemp(join(tmpdir(), "fusion-job-restart-"));
  const jobs = join(root, "jobs");
  await mkdir(jobs, { recursive: true });
  await writeFile(join(jobs, "stale.json"), JSON.stringify({ id: "stale", submissionState: "submitting" }));
  const service = new JobService({ root: repoRoot, stateDir: root, command: commandFor(), poll: false });
  try {
    await service.initialize();
    const value = JSON.parse(await readFile(join(jobs, "stale.json"), "utf8")) as { submissionState: string; launchError: string };
    assert.equal(value.submissionState, "unknown");
    assert.match(value.launchError, /restarted/);
  } finally { await service.close(); await rm(root, { recursive: true, force: true }); }
});
