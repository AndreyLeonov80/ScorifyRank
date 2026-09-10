import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const source = await readFile(path.join(root, 'js', 'api.client.js'), 'utf8');
const setupWizard = await readFile(path.join(root, 'js', 'react.setup_wizard.js'), 'utf8');
const errors = [];

for (const marker of [
  'normalizeApiErrorDetail',
  'Content-Type',
  'application/json',
  'options.body',
  'Array.isArray(detail)',
]) {
  if (!source.includes(marker)) {
    errors.push(`api.client.js missing marker: ${marker}`);
  }
}

if (!source.includes('HTTP ${response.status} ${response.statusText}${detailText ?')) {
  errors.push('api.client.js should build readable HTTP errors from normalized detail text');
}

if (!setupWizard.includes('apiPostJson')) {
  errors.push('setup wizard should use BackfrontApi.apiPostJson for JSON POST requests');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
