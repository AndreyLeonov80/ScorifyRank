export type ChatPromptConfig = {
  id: string;
  title: string;
  is_default: boolean;
  provider: 'openrouter' | 'local';
  model: string;
  temperature: number;
  top_p: number;
  max_tokens: number;
  prompt: string;
};

export const CHAT_PROMPT_DEFAULTS: ChatPromptConfig[] = [
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

export function formatEta(sec: unknown): string {
  const total = Math.max(0, Number(sec || 0));
  if (!total) return '—';
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (!minutes) return `${seconds} сек`;
  return `${minutes} мин ${String(seconds).padStart(2, '0')} сек`;
}

export function normalizeChatPromptId(value: unknown, index: number): string {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 80) || `answer${index + 1}`;
}

export function boundedNumber(value: unknown, fallback: number, min: number, max: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

export function normalizeChatAnswerPrompts(value: unknown): ChatPromptConfig[] {
  const source = Array.isArray(value) && value.length ? value : CHAT_PROMPT_DEFAULTS;
  const seen = new Set<string>();
  const prompts = source.slice(0, 20).map((raw, index): ChatPromptConfig => {
    const item = raw as Partial<ChatPromptConfig> | null | undefined;
    const fallback = CHAT_PROMPT_DEFAULTS[Math.min(index, CHAT_PROMPT_DEFAULTS.length - 1)];
    let id = normalizeChatPromptId(item?.id || fallback.id, index);
    if (seen.has(id)) id = `${id}_${index + 1}`;
    seen.add(id);
    const provider: ChatPromptConfig['provider'] = String(item?.provider || fallback.provider || 'openrouter').toLowerCase() === 'local'
      ? 'local'
      : 'openrouter';
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

export function selectDefaultChatPrompt(prompts: ChatPromptConfig[]): ChatPromptConfig {
  return prompts.find((item) => item.is_default) || prompts[0] || CHAT_PROMPT_DEFAULTS[0];
}

export function normalizeAnalysisText(text: unknown): string {
  return String(text || '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>/gi, '\n\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .trim();
}
