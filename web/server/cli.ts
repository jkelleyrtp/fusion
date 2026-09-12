import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(new URL("../..", import.meta.url).pathname);
const baseUrl = process.env.FUSION_CONTROL_URL ?? "http://127.0.0.1:4173";
const tokenPath = process.env.FUSION_CONTROL_TOKEN ?? resolve(root, ".fusion/control-token");

async function request(path: string, method: string, value?: Record<string, unknown>): Promise<void> {
  const token = method === "GET" ? undefined : (process.env.FUSION_CONTROL_AUTH ?? await readFile(tokenPath, "utf8")).trim();
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), ...(value ? { "content-type": "application/json" } : {}) },
    body: value ? JSON.stringify(value) : undefined,
  });
  const payload = await response.text();
  process.stdout.write(`${payload}\n`);
  if (!response.ok) process.exitCode = 1;
}

function option(args: string[], name: string): string {
  const index = args.indexOf(name);
  if (index < 0 || !args[index + 1]) throw new Error(`Missing ${name}`);
  return args[index + 1];
}

async function main(): Promise<void> {
  const [command, ...args] = process.argv.slice(2);
  if (command === "launch") {
    const extras = args.slice(1);
    if (args[0] !== "poisson-reference" || ![0, 2].includes(extras.length) || (extras.length === 2 && extras[0] !== "--request-id")) throw new Error("Usage: npm run job -- launch poisson-reference [--request-id UUID]");
    const requestId = extras.length === 2 ? extras[1] : randomUUID();
    process.stdout.write(`requestId ${requestId}\n`);
    await request("/api/jobs/launch", "POST", { profile: "poisson-reference", requestId });
    return;
  }
  if (command === "list") {
    await request("/api/jobs", "GET");
    return;
  }
  if (command === "register") {
    const campaign = args.includes("--campaign-id") ? option(args, "--campaign-id") : null;
    await request("/api/jobs/register", "POST", {
      profile: args.includes("--profile") ? option(args, "--profile") : "poisson-reference",
      brokerJobId: option(args, "--job-id"),
      runDirectory: option(args, "--run-directory"),
      campaignId: campaign,
      title: option(args, "--title")
    });
    return;
  }
  throw new Error("Usage: npm run job -- launch poisson-reference [--request-id UUID] | list | register --job-id ID --run-directory RUN --title TITLE [--campaign-id ID] [--profile PROFILE]");
}

main().catch((error) => { console.error(error instanceof Error ? error.message : error); process.exitCode = 1; });
