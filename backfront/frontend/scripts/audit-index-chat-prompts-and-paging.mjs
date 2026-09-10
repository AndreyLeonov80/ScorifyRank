import { readFileSync } from 'node:fs';

const reactIndex = readFileSync(new URL('../js/react.index.js', import.meta.url), 'utf8');
const reactIndexChat = readFileSync(new URL('../js/react.index.chat.js', import.meta.url), 'utf8');
const reactIndexHistory = readFileSync(new URL('../js/react.index.history.js', import.meta.url), 'utf8');
const styleCss = readFileSync(new URL('../css/style.css', import.meta.url), 'utf8');
const leadStore = readFileSync(new URL('../js/legacy.lead.store.js', import.meta.url), 'utf8');
const packageJson = readFileSync(new URL('../package.json', import.meta.url), 'utf8');
const backend = readFileSync(new URL('../../backend/back.py', import.meta.url), 'utf8');
const backendState = readFileSync(new URL('../../backend/app/core/state.py', import.meta.url), 'utf8');
const backendTelegramSources = readFileSync(new URL('../../backend/app/services/telegram_sources_runtime.py', import.meta.url), 'utf8');
const backendLeads = readFileSync(new URL('../../backend/app/services/leads.py', import.meta.url), 'utf8');
const indexRuntime = `${reactIndex}\n${reactIndexChat}\n${reactIndexHistory}`;
const leadRuntime = `${leadStore}\n${reactIndex}`;
const backendRuntime = `${backend}\n${backendState}\n${backendTelegramSources}\n${backendLeads}`;

const requiredReactMarkers = [
  'PromptSettingsModal',
  'PROMPT_SETTINGS_PAGE_SIZE = 5',
  'promptTotalPages',
  'visiblePrompts',
  'Назад',
  'Далее',
  'prompt-settings-title',
  'prompt-settings-label-row',
  'openGlobalPromptSettings',
  'Промты',
  'RepeatRequestModal',
  'Повторить в LLM',
  'repeat-request-card',
  'repeat-request-prompt-field',
  'repeat-request-label-row',
  'placeholder="Отредактируйте промт',
  'usersPagingKey',
  '2 строки',
  '15 строк',
  '20 строк',
  'chat-users-toolbar',
  'Предыдущая страница пользователей',
  'Следующая страница пользователей',
  'onManagePrompts',
  'chat-message-input',
  'event.shiftKey',
  'resizeComposer',
];

const requiredStoreMarkers = [
  'LAST_OPEN_CHAT_KEY',
  'rememberCurrentLead',
  'openLastLeadAfterLoad',
  'requestAnimationFrame',
  'preserveTopScrollAfterOlderLoad',
  'appendOptimisticOutgoingMessage',
  'updateOptimisticOutgoingMessage',
];

for (const marker of requiredReactMarkers) {
  if (!indexRuntime.includes(marker)) {
    throw new Error(`react.index runtime missing marker: ${marker}`);
  }
}

for (const marker of [
  'width: min(92vw, 1500px)',
  'height: 92vh',
  'min-height: 360px',
  '.prompt-settings-title-input',
]) {
  if (!styleCss.includes(marker)) {
    throw new Error(`prompt CSS missing marker: ${marker}`);
  }
}

for (const marker of requiredStoreMarkers) {
  if (!leadRuntime.includes(marker)) {
    throw new Error(`lead runtime missing marker: ${marker}`);
  }
}

for (const marker of [
  'FileNotFoundError',
  'uuid.uuid4().hex',
  'errno.ENOENT',
  'dialog.is_already_added = bool(dialog_identities.intersection(source_identities))',
  '_mark_telegram_dialogs_cache_removed([normalized_selector])',
]) {
  if (!backendRuntime.includes(marker)) {
    throw new Error(`backend runtime missing marker: ${marker}`);
  }
}

if (!packageJson.includes('"scss:build"') || !packageJson.includes('"audit:scss"')) {
  throw new Error('package.json missing SCSS scripts');
}

console.log(JSON.stringify({ ok: true }, null, 2));
