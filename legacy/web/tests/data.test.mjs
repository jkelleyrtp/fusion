import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { gzipSync } from "node:zlib";
import { test } from "node:test";
import { DataStore, parseChunk } from "../.test-build/data.js";

globalThis.window = globalThis;
const payload = Buffer.from('{"answer":42}');
const compressed = gzipSync(payload);
const ref = { path: "fixture.cspz", bytes: compressed.length,
  sha256: createHash("sha256").update(compressed).digest("hex") };

function harness() {
  const entries = new Map();
  const key = value => new URL(typeof value === "string" ? value : value.url, "http://test.local").href;
  const cache = {
    match: async url => entries.get(key(url))?.clone(),
    put: async (url, response) => entries.set(key(url), response.clone()),
    keys: async () => [...entries.keys()].map(url => new Request(url)),
    delete: async url => entries.delete(key(url)),
  };
  globalThis.caches = { open: async () => cache, delete: async () => { entries.clear(); return true; } };
  let requests = 0;
  globalThis.fetch = async () => { requests++; return new Response(compressed); };
  return { store: new DataStore(), requests: () => requests };
}

test("compressed bytes are counted once; cached data works offline", async () => {
  const h = harness();
  assert.deepEqual(await h.store.json(ref), { answer: 42 });
  assert.equal(h.store.spent, compressed.length);
  h.store.offline = true;
  assert.deepEqual(await h.store.json(ref), { answer: 42 });
  assert.equal(h.requests(), 1);
  assert.equal(h.store.spent, compressed.length);
  await assert.rejects(h.store.bytes({ ...ref, path: "uncached.cspz" }), /Offline mode/);
  assert.equal(h.requests(), 1);
});

test("in-flight requests share a single transfer", async () => {
  const h = harness();
  await Promise.all([h.store.json(ref), h.store.json(ref)]);
  assert.equal(h.requests(), 1);
  assert.equal(h.store.spent, compressed.length);
});

test("budget rejection makes no request and corrupt bytes fail integrity", async () => {
  const h = harness();
  h.store.budget = ref.bytes - 1;
  await assert.rejects(h.store.bytes(ref), /budget reached/);
  assert.equal(h.requests(), 0);
  h.store.budget = 1000;
  await assert.rejects(h.store.bytes({ ...ref, sha256: "0".repeat(64) }), /integrity check failed/);
  assert.equal(h.store.spent, compressed.length);
});

test("CSP1 parser preserves particle IDs and rejects dimension mismatches", () => {
  const buffer = new ArrayBuffer(56);
  new Uint8Array(buffer, 0, 4).set(Buffer.from("CSP1"));
  const view = new DataView(buffer);
  for (const [offset, value] of [[4, 1], [8, 2], [12, 6], [16, 16], [20, 1], [24, 0], [28, 6]]) {
    view.setUint32(offset, value, true);
  }
  new Float32Array(buffer, 32).set([1, 2, 3, 4, 5, 6]);
  const chunk = parseChunk(buffer, { ...ref, first: 16, count: 1 });
  assert.equal(chunk.first, 16);
  assert.deepEqual([...chunk.indices], [0, 6]);
  assert.deepEqual([...chunk.positions], [1, 2, 3, 4, 5, 6]);
  assert.throws(() => parseChunk(buffer, { ...ref, first: 0, count: 1 }), /dimensions/);
  assert.throws(() => parseChunk(buffer.slice(0, 50), { ...ref, first: 16, count: 1 }), /dimensions/);
});
