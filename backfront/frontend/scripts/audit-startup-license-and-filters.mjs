import { readFileSync } from 'node:fs';

const files = {
  lead: readFileSync(new URL('../js/legacy.lead.store.js', import.meta.url), 'utf8'),
  importStore: readFileSync(new URL('../js/legacy.import.store.js', import.meta.url), 'utf8'),
  gridStore: readFileSync(new URL('../js/legacy.grid.store.js', import.meta.url), 'utf8'),
  index: readFileSync(new URL('../js/react.index.js', import.meta.url), 'utf8'),
  settings: readFileSync(new URL('../js/react.settings.js', import.meta.url), 'utf8'),
  pkg: readFileSync(new URL('../package.json', import.meta.url), 'utf8'),
  backend: [
    readFileSync(new URL('../../backend/app/legacy_runtime.py', import.meta.url), 'utf8'),
    readFileSync(new URL('../../backend/app/core/app_settings.py', import.meta.url), 'utf8'),
    readFileSync(new URL('../../backend/app/services/config.py', import.meta.url), 'utf8'),
    readFileSync(new URL('../../backend/app/services/license_runtime.py', import.meta.url), 'utf8'),
  ].join('\n'),
  tariffs: readFileSync(new URL('../../backend/x_files_license/tariffs.py', import.meta.url), 'utf8'),
};

for (const [name, source] of Object.entries({
  'legacy.lead.store.js': files.lead,
  'legacy.import.store.js': files.importStore,
  'legacy.grid.store.js': files.gridStore,
})) {
  for (const marker of ['showChannels: false', 'showGroups: true', 'showPrivate: false']) {
    if (!source.includes(marker)) throw new Error(`${name} missing default marker: ${marker}`);
  }
  for (const marker of ['showBots:', 'showArchived:', 'Боты</label>', 'Архив</label>']) {
    if (source.includes(marker)) throw new Error(`${name} must not expose hidden source filter: ${marker}`);
  }
  if (!source.includes('groups-default.v1')) {
    throw new Error(`${name} missing versioned groups-only UI state key`);
  }
}

for (const marker of ['openGlobalPromptSettings', '>Промты<', '>Лог LLM<']) {
  if (!files.index.includes(marker)) throw new Error(`react.index.js missing ${marker}`);
}
if (files.index.includes('setSettings(event?.detail || settings)')) {
  throw new Error('react.index.js keeps stale ChatUsersPanel setSettings handler');
}

for (const marker of [
  'Данные лицензии',
  'Проверить статус',
  'enableUnlimitedImportMode',
  'Включить безлимитную загрузку',
  'telegram_unlimited_import',
  'local_import_limits_enabled',
  'Расширить локальные лимиты Import',
]) {
  if (!files.settings.includes(marker)) throw new Error(`react.settings.js missing ${marker}`);
}

for (const marker of [
  'local_import_limits_enabled',
  'api_payme_license_update',
  'license_capabilities',
  '_local_import_limit_override',
]) {
  if (!files.backend.includes(marker)) throw new Error(`backend runtime missing ${marker}`);
}

for (const marker of ['import_history_months_max', 'import_message_limit_max', 'license_capabilities']) {
  if (!files.tariffs.includes(marker)) throw new Error(`tariffs.py missing ${marker}`);
}

if (!files.pkg.includes('"audit:startup-license-filters"')) {
  throw new Error('package.json missing audit:startup-license-filters');
}

console.log(JSON.stringify({ ok: true }, null, 2));
