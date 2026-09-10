import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const source = fs.readFileSync(path.join(root, 'js', 'react.setup_wizard.js'), 'utf8');

const checks = [
  ['delivery text helper', 'authCodeDeliveryText'],
  ['delivery status field', 'auth_code_delivery_type'],
  ['next delivery field', 'auth_code_next_type'],
  ['cooldown field', 'auth_code_timeout_sec'],
  ['resend endpoint', '/api/payme/auth/phone/resend'],
  ['resend button', 'Запросить SMS/другой способ'],
  ['reset button', 'Сбросить код и запросить заново'],
  ['restart hint', 'Код был запрошен до перезапуска backend'],
  ['runtime diagnostics block', 'Диагностика Telegram runtime'],
  ['auth action message helper', 'telegramAuthActionMessage'],
  ['auth action prefers backend sent-code message', 'data?.status?.auth_code_message'],
  ['session file fact', 'session_file_exists'],
  ['authorized fact', 'telegram_authorized'],
  ['worker fact', 'worker_connected'],
  ['sync paused fact', 'sync_paused'],
  ['sync reading fact', 'sync_reading'],
];

const missing = checks.filter(([, needle]) => !source.includes(needle));

if (missing.length) {
  console.error(JSON.stringify({ ok: false, missing: missing.map(([name]) => name) }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true, checks: checks.map(([name]) => name) }, null, 2));
