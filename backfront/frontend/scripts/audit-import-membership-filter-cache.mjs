import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const apiSource = await readFile(path.join(root, 'js', 'script.api.js'), 'utf8');
const storeSource = await readFile(path.join(root, 'js', 'legacy.import.store.js'), 'utf8');
const manifestSource = await readFile(path.join(root, 'app.manifest.json'), 'utf8');

const errors = [];

if (!apiSource.includes("gramlead.import.dialogs.cache.v3")) {
  errors.push('script.api.js: Import dialogs cache key must be v3 to ignore stale membership-filter caches.');
}

if (!manifestSource.includes('script.api.js?v=20260523-import-membership-cache-v3') ||
    !manifestSource.includes('legacy.import.store.js?v=20260523-import-membership-cache-v3')) {
  errors.push('app.manifest.json: import.html must bump script.api.js and legacy.import.store.js versions for browser cache busting.');
}

if (!storeSource.includes("buildPagedRequestOptions('import:dialogs:v3'")) {
  errors.push('legacy.import.store.js: Import dialogs API cache scope must be v3 to ignore stale persistent membership-filter responses.');
}

if (!/setMembershipFilter\(filterName\)[\s\S]*?this\.dialogs\s*=\s*\[\]/.test(storeSource)) {
  errors.push('legacy.import.store.js: setMembershipFilter must clear visible rows before loading a new membership filter.');
}

if (!/setMembershipFilter\(filterName\)[\s\S]*?this\.totalDialogs\s*=\s*0/.test(storeSource)) {
  errors.push('legacy.import.store.js: setMembershipFilter must reset totalDialogs before loading a new membership filter.');
}

if (!/setMembershipFilter\(filterName\)[\s\S]*?this\.cacheWarning\s*=\s*null/.test(storeSource)) {
  errors.push('legacy.import.store.js: setMembershipFilter must clear old cache warnings before loading a new membership filter.');
}

if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}

console.log('OK import membership filter cache audit');
