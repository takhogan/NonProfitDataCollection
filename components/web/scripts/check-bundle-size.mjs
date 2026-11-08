// NFR-03 / WEB-006: initial load ≤ 300 KB compressed JS+CSS, and no map
// library in it. Run after `npm run build`.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const BUDGET = 300 * 1024;
const dist = new URL('../dist/', import.meta.url).pathname;
const html = readFileSync(join(dist, 'index.html'), 'utf8');
const assets = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.(?:js|css))"/g)].map((m) => m[1]);

let total = 0;
for (const a of assets) {
  const buf = readFileSync(join(dist, a));
  const gz = gzipSync(buf).length;
  total += gz;
  if (/maplibre/i.test(buf.toString('utf8'))) {
    console.error(`✗ ${a} contains a map library; load it only when a map is opened (WEB-006).`);
    process.exit(1);
  }
  console.log(`${(gz / 1024).toFixed(1).padStart(7)} KB  ${a}`);
}
console.log(`${(total / 1024).toFixed(1).padStart(7)} KB  initial JS+CSS (gzip), budget ${BUDGET / 1024} KB`);
if (total > BUDGET) {
  console.error('✗ over budget');
  process.exit(1);
}
