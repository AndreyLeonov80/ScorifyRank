import fs from 'node:fs';
import path from 'node:path';

const frontendRoot = process.cwd();
const repoRoot = path.resolve(frontendRoot, '..', '..');
const backendRoot = path.join(repoRoot, 'backfront', 'backend');

function read(relativePath) {
  return fs.readFileSync(path.join(repoRoot, relativePath), 'utf8');
}

const checks = [
  {
    file: 'backfront/backend/app/routers/data_sources.py',
    markers: [
      '/api/payme/data-sources/plugins',
      '/api/payme/data-sources',
      'connect_plugin',
      'preview_plugin',
      'enqueue_sync',
    ],
  },
  {
    file: 'backfront/backend/app/services/data_sources/base.py',
    markers: ['class BaseDataSourcePlugin', 'def connect', 'def introspect', 'def preview', 'def sync'],
  },
  {
    file: 'backfront/backend/app/services/data_sources/sql_table.py',
    markers: ['class SQLiteDataSourcePlugin', 'class DuckDBDataSourcePlugin', 'CanonicalMessagePreviewDTO'],
  },
  {
    file: 'backfront/backend/app/services/data_sources/registry.py',
    markers: ['plugin_type="telegram"', 'SQLiteDataSourcePlugin', 'DuckDBDataSourcePlugin', '"postgres"', '"mysql"', '"clickhouse"'],
  },
  {
    file: 'backfront/backend/app/services/jobs_runtime.py',
    markers: ['data_source.connect', 'data_source.introspect', 'data_source.preview', 'data_source.sync'],
  },
  {
    file: 'backfront/backend/x_files_license/tariffs.py',
    markers: ['data_source_plugins', 'data_source_writeback', 'data_source_plugins_max'],
  },
  {
    file: 'backfront/frontend/js/react.settings.js',
    markers: [
      'Источники данных / Plugins',
      '/api/payme/data-sources/plugins',
      '/api/payme/data-sources',
      'Проверить подключение',
      'Подключить источник',
      'data_source_plugins',
    ],
  },
];

const failures = [];

if (!fs.existsSync(backendRoot)) {
  failures.push(`backend root not found: ${backendRoot}`);
}

for (const check of checks) {
  const content = read(check.file);
  for (const marker of check.markers) {
    if (!content.includes(marker)) {
      failures.push(`${check.file}: missing marker "${marker}"`);
    }
  }
}

if (failures.length) {
  console.error('[audit:data-source-plugins] failed');
  for (const failure of failures) console.error(`- ${failure}`);
  process.exit(1);
}

console.log('[audit:data-source-plugins] ok');
