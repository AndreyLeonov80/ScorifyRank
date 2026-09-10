import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const source = await readFile(path.join(root, 'js', 'react.dashboard.js'), 'utf8');
const errors = [];

for (const marker of [
  'DashboardLightPage',
  'Состояние сейчас',
  'Telegram / Import',
  'DuckDB / база',
  'активного чтения прямо сейчас нет',
  'scheduleWaitHint',
  'statusSlot',
]) {
  if (!source.includes(marker)) errors.push(`react.dashboard.js missing lean marker: ${marker}`);
}

for (const heavyMarker of [
  'Deal OS: воронка',
  'Лог backend',
  'Режимы функций',
  'preview-grid',
  'href="import.html">Import',
  'href="grid.html">Открыть Sync',
  'Обновить сейчас',
]) {
  if (source.includes(heavyMarker)) errors.push(`react.dashboard.js should not include heavy dashboard block: ${heavyMarker}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
