import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const apiClient = fs.readFileSync(path.join(root, 'js', 'api.client.js'), 'utf8');

const markers = [
  'const inflightRequests = new Map()',
  'dedupeKey =',
  'staleWhileRevalidate = false',
  'onRevalidate = null',
  'inflightRequests.has(effectiveDedupeKey)',
  'apiJsonNetwork(url',
  'dedupeKey: `swr:${cacheKey}`',
];

const missing = markers.filter((marker) => !apiClient.includes(marker));
if (missing.length) {
  console.error('[audit:api-cache-dedupe] failed');
  for (const marker of missing) console.error(`- missing marker: ${marker}`);
  process.exit(1);
}

console.log('[audit:api-cache-dedupe] ok');

