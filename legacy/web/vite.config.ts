import { readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { createJobService } from "./server/service.ts";
import { jobsMiddleware } from "./server/middleware.ts";

const webRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(webRoot, "..");
const stateDir = resolve(process.env.FUSION_STATE_DIR ?? join(repoRoot, ".fusion"));
const runsFeed = resolve(process.env.FUSION_RUNS_FEED ?? "/home/ubuntu/warpx/live/runs.json");
const controlToken = resolve(process.env.FUSION_CONTROL_TOKEN ?? join(stateDir, "control-token"));

type ServiceSlot = { service: Awaited<ReturnType<typeof createJobService>> };
type GlobalWithService = typeof globalThis & { __fusionJobService?: ServiceSlot };

function jobsPlugin(): Plugin {
  return {
    name: "fusion-jobs-api",
    async configureServer(server) {
      const globals = globalThis as GlobalWithService;
      const slot = { service: globals.__fusionJobService?.service ?? await createJobService() };
      globals.__fusionJobService = slot;
      server.middlewares.use(jobsMiddleware(slot.service));
      // The file warpx/runs_feed.py keeps; the production server (src/serve_viewer.py) serves it at the same path.
      server.middlewares.use("/api/runs", (_req, res) => {
        readFile(runsFeed).then(body => {
          res.setHeader("content-type", "application/json; charset=utf-8");
          res.setHeader("cache-control", "no-store");
          res.end(body);
        }, () => { res.statusCode = 503; res.end("No run feed yet: start warpx/runs_feed.py"); });
      });
      server.httpServer?.once("close", () => {
        if (globals.__fusionJobService === slot) {
          delete globals.__fusionJobService;
          void slot.service.close();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [jobsPlugin()],
  server: {
    fs: {
      deny: [
        ".env", ".env.*", "*.{crt,pem,key,p12,pfx,cer,der}", ".npmrc", ".yarnrc.yml", "**/.git/**",
        "**/.fusion/**", stateDir, `${stateDir}/**`, controlToken,
      ],
    },
  },
});
