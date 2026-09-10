import { copyFile, mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { transform } from 'esbuild';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DIST = path.join(ROOT, 'dist');
const ASSET_DIRS = ['css', 'js'];
const ROOT_FILES = ['app.manifest.json'];

function minifyCss(input) {
  return input
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\s+/g, ' ')
    .replace(/\s*([{}:;,>+~])\s*/g, '$1')
    .replace(/;}/g, '}')
    .trim();
}

async function minifyJs(input) {
  const result = await transform(input, {
    loader: 'js',
    minify: true,
    legalComments: 'none',
  });
  return result.code.trim();
}

async function ensureDir(dir) {
  await mkdir(dir, { recursive: true });
}

async function copyTree(src, dest, transformContent = null) {
  await ensureDir(dest);
  const entries = await readdir(src, { withFileTypes: true });
  const copied = [];

  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copied.push(...await copyTree(srcPath, destPath, transformContent));
      continue;
    }
    if (!entry.isFile()) continue;

    if (transformContent) {
      const content = await readFile(srcPath, 'utf8');
      await writeFile(destPath, await transformContent(content, srcPath));
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
  for (const dir of ASSET_DIRS) {
    const srcDir = path.join(ROOT, dir);
    const destDir = path.join(DIST, dir);
    const transformContent = dir === 'css'
      ? (content) => minifyCss(content)
      : (content, srcPath) => srcPath.endsWith('.js') ? minifyJs(content) : content;
    await copyTree(srcDir, destDir, transformContent);
  }

  for (const file of ROOT_FILES) {
    await copyFile(path.join(ROOT, file), path.join(DIST, file));
  }

  await assertManifestAssetLinks();

  const totals = await collectBytes(DIST);
  const manifest = JSON.parse(await readFile(path.join(DIST, 'app.manifest.json'), 'utf8'));
  const report = {
    generatedAt: new Date().toISOString(),
    htmlFiles: 1,
    pages: Object.keys(manifest.pages || {}).length,
    assetDirs: [...ASSET_DIRS, 'assets'],
    files: totals.files,
    bytes: totals.bytes,
    kib: Number((totals.bytes / 1024).toFixed(2)),
  };
  await writeFile(path.join(DIST, 'build-report.json'), `${JSON.stringify(report, null, 2)}\n`);

  console.log(JSON.stringify(report, null, 2));
}

await main();
