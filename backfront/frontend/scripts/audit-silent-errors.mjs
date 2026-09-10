import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const runtimeStatus = await readRepo('backfront/backend/app/services/runtime_status.py');
const dashboard = await readRepo('backfront/frontend/js/react.dashboard.js');

if (runtimeStatus.includes('except Exception:\n        pass')) {
  errors.push('runtime_status.py still silently swallows a dashboard exception');
}
if (!runtimeStatus.includes('_append_runtime_log("dashboard", f"Dashboard scanned_sources merge failed: {exc}")')) {
  errors.push('runtime_status.py does not log scanned_sources merge failures');
}
if (dashboard.includes('loadSummary().catch(() => {})')) {
  errors.push('react.dashboard.js still silently swallows background dashboard refresh errors');
}
if (!dashboard.includes("console.warn('Dashboard background refresh failed:', error);")) {
  errors.push('react.dashboard.js does not log background dashboard refresh failures');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
