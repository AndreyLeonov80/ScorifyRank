import { readFileSync } from 'node:fs';

const reactIndex = readFileSync(new URL('../js/react.index.js', import.meta.url), 'utf8');
const reactIndexDetail = readFileSync(new URL('../js/react.index.detail.js', import.meta.url), 'utf8');
const reactIndexHistory = readFileSync(new URL('../js/react.index.history.js', import.meta.url), 'utf8');
const reactIndexChat = readFileSync(new URL('../js/react.index.chat.js', import.meta.url), 'utf8');
const leadStore = readFileSync(new URL('../js/legacy.lead.store.js', import.meta.url), 'utf8');

const requiredReactMarkers = [
  'onEnter,',
  'openGlobalLlmLog',
  'Обновить пользователей',
  'React.useLayoutEffect',
  'pinToLatest',
  'store.messageScrollRatio || 1',
  'chat-users-refresh-progress',
];

const requiredDetailMarkers = [
  'LlmLogNavigator',
  'Предыдущий лог',
  'Следующий лог',
  'Открыть полный лог',
  'logFileHref',
];

const requiredHistoryMarkers = [
  'ChatHistoryPager',
  'AnalysisHistoryPager',
];

const requiredChatMarkers = [
  'store.visibleMessages().map',
  'store.handleChatScroll?.(event)',
  'chat-scroll-meter',
  'Здесь будет живая история сообщений и выбор сообщений для LLM-анализа',
];

const requiredStoreMarkers = [
  'isAbortedRequestError(e)',
  'refreshChatUsers',
  'chatUsersRefresh',
  'loadOlderMessages',
  'visibleMessages',
  'handleChatScroll',
  'messagesLimit: 30',
  'messageRenderSize: 30',
  'messageRenderWindowSize',
  'Math.min(30',
  'messagesLoadingMore',
  'messagesLoadedOffset',
  'verifyOutgoingDelivery',
  "send_status: 'checking'",
  'hasDeliveredOutgoingMessage',
  '_authInflight',
  '_leadInflight',
  '_llmInflight',
  '15000',
  '30000',
];

for (const marker of requiredReactMarkers) {
  if (!reactIndex.includes(marker)) {
    throw new Error(`react.index.js missing marker: ${marker}`);
  }
}

for (const marker of requiredDetailMarkers) {
  if (!reactIndexDetail.includes(marker)) {
    throw new Error(`react.index.detail.js missing marker: ${marker}`);
  }
}

for (const marker of requiredHistoryMarkers) {
  if (!reactIndexHistory.includes(marker)) {
    throw new Error(`react.index.history.js missing marker: ${marker}`);
  }
}

for (const marker of requiredChatMarkers) {
  if (!reactIndexChat.includes(marker)) {
    throw new Error(`react.index.chat.js missing marker: ${marker}`);
  }
}

for (const marker of requiredStoreMarkers) {
  if (!leadStore.includes(marker)) {
    throw new Error(`legacy.lead.store.js missing marker: ${marker}`);
  }
}

if (reactIndex.includes('Пользователи в чате')) {
  throw new Error('ChatUsersPanel should not render the old "Пользователи в чате" header block');
}

if (reactIndex.includes('chat-analysis-progress-log')) {
  throw new Error('Inline "Лог LLM" block should be removed from the right panel');
}

if (leadStore.includes('Math.round(maxStart * ratio)')) {
  throw new Error('Chat scroll must not swap rendered message window on every scroll event');
}

if (reactIndex.includes('<${OutreachToggle} store=${store} payload=${payload} title="Добавить сообщение в enReach" />')) {
  throw new Error('Chat message bubbles must not render the plus/enReach toggle');
}

console.log(JSON.stringify({ ok: true }, null, 2));
