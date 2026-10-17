import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import { createJobService } from "./server/service.ts";
import { jobsMiddleware } from "./server/middleware.ts";

const webRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(webRoot, "..");
const stateDir = resolve(process.env.FUSION_STATE_DIR ?? join(repoRoot, ".fusion"));
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
