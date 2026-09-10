/* Shared settings runtime utilities */
'use strict';

(function initReactSettingsUtils() {
  window.BackfrontSettingsUtils = function BackfrontSettingsUtils() {
  const API_BASE = window.API_BASE || (window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : 'http://localhost:8001');

  const DEFAULT_SCAN_GROUPS = [
    { id: 'A', label: 'A — критичные продажи/лиды', channels_range: '50–100', frequency: 'каждые 1–5 минут', interval_minutes: 5 },
    { id: 'B', label: 'B — важные отраслевые', channels_range: '100–200', frequency: 'каждые 10–30 минут', interval_minutes: 30 },
    { id: 'C', label: 'C — фоновые', channels_range: '300–500', frequency: '1–4 раза в день', interval_minutes: 360 },
    { id: 'D', label: 'D — архив/редко', channels_range: 'остаток', frequency: 'раз в сутки/неделю', interval_minutes: 1440 },
  ];

  const DEFAULT_SETTINGS = {
    setup_wizard_completed: false,
    first_start_wizard_required: true,
    localhost_bind: '127.0.0.1',
    localhost_port: 8001,
    telegram_api_id: '',
    telegram_api_hash: '',
    telegram_phone: '',
    telegram_api_configured: false,
    telegram_api_credentials_source: 'missing',
    telegram_client_backend: 'telethon',
    telegram_scan_groups: DEFAULT_SCAN_GROUPS,
    telegram_scan_group_assignments: {},
    ocr_images_enabled: false,
    ocr_delete_images_after_processing: false,
    ocr_service_url: '',
    openrouter_api_key: '',
    llm_provider: 'openrouter',
    lmstudio_base_url: 'http://127.0.0.1:1234/v1',
    lmstudio_model: 'local-model',
    openrouter_model: 'openai/gpt-oss-120b:free',
    openrouter_paid_model: 'openai/gpt-5-chat',
    openrouter_paid_model_enabled: false,
    openrouter_show_paid_models: false,
    openrouter_temperature: 0.2,
    openrouter_top_p: 0.9,
    openrouter_max_tokens: 2048,
    openrouter_frequency_penalty: 0,
    openrouter_presence_penalty: 0,
    openrouter_event_date_message_days: 30,
    openrouter_timeout_sec: 300,
    openrouter_allow_pii: false,
    runtime_log_mask_pii: true,
    contact_qualification_prompts: [
      {
        id: 'needs_priority',
        title: 'Потребности и покупки',
        prompt: 'проанализируй сообщения человека и оцени его потребности что человек может покупать в приоритете?',
      },
      {
        id: 'first_message',
        title: 'Первое сообщение для знакомства',
        prompt: 'оцени какое первое сообщение написать человек на основе его сообщений для того чтобы познакомиться',
      },
      {
        id: 'product_offer',
        title: 'Какой продукт предложить',
        prompt: 'проанализируй сообщения человека и определи какой продукт, оффер или услугу ему стоит предложить. Верни: основной продукт, альтернативный продукт, почему это подходит, что уточнить перед продажей.',
      },
    ],
    llm_answer_prompts: [
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
    ],
    import_default_add_limit: 50,
    import_default_history_months: 1,
    import_default_message_limit: 1000,
    import_max_history_months: 1,
    import_max_message_limit: 1000,
    telegram_unlimited_import_enabled: false,
    local_import_limits_enabled: false,
    local_import_max_history_months: 1,
    local_import_max_message_limit: 1000,
    outreach_auto_send_enabled: false,
    show_contact_qualification_prompt_settings: false,
    show_license_email_settings: false,
    dashboard_show_money_metrics: false,
    license_email_enabled: false,
    license_email_host: '',
    license_email_port: 993,
    license_email_smtp_host: '',
    license_email_smtp_port: 465,
    license_email_login: '',
    license_email_password: '',
    license_email_clear_password: false,
    license_email_password_configured: false,
    license_email_inbox_folder: 'INBOX',
    license_email_allow_activation_receipt: false,
    license_email_last_import_at: '',
  };

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const response = await fetch(url, {
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`HTTP ${response.status}${text ? ` — ${text}` : ''}`);
    }
    return await response.json();
  }

  function normalizeModelId(value) {
    return String(value || '')
      .replace(/^https:\/\/openrouter\.ai\//, '')
      .replace(/^openrouter\.ai\//, '')
      .replace(/^\/+|\/+$/g, '')
      || DEFAULT_SETTINGS.openrouter_model;
  }

  function normalizeScanGroups(value) {
    const groups = Array.isArray(value) && value.length ? value : DEFAULT_SCAN_GROUPS;
    const defaults = new Map(DEFAULT_SCAN_GROUPS.map((group) => [group.id, group]));
    const byId = new Map();

    groups.forEach((group) => {
      const id = String(group?.id || '').trim().toUpperCase();
      if (!id) return;
      const fallback = defaults.get(id) || {};
      byId.set(id, {
        id,
        label: String(group?.label || fallback.label || id).trim(),
        channels_range: String(group?.channels_range || fallback.channels_range || '').trim(),
        frequency: String(group?.frequency || fallback.frequency || '').trim(),
        interval_minutes: Math.min(10080, Math.max(1, Number(group?.interval_minutes || fallback.interval_minutes || 60))),
      });
    });

    DEFAULT_SCAN_GROUPS.forEach((group) => {
      if (!byId.has(group.id)) byId.set(group.id, { ...group });
    });

    return [...DEFAULT_SCAN_GROUPS.map((group) => byId.get(group.id)), ...[...byId.values()].filter((group) => !defaults.has(group.id))];
  }

  function normalizePromptId(value, title = '', prompt = '') {
    const raw = String(value || '').trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '');
    if (raw) return raw.slice(0, 80);
    const source = `${title}\n${prompt}`.trim() || `prompt_${Date.now()}`;
    let hash = 0;
    for (let i = 0; i < source.length; i += 1) hash = ((hash << 5) - hash + source.charCodeAt(i)) | 0;
    return `prompt_${Math.abs(hash)}`;
  }

  function normalizeContactPrompts(value) {
    const source = Array.isArray(value) && value.length ? value : DEFAULT_SETTINGS.contact_qualification_prompts;
    const seen = new Set();
    const prompts = [];
    source.forEach((item, index) => {
      const title = String(item?.title || `Шаблон ${index + 1}`).trim();
      const prompt = String(item?.prompt || '').trim();
      if (!prompt) return;
      let id = normalizePromptId(item?.id, title, prompt);
      if (seen.has(id)) id = `${id}_${index + 1}`;
      seen.add(id);
      prompts.push({ id, title: title || id, prompt });
    });
    DEFAULT_SETTINGS.contact_qualification_prompts.forEach((item) => {
      const id = normalizePromptId(item.id, item.title, item.prompt);
      if (!seen.has(id)) {
        seen.add(id);
        prompts.push({ ...item, id });
      }
    });
    return prompts.length ? prompts : DEFAULT_SETTINGS.contact_qualification_prompts;
  }

  function normalizeAnswerPrompts(value) {
    const source = Array.isArray(value) && value.length ? value : DEFAULT_SETTINGS.llm_answer_prompts;
    const prompts = [];
    const seen = new Set();
    source.slice(0, 20).forEach((item, index) => {
      const fallback = DEFAULT_SETTINGS.llm_answer_prompts[index] || DEFAULT_SETTINGS.llm_answer_prompts[0];
      const title = String(item?.title || fallback.title || `Промт ${index + 1}`).trim();
      const prompt = String(item?.prompt || fallback.prompt || '').trim();
      if (!prompt) return;
      let id = normalizePromptId(item?.id, title, prompt);
      if (seen.has(id)) id = `${id}_${index + 1}`;
      seen.add(id);
      const provider = ['openrouter', 'local'].includes(String(item?.provider || '').toLowerCase())
        ? String(item.provider).toLowerCase()
        : 'openrouter';
      prompts.push({
        id,
        title: title || id,
        prompt,
        is_default: Boolean(item?.is_default),
        provider,
        model: normalizeModelId(item?.model || DEFAULT_SETTINGS.openrouter_model),
        temperature: Math.min(2, Math.max(0, Number(item?.temperature ?? DEFAULT_SETTINGS.openrouter_temperature))),
        top_p: Math.min(1, Math.max(0, Number(item?.top_p ?? DEFAULT_SETTINGS.openrouter_top_p))),
        max_tokens: Math.min(262144, Math.max(1, Number(item?.max_tokens ?? DEFAULT_SETTINGS.openrouter_max_tokens))),
      });
    });
    if (!prompts.length) prompts.push(...DEFAULT_SETTINGS.llm_answer_prompts.map((item) => ({ ...item })));
    if (!prompts.some((item) => item.is_default)) prompts[0].is_default = true;
    let defaultSeen = false;
    return prompts.map((item) => {
      if (item.is_default && !defaultSeen) {
        defaultSeen = true;
        return item;
      }
      return { ...item, is_default: false };
    });
  }

    return {
      API_BASE,
      DEFAULT_SCAN_GROUPS,
      DEFAULT_SETTINGS,
      apiJson,
      normalizeModelId,
      normalizeScanGroups,
      normalizePromptId,
      normalizeContactPrompts,
      normalizeAnswerPrompts,
    };
  };
})();
