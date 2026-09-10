import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const entrypoint = await readFile(path.join(root, 'js', 'app.entry.js'), 'utf8');
const errors = [];

for (const marker of [
  '/api/payme/runtime-status',
  'authorized',
  'SESSION_RECONNECTING_STATUSES',
  'needs_api_credentials',
  'needs_auth',
  'timeoutMs: 1000',
  'setup_wizard.html',
  'redirectToSetupWizard',
]) {
  if (!entrypoint.includes(marker)) {
    errors.push(`app.entry.js: missing setup redirect marker ${marker}`);
  }
}

if (!entrypoint.includes("SETUP_REQUIRED_STATUSES") || !entrypoint.includes("'needs_api_credentials'") || !entrypoint.includes("'needs_auth'")) {
  errors.push('app.entry.js: protected pages must redirect only for concrete setup/auth requirements');
}

if (!entrypoint.includes("SESSION_RECONNECTING_STATUSES.has(authStatus)")) {
  errors.push('app.entry.js: session_present/unknown must not block the app while backend reconnects');
}

if (!/encodeURIComponent\([^)]*window\.location\.pathname/.test(entrypoint)) {
  errors.push('app.entry.js: setup redirect must preserve current page in next=');
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
