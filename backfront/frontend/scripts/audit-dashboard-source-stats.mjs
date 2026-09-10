import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readFromRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const dashboard = await readFromRepo('backfront/frontend/js/react.dashboard.js');
const runtimeStatus = await readFromRepo('backfront/backend/app/services/runtime_status.py');
const sourceStats = await readFromRepo('backfront/backend/app/services/dashboard_source_stats.py');

for (const marker of [
  'Dashboard оставлен лёгким',
  'scannedSources',
  'summary-lite',
  'sources/runtime-status',
  'Telegram sync:',
  'JSONL → DuckDB',
  'Перекачано',
  'активных',
  'ожидают',
]) {
  if (!dashboard.includes(marker)) errors.push(`dashboard missing marker: ${marker}`);
}

for (const marker of [
  'scanned_sources',
  'build_dashboard_scanned_sources_payload',
  'dashboard_source_stats',
]) {
  if (!runtimeStatus.includes(marker)) errors.push(`runtime_status missing marker: ${marker}`);
}

for (const marker of [
  'build_dashboard_scanned_sources_payload',
  'selected_sources',
  'scan_group',
  'last_message_at',
  'messages_count',
]) {
  if (!sourceStats.includes(marker)) errors.push(`dashboard_source_stats missing marker: ${marker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
