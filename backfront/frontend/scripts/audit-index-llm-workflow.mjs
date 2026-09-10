import { readFile } from 'node:fs/promises';
import path from 'node:path';

const root = process.cwd();
const reactIndex = await readFile(path.join(root, 'js', 'react.index.js'), 'utf8');
const reactIndexDetail = await readFile(path.join(root, 'js', 'react.index.detail.js'), 'utf8');
const reactIndexHistory = await readFile(path.join(root, 'js', 'react.index.history.js'), 'utf8');
const reactIndexAnalysis = await readFile(path.join(root, 'js', 'react.index.analysis.js'), 'utf8');
const leadStore = await readFile(path.join(root, 'js', 'legacy.lead.store.js'), 'utf8');
const css = await readFile(path.join(root, 'css', 'pages', 'index.css'), 'utf8');
const errors = [];

for (const marker of [
  'openHistoryPopup',
  'answerPopupItem',
  'latestAnswerFor',
  'Скопировать в буфер и в сообщение',
  'layout-resize-handle',
  'startPanelResize',
]) {
  if (!reactIndex.includes(marker)) {
    errors.push(`js/react.index.js: missing ${marker}`);
  }
}

for (const marker of [
  'ChatAnalysisPanel',
  'ChatAnalysisModal',
  'openLogPopup',
  'setLogPopupOpen(true);',
]) {
  if (!reactIndexAnalysis.includes(marker)) {
    errors.push(`js/react.index.analysis.js: missing ${marker}`);
  }
}

for (const marker of [
  'DetailPopup',
  'chat-analysis-detail-popup',
  'LlmLogPopupBody',
  'LlmLogNavigator',
  'logFileHref',
]) {
  if (!reactIndexDetail.includes(marker)) {
    errors.push(`js/react.index.detail.js: missing ${marker}`);
  }
}

for (const marker of [
  'xfiles.chatPanelLayout.v1',
  'ChatHistoryPager',
  'AnalysisHistoryPager',
  'PromptSettingsModal',
]) {
  if (!reactIndexHistory.includes(marker)) {
    errors.push(`js/react.index.history.js: missing ${marker}`);
  }
}

for (const marker of [
  '_chatAnalysisProgressTimer',
  '_startChatAnalysisProgress',
  'refreshChatAnalysis',
  'kind: \'request\'',
  'kind: \'response\'',
  '3000',
]) {
  if (!leadStore.includes(marker)) {
    errors.push(`js/legacy.lead.store.js: missing ${marker}`);
  }
}

for (const marker of [
  '.detail-popup-backdrop',
  '.detail-popup',
  '80vw',
  '80vh',
  '.layout-resize-handle',
  '--chat-main-width',
  '--chat-ai-width',
]) {
  if (!css.includes(marker)) {
    errors.push(`css/pages/index.css: missing ${marker}`);
  }
}

if (errors.length) {
  console.error(JSON.stringify({ ok: false, errors }, null, 2));
  process.exit(1);
}

console.log(JSON.stringify({ ok: true }, null, 2));
