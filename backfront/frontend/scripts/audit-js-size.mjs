import { stat } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const budgets = [
  ['js/script.api.js', 46 * 1024],
  ['js/api.client.js', 80 * 1024],
  ['js/react.runtime.js', 40 * 1024],
  ['js/react.index.js', 130 * 1024],
  ['js/legacy.lead.store.js', 85 * 1024],
  ['css/pages/index.css', 32 * 1024],
];

const results = [];
const errors = [];

for (const [file, maxBytes] of budgets) {
  const info = await stat(path.join(root, file));
  results.push({ file, bytes: info.size, maxBytes });
  if (info.size > maxBytes) {
    errors.push(`${file}: ${info.size} bytes exceeds ${maxBytes} bytes`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, results, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, results }, null, 2));
