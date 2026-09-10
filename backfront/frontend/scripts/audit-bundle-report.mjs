import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();
const OUTPUT = path.join(ROOT, 'dist', 'bundle-report.json');
const BASELINE = process.env.BUNDLE_REPORT_BASELINE || '';
const INCLUDE_DIRS = ['js', 'css', 'assets'];

function walk(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return walk(full);
    if (!entry.isFile()) return [];
    const rel = path.relative(ROOT, full).replaceAll(path.sep, '/');
    return [{ path: rel, bytes: fs.statSync(full).size }];
  });
}

function collectReport() {
  const files = [
    ...INCLUDE_DIRS.flatMap((dir) => walk(path.join(ROOT, dir))),
    ...walk(path.join(ROOT, 'dist', 'assets')),
  ].filter((item) => !item.path.includes('/vendor/'));
  files.sort((a, b) => b.bytes - a.bytes || a.path.localeCompare(b.path));
  return {
    generatedAt: new Date().toISOString(),
    files: files.length,
    bytes: files.reduce((sum, item) => sum + item.bytes, 0),
    largest: files.slice(0, 40),
  };
}

function diffReport(current, baselinePath) {
  if (!baselinePath || !fs.existsSync(baselinePath)) return [];
  const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
  const before = new Map((baseline.largest || []).map((item) => [item.path, item.bytes]));
  return current.largest.map((item) => ({
    path: item.path,
    bytes: item.bytes,
    before: before.get(item.path) ?? null,
    delta: before.has(item.path) ? item.bytes - before.get(item.path) : null,
  }));
}

const report = collectReport();
report.diff = diffReport(report, BASELINE);
fs.mkdirSync(path.dirname(OUTPUT), { recursive: true });
fs.writeFileSync(OUTPUT, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify({ ok: true, output: path.relative(ROOT, OUTPUT), files: report.files, bytes: report.bytes }, null, 2));
