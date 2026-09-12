import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { PIC_PROFILE } from "./profile.ts";
import { JobService } from "./service.ts";

type Result = { stdout: Buffer; stderr: Buffer; code: number };
type Runner = (argv: string[], input?: Buffer, timeout?: number, cwd?: string) => Promise<Result>;
const repoRoot = new URL("../..", import.meta.url).pathname;
const ok = (stdout = ""): Result => ({ stdout: Buffer.from(stdout), stderr: Buffer.alloc(0), code: 0 });

const progress = {
  attempt: "attempt-pic",
  sourceRevision: "0123456789abcdef0123456789abcdef01234567",
  purpose: "transient test",
  done: false,
  statusText: null,
  progressUnit: "steps",
  cases: [
    {
      name: "pic_vacuum",
      iteration: 2,
      target: 4,
      status: "running",
      exitCode: null,
      updatedAt: null,
      physicalTimeS: 2e-12,
      settings: { dt: "1e-12", duration: "4e-12" },
    },
    {
      name: "pic_1A",
      iteration: 8,
      target: 8,
      status: "completed",
      exitCode: 0,
      updatedAt: null,
      physicalTimeS: 4e-12,
      settings: { dt: "5e-13", duration: "4e-12" },
    },
  ],
};

function runner(progressPayload: unknown = progress): Runner {
  return async (argv) => {
    if (argv.slice(0, 5).join(" ") === "uv run train job show") {
      return ok("job_id               broker-pic\nphase                RUNNING\nrestart_count        0\npreempted_count      0\nmessage              running\n# template.yaml\n");
    }
    if (argv[0] === "kubectl" && argv.includes("python3")) {
      return ok(JSON.stringify(progressPayload));
    }
    return ok();
  };
}

test("transient PIC profile registration and step progress parse", async () => {
  const root = await mkdtemp(join(tmpdir(), "fusion-pic-progress-"));
  const service = new JobService({ root: repoRoot, stateDir: root, command: runner(), poll: false });
  try {
    await service.initialize();
    const job = await service.register(
      "broker-pic",
      "pic-run",
      "transient-pic",
      "5 keV transient PIC startup",
      "transient-pic",
    );
    assert.equal(job.profile, "transient-pic");
    assert.equal(job.gpus, 4);
    assert.equal(job.purpose, PIC_PROFILE.purpose);

    await service.pollAll();
    const parsed = (await service.jobs()).jobs[0].progress;
    assert.equal(parsed?.progressUnit, "steps");
    assert.equal(parsed?.cases[0].physicalTimeS, 2e-12);
    assert.equal(parsed?.cases[0].settings.dt, "1e-12");
    assert.equal(parsed?.cases[1].physicalTimeS, 4e-12);
    assert.equal(parsed?.cases[1].settings.dt, "5e-13");
  } finally {
    await service.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("array progress unit is rejected", async () => {
  const root = await mkdtemp(join(tmpdir(), "fusion-pic-progress-"));
  const service = new JobService({
    root: repoRoot,
    stateDir: root,
    command: runner({ ...progress, progressUnit: ["steps"] }),
    poll: false,
  });
  try {
    await service.initialize();
    await service.register("broker-pic-array", "pic-run-array", null, "PIC", "transient-pic");
    await service.pollAll();
    const job = (await service.jobs()).jobs[0];
    assert.equal(job.progress, null);
    assert.match(job.progressError ?? "", /Malformed progress unit/);
  } finally {
    await service.close();
    await rm(root, { recursive: true, force: true });
  }
});

test("malformed optional progress fields are rejected", async () => {
  const root = await mkdtemp(join(tmpdir(), "fusion-pic-progress-"));
  const service = new JobService({
    root: repoRoot,
    stateDir: root,
    command: runner({ ...progress, progressUnit: "pulses" }),
    poll: false,
  });
  try {
    await service.initialize();
    await service.register("broker-pic", "pic-run", null, "PIC", "transient-pic");
    await service.pollAll();
    const job = (await service.jobs()).jobs[0];
    assert.equal(job.progress, null);
    assert.match(job.progressError ?? "", /Malformed progress unit/);
  } finally {
    await service.close();
    await rm(root, { recursive: true, force: true });
  }
});
