import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const errors = [];

const apiClient = await readFile(path.join(root, 'js', 'api.client.js'), 'utf8');
const scriptApi = await readFile(path.join(root, 'js', 'script.api.js'), 'utf8');
const importStore = await readFile(path.join(root, 'js', 'legacy.import.store.js'), 'utf8');

for (const marker of [
  'getApiCandidates()',
  'for (const base of candidates)',
  'lastError',
  'normalizeApiErrorDetail',
]) {
  if (!apiClient.includes(marker)) errors.push(`api.client.js missing fallback marker: ${marker}`);
}

for (const marker of [
  "rawError.includes('Failed to fetch')",
  'Backend не ответил',
  'getImportDialogsCachedResponse(params)',
  'Показываю',
  '__cache_exact_match',
  '_retriedNetwork',
]) {
  if (!importStore.includes(marker)) errors.push(`legacy.import.store.js missing Failed to fetch fallback marker: ${marker}`);
}

for (const marker of [
  'humanizeApiError',
  'Failed to fetch',
  'requestKey',
  'AbortError',
  '__REQUEST_ABORTED__',
]) {
  if (!scriptApi.includes(marker)) errors.push(`script.api.js missing request reliability marker: ${marker}`);
}

if (/\[object Object\]/.test(apiClient + scriptApi + importStore)) {
  errors.push('frontend must not hard-code or surface [object Object]');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
