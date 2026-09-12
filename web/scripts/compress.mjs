import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { join } from "node:path";

const assets = fileURLToPath(new URL("../dist/assets/", import.meta.url));
for (const filename of readdirSync(assets)) {
  if (/\.(js|css)$/.test(filename)) {
    writeFileSync(join(assets, `${filename}.gz`), gzipSync(readFileSync(join(assets, filename)), { level: 9 }));
  }
}
