import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const expected = [
  ['js/legacy.lead.dom.js', ['window.BackfrontLeadDom']],
  ['js/legacy.lead.store.js', ['window.leadApp']],
  ['js/legacy.grid.store.js', ['window.gridApp']],
  ['js/legacy.contacts.store.js', ['window.contactsApp']],
  ['js/legacy.crm.store.js', ['window.crmApp']],
  ['js/legacy.outreach.store.js', ['window.outreachApp']],
  ['js/legacy.media.store.js', ['window.mediaApp', 'window.imagesApp']],
  ['js/legacy.events.store.js', ['window.eventsApp']],
  ['js/legacy.import.store.js', ['window.telegramImportApp']],
  ['js/legacy.jur-entities.store.js', ['window.jurEntitiesApp']],
];

const manifest = JSON.parse(await readFile(path.join(root, 'app.manifest.json'), 'utf8'));
const errors = [];

for (const [file, markers] of expected) {
  let source = '';
  try {
    source = await readFile(path.join(root, file), 'utf8');
  } catch (error) {
    errors.push(`${file}: cannot read (${error.message})`);
    continue;
  }
  for (const marker of markers) {
    if (!source.includes(marker)) {
      errors.push(`${file}: missing ${marker}`);
    }
  }
}

const dependencyText = JSON.stringify(manifest.pages || {});
for (const [file] of expected) {
  if (!dependencyText.includes(file)) {
    errors.push(`app.manifest.json: missing dependency ${file}`);
  }
}

const scriptSource = await readFile(path.join(root, 'js', 'script.api.js'), 'utf8');
for (const marker of expected.filter(([file]) => file !== 'js/legacy.lead.dom.js').flatMap(([, markers]) => markers)) {
  if (scriptSource.includes(`${marker} = function`)) {
    errors.push(`script.api.js still defines ${marker}`);
  }
}

const leadStoreSource = await readFile(path.join(root, 'js', 'legacy.lead.store.js'), 'utf8');
for (const marker of ['document.', 'localStorage', 'window.confirm', 'document.addEventListener', 'requestAnimationFrame']) {
  if (leadStoreSource.includes(marker)) {
    errors.push(`legacy.lead.store.js still has direct DOM side effect marker ${marker}`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
