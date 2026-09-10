import { mkdir, readdir, readFile, rm, stat, writeFile, copyFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(ROOT, 'dist');
const ASSET_DIRS = ['css', 'js'];
const ENTRYPOINT = 'app.html';
const ROOT_FILES = ['app.manifest.json'];

function minifyCss(input) {
  return input
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\s+/g, ' ')
    .replace(/\s*([{}:;,>+~])\s*/g, '$1')
    .replace(/;}/g, '}')
    .trim();
}

function minifyHtml(input) {
  const placeholders = [];
  let html = input.replace(/<script\b[\s\S]*?<\/script>/gi, (match) => {
    const token = `__BACKFRONT_SCRIPT_${placeholders.length}__`;
    placeholders.push([token, match]);
    return token;
  });

  html = html.replace(/<style\b([^>]*)>([\s\S]*?)<\/style>/gi, (_, attrs, css) => {
    return `<style${attrs}>${minifyCss(css)}</style>`;
  });

  html = html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/>\s+</g, '><')
    .replace(/\s{2,}/g, ' ')
    .trim();

  for (const [token, script] of placeholders) {
    html = html.replace(token, script.trim());
  }

  return `${html}\n`;
}

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true });
}

async function copyTree(src, dest, transform = null) {
  await ensureDir(dest);
  const entries = await readdir(src, { withFileTypes: true });
  const copied = [];

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copied.push(...await copyTree(srcPath, destPath, transform));
      continue;
    }
    if (!entry.isFile()) continue;

    if (transform) {
      const content = await readFile(srcPath, 'utf8');
      await writeFile(destPath, transform(content, srcPath));
    } else {
      await copyFile(srcPath, destPath);
    }
    copied.push(destPath);
  }

  return copied;
}

async function collectBytes(dir) {
  let bytes = 0;
  let files = 0;
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const target = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const nested = await collectBytes(target);
      bytes += nested.bytes;
      files += nested.files;
      continue;
    }
    if (!entry.isFile()) continue;
    const info = await stat(target);
    bytes += info.size;
    files += 1;
  }
  return { bytes, files };
}

async function assertHtmlAssetLinks(htmlFiles) {
  const missing = [];
  for (const file of htmlFiles) {
    const html = await readFile(file, 'utf8');
    const refs = Array.from(html.matchAll(/\b(?:src|href|data-page-script)="([^"]+)"/g), (match) => match[1])
      .filter((ref) => !ref.startsWith('http') && !ref.startsWith('#') && !ref.startsWith('mailto:'))
      .map((ref) => ref.split(/[?#]/)[0])
      .filter(Boolean);

    for (const ref of refs) {
      const target = path.join(DIST, ref);
      try {
        const info = await stat(target);
        if (!info.isFile()) missing.push(`${path.basename(file)} -> ${ref}`);
      } catch {
        missing.push(`${path.basename(file)} -> ${ref}`);
      }
    }
  }

  if (missing.length) {
    throw new Error(`Missing built assets:\n${missing.join('\n')}`);
  }
}

function localAsset(ref) {
  return ref && !ref.startsWith('http') && !ref.startsWith('#') && !ref.startsWith('mailto:');
}

async function assertManifestAssetLinks() {
  const manifestPath = path.join(DIST, 'app.manifest.json');
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  const missing = [];

  for (const [pageName, page] of Object.entries(manifest.pages || {})) {
    const refs = [page.script, page.style, ...(page.dependencies || [])]
      .filter(localAsset)
      .map((ref) => ref.split(/[?#]/)[0])
      .filter(Boolean);

    for (const ref of refs) {
      const target = path.join(DIST, ref);
      try {
        const info = await stat(target);
        if (!info.isFile()) missing.push(`${pageName} -> ${ref}`);
      } catch {
        missing.push(`${pageName} -> ${ref}`);
      }
    }
  }

  if (missing.length) {
    throw new Error(`Missing manifest assets:\n${missing.join('\n')}`);
  }
}

async function main() {
  await rm(DIST, { recursive: true, force: true });
  await ensureDir(DIST);

  const html = await readFile(path.join(ROOT, ENTRYPOINT), 'utf8');
  const builtHtml = [path.join(DIST, 'index.html')];
  await writeFile(builtHtml[0], minifyHtml(html));

  for (const dir of ASSET_DIRS) {
    const srcDir = path.join(ROOT, dir);
    const destDir = path.join(DIST, dir);
    const transform = dir === 'css' ? minifyCss : null;
    await copyTree(srcDir, destDir, transform);
  }

  for (const file of ROOT_FILES) {
    await copyFile(path.join(ROOT, file), path.join(DIST, file));
  }

  await assertHtmlAssetLinks(builtHtml);
  await assertManifestAssetLinks();

  const totals = await collectBytes(DIST);
  const manifest = JSON.parse(await readFile(path.join(DIST, 'app.manifest.json'), 'utf8'));
  const report = {
    generatedAt: new Date().toISOString(),
    htmlFiles: builtHtml.length,
    pages: Object.keys(manifest.pages || {}).length,
    assetDirs: ASSET_DIRS,
    files: totals.files,
    bytes: totals.bytes,
    kib: Number((totals.bytes / 1024).toFixed(2)),
  };
  await writeFile(path.join(DIST, 'build-report.json'), `${JSON.stringify(report, null, 2)}\n`);

  console.log(JSON.stringify(report, null, 2));
}

await main();
