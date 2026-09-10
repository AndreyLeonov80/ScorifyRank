import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const repoRoot = path.resolve(root, '..', '..');
const errors = [];

async function readRepo(relPath) {
  return readFile(path.join(repoRoot, relPath), 'utf8');
}

const shared = await readRepo('backfront/frontend/js/react.shared.js');
const importPage = await readRepo('backfront/frontend/js/react.import.js');
const gridPage = await readRepo('backfront/frontend/js/react.grid.js');
const chatPage = await readRepo('backfront/frontend/js/react.index.chat.js');
const leadStore = await readRepo('backfront/frontend/js/legacy.lead.store.js');

for (const marker of ['function VirtualizedRows', 'rows.slice(0, safeLimit)', 'maxRows = 100']) {
  if (!shared.includes(marker)) errors.push(`react.shared.js missing virtualized rows marker: ${marker}`);
}
for (const [file, source] of [['react.import.js', importPage], ['react.grid.js', gridPage]]) {
  if (!source.includes('VirtualizedRows')) errors.push(`${file} does not use VirtualizedRows`);
  if (!source.includes('maxRows=${store.ui.pageSize}')) errors.push(`${file} does not bind render window to page size`);
}
if (!chatPage.includes('store.visibleMessages().map')) errors.push('react.index.chat.js must render only visibleMessages()');
if (!leadStore.includes('messageRenderWindowSize()') || !leadStore.includes('visibleMessages()')) {
  errors.push('legacy.lead.store.js must keep chat message rendering windowed');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
