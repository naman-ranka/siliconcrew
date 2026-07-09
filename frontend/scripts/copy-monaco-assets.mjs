import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const monacoRoot = dirname(require.resolve("monaco-editor/package.json"));
const source = join(monacoRoot, "min", "vs");
const target = join(process.cwd(), "public", "monaco", "vs");

await rm(target, { recursive: true, force: true });
await mkdir(dirname(target), { recursive: true });
await cp(source, target, { recursive: true });

console.log(`Copied Monaco assets to ${target}`);
