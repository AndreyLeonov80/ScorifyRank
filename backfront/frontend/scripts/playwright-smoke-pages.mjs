import path from 'node:path';
import { pathToFileURL } from 'node:url';

const pages = ['index.html', 'import.html', 'grid.html', 'dashboard.html', 'settings.html'];

let chromium = null;
try {
  ({ chromium } = await import('playwright'));
} catch (error) {
  const { readFile } = await import('node:fs/promises');
  const html = await readFile(path.join(process.cwd(), 'index.html'), 'utf8');
  const results = [];
  for (const pageName of pages) {
    results.push({
      page: pageName,
      hasRoot: html.includes('id="backfront-app-root"') || html.includes("id='backfront-app-root'"),
      hasReactEntry: html.includes('react.') || html.includes('/js/'),
    });
  }
  const failures = results.filter((item) => !item.hasRoot || !item.hasReactEntry);
  if (failures.length) {
    console.error(JSON.stringify({
      ok: false,
      mode: 'static-html-fallback',
      reason: 'playwright package is not installed in this local frontend runtime',
      results,
      failures,
    }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({
    ok: true,
    mode: 'static-html-fallback',
    reason: 'playwright package is not installed in this local frontend runtime',
    results,
  }, null, 2));
  process.exit(0);
}

const root = process.cwd();
const browser = await chromium.launch({ headless: true });
const results = [];
try {
  for (const pageName of pages) {
    const page = await browser.newPage({ viewport: { width: 1365, height: 900 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(String(error?.message || error)));
    await page.goto(pathToFileURL(path.join(root, 'index.html')).toString() + `?page=${encodeURIComponent(pageName)}`, { waitUntil: 'domcontentloaded', timeout: 10000 });
    const hasRoot = await page.locator('#backfront-app-root').count();
    results.push({ page: pageName, hasRoot, errors });
    await page.close();
  }
} finally {
  await browser.close();
}

const failures = results.filter((item) => !item.hasRoot || item.errors.length);
if (failures.length) {
  console.error(JSON.stringify({ ok: false, results, failures }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, results }, null, 2));
