// Checks the built site (dist/) against the size budget of P-20: run after `yarn build`.
// - main block: the entry script of index.html, what the phone must parse before the first screen; must stay under LIMIT_KB.
// - first load: the entry plus the blocks index.html preloads (modulepreload), i.e. everything fetched before the first screen.
// Prints every JS block with its gzip size; exits 1 when the main block is over budget.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const LIMIT_KB = 400;
const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const kb = (n) => (n / 1000).toFixed(1);

const html = readFileSync(join(dist, "index.html"), "utf8");
const entry = html.match(/<script[^>]+type="module"[^>]+src="\/(assets\/[^"]+\.js)"/)?.[1];
if (!entry) {
  console.error("check-bundle-size: nessuno script principale in dist/index.html (manca la build?)");
  process.exit(2);
}
const preloads = [...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);

const size = (file) => {
  const buf = readFileSync(join(dist, file));
  return { raw: buf.length, gz: gzipSync(buf).length };
};

const blocks = readdirSync(join(dist, "assets"))
  .filter((f) => f.endsWith(".js"))
  .map((f) => ({ file: `assets/${f}`, ...size(`assets/${f}`) }))
  .sort((a, b) => b.raw - a.raw);

for (const b of blocks) {
  const tag = b.file === entry ? "principale" : preloads.includes(b.file) ? "all'apertura" : "a richiesta";
  console.log(`${kb(b.raw).padStart(8)} kB ${kb(b.gz).padStart(7)} kB gzip  ${tag.padEnd(12)} ${b.file}`);
}

const main = size(entry);
const first = [entry, ...preloads].map(size).reduce((a, s) => ({ raw: a.raw + s.raw, gz: a.gz + s.gz }), { raw: 0, gz: 0 });
console.log(`Blocco principale: ${kb(main.raw)} kB (${kb(main.gz)} kB gzip), soglia ${LIMIT_KB} kB`);
console.log(`Prima apertura (principale + precaricati): ${kb(first.raw)} kB (${kb(first.gz)} kB gzip), ${1 + preloads.length} file`);

if (main.raw > LIMIT_KB * 1000) {
  console.error(`check-bundle-size: blocco principale sopra la soglia di ${LIMIT_KB} kB`);
  process.exit(1);
}
