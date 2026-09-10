import { readFile, stat } from 'node:fs/promises';
import { gzipSync } from 'node:zlib';
import path from 'node:path';

const root = process.cwd();
const scriptPath = path.join(root, 'js', 'script.api.js');
const scriptSource = await readFile(scriptPath, 'utf8');
const scriptStat = await stat(scriptPath);
const entrypointSource = await readFile(path.join(root, 'app.html'), 'utf8');
const manifest = JSON.parse(await readFile(path.join(root, 'app.manifest.json'), 'utf8'));
const manifestReferences = Object.entries(manifest.pages || {})
  .filter(([, page]) => (page.dependencies || []).some((dependency) => dependency.includes('js/script.api.js')))
  .map(([page]) => page)
  .sort();

const globalFactories = Array.from(scriptSource.matchAll(/window\.([A-Za-z0-9_]+)\s*=\s*function\s+([A-Za-z0-9_]+)/g))
  .map((match) => `${match[1]}:${match[2]}`);
const endpointConstants = Array.from(scriptSource.matchAll(/const\s+(URL_[A-Z0-9_]+)\s*=/g))
  .map((match) => match[1]);
const apiHelpers = Array.from(scriptSource.matchAll(/async function\s+(api[A-Za-z0-9_]+)/g))
  .map((match) => match[1]);
const debugConsoleLogs = Array.from(scriptSource.matchAll(/console\.log\(/g)).length;

const result = {
  script: path.relative(root, scriptPath),
  sourceBytes: scriptStat.size,
  gzipBytes: gzipSync(scriptSource).length,
  manifestReferences,
  globalFactories,
  endpointConstantsCount: endpointConstants.length,
  apiHelpersCount: apiHelpers.length,
  debugConsoleLogs,
};

console.log(JSON.stringify(result, null, 2));

if (!scriptSource.includes('window.BackfrontApi.apiJson')) {
  throw new Error('script.api.js does not delegate to window.BackfrontApi.apiJson');
}

if (entrypointSource.includes('js/script.api.js')) {
  throw new Error('app.html should not load script.api.js directly');
}

if (debugConsoleLogs > 0) {
  throw new Error(`script.api.js still has ${debugConsoleLogs} direct console.log calls`);
}

if (scriptStat.size > 48 * 1024) {
  throw new Error(`script.api.js source is ${scriptStat.size} bytes, expected <= ${48 * 1024}`);
}

if (gzipSync(scriptSource).length > 25 * 1024) {
  throw new Error(`script.api.js gzip is ${gzipSync(scriptSource).length} bytes, expected <= ${25 * 1024}`);
}

if (!manifestReferences.every((page) => {
  const deps = manifest.pages?.[page]?.dependencies || [];
  return deps.some((dependency) => dependency.includes('js/outreach.shared.js'));
})) {
  throw new Error('pages that load script.api.js must load outreach.shared.js before it');
}
