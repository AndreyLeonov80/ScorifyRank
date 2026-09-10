import fs from 'node:fs';

const checks = [];

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}

function exists(path) {
  return fs.existsSync(new URL(`../${path}`, import.meta.url));
}

function assert(name, ok) {
  checks.push({ name, ok: Boolean(ok) });
}

const packageJson = JSON.parse(read('package.json'));
const tsconfig = JSON.parse(read('tsconfig.json'));
const apiTypes = read('src/types/api.ts');
const manifest = read('app.manifest.json');
const importStore = read('js/legacy.import.store.js');
const importPage = read('js/react.import.js');
const importScss = read('scss/pages/import.scss');

assert('tsconfig keeps gradual allowJs migration', tsconfig.compilerOptions?.allowJs === true);
assert('tsconfig keeps strict TS for new files', tsconfig.compilerOptions?.strict === true);
assert('package exposes npm run typecheck', packageJson.scripts?.typecheck === 'tsc --noEmit');
assert('shared ApiResponse<T> contract exists', /export type ApiResponse<T>/.test(apiTypes));
assert('typed Telegram API client exists', exists('src/api/telegramApi.ts'));
assert('typed leads API client exists', exists('src/api/leadsApi.ts'));
assert('typed chat API client exists', exists('src/api/chatApi.ts'));
assert('typed chat analysis API client exists', exists('src/api/analysisApi.ts'));
assert('typed deals API client exists', exists('src/api/dealsApi.ts'));
assert('typed settings API client exists', exists('src/api/settingsApi.ts'));
assert('typed jobs API client exists', exists('src/api/jobsApi.ts'));
assert('typed prompts API client exists', exists('src/api/promptsApi.ts'));
assert('legacy response adapter exists', exists('src/api/response.ts') && read('src/api/response.ts').includes('unwrapApiResponse'));
assert('Import progress TSX component exists', exists('src/pages/import/ImportProgressDialog.tsx'));
assert('index TSX component split exists', [
  'src/pages/index/ChatApp.tsx',
  'src/pages/index/ChatMessages.tsx',
  'src/pages/index/ChatUsers.tsx',
  'src/pages/index/ChatAnalysis.tsx',
  'src/pages/index/LlmLogPopup.tsx',
  'src/pages/index/PromptSettings.tsx',
].every(exists));
assert('dashboard jobs panel TSX exists', exists('src/pages/dashboard/JobsPanel.tsx') && read('src/pages/dashboard/JobsPanel.tsx').includes('getJobs'));
assert('settings typed sections exist', exists('src/pages/settings/SettingsSections.tsx') && [
  'TelegramSettingsSection',
  'OpenRouterSettingsSection',
  'LicenseOverrideSettingsSection',
  'ImportLimitsSettingsSection',
  'RuntimeStatusSettingsSection',
].every((marker) => read('src/pages/settings/SettingsSections.tsx').includes(marker)));
assert('deals cache status TSX exists', exists('src/pages/deals/DealsCacheStatus.tsx') && read('src/pages/deals/DealsCacheStatus.tsx').includes('isDealsPostgresWaiting'));
assert('legacy lead typed slices exist', exists('src/pages/index/legacyLeadSlices.ts'));
assert('legacy lead domain slice files exist', [
  'src/pages/index/leadStore.core.ts',
  'src/pages/index/leadStore.chat.ts',
  'src/pages/index/leadStore.analysis.ts',
  'src/pages/index/leadStore.users.ts',
  'src/pages/index/leadStore.prompts.ts',
].every(exists));
assert('index typed utility helpers exist', exists('src/pages/index/utils.ts') && read('src/pages/index/utils.ts').includes('normalizeChatAnswerPrompts'));
assert('shared typed components exist', [
  'src/components/ChannelFilter.tsx',
  'src/components/DealTable.tsx',
  'src/components/LeadCard.tsx',
  'src/components/ProgressDialog.tsx',
].every(exists));
assert('import store has first-load progress state', /importProgress:\s*\{/.test(importStore) && /startImportProgress/.test(importStore));
assert('import page renders progress popup', /ImportProgressPopup/.test(importPage) && /Импорт Telegram/.test(importPage));
assert('import progress popup is styled in SCSS', /import-progress-popup/.test(importScss) && /import-progress-bar/.test(importScss));
assert('manifest cache busts import progress build', /import-progress-ts-plan/.test(manifest));

const failed = checks.filter((check) => !check.ok);
for (const check of checks) {
  console.log(`${check.ok ? '[x]' : '[ ]'} ${check.name}`);
}

if (failed.length) {
  console.error(`\nFailed checks: ${failed.map((check) => check.name).join(', ')}`);
  process.exit(1);
}
