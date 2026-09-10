import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const shared = fs.readFileSync(path.join(root, 'js', 'react.shared.js'), 'utf8');

const markers = [
  'const APP_VERSION =',
  'const APP_RELEASE_AT =',
  'window.XFILES_APP_VERSION',
  'window.XFILES_RELEASE_AT',
  'xfiles-version-badge',
  'xfiles-release-meta',
  'Docker release',
];

const missing = markers.filter((marker) => !shared.includes(marker));
const versionMatch = shared.match(/APP_VERSION\s*=\s*String\([^|]+\|\|\s*'([^']+)'/);
const releaseMatch = shared.match(/APP_RELEASE_AT\s*=\s*String\([^|]+\|\|\s*'([^']+)'/);

if (!versionMatch || !/^\d+\.\d{2}$/.test(versionMatch[1])) {
  missing.push('APP_VERSION default must look like 2.02');
}
if (!releaseMatch || !/^\d{4}-\d{2}-\d{2} \d{2}:\d{2} MSK$/.test(releaseMatch[1])) {
  missing.push('APP_RELEASE_AT default must include date/time and MSK');
}

if (missing.length) {
  console.error('[audit:release-version] failed');
  for (const marker of missing) console.error(`- ${marker}`);
  process.exit(1);
}

console.log('[audit:release-version] ok', { version: versionMatch[1], releaseAt: releaseMatch[1] });

