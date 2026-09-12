import type { IncomingMessage, ServerResponse } from "node:http";
import type { JobService } from "./service.ts";

type JsonRecord = Record<string, unknown>;

function send(res: ServerResponse, status: number, body: unknown): void {
  const payload = JSON.stringify(body);
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("content-length", Buffer.byteLength(payload));
  res.end(payload);
}

async function body(req: IncomingMessage): Promise<JsonRecord> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of req) {
    const value = Buffer.from(chunk);
    size += value.length;
    if (size > 64 * 1024) throw new Error("Request body too large");
    chunks.push(value);
  }
  const value: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Expected a JSON object");
  return value as JsonRecord;
}

function authorized(req: IncomingMessage, service: JobService): boolean {
  return req.headers.authorization === `Bearer ${service.getToken()}`;
}

export function jobsMiddleware(service: JobService) {
  return async (req: IncomingMessage, res: ServerResponse, next: () => void): Promise<void> => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    if (url.pathname !== "/api/jobs" && url.pathname !== "/api/jobs/launch" && url.pathname !== "/api/jobs/register") {
      next();
      return;
    }
    try {
      if (url.pathname === "/api/jobs" && req.method === "GET") {
        send(res, 200, await service.jobs());
        return;
      }
      if (req.method !== "POST" || !authorized(req, service)) {
        send(res, req.method === "POST" ? 401 : 405, { error: req.method === "POST" ? "Unauthorized" : "Method not allowed" });
        return;
      }
      const value = await body(req);
      if (url.pathname === "/api/jobs/launch") {
        const launchKeys = Object.keys(value).sort().join(",");
        if (launchKeys !== "profile,requestId" || value.profile !== "poisson-reference" || typeof value.requestId !== "string") {
          send(res, 400, { error: "Expected profile poisson-reference and requestId" });
          return;
        }
        send(res, 202, await service.launch(value.requestId));
        return;
      }
      const registerKeys = Object.keys(value).sort();
      if (registerKeys.some((key) => !["brokerJobId", "campaignId", "profile", "runDirectory", "title"].includes(key))) {
        send(res, 400, { error: "Unknown registration field" });
        return;
      }
      const profile = value.profile === undefined ? "poisson-reference" : value.profile;
      if (profile !== "poisson-reference" && profile !== "poisson-high-voltage" && profile !== "poisson-filament") {
        send(res, 400, { error: "Unknown profile" });
        return;
      }
      if (typeof value.brokerJobId !== "string" || typeof value.runDirectory !== "string" || (value.campaignId !== undefined && value.campaignId !== null && typeof value.campaignId !== "string") || typeof value.title !== "string") {
        send(res, 400, { error: "brokerJobId, runDirectory, campaignId and title must have valid types" });
        return;
      }
      send(res, 202, await service.register(value.brokerJobId, value.runDirectory, value.campaignId === undefined ? null : value.campaignId, value.title, profile));
    } catch (error) {
      send(res, 400, { error: error instanceof Error ? error.message : String(error) });
    }
  };
}
