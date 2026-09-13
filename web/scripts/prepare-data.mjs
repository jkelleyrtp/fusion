import { cpSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = new URL("../", import.meta.url);
const target = new URL("public/data/", root);
if (!existsSync(new URL("catalog.json", target))) {
  cpSync(fileURLToPath(new URL("sample-data/", root)), fileURLToPath(target), { recursive: true });
}
cpSync(fileURLToPath(new URL("../docs/images/", root)), fileURLToPath(new URL("public/figures/", root)), { recursive: true });
