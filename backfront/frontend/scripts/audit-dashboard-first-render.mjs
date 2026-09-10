import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const source = await readFile(path.join(root, 'js', 'react.dashboard.js'), 'utf8');
const errors = [];

const loadSummaryMatch = source.match(/const loadSummary = React\.useCallback\(async \(\) => \{[\s\S]*?\n    \}, \[summary\]\);/);
if (!loadSummaryMatch) {
  errors.push('react.dashboard.js loadSummary callback was not found');
} else {
  const loadSummaryBody = loadSummaryMatch[0];
  const apiCalls = [...loadSummaryBody.matchAll(/\bapiJson\(/g)].length + [...loadSummaryBody.matchAll(/\bapiPostJson\(/g)].length;
  if (apiCalls > 3) {
    errors.push(`dashboard first render makes too many direct API calls: ${apiCalls}`);
  }
  for (const marker of [
    '/api/payme/dashboard/summary-lite',
    '/api/payme/sources/runtime-status',
    "dedupeKey: 'dashboard:summary-lite'",
    "dedupeKey: 'dashboard:sources-runtime'",
  ]) {
    if (!loadSummaryBody.includes(marker)) errors.push(`dashboard first render missing marker: ${marker}`);
  }
}

if (!source.includes('}, 30000);')) {
  errors.push('dashboard background refresh interval should stay at 30000ms or slower');
}

if (source.includes('/api/payme/dashboard/summary?limit=50')) {
  errors.push('dashboard first render still references the heavy summary endpoint');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
