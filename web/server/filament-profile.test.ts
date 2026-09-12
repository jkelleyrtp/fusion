import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { JobService } from "./service.ts";

test("registration preserves the compact-source profile", async () => {
  const stateDir = await mkdtemp(join(tmpdir(), "fusion-filament-profile-"));
  const command = async () => ({ stdout: Buffer.alloc(0), stderr: Buffer.alloc(0), code: 0 });
  const service = new JobService({ stateDir, command, poll: false });
  try {
    await service.initialize();
    const job = await service.register(
      "jonathan-cusp-poisson-filament-test",
      "poisson-filament-test",
      "poisson-filament",
      "5 keV compact-source comparison",
      "poisson-filament",
    );
    assert.equal(job.profile, "poisson-filament");
    assert.equal(job.gpus, 4);
    assert.equal(job.nodes, 1);
    assert.match(job.purpose, /broad 3 cm \/ 0 degree/);
    assert.match(job.purpose, /50 um \/ 10 degree/);
  } finally {
    await service.close();
    await rm(stateDir, { recursive: true, force: true });
  }
});
