import type { FileRef, ChunkRef, TrajectoryChunk } from "./types";

const MIB = 1024 * 1024;
const CACHE_NAME = "fusion-binary-v1";

export class DataStore {
  spent = 0;
  cacheHits = 0;
  budget = 5 * MIB;
  offline = false;
  cacheNotice = "";
  private reserved = 0;
  private memory = new Map<string, ArrayBuffer>();
  private memoryBytes = 0;
  private inFlight = new Map<string, Promise<ArrayBuffer>>();
  onChange: () => void = () => undefined;

  private async cached(url: string): Promise<ArrayBuffer | undefined> {
    const memory = this.memory.get(url);
    if (memory) return memory;
    try {
      const hit = await (await caches.open(CACHE_NAME)).match(url);
      if (hit) return hit.arrayBuffer();
    } catch { this.cacheNotice = "Persistent cache unavailable; this tab still caches data."; }
  }

  private async save(url: string, bytes: ArrayBuffer): Promise<void> {
    this.memoryBytes -= this.memory.get(url)?.byteLength ?? 0;
    this.memory.set(url, bytes);
    this.memoryBytes += bytes.byteLength;
    while (this.memoryBytes > 24 * MIB) {
      const key = this.memory.keys().next().value;
      if (!key) break;
      this.memoryBytes -= this.memory.get(key)!.byteLength;
      this.memory.delete(key);
    }
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(url, new Response(bytes, { headers: { "X-Fusion-Bytes": String(bytes.byteLength) } }));
      const keys = await cache.keys();
      let size = 0;
      for (const key of keys.slice().reverse()) {
        size += Number((await cache.match(key))?.headers.get("X-Fusion-Bytes") ?? 0);
        if (size > 48 * MIB) await cache.delete(key);
      }
    } catch { this.cacheNotice = "Persistent cache unavailable; this tab still caches data."; }
  }

  private async download(url: string, expected: number): Promise<ArrayBuffer> {
    if (this.offline) throw new Error("Offline mode: this data is not cached. Enable downloads to fetch it.");
    if (this.spent + this.reserved + expected > this.budget)
      throw new Error("Data budget reached. Increase the session limit to load this selection.");
    this.reserved += expected;
    let remaining = expected;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok || !response.body) throw new Error(`Could not load data (HTTP ${response.status}).`);
      const reader = response.body.getReader();
      const pieces: Uint8Array[] = [];
      let length = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        this.spent += value.byteLength;
        length += value.byteLength;
        const consumed = Math.min(remaining, value.byteLength);
        this.reserved -= consumed; remaining -= consumed;
        this.onChange();
        if (length > expected || this.spent > this.budget) {
          controller.abort(); throw new Error("Response exceeded its declared size or the data budget.");
        }
        pieces.push(value);
      }
      const buffer = new Uint8Array(length);
      let offset = 0;
      for (const piece of pieces) { buffer.set(piece, offset); offset += piece.length; }
      return buffer.buffer;
    } finally {
      clearTimeout(timer);
      this.reserved -= remaining;
      this.onChange();
    }
  }

  async catalog<T>(): Promise<T> {
    const url = "/data/catalog.json";
    const bytes = this.offline ? await this.cached(url) : await this.download(url, 512 * 1024);
    if (!bytes) throw new Error("No cached catalog. Load once while online.");
    if (!this.offline) await this.save(url, bytes);
    return JSON.parse(new TextDecoder().decode(bytes)) as T;
  }

  async bytes(ref: FileRef): Promise<ArrayBuffer> {
    const url = `/data/${ref.path}`;
    const pending = this.inFlight.get(url);
    if (pending) return pending;
    const promise = (async () => {
      let bytes = await this.cached(url);
      if (bytes) { this.cacheHits++; this.onChange(); }
      else bytes = await this.download(url, ref.bytes);
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
        .map(v => v.toString(16).padStart(2, "0")).join("");
      if (digest !== ref.sha256) throw new Error("Data integrity check failed. Clear the cache and retry.");
      await this.save(url, bytes);
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
      return new Response(stream).arrayBuffer();
    })();
    this.inFlight.set(url, promise);
    try { return await promise; } finally { this.inFlight.delete(url); }
  }

  async json<T>(ref: FileRef): Promise<T> {
    return JSON.parse(new TextDecoder().decode(await this.bytes(ref))) as T;
  }

  async clear(): Promise<void> {
    this.memory.clear(); this.memoryBytes = 0; this.cacheHits = 0;
    await caches.delete(CACHE_NAME);
    this.onChange();
  }
}

export function parseChunk(buffer: ArrayBuffer, ref: ChunkRef): TrajectoryChunk {
  const view = new DataView(buffer);
  if (buffer.byteLength < 24 || new TextDecoder().decode(buffer.slice(0, 4)) !== "CSP1")
    throw new Error("Invalid trajectory header.");
  const count = view.getUint32(4, true), frames = view.getUint32(8, true);
  const first = view.getUint32(16, true), version = view.getUint32(20, true);
  if (count !== ref.count || first !== ref.first || version !== 1 ||
      buffer.byteLength !== 24 + frames * 4 + count * frames * 12)
    throw new Error("Trajectory dimensions do not match the catalog.");
  return {
    count, frames, first, indices: new Uint32Array(buffer, 24, frames),
    positions: new Float32Array(buffer, 24 + frames * 4, count * frames * 3),
  };
}
