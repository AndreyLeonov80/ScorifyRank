import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(new URL('..', import.meta.url).pathname);
const runtimePath = resolve(root, 'js/react.runtime.js');
const runtime = readFileSync(runtimePath, 'utf8');

const checks = [
  ['BackfrontErrorBoundary class', /class\s+BackfrontErrorBoundary\s+extends\s+ReactApi\.Component/],
  ['createRoot patch', /reactDom\.createRoot\s*=\s*function\s+createRootWithBackfrontBoundary/],
  ['render wrapper', /originalRender\(withErrorBoundary\(node\)\)/],
  ['fallback reload button', /Обновить страницу/],
];

const failures = checks.filter(([, pattern]) => !pattern.test(runtime));
if (failures.length) {
  console.error('ErrorBoundary audit failed:');
  for (const [name] of failures) console.error(`- ${name}`);
  process.exit(1);
}

console.log('ErrorBoundary audit OK');
