import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const errors = [];

async function read(relPath) {
  return readFile(path.join(root, relPath), 'utf8');
}

function exists(relPath) {
  return existsSync(path.join(root, relPath));
}

const indexHtml = await read('index.html');
const appHtml = await read('app.html');
const pageLoader = await read('js/react.page-loader.js');
const routes = await read('app.manifest.json');
const indexPage = await read('js/react.index.js');
const importPage = await read('js/react.import.js');
const gridPage = await read('js/react.grid.js');
const mediaPage = await read('js/react.media.js');
const dashboardPage = await read('js/react.dashboard.js');
const settingsPage = await read('js/react.settings.js');
const jobsApi = await read('src/api/jobsApi.ts');

for (const marker of ['react.page-loader.js', 'react.shared.js']) {
  if (!indexHtml.includes(marker)) errors.push(`index.html missing ${marker}`);
}
if (!indexHtml.includes('id="backfront-app-root"')) {
  errors.push('index.html missing id="backfront-app-root"');
}

for (const page of ['index.html', 'import.html', 'grid.html', 'dashboard.html', 'settings.html']) {
  if (!routes.includes(page)) errors.push(`app.manifest.json missing ${page}`);
}

for (const [name, source, markers] of [
  ['index', indexPage, ['>Лог LLM<', '>Промты<', 'TablePaginationFooter']],
  ['import', importPage, ['ImportProgressPopup', 'TablePaginationFooter', 'setMembershipFilter']],
  ['grid', gridPage, ['TablePaginationFooter', 'Лимит времени', 'Лимит сообщений']],
  ['dashboard', dashboardPage, ['ETA', 'Состояние сейчас', 'progress']],
  ['settings', settingsPage, ['Данные лицензии', 'Проверить статус', 'Расширить локальные лимиты Import', 'settings-tabs']],
]) {
  for (const marker of markers) {
    if (!source.includes(marker)) errors.push(`js/react.${name}.js missing ${marker}`);
  }
}

for (const [name, source] of [
  ['index', indexPage],
  ['import', importPage],
  ['grid', gridPage],
  ['media', mediaPage],
]) {
  for (const forbidden of ['Боты</label>', 'Архив</label>', 'store.ui.showBots', 'store.ui.showArchived']) {
    if (source.includes(forbidden)) errors.push(`js/react.${name}.js must not expose source filter ${forbidden}`);
  }
}

for (const marker of ['createJob', 'getJob(', 'getJobEvents', 'cancelJob']) {
  if (!jobsApi.includes(marker)) errors.push(`src/api/jobsApi.ts missing ${marker}`);
}

for (const relPath of [
  'src/pages/index/ChatApp.tsx',
  'src/pages/index/ChatMessages.tsx',
  'src/pages/index/PromptSettings.tsx',
  'src/components/ProgressDialog.tsx',
]) {
  if (!exists(relPath)) errors.push(`missing split TSX artifact ${relPath}`);
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
