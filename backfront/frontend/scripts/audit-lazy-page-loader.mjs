import { access, readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PAGE_SCRIPT_RE = /<script\s+src="(js\/react\.(?!(?:runtime|shared|stub|page-loader)\b)[^"]+\.js(?:\?[^"]+)?)"\s+defer><\/script>/;

async function main() {
  const errors = [];
  const pageLoaderPath = path.join(ROOT, 'js', 'react.page-loader.js');
  try {
    await access(pageLoaderPath);
  } catch {
    errors.push('missing js/react.page-loader.js');
  }

  const entrypoint = await readFile(path.join(ROOT, 'app.html'), 'utf8');
  const directPageScript = entrypoint.match(PAGE_SCRIPT_RE)?.[1] || '';
  if (directPageScript) {
    errors.push(`app.html: direct page bundle script remains: ${directPageScript}`);
  }
  if (!/src="js\/react\.page-loader\.js(?:\?[^"]+)?"/.test(entrypoint)) {
    errors.push('app.html: missing lazy page loader script');
  }
  if (!/src="\/src\/main\.tsx(?:\?[^"]+)?"/.test(entrypoint)) {
    errors.push('app.html: missing Vite TSX entrypoint');
  }

  const manifest = JSON.parse(await readFile(path.join(ROOT, 'app.manifest.json'), 'utf8'));
  for (const [pageName, page] of Object.entries(manifest.pages || {})) {
    if (!/^js\/react\.[^"]+\.js(?:\?[^"]+)?$/.test(page.script || '')) {
      errors.push(`${pageName}: invalid page script ${page.script || ''}`);
    }
    if (!page.rootId) {
      errors.push(`${pageName}: missing rootId`);
    }
    if (!page.style?.startsWith('css/pages/')) {
      errors.push(`${pageName}: missing page stylesheet`);
    }
  }

  if (errors.length) {
    console.error(JSON.stringify({ ok: false, errors }, null, 2));
    process.exit(1);
  }

  console.log(JSON.stringify({ ok: true, entrypoint: 'app.html', pages: Object.keys(manifest.pages || {}).length }, null, 2));
}

await main();
