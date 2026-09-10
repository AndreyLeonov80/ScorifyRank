import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const runtime = await readRepo('backfront/frontend/js/script.api.js');
const stores = {
  'legacy.import.store.js': await readRepo('backfront/frontend/js/legacy.import.store.js'),
  'legacy.grid.store.js': await readRepo('backfront/frontend/js/legacy.grid.store.js'),
  'legacy.lead.store.js': await readRepo('backfront/frontend/js/legacy.lead.store.js'),
};

for (const marker of [
  'function isSafePersistedUiField',
  'leads|dialogs|messages|items|rows|cache|history',
  'if (!isSafePersistedUiField(field)) continue;',
]) {
  if (!runtime.includes(marker)) errors.push(`script.api.js missing persisted UI safety marker: ${marker}`);
}

const forbiddenPersistedFields = /\b(leads|dialogs|messages|items|rows|cache|history)\b/;
for (const [file, source] of Object.entries(stores)) {
  const persistCalls = [...source.matchAll(/persistUiState\([^;]+;/gs)].map((match) => match[0]);
  if (!persistCalls.length) errors.push(`${file} does not persist explicit UI allowlist`);
  for (const call of persistCalls) {
    if (forbiddenPersistedFields.test(call)) {
      errors.push(`${file} persists a heavy field in UI state: ${call.replace(/\s+/g, ' ').slice(0, 180)}`);
    }
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
