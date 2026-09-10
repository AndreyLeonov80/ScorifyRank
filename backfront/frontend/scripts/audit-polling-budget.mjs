import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const dashboard = await readRepo('backfront/frontend/js/react.dashboard.js');
const leadStore = await readRepo('backfront/frontend/js/legacy.lead.store.js');
const gridStore = await readRepo('backfront/frontend/js/legacy.grid.store.js');
const apiClient = await readRepo('backfront/frontend/js/api.client.js');

for (const marker of [
  "dedupeKey: 'dashboard:summary-lite'",
  "cacheKey: 'dashboard:summary-lite:v1'",
  "dedupeKey: 'dashboard:sources-runtime'",
  "cacheKey: 'dashboard:sources-runtime:v1'",
  'staleWhileRevalidate: true',
  'summaryInflightRef.current',
  'if (document.hidden || summaryInflightRef.current) return;',
]) {
  if (!dashboard.includes(marker)) errors.push(`react.dashboard.js missing polling budget marker: ${marker}`);
}

for (const marker of [
  'if (leadDom.isDocumentHidden?.() || this._authInflight) return;',
  'if (leadDom.isDocumentHidden?.() || this._leadInflight) return;',
]) {
  if (!leadStore.includes(marker)) errors.push(`legacy.lead.store.js missing polling budget marker: ${marker}`);
}

if (!gridStore.includes('if (document.hidden || this.loading) return;')) {
  errors.push('legacy.grid.store.js missing hidden/loading guard for grid polling');
}

for (const marker of ['const inflightRequests = new Map();', 'dedupeKey', 'staleWhileRevalidate']) {
  if (!apiClient.includes(marker)) errors.push(`api.client.js missing shared API dedupe marker: ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
