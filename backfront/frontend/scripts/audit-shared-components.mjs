import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

async function read(relPath) {
  return readFile(path.join(ROOT, relPath), 'utf8');
}

async function main() {
  const errors = [];
  const shared = await read('js/react.shared.js');
  const needs = await read('js/react.needs.js');
  const calendar = await read('js/react.calendar.js');

  for (const name of ['DataTable', 'Modal', 'FormGrid', 'FormField']) {
    if (!shared.includes(`function ${name}(`)) errors.push(`react.shared.js: missing function ${name}`);
    if (!new RegExp(`\\n\\s*${name},`).test(shared)) errors.push(`react.shared.js: ${name} is not exported`);
  }

  for (const name of ['DataTable', 'FormGrid', 'FormField']) {
    if (!needs.includes(name)) errors.push(`react.needs.js: missing ${name} usage`);
  }

  if (!calendar.includes('Modal')) errors.push('react.calendar.js: missing Modal usage');
  for (const marker of ['telegram-logout', 'logoutTelegram', "label: 'Выйти'"]) {
    if (!shared.includes(marker)) errors.push(`react.shared.js: missing Ext logout marker ${marker}`);
  }
  if (/<div className="event-modal-backdrop"/.test(calendar)) {
    errors.push('react.calendar.js: still renders event modal backdrop inline');
  }
  if (/<div className="table-scroll">\\s*<table/.test(needs)) {
    errors.push('react.needs.js: still renders needs table inline');
  }

  if (errors.length) {
    console.error(JSON.stringify({ ok: false, errors }, null, 2));
    process.exit(1);
  }

  console.log(JSON.stringify({ ok: true }, null, 2));
}

await main();
