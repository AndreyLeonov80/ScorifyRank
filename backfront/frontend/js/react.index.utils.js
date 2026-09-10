/* Shared helpers for react.index.js legacy entrypoint */
'use strict';

(function initReactIndexUtils() {
  function formatEta(sec) {
    const total = Math.max(0, Number(sec || 0));
    if (!total) return '—';
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    if (!minutes) return `${seconds} сек`;
    return `${minutes} мин ${String(seconds).padStart(2, '0')} сек`;
  }

  function parseLlmPanelHtml(rawHtml = '') {
    const emptyAnswers = [1, 2, 3].map((idx) => ({
      id: `answer-${idx}`,
      title: `Ответ ${idx}`,
      label: 'Ответ ещё не создан',
      text: '',
      isPlaceholder: true,
    }));
    const fallback = {
      tokens: '—',
      answers: emptyAnswers,
      hasLegacyDraft: false,
    };
    const source = String(rawHtml || '').trim();
    if (!source) return fallback;

    try {
      const doc = new DOMParser().parseFromString(source, 'text/html');
      const text = doc.body?.innerText || '';
      const tokenMatch = text.match(/([\d\s]+)\s*токен/i);
      const tokens = tokenMatch ? tokenMatch[1].replace(/\s+/g, '') : fallback.tokens;
      const answers = Array.from(doc.querySelectorAll('button.llm-btn'))
        .filter((button) => !button.classList.contains('llm-ag1') && !button.classList.contains('llm-ag2'))
        .map((button, index) => {
          const label = String(button.textContent || '').replace(/\s+/g, ' ').trim();
          const fullText = String(button.dataset?.text || label || '').trim();
          const isPlaceholder = !fullText || /^\.{3}\s*ответ\d+\s*\.{3}$/i.test(fullText);
          return {
            id: `answer-${index + 1}`,
            title: `Ответ ${index + 1}`,
            label: isPlaceholder ? 'Ответ ещё не создан' : label,
            text: isPlaceholder ? '' : fullText,
            isPlaceholder,
          };
        })
        .slice(0, 3);

      while (answers.length < 3) {
        answers.push({
          id: `answer-${answers.length + 1}`,
          title: `Ответ ${answers.length + 1}`,
          label: 'Ответ ещё не создан',
          text: '',
          isPlaceholder: true,
        });
      }

      return {
        tokens,
        answers,
        hasLegacyDraft: /ПОСЧИТАТЬ|АГЕНТ-1|ответ1|ответ2|ответ3/i.test(text),
      };
    } catch (_) {
      return fallback;
    }
  }

  const CHAT_PROMPT_DEFAULTS = [
    {
      id: 'answer1',
      title: 'Ответ 1 · мягкое знакомство',
      is_default: true,
      provider: 'openrouter',
      model: 'openai/gpt-oss-120b:free',
      temperature: 0.2,
      top_p: 0.9,
      max_tokens: 2048,
      prompt: 'Сформулируй короткий, живой и безопасный ответ для первого касания. Тон: уважительно, без давления, как человек человеку. Цель: начать диалог.',
    },
    {
      id: 'answer2',
      title: 'Ответ 2 · польза и вопрос',
      is_default: false,
      provider: 'openrouter',
      model: 'openai/gpt-oss-120b:free',
      temperature: 0.2,
      top_p: 0.9,
      max_tokens: 2048,
      prompt: 'Сформулируй ответ, где сначала есть польза или наблюдение по контексту, а в конце один простой вопрос, который помогает понять потребность человека.',
    },
    {
      id: 'answer3',
      title: 'Ответ 3 · следующий шаг',
      is_default: false,
      provider: 'openrouter',
      model: 'openai/gpt-oss-120b:free',
      temperature: 0.2,
      top_p: 0.9,
      max_tokens: 2048,
      prompt: 'Сформулируй ответ с предложением понятного следующего шага: короткий созвон, обмен материалом или уточнение задачи. Без навязчивой продажи.',
    },
  ];

  function normalizeChatPromptId(value, index) {
    return String(value || '')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 80) || `answer${index + 1}`;
  }

  function boundedNumber(value, fallback, min, max) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(min, Math.min(max, parsed));
  }

  function normalizeChatAnswerPrompts(value) {
    const source = Array.isArray(value) && value.length ? value : CHAT_PROMPT_DEFAULTS;
    const seen = new Set();
    const prompts = source.slice(0, 20).map((item, index) => {
      const fallback = CHAT_PROMPT_DEFAULTS[Math.min(index, CHAT_PROMPT_DEFAULTS.length - 1)];
      let id = normalizeChatPromptId(item?.id || fallback.id, index);
      if (seen.has(id)) id = `${id}_${index + 1}`;
      seen.add(id);
      const provider = String(item?.provider || fallback.provider || 'openrouter').toLowerCase() === 'local' ? 'local' : 'openrouter';
      return {
        id,
        title: String(item?.title || fallback.title || id).trim(),
        is_default: Boolean(item?.is_default),
        provider,
        model: String(item?.model || fallback.model || 'openai/gpt-oss-120b:free').trim(),
        temperature: boundedNumber(item?.temperature, 0.2, 0, 2),
        top_p: boundedNumber(item?.top_p, 0.9, 0, 1),
        max_tokens: Math.round(boundedNumber(item?.max_tokens, 2048, 1, 262144)),
        prompt: String(item?.prompt || fallback.prompt || '').trim(),
      };
    }).filter((item) => item.prompt);

    const normalized = prompts.length ? prompts : CHAT_PROMPT_DEFAULTS.map((item) => ({ ...item }));
    if (!normalized.some((item) => item.is_default)) normalized[0].is_default = true;
    let defaultSeen = false;
    return normalized.map((item) => {
      const isDefault = item.is_default && !defaultSeen;
      if (isDefault) defaultSeen = true;
      return { ...item, is_default: isDefault };
    });
  }

  function selectDefaultChatPrompt(prompts) {
    return (prompts || []).find((item) => item.is_default) || (prompts || [])[0] || CHAT_PROMPT_DEFAULTS[0];
  }

  function normalizeAnalysisText(text) {
    return String(text || '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/p>/gi, '\n\n')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .trim();
  }

  window.BackfrontIndexUtils = {
    formatEta,
    parseLlmPanelHtml,
    CHAT_PROMPT_DEFAULTS,
    normalizeChatPromptId,
    boundedNumber,
    normalizeChatAnswerPrompts,
    selectDefaultChatPrompt,
    normalizeAnalysisText,
  };
})();
