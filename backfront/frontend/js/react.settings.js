/* React settings page */
'use strict';

(function mountReactSettingsPage() {
  if (!window.React || !window.ReactDOM || !window.htm || !window.BackfrontReactShared || !window.BackfrontSettingsUtils) {
    console.error('[React] Runtime libraries are not loaded for Settings');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const { PageHeader } = window.BackfrontReactShared;
  const {
    API_BASE,
    DEFAULT_SCAN_GROUPS,
    DEFAULT_SETTINGS,
    apiJson,
    normalizeModelId,
    normalizeScanGroups,
    normalizePromptId,
    normalizeContactPrompts,
    normalizeAnswerPrompts,
  } = window.BackfrontSettingsUtils();

  const importLimit = (value, fallback) => {
    const parsed = Number(value);
    if (Number.isFinite(parsed) && parsed === 0) return 0;
    if (!Number.isFinite(parsed)) return fallback;
    return Math.max(1, Math.trunc(parsed));
  };

  const importLimitLabel = (value, unit) => Number(value) === 0 ? `безлимит (${unit})` : `${value} ${unit}`;
  const importLimitInputMax = (value, fallback) => {
    const limit = importLimit(value, fallback);
    return limit === 0 ? undefined : limit;
  };
  const clampImportDefault = (value, maxValue, fallback) => {
    const maxLimit = importLimit(maxValue, fallback);
    const parsed = Number(value);
    if (maxLimit === 0) return Number.isFinite(parsed) ? Math.max(0, Math.trunc(parsed)) : 0;
    return Math.min(maxLimit, Math.max(1, Number.isFinite(parsed) ? Math.trunc(parsed) : fallback));
  };
  const formatLicenseDate = (value) => {
    if (!value) return 'не указано';
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      return date.toLocaleDateString('ru-RU', { year: 'numeric', month: '2-digit', day: '2-digit' });
    } catch (_) {
      return String(value);
    }
  };
  const licenseStatusText = (status) => {
    const normalized = String(status || '').toLowerCase();
    if (normalized === 'active') return 'активна';
    if (normalized === 'grace') return 'grace period';
    if (normalized === 'expired') return 'истекла';
    if (normalized === 'revoked') return 'отозвана';
    if (normalized === 'not_activated') return 'не активна';
    if (normalized === 'license_server_unavailable') return 'проверка недоступна';
    if (normalized === 'license_server_invalid_response') return 'ошибка проверки';
    if (normalized === 'missing') return 'нет локальной активации';
    if (normalized === 'tampered') return 'повреждена';
    return status || 'не загружено';
  };
  const licenseBadgeClass = (status, ok) => {
    const normalized = String(status || '').toLowerCase();
    if (ok || normalized === 'active' || normalized === 'grace') return 'badge-green';
    if (normalized === 'revoked' || normalized === 'expired' || normalized === 'tampered') return 'badge-red';
    return 'badge-yellow';
  };

  function SettingsPage() {
    const [settings, setSettings] = React.useState(DEFAULT_SETTINGS);
    const [models, setModels] = React.useState([]);
    const [modelQuery, setModelQuery] = React.useState('');
    const [loading, setLoading] = React.useState(true);
    const [saving, setSaving] = React.useState(false);
    const [emailImporting, setEmailImporting] = React.useState(false);
    const [licenseBusy, setLicenseBusy] = React.useState(false);
    const [licenseStatus, setLicenseStatus] = React.useState(null);
    const [modelsLoading, setModelsLoading] = React.useState(false);
    const [resetStatus, setResetStatus] = React.useState(null);
    const [resetBusy, setResetBusy] = React.useState(false);
    const [dataSourcePlugins, setDataSourcePlugins] = React.useState([]);
    const [dataSources, setDataSources] = React.useState([]);
    const [dataSourceBusy, setDataSourceBusy] = React.useState(false);
    const [dataSourceForm, setDataSourceForm] = React.useState({
      source_type: 'sqlite',
      source_name: '',
      path: '',
    });
    const [bitrix24, setBitrix24] = React.useState({
      portal_url: '',
      auth_mode: 'webhook',
      webhook_url: '',
      access_token: '',
      client_id: '',
      client_secret: '',
      refresh_token: '',
      selected_entity: 'lead',
      dry_run_limit: 25,
      export_contacts: true,
      export_leads: true,
      export_timeline: true,
    });
    const [bitrix24Busy, setBitrix24Busy] = React.useState(false);
    const [bitrix24Result, setBitrix24Result] = React.useState(null);
    const [amocrm, setAmocrm] = React.useState({
      subdomain: '',
      client_id: '',
      client_secret: '',
      redirect_uri: '',
      access_token: '',
      refresh_token: '',
      selected_pipeline_id: '',
      selected_status_id: '',
      responsible_user_id: '',
      dry_run_limit: 25,
      export_contacts: true,
      export_companies: false,
      export_leads: true,
      export_notes: true,
      export_tags: true,
    });
    const [amocrmBusy, setAmocrmBusy] = React.useState(false);
    const [amocrmResult, setAmocrmResult] = React.useState(null);
    const [activeTab, setActiveTab] = React.useState(() => {
      try {
        const saved = localStorage.getItem('xfiles.settings.activeTab.v1') || 'telegram';
        return saved === 'data' ? 'telegram' : saved;
      } catch (_) {
        return 'telegram';
      }
    });
    const [message, setMessage] = React.useState('');
    const [error, setError] = React.useState('');

    function changeSettingsTab(tab) {
      setActiveTab(tab);
      try {
        localStorage.setItem('xfiles.settings.activeTab.v1', tab);
      } catch (_) {}
    }

    function tabPanelClass(tab, extra = '') {
      return `panel settings-tab-panel ${activeTab === tab ? 'settings-tab-active' : ''} ${extra}`.trim();
    }

    const settingsTabs = [
      { id: 'telegram', label: 'Telegram' },
      { id: 'import', label: 'Import' },
      { id: 'license', label: 'Лицензия' },
      { id: 'llm', label: 'LLM' },
      { id: 'bitrix24', label: 'Bitrix24' },
      { id: 'amocrm', label: 'amoCRM' },
      { id: 'system', label: 'Система' },
    ];

    async function loadSettings() {
      setLoading(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/settings`);
        const next = {
          ...DEFAULT_SETTINGS,
          ...data,
          localhost_bind: ['localhost', '127.0.0.1'].includes(String(data.localhost_bind || '').toLowerCase())
            ? String(data.localhost_bind).toLowerCase()
            : DEFAULT_SETTINGS.localhost_bind,
          localhost_port: Math.min(65535, Math.max(1, Number(data.localhost_port || DEFAULT_SETTINGS.localhost_port))),
          telegram_api_id: String(data.telegram_api_id || ''),
          telegram_api_hash: String(data.telegram_api_hash || ''),
          telegram_phone: String(data.telegram_phone || ''),
          openrouter_model: normalizeModelId(data.openrouter_model),
          llm_provider: ['openrouter', 'local'].includes(data.llm_provider) ? data.llm_provider : DEFAULT_SETTINGS.llm_provider,
          lmstudio_base_url: String(data.lmstudio_base_url || DEFAULT_SETTINGS.lmstudio_base_url),
          lmstudio_model: String(data.lmstudio_model || DEFAULT_SETTINGS.lmstudio_model),
          openrouter_paid_model: normalizeModelId(data.openrouter_paid_model || DEFAULT_SETTINGS.openrouter_paid_model),
          openrouter_paid_model_enabled: Boolean(data.openrouter_paid_model_enabled),
          ocr_service_url: String(data.ocr_service_url || ''),
          import_max_history_months: importLimit(data.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months),
          import_max_message_limit: importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit),
          telegram_unlimited_import_enabled: Boolean(data.telegram_unlimited_import_enabled),
          local_import_limits_enabled: Boolean(data.local_import_limits_enabled),
          local_import_max_history_months: importLimit(data.local_import_max_history_months, importLimit(data.import_max_history_months, DEFAULT_SETTINGS.local_import_max_history_months)),
          local_import_max_message_limit: importLimit(data.local_import_max_message_limit, importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.local_import_max_message_limit)),
          import_default_history_months: importLimit(data.import_max_history_months, 1) === 0 ? 0 : Math.min(
            importLimit(data.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months),
            importLimit(data.import_default_history_months, DEFAULT_SETTINGS.import_default_history_months),
          ),
          import_default_message_limit: importLimit(data.import_max_message_limit, 1000) === 0 ? 0 : Math.min(
            importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit),
            importLimit(data.import_default_message_limit, DEFAULT_SETTINGS.import_default_message_limit),
          ),
          telegram_scan_groups: normalizeScanGroups(data.telegram_scan_groups),
          telegram_scan_group_assignments: data.telegram_scan_group_assignments || {},
          license_email_password: '',
          license_email_clear_password: false,
          show_contact_qualification_prompt_settings: Boolean(data.show_contact_qualification_prompt_settings),
          show_license_email_settings: Boolean(data.show_license_email_settings),
          dashboard_show_money_metrics: Boolean(data.dashboard_show_money_metrics),
          contact_qualification_prompts: normalizeContactPrompts(data.contact_qualification_prompts),
          llm_answer_prompts: normalizeAnswerPrompts(data.llm_answer_prompts),
        };
        setSettings(next);
        setMessage(data.message || 'Настройки загружены');
        await loadLicenseStatus();
        await loadBitrix24Settings();
        await loadAmocrmSettings();
        await loadModels({ includePaid: next.openrouter_show_paid_models, query: modelQuery });
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setLoading(false);
      }
    }

    async function loadModels({ includePaid = settings.openrouter_show_paid_models, query = modelQuery } = {}) {
      setModelsLoading(true);
      try {
        const params = new URLSearchParams({
          include_paid: includePaid ? 'true' : 'false',
          query: query || '',
        });
        const data = await apiJson(`${API_BASE}/api/payme/openrouter/models?${params.toString()}`);
        setModels(Array.isArray(data.items) ? data.items : []);
        if (data.message) setMessage(data.message);
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setModelsLoading(false);
      }
    }

    async function loadLicenseStatus() {
      setLicenseBusy(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/license/status`);
        setLicenseStatus(data);
        setMessage('Статус лицензии обновлён');
      } catch (err) {
        console.warn('[settings] license status failed', err);
        setError(`Не удалось проверить лицензию: ${String(err?.message || err)}`);
      } finally {
        setLicenseBusy(false);
      }
    }

    async function saveSettings(overrides = {}) {
      const safeOverrides = overrides && typeof overrides === 'object' && !overrides.nativeEvent ? overrides : {};
      const nextSettings = { ...settings, ...safeOverrides };
      setSaving(true);
      setError('');
      try {
        const payload = {
          ...nextSettings,
          setup_wizard_completed: Boolean(nextSettings.setup_wizard_completed),
          localhost_bind: ['localhost', '127.0.0.1'].includes(String(nextSettings.localhost_bind || '').toLowerCase())
            ? String(nextSettings.localhost_bind).toLowerCase()
            : DEFAULT_SETTINGS.localhost_bind,
          localhost_port: Math.min(65535, Math.max(1, Number(nextSettings.localhost_port || DEFAULT_SETTINGS.localhost_port))),
          telegram_client_backend: ['telethon', 'tdlib'].includes(nextSettings.telegram_client_backend)
            ? nextSettings.telegram_client_backend
            : DEFAULT_SETTINGS.telegram_client_backend,
          telegram_api_id: String(nextSettings.telegram_api_id || '').trim(),
          telegram_api_hash: String(nextSettings.telegram_api_hash || '').trim(),
          telegram_phone: String(nextSettings.telegram_phone || '').trim(),
          telegram_scan_groups: normalizeScanGroups(nextSettings.telegram_scan_groups),
          telegram_scan_group_assignments: nextSettings.telegram_scan_group_assignments || {},
          ocr_service_url: String(nextSettings.ocr_service_url || '').trim().replace(/\/+$/g, ''),
          contact_qualification_prompts: normalizeContactPrompts(nextSettings.contact_qualification_prompts),
          llm_answer_prompts: normalizeAnswerPrompts(nextSettings.llm_answer_prompts),
          llm_provider: ['openrouter', 'local'].includes(nextSettings.llm_provider) ? nextSettings.llm_provider : DEFAULT_SETTINGS.llm_provider,
          lmstudio_base_url: String(nextSettings.lmstudio_base_url || DEFAULT_SETTINGS.lmstudio_base_url).trim().replace(/\/+$/g, ''),
          lmstudio_model: String(nextSettings.lmstudio_model || DEFAULT_SETTINGS.lmstudio_model).trim() || DEFAULT_SETTINGS.lmstudio_model,
          openrouter_model: normalizeModelId(nextSettings.openrouter_model),
          openrouter_paid_model: normalizeModelId(nextSettings.openrouter_paid_model || DEFAULT_SETTINGS.openrouter_paid_model),
          openrouter_paid_model_enabled: Boolean(nextSettings.openrouter_paid_model_enabled),
          openrouter_temperature: Number(nextSettings.openrouter_temperature || 0),
          openrouter_top_p: Number(nextSettings.openrouter_top_p || 0),
          openrouter_max_tokens: Number(nextSettings.openrouter_max_tokens || 1),
          openrouter_frequency_penalty: Number(nextSettings.openrouter_frequency_penalty || 0),
          openrouter_presence_penalty: Number(nextSettings.openrouter_presence_penalty || 0),
          openrouter_event_date_message_days: Math.min(3650, Math.max(1, Number(nextSettings.openrouter_event_date_message_days || 30))),
          openrouter_timeout_sec: Math.min(300, Math.max(5, Number(nextSettings.openrouter_timeout_sec || 300))),
          openrouter_allow_pii: Boolean(nextSettings.openrouter_allow_pii),
          runtime_log_mask_pii: Boolean(nextSettings.runtime_log_mask_pii),
          show_contact_qualification_prompt_settings: Boolean(nextSettings.show_contact_qualification_prompt_settings),
          show_license_email_settings: Boolean(nextSettings.show_license_email_settings),
          dashboard_show_money_metrics: Boolean(nextSettings.dashboard_show_money_metrics),
          import_default_add_limit: Math.min(1000000, Math.max(1, Number(nextSettings.import_default_add_limit || 50))),
          import_default_history_months: nextSettings.telegram_unlimited_import_enabled ? 0 : Math.min(
            importLimit(nextSettings.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months),
            importLimit(nextSettings.import_default_history_months, DEFAULT_SETTINGS.import_default_history_months),
          ),
          import_default_message_limit: nextSettings.telegram_unlimited_import_enabled ? 0 : Math.min(
            importLimit(nextSettings.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit),
            importLimit(nextSettings.import_default_message_limit, DEFAULT_SETTINGS.import_default_message_limit),
          ),
          telegram_unlimited_import_enabled: Boolean(nextSettings.telegram_unlimited_import_enabled),
          local_import_limits_enabled: Boolean(nextSettings.local_import_limits_enabled || nextSettings.telegram_unlimited_import_enabled),
          local_import_max_history_months: nextSettings.telegram_unlimited_import_enabled ? 0 : Math.min(1200, importLimit(nextSettings.local_import_max_history_months, importLimit(nextSettings.import_max_history_months, 1))),
          local_import_max_message_limit: nextSettings.telegram_unlimited_import_enabled ? 0 : Math.min(100000000, importLimit(nextSettings.local_import_max_message_limit, importLimit(nextSettings.import_max_message_limit, 1000))),
          license_email_enabled: Boolean(nextSettings.license_email_enabled),
          license_email_host: String(nextSettings.license_email_host || '').trim(),
          license_email_port: Math.min(65535, Math.max(1, Number(nextSettings.license_email_port || 993))),
          license_email_smtp_host: String(nextSettings.license_email_smtp_host || '').trim(),
          license_email_smtp_port: Math.min(65535, Math.max(1, Number(nextSettings.license_email_smtp_port || 465))),
          license_email_login: String(nextSettings.license_email_login || '').trim(),
          license_email_password: String(nextSettings.license_email_password || ''),
          license_email_clear_password: Boolean(nextSettings.license_email_clear_password),
          license_email_inbox_folder: String(nextSettings.license_email_inbox_folder || 'INBOX').trim() || 'INBOX',
          license_email_allow_activation_receipt: Boolean(nextSettings.license_email_allow_activation_receipt),
        };
        const data = await apiJson(`${API_BASE}/api/payme/settings`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setSettings({
          ...DEFAULT_SETTINGS,
          ...data,
          localhost_bind: ['localhost', '127.0.0.1'].includes(String(data.localhost_bind || '').toLowerCase())
            ? String(data.localhost_bind).toLowerCase()
            : DEFAULT_SETTINGS.localhost_bind,
          localhost_port: Math.min(65535, Math.max(1, Number(data.localhost_port || DEFAULT_SETTINGS.localhost_port))),
          telegram_api_id: String(data.telegram_api_id || ''),
          telegram_api_hash: String(data.telegram_api_hash || ''),
          telegram_phone: String(data.telegram_phone || ''),
          openrouter_model: normalizeModelId(data.openrouter_model),
          llm_provider: ['openrouter', 'local'].includes(data.llm_provider) ? data.llm_provider : DEFAULT_SETTINGS.llm_provider,
          lmstudio_base_url: String(data.lmstudio_base_url || DEFAULT_SETTINGS.lmstudio_base_url),
          lmstudio_model: String(data.lmstudio_model || DEFAULT_SETTINGS.lmstudio_model),
          openrouter_paid_model: normalizeModelId(data.openrouter_paid_model || DEFAULT_SETTINGS.openrouter_paid_model),
          openrouter_paid_model_enabled: Boolean(data.openrouter_paid_model_enabled),
          ocr_service_url: String(data.ocr_service_url || ''),
          import_max_history_months: importLimit(data.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months),
          import_max_message_limit: importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit),
          telegram_unlimited_import_enabled: Boolean(data.telegram_unlimited_import_enabled),
          local_import_limits_enabled: Boolean(data.local_import_limits_enabled),
          local_import_max_history_months: importLimit(data.local_import_max_history_months, importLimit(data.import_max_history_months, DEFAULT_SETTINGS.local_import_max_history_months)),
          local_import_max_message_limit: importLimit(data.local_import_max_message_limit, importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.local_import_max_message_limit)),
          import_default_history_months: importLimit(data.import_max_history_months, 1) === 0 ? 0 : Math.min(
            importLimit(data.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months),
            importLimit(data.import_default_history_months, DEFAULT_SETTINGS.import_default_history_months),
          ),
          import_default_message_limit: importLimit(data.import_max_message_limit, 1000) === 0 ? 0 : Math.min(
            importLimit(data.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit),
            importLimit(data.import_default_message_limit, DEFAULT_SETTINGS.import_default_message_limit),
          ),
          telegram_scan_groups: normalizeScanGroups(data.telegram_scan_groups),
          telegram_scan_group_assignments: data.telegram_scan_group_assignments || {},
          license_email_password: '',
          license_email_clear_password: false,
          show_contact_qualification_prompt_settings: Boolean(data.show_contact_qualification_prompt_settings),
          show_license_email_settings: Boolean(data.show_license_email_settings),
          dashboard_show_money_metrics: Boolean(data.dashboard_show_money_metrics),
          contact_qualification_prompts: normalizeContactPrompts(data.contact_qualification_prompts),
          llm_answer_prompts: normalizeAnswerPrompts(data.llm_answer_prompts),
        });
        setMessage(data.message || 'Настройки сохранены');
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setSaving(false);
      }
    }

    async function importLicenseFromEmail() {
      setEmailImporting(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/license/email/import`, { method: 'POST' });
        setMessage(data.message || 'Invite-license импортирован из email');
        setLicenseStatus(data.status || null);
        await loadSettings();
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setEmailImporting(false);
      }
    }

    async function enableUnlimitedImportMode() {
      const caps = licenseStatus?.license_capabilities || {};
      if (caps.telegram_unlimited_import === false && caps.local_import_limit_override === false) {
        setError('Текущая лицензия не разрешает безлимитную загрузку Telegram.');
        return;
      }
      setLicenseBusy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/settings/import/unlimited`, { method: 'POST' });
        if (data?.settings) {
          setSettings({
            ...DEFAULT_SETTINGS,
            ...data.settings,
            telegram_unlimited_import_enabled: true,
            local_import_limits_enabled: true,
            import_max_history_months: 0,
            import_max_message_limit: 0,
            import_default_history_months: 0,
            import_default_message_limit: 0,
            local_import_max_history_months: 0,
            local_import_max_message_limit: 0,
            license_email_password: '',
            license_email_clear_password: false,
            telegram_scan_groups: normalizeScanGroups(data.settings.telegram_scan_groups),
            contact_qualification_prompts: normalizeContactPrompts(data.settings.contact_qualification_prompts),
            llm_answer_prompts: normalizeAnswerPrompts(data.settings.llm_answer_prompts),
          });
        }
        setMessage(
          data?.message ||
          `Безлимитная загрузка включена. Обновлено источников: ${Number(data?.updated_sources_count || 0)}.`,
        );
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setLicenseBusy(false);
      }
    }

    async function loadDataSources() {
      try {
        const [plugins, sources] = await Promise.all([
          apiJson(`${API_BASE}/api/payme/data-sources/plugins`),
          apiJson(`${API_BASE}/api/payme/data-sources`),
        ]);
        const pluginItems = Array.isArray(plugins?.items) ? plugins.items : [];
        const sourceItems = Array.isArray(sources?.items) ? sources.items : [];
        setDataSourcePlugins(pluginItems);
        setDataSources(sourceItems);
        if (!pluginItems.some((plugin) => plugin.type === dataSourceForm.source_type) && pluginItems.length) {
          setDataSourceForm((prev) => ({ ...prev, source_type: pluginItems[0].type }));
        }
      } catch (err) {
        console.warn('[settings] data source plugins failed', err);
      }
    }

    async function testDataSourceConnection() {
      const path = String(dataSourceForm.path || '').trim();
      if (!path) {
        setError('Укажите путь к SQLite/DuckDB базе или DSN источника.');
        return;
      }
      setDataSourceBusy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/data-sources/${dataSourceForm.source_type}/connect`, {
          method: 'POST',
          body: JSON.stringify({ connection: { path } }),
        });
        setMessage(data.message || 'Подключение проверено.');
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setDataSourceBusy(false);
      }
    }

    async function registerDataSource() {
      const path = String(dataSourceForm.path || '').trim();
      const sourceName = String(dataSourceForm.source_name || '').trim() || `${dataSourceForm.source_type}: ${path.split('/').pop() || path}`;
      if (!path) {
        setError('Укажите путь к SQLite/DuckDB базе или DSN источника.');
        return;
      }
      setDataSourceBusy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/data-sources`, {
          method: 'POST',
          body: JSON.stringify({
            source_type: dataSourceForm.source_type,
            source_name: sourceName,
            connection: { path },
          }),
        });
        setMessage(data.message || `Источник ${sourceName} подключен.`);
        setDataSourceForm((prev) => ({ ...prev, source_name: '', path: '' }));
        await loadDataSources();
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setDataSourceBusy(false);
      }
    }

    async function disconnectDataSource(sourceId) {
      setDataSourceBusy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/data-sources/${encodeURIComponent(sourceId)}/disconnect`, { method: 'POST' });
        setMessage(data.message || 'Источник отключён.');
        await loadDataSources();
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setDataSourceBusy(false);
      }
    }

    function updateBitrix24(patch) {
      setBitrix24((prev) => ({ ...prev, ...patch }));
    }

    function bitrix24Payload() {
      return {
        portal_url: String(bitrix24.portal_url || '').trim(),
        auth_mode: bitrix24.auth_mode === 'oauth' ? 'oauth' : 'webhook',
        webhook_url: String(bitrix24.webhook_url || '').trim(),
        access_token: String(bitrix24.access_token || '').trim(),
        client_id: String(bitrix24.client_id || '').trim(),
        client_secret: String(bitrix24.client_secret || '').trim(),
        refresh_token: String(bitrix24.refresh_token || '').trim(),
        selected_entity: bitrix24.selected_entity === 'deal' ? 'deal' : 'lead',
        dry_run_limit: Math.min(500, Math.max(1, Number(bitrix24.dry_run_limit || 25))),
      };
    }

    function bitrix24RunPayload({ dryRun = false } = {}) {
      return {
        dry_run: Boolean(dryRun),
        limit: Math.min(5000, Math.max(1, Number(bitrix24.dry_run_limit || 25))),
        export_contacts: Boolean(bitrix24.export_contacts),
        export_leads: Boolean(bitrix24.export_leads),
        export_timeline: Boolean(bitrix24.export_timeline),
      };
    }

    async function loadBitrix24Settings() {
      try {
        const data = await apiJson(`${API_BASE}/api/payme/exports/bitrix24/settings`);
        const saved = data?.settings || {};
        setBitrix24((prev) => ({
          ...prev,
          ...saved,
          webhook_url: '',
          access_token: '',
          client_secret: '',
          refresh_token: '',
          auth_mode: saved.auth_mode === 'oauth' ? 'oauth' : 'webhook',
          selected_entity: saved.selected_entity === 'deal' ? 'deal' : 'lead',
          dry_run_limit: Math.min(500, Math.max(1, Number(saved.dry_run_limit || prev.dry_run_limit || 25))),
        }));
        setBitrix24Result(data);
      } catch (err) {
        console.warn('[settings] bitrix24 settings failed', err);
      }
    }

    async function saveBitrix24Settings() {
      setBitrix24Busy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/exports/bitrix24/settings`, {
          method: 'POST',
          body: JSON.stringify(bitrix24Payload()),
        });
        setBitrix24Result(data);
        setMessage(data.message || 'Настройки Bitrix24 сохранены.');
        await loadBitrix24Settings();
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setBitrix24Busy(false);
      }
    }

    async function runBitrix24Action(kind) {
      setBitrix24Busy(true);
      setError('');
      try {
        let url = `${API_BASE}/api/payme/exports/bitrix24/test`;
        let body = null;
        if (kind === 'setup') {
          url = `${API_BASE}/api/payme/exports/bitrix24/setup`;
          body = JSON.stringify({ dry_run: false });
        } else if (kind === 'setup-dry') {
          url = `${API_BASE}/api/payme/exports/bitrix24/setup`;
          body = JSON.stringify({ dry_run: true });
        } else if (kind === 'dry-run') {
          url = `${API_BASE}/api/payme/exports/bitrix24/dry-run`;
          body = JSON.stringify(bitrix24RunPayload({ dryRun: true }));
        } else if (kind === 'run') {
          url = `${API_BASE}/api/payme/exports/bitrix24/run`;
          body = JSON.stringify(bitrix24RunPayload({ dryRun: false }));
        }
        const data = await apiJson(url, { method: 'POST', ...(body ? { body } : {}) });
        setBitrix24Result(data);
        setMessage(data.message || data?.job?.message || 'Bitrix24 действие выполнено.');
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setBitrix24Busy(false);
      }
    }

    function updateAmocrm(patch) {
      setAmocrm((prev) => ({ ...prev, ...patch }));
    }

    function amocrmPayload() {
      return {
        subdomain: String(amocrm.subdomain || '').trim(),
        client_id: String(amocrm.client_id || '').trim(),
        client_secret: String(amocrm.client_secret || '').trim(),
        redirect_uri: String(amocrm.redirect_uri || '').trim(),
        access_token: String(amocrm.access_token || '').trim(),
        refresh_token: String(amocrm.refresh_token || '').trim(),
        selected_pipeline_id: String(amocrm.selected_pipeline_id || '').trim(),
        selected_status_id: String(amocrm.selected_status_id || '').trim(),
        responsible_user_id: String(amocrm.responsible_user_id || '').trim(),
        dry_run_limit: Math.min(500, Math.max(1, Number(amocrm.dry_run_limit || 25))),
      };
    }

    function amocrmRunPayload({ dryRun = false } = {}) {
      return {
        dry_run: Boolean(dryRun),
        limit: Math.min(5000, Math.max(1, Number(amocrm.dry_run_limit || 25))),
        export_contacts: Boolean(amocrm.export_contacts),
        export_companies: Boolean(amocrm.export_companies),
        export_leads: Boolean(amocrm.export_leads),
        export_notes: Boolean(amocrm.export_notes),
        export_tags: Boolean(amocrm.export_tags),
      };
    }

    async function loadAmocrmSettings() {
      try {
        const data = await apiJson(`${API_BASE}/api/payme/exports/amocrm/settings`);
        const saved = data?.settings || {};
        setAmocrm((prev) => ({
          ...prev,
          ...saved,
          client_secret: '',
          access_token: '',
          refresh_token: '',
          dry_run_limit: Math.min(500, Math.max(1, Number(saved.dry_run_limit || prev.dry_run_limit || 25))),
        }));
        setAmocrmResult(data);
      } catch (err) {
        console.warn('[settings] amocrm settings failed', err);
      }
    }

    async function saveAmocrmSettings() {
      setAmocrmBusy(true);
      setError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/exports/amocrm/settings`, {
          method: 'POST',
          body: JSON.stringify(amocrmPayload()),
        });
        setAmocrmResult(data);
        setMessage(data.message || 'Настройки amoCRM сохранены.');
        await loadAmocrmSettings();
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setAmocrmBusy(false);
      }
    }

    async function runAmocrmAction(kind) {
      setAmocrmBusy(true);
      setError('');
      try {
        let url = `${API_BASE}/api/payme/exports/amocrm/test`;
        let body = null;
        if (kind === 'setup') {
          url = `${API_BASE}/api/payme/exports/amocrm/setup`;
          body = JSON.stringify({ dry_run: false });
        } else if (kind === 'setup-dry') {
          url = `${API_BASE}/api/payme/exports/amocrm/setup`;
          body = JSON.stringify({ dry_run: true });
        } else if (kind === 'dry-run') {
          url = `${API_BASE}/api/payme/exports/amocrm/dry-run`;
          body = JSON.stringify(amocrmRunPayload({ dryRun: true }));
        } else if (kind === 'run') {
          url = `${API_BASE}/api/payme/exports/amocrm/run`;
          body = JSON.stringify(amocrmRunPayload({ dryRun: false }));
        }
        const data = await apiJson(url, { method: 'POST', ...(body ? { body } : {}) });
        setAmocrmResult(data);
        setMessage(data.message || data?.job?.message || 'amoCRM действие выполнено.');
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setAmocrmBusy(false);
      }
    }

    async function loadResetStatus() {
      try {
        const data = await apiJson(`${API_BASE}/api/payme/system/reset-data/status`);
        setResetStatus(data);
        return data;
      } catch (err) {
        const fallback = {
          running: false,
          progress_percent: 0,
          progress_label: 'Не удалось загрузить статус сброса данных',
          last_error: String(err?.message || err),
          log: [],
        };
        setResetStatus(fallback);
        return fallback;
      }
    }

    async function resetRuntimeData() {
      const confirmed = window.confirm(
        'Стереть производные данные и пересобрать базу с нуля? Настройки, лицензия и Telegram-сессия сохранятся.',
      );
      if (!confirmed) return;
      setResetBusy(true);
      setError('');
      try {
        const first = await apiJson(`${API_BASE}/api/payme/system/reset-data`, { method: 'POST' });
        setResetStatus(first);
        if (typeof window.BackfrontClearRuntimeState === 'function') {
          window.BackfrontClearRuntimeState();
        }
        const startedAt = Date.now();
        while (Date.now() - startedAt < 120000) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const status = await loadResetStatus();
          if (!status?.running) break;
        }
        setMessage('Сброс данных выполнен или запущен в фоне. Настройки сохранены.');
      } catch (err) {
        setError(String(err?.message || err));
      } finally {
        setResetBusy(false);
      }
    }

    React.useEffect(() => {
      loadSettings();
      loadResetStatus();
    }, []);

    React.useEffect(() => {
      const timer = window.setTimeout(() => {
        loadModels({
          includePaid: settings.openrouter_show_paid_models,
          query: modelQuery,
        });
      }, 350);
      return () => window.clearTimeout(timer);
    }, [modelQuery, settings.openrouter_show_paid_models]);

    const currentModelInList = models.some((model) => model.id === settings.openrouter_model);
    const selectModels = currentModelInList
      ? models
      : [{ id: settings.openrouter_model, name: `${settings.openrouter_model} (текущая)`, free: settings.openrouter_model.endsWith(':free') }, ...models];
    const setupWizardVisible = Boolean(settings.first_start_wizard_required || !settings.setup_wizard_completed);
    const resetPercent = Math.max(0, Math.min(100, Number(resetStatus?.progress_percent || 0)));
    const resetLogSource = Array.isArray(resetStatus?.progress_log)
      ? resetStatus.progress_log
      : (Array.isArray(resetStatus?.log) ? resetStatus.log : []);
    const resetLogs = resetLogSource.slice(0, 6);
    const licenseRows = [
      ['Лицензия', licenseStatus?.license_id_display || 'не указана'],
      ['Статус', licenseStatusText(licenseStatus?.status)],
      ['Email клиента', licenseStatus?.client_email || 'не указан'],
      ['Тариф', licenseStatus?.plan_title || licenseStatus?.plan || 'не указан'],
      ['Тип лицензии', licenseStatus?.license_kind || 'не указан'],
      ['Действует до', formatLicenseDate(licenseStatus?.valid_until)],
      ['Invite-code', licenseStatus?.invite_code_display || 'не указан'],
      [
        'Осталось',
        Number.isFinite(Number(licenseStatus?.days_remaining))
          ? `${Math.max(0, Number(licenseStatus.days_remaining))} дн.`
          : 'не рассчитано',
      ],
    ];
    const setupWizardSteps = [
      {
        title: 'Telegram API',
        ok: !!settings.telegram_api_configured,
        text: 'api_id и api_hash нужны, чтобы программа могла подключиться к Telegram от имени клиента.',
      },
      {
        title: 'OpenRouter',
        ok: !!String(settings.openrouter_api_key || '').trim(),
        text: 'Ключ нужен для LLM-анализа контактов, дат мероприятий, маршрутов и сделок.',
      },
      {
        title: 'OCR-сервис',
        ok: !!String(settings.ocr_service_url || '').trim(),
        text: 'Адрес x-files-ocr нужен для распознавания текста на изображениях.',
      },
      {
        title: 'Email лицензий',
        ok: !settings.license_email_enabled || (!!settings.license_email_login && !!settings.license_email_password_configured),
        text: 'Если email-лицензии включены, укажите почту и app-password клиента.',
      },
    ];

    return html`
      <div className="page">
        <${PageHeader}
          title="Настройки"
          subtitle="OCR изображений, OpenRouter API и параметры модели по умолчанию."
          active="settings"
        />

        <section className="toolbar">
          <div className="nav">
            <span className=${`badge ${error ? 'badge-yellow' : 'badge-green'}`}>${loading ? 'Загрузка' : (error ? 'Нужно внимание' : 'Готово')}</span>
            <span className="subtle">${error || message || 'Настройки готовы.'}</span>
          </div>
          <div className="nav">
            <button className="btn" onClick=${loadSettings} disabled=${loading || saving}>Обновить</button>
            <button className="btn btn-active" onClick=${saveSettings} disabled=${loading || saving}>
              ${saving ? 'Сохранение…' : 'Сохранить настройки'}
            </button>
          </div>
        </section>

        <section className="settings-tabs" aria-label="Разделы настроек">
          ${settingsTabs.map((tab) => html`
            <button
              key=${tab.id}
              className=${`btn settings-tab-button ${activeTab === tab.id ? 'btn-active' : ''}`}
              type="button"
              onClick=${() => changeSettingsTab(tab.id)}
            >
              ${tab.label}
            </button>
          `)}
        </section>

        <section className=${tabPanelClass('system', 'danger-zone')}>
          <div className="section-title">Данные и переинициализация</div>
          <div className="section-subtitle">
            Сбрасывает import, Sync, чаты, JSONL/out, DuckDB, media/HTML и кеши анализа, но сохраняет настройки, лицензию и Telegram-сессию. Это безопасный способ начать демо-базу с нуля.
          </div>
          <div className="actions">
            <button
              className="btn btn-danger"
              type="button"
              disabled=${resetBusy || resetStatus?.running}
              onClick=${resetRuntimeData}
            >
              ${resetBusy || resetStatus?.running ? 'Инициализация…' : 'Стереть базу данных и инициализировать с нуля'}
            </button>
            <button className="btn" type="button" onClick=${loadResetStatus}>Обновить статус</button>
            <span className="muted">${resetStatus?.progress_label || 'Сброс ещё не запускался'}</span>
          </div>
          <div className="reset-progress">
            <div className="progress-shell">
              <div className="progress-fill" style=${{ width: `${resetPercent}%` }}></div>
            </div>
            <div className="muted">${resetPercent}%</div>
          </div>
          ${resetStatus?.last_error ? html`<div className="error-box">${resetStatus.last_error}</div>` : null}
          ${resetLogs.length ? html`
            <div className="log-lines">
              ${resetLogs.map((row, index) => html`
                <div key=${`reset-log-${index}`}>
                  ${typeof row === 'string' ? row : `${row.ts || ''} ${row.message || row.progress_label || ''}`}
                </div>
              `)}
            </div>
          ` : null}
        </section>

        <section className=${tabPanelClass('system')}>
          <div className="section-title">Локальный адрес интерфейса</div>
          <div className="section-subtitle">
            Клиентская поставка слушает только локальную машину: <code>localhost</code> / <code>127.0.0.1</code>. Внешний доступ по IP сети отключён. Смена порта применяется после перезапуска Docker compose с обновлённым <code>.env</code>.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Bind host</label>
              <select
                className="select"
                value=${settings.localhost_bind || '127.0.0.1'}
                onChange=${(e) => setSettings((prev) => ({ ...prev, localhost_bind: e.target.value }))}
              >
                <option value="127.0.0.1">127.0.0.1</option>
                <option value="localhost">localhost</option>
              </select>
            </div>
            <div className="field">
              <label>Port</label>
              <input
                className="input"
                type="number"
                min="1"
                max="65535"
                step="1"
                value=${settings.localhost_port || 8001}
                onChange=${(e) => setSettings((prev) => ({ ...prev, localhost_port: e.target.value }))}
              />
              <div className="muted">Текущий локальный URL после применения: <code>http://localhost:${settings.localhost_port || 8001}/</code>.</div>
            </div>
          </div>
        </section>

        ${setupWizardVisible ? html`
          <section className=${tabPanelClass('telegram')} style=${{ borderColor: '#fbbf24', background: 'rgba(255,251,235,.82)' }}>
            <div className="section-title">Стартовый мастер настройки</div>
            <div className="section-subtitle">
              Первый запуск X-Files: заполните ключи Telegram, OpenRouter, OCR и лицензий. После сохранения мастер можно закрыть, но он снова появится, если Telegram api_id/api_hash пропадут.
            </div>
            <div className="model-list">
              ${setupWizardSteps.map((step) => html`
                <div className="model-row" key=${step.title} style=${{ gridTemplateColumns: '180px 120px 1fr' }}>
                  <strong>${step.title}</strong>
                  <span className=${`badge ${step.ok ? 'badge-green' : 'badge-yellow'}`}>${step.ok ? 'готово' : 'нужно заполнить'}</span>
                  <span className="muted">${step.text}</span>
                </div>
              `)}
            </div>
            <div className="actions">
              <button
                className="btn btn-active"
                type="button"
                disabled=${saving || !settings.telegram_api_configured}
                onClick=${() => saveSettings({ setup_wizard_completed: true })}
              >
                ${saving ? 'Сохраняю…' : 'Сохранить и закрыть мастер'}
              </button>
              <button className="btn" type="button" disabled=${saving} onClick=${() => saveSettings()}>
                Сохранить введённые настройки
              </button>
              <span className="muted">
                ${settings.telegram_api_configured
                  ? 'Telegram API указан, можно закрыть мастер после проверки остальных настроек.'
                  : 'Сначала укажите Telegram api_id и api_hash ниже.'}
              </span>
            </div>
          </section>
        ` : null}

        <section className=${tabPanelClass('telegram')}>
          <div className="section-title">Telegram API backend</div>
          <div className="section-subtitle">
            Сначала укажите api_id и api_hash из my.telegram.org → API development tools. Если ключи уже заданы, они отображаются здесь и их можно поменять без пересборки Docker.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Telegram api_id</label>
              <input
                className="input"
                type="text"
                inputMode="numeric"
                value=${settings.telegram_api_id || ''}
                placeholder="например 12345678"
                onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_api_id: e.target.value }))}
              />
              <div className="muted">
                Статус: <span className=${`badge ${settings.telegram_api_configured ? 'badge-green' : 'badge-yellow'}`}>
                  ${settings.telegram_api_configured ? 'указаны' : 'нужно указать'}
                </span>
                ${settings.telegram_api_credentials_source ? html` · источник: ${settings.telegram_api_credentials_source}` : null}
              </div>
            </div>
            <div className="field">
              <label>Telegram api_hash</label>
              <input
                className="input"
                type="password"
                value=${settings.telegram_api_hash || ''}
                placeholder="api_hash из my.telegram.org"
                onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_api_hash: e.target.value }))}
              />
              <div className="muted">Получить ключи можно в Telegram: <code>my.telegram.org → API development tools</code>.</div>
            </div>
            <div className="field">
              <label>Backend Telegram клиента</label>
              <select
                className="select"
                value=${settings.telegram_client_backend || 'telethon'}
                onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_client_backend: e.target.value }))}
              >
                <option value="telethon">Telethon — основной режим</option>
                <option value="tdlib">TDLib — экспериментальный целевой режим</option>
              </select>
              <div className="muted">
                Выбор сохраняется в runtime-state. Реальное переключение на TDLib будет включено после выполнения плана в <code>TDLib-todo.md</code>.
              </div>
            </div>
            <div className="field">
              <label>Мобильный телефон Telegram</label>
              <input
                className="input"
                type="tel"
                value=${settings.telegram_phone || ''}
                placeholder="+79991234567"
                onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_phone: e.target.value }))}
              />
              <div className="muted">В клиентской поставке телефон вводится в стартовом мастере и сохраняется здесь для повторной проверки.</div>
            </div>
          </div>
        </section>

        <section className=${tabPanelClass('telegram')}>
          <div className="section-title">Media OCR</div>
          <div className="section-subtitle">
            Если включено, программа скачивает только изображения из media-чатов, распознаёт OCR, извлекает CRM-поля и записывает результат в базу с источником media. По умолчанию изображения сохраняются рядом с .txt, чтобы результат OCR был виден в Media.
          </div>
          <div className="form-grid">
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <label>Адрес OCR-сервиса x-files-ocr</label>
              <input
                className="input"
                type="text"
                value=${settings.ocr_service_url || ''}
                placeholder="например http://127.0.0.1:8010"
                onChange=${(e) => setSettings((prev) => ({ ...prev, ocr_service_url: e.target.value }))}
              />
              <div className="muted">
                Сейчас OCR вынесен в отдельный Docker-сервис. В мастере первого запуска по умолчанию предлагается адрес на той же машине, где открыт интерфейс.
              </div>
            </div>
            <label className="chip">
              <input
                type="checkbox"
                checked=${!!settings.ocr_images_enabled}
                onChange=${(e) => setSettings((prev) => ({ ...prev, ocr_images_enabled: e.target.checked }))}
              />
              Включить OCR изображений
            </label>
            <label className="chip">
              <input
                type="checkbox"
                checked=${!!settings.ocr_delete_images_after_processing}
                onChange=${(e) => setSettings((prev) => ({ ...prev, ocr_delete_images_after_processing: e.target.checked }))}
              />
              Удалять изображения после OCR
            </label>
          </div>
        </section>

        <section className=${tabPanelClass('import')}>
          <div className="section-title">Группы частоты Telegram-сканирования</div>
          <div className="section-subtitle">
            Эти группы назначаются каналам в Сетке. Частоты сохраняются в настройках и будут использоваться scheduler-очередью после внедрения задач из <code>группы-todo.md</code>.
          </div>
          <div className="model-list">
            ${normalizeScanGroups(settings.telegram_scan_groups).map((group, index) => html`
              <div className="model-row" key=${group.id} style=${{ gridTemplateColumns: '72px 1.4fr 180px 1fr 180px' }}>
                <div>
                  <div className="muted">Группа</div>
                  <strong>${group.id}</strong>
                </div>
                <div className="field">
                  <label>Название</label>
                  <input
                    className="input"
                    type="text"
                    value=${group.label}
                    onChange=${(e) => setSettings((prev) => {
                      const groups = normalizeScanGroups(prev.telegram_scan_groups);
                      groups[index] = { ...groups[index], label: e.target.value };
                      return { ...prev, telegram_scan_groups: groups };
                    })}
                  />
                </div>
                <div className="field">
                  <label>Каналов</label>
                  <input
                    className="input"
                    type="text"
                    value=${group.channels_range}
                    onChange=${(e) => setSettings((prev) => {
                      const groups = normalizeScanGroups(prev.telegram_scan_groups);
                      groups[index] = { ...groups[index], channels_range: e.target.value };
                      return { ...prev, telegram_scan_groups: groups };
                    })}
                  />
                </div>
                <div className="field">
                  <label>Частота</label>
                  <input
                    className="input"
                    type="text"
                    value=${group.frequency}
                    onChange=${(e) => setSettings((prev) => {
                      const groups = normalizeScanGroups(prev.telegram_scan_groups);
                      groups[index] = { ...groups[index], frequency: e.target.value };
                      return { ...prev, telegram_scan_groups: groups };
                    })}
                  />
                </div>
                <div className="field">
                  <label>Интервал, мин</label>
                  <input
                    className="input"
                    type="number"
                    min="1"
                    max="10080"
                    step="1"
                    value=${group.interval_minutes}
                    onChange=${(e) => setSettings((prev) => {
                      const groups = normalizeScanGroups(prev.telegram_scan_groups);
                      groups[index] = {
                        ...groups[index],
                        interval_minutes: Math.min(10080, Math.max(1, Number(e.target.value || group.interval_minutes || 60))),
                      };
                      return { ...prev, telegram_scan_groups: groups };
                    })}
                  />
                </div>
              </div>
            `)}
          </div>
        </section>

        <section className=${tabPanelClass('import')}>
          <div className="section-title">Import</div>
          <div className="section-subtitle">
            Ограничения защищают Telegram-сканирование от случайной массовой выгрузки. По умолчанию клиентская демо-лицензия читает только последний месяц и до 1000 сообщений на источник; максимумы задаются лицензией.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Лимит “Добавить все”</label>
              <input
                className="input"
                type="number"
                min="1"
                max="1000000"
                step="1"
                value=${settings.import_default_add_limit}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  import_default_add_limit: Math.min(1000000, Math.max(1, Number(e.target.value || 50))),
                }))}
              />
              <div className="muted">По умолчанию 50. На этой машине лимит можно поднять выше, тарифный лимит источников задаётся лицензией или локальным override.</div>
            </div>
            <div className="field">
              <label>История Import по умолчанию, месяцев</label>
              <input
                className="input"
                type="number"
                min="0"
                max=${importLimitInputMax(settings.import_max_history_months, DEFAULT_SETTINGS.import_max_history_months)}
                step="1"
                value=${settings.import_default_history_months}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  import_default_history_months: clampImportDefault(e.target.value, prev.import_max_history_months, DEFAULT_SETTINGS.import_default_history_months),
                }))}
              />
              <div className="muted">
                Лицензия разрешает максимум: <strong>${importLimitLabel(settings.import_max_history_months, 'мес.')}</strong>
                Можно переопределить отдельно для каждого источника на вкладке Import.
              </div>
            </div>
            <div className="field">
              <label>Сообщений Import по умолчанию на источник</label>
              <input
                className="input"
                type="number"
                min="0"
                max=${importLimitInputMax(settings.import_max_message_limit, DEFAULT_SETTINGS.import_max_message_limit)}
                step="50"
                value=${settings.import_default_message_limit}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  import_default_message_limit: clampImportDefault(e.target.value, prev.import_max_message_limit, DEFAULT_SETTINGS.import_default_message_limit),
                }))}
              />
              <div className="muted">
                Лицензия разрешает максимум: <strong>${importLimitLabel(settings.import_max_message_limit, 'сообщений')}</strong>.
                Если источник уже есть в базе, backend продолжает с сохранённого cursor/state и не перечитывает всё заново.
              </div>
            </div>
          </div>
        </section>

        <section className=${tabPanelClass('license')}>
          <div className="section-title">Лицензия и локальные лимиты</div>
          <div className="section-subtitle">
            Статус лицензии проверяется онлайн. Продление и отзыв выполняются владельцем продукта.
          </div>
          <div className="form-grid">
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <label>Статус лицензии</label>
              <div className="license-status-summary">
                <span className=${`badge ${licenseBadgeClass(licenseStatus?.status, licenseStatus?.ok)}`}>
                  ${settings.telegram_unlimited_import_enabled ? 'local_owner_override' : licenseStatusText(licenseStatus?.status)}
                </span>
                <strong>${licenseStatus?.client_email || 'email не указан'}</strong>
                <span className="muted">${licenseStatus?.plan_title || licenseStatus?.plan || 'тариф не указан'}</span>
                <span className="muted">до ${formatLicenseDate(licenseStatus?.valid_until)}</span>
                ${settings.telegram_unlimited_import_enabled ? ' · безлимит включён локально' : ''}
              </div>
              <div className="muted">
                Import до ${importLimitLabel(settings.import_max_history_months, 'мес.')} и ${importLimitLabel(settings.import_max_message_limit, 'сообщений')}.
                Безлимит: ${licenseStatus?.license_capabilities?.telegram_unlimited_import ? 'разрешён лицензией' : 'доступен только через локальный override, если разрешён лицензией'}.
              </div>
            </div>
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <label>Данные лицензии</label>
              <div className="license-status-grid">
                ${licenseRows.map(([label, value]) => html`
                  <div className="license-status-cell" key=${label}>
                    <span className="muted">${label}</span>
                    <strong>${value}</strong>
                  </div>
                `)}
              </div>
              ${licenseStatus?.disabled_reason ? html`
                <div className="error-box" style=${{ marginTop: '12px' }}>${licenseStatus.disabled_reason}</div>
              ` : null}
              <div className="actions" style=${{ marginTop: '12px' }}>
                <button className="btn" type="button" disabled=${licenseBusy} onClick=${loadLicenseStatus}>
                  ${licenseBusy ? 'Проверяю…' : 'Проверить статус'}
                </button>
                <span className="muted">Изменение срока, тарифа и отзыв делает владелец продукта в панели лицензий.</span>
              </div>
            </div>
            <label className="chip" style=${{ gridColumn: '1 / -1' }}>
              <input
                type="checkbox"
                checked=${!!settings.local_import_limits_enabled}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  local_import_limits_enabled: e.target.checked,
                  telegram_unlimited_import_enabled: e.target.checked ? prev.telegram_unlimited_import_enabled : false,
                }))}
              />
              Расширить локальные лимиты Import только на этой машине
            </label>
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <button
                className="btn btn-active"
                type="button"
                disabled=${licenseBusy || (licenseStatus?.license_capabilities?.telegram_unlimited_import === false && licenseStatus?.license_capabilities?.local_import_limit_override === false)}
                onClick=${enableUnlimitedImportMode}
              >
                ${settings.telegram_unlimited_import_enabled ? 'Безлимитная загрузка включена' : 'Включить безлимитную загрузку'}
              </button>
              <div className="muted">
                Кнопка включает <code>telegram_unlimited_import</code>: 0 месяцев и 0 сообщений означает без ограничения по времени и количеству.
                Режим применяется ко всем уже импортированным источникам и сохраняется в локальном контуре Docker.
              </div>
            </div>
            <div className="field">
              <label>Локально месяцев сканирования</label>
              <input
                className="input"
                type="number"
                min="0"
                step="1"
                value=${settings.local_import_max_history_months ?? 1}
                onChange=${(e) => setSettings((prev) => ({ ...prev, local_import_max_history_months: Math.max(0, Number(e.target.value || 0)) }))}
              />
              <div className="muted">0 = безлимит по времени.</div>
            </div>
            <div className="field">
              <label>Локально сообщений на источник</label>
              <input
                className="input"
                type="number"
                min="0"
                step="100"
                value=${settings.local_import_max_message_limit ?? 1000}
                onChange=${(e) => setSettings((prev) => ({ ...prev, local_import_max_message_limit: Math.max(0, Number(e.target.value || 0)) }))}
              />
              <div className="muted">0 = безлимит по числу сообщений.</div>
            </div>
          </div>
        </section>

        <section className=${tabPanelClass('bitrix24')}>
          <div className="section-title">Bitrix24 export</div>
          <div className="section-subtitle">
            Экспортирует GramLead CRM-контакты и лид-сигналы в Bitrix24. Для первого запуска используйте inbound webhook с правом CRM: секрет сохраняется на backend и не возвращается во frontend.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Bitrix24 portal URL</label>
              <input
                className="input"
                type="text"
                value=${bitrix24.portal_url || ''}
                placeholder="https://example.bitrix24.ru"
                onChange=${(e) => updateBitrix24({ portal_url: e.target.value })}
              />
              <div className="muted">Адрес портала без REST-кода. Например: <code>https://company.bitrix24.ru</code>.</div>
            </div>
            <div className="field">
              <label>Auth mode</label>
              <select
                className="select"
                value=${bitrix24.auth_mode || 'webhook'}
                onChange=${(e) => updateBitrix24({ auth_mode: e.target.value })}
              >
                <option value="webhook">Inbound webhook</option>
                <option value="oauth">OAuth / local app</option>
              </select>
            </div>
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <label>Webhook URL</label>
              <input
                className="input"
                type="password"
                value=${bitrix24.webhook_url || ''}
                placeholder=${bitrix24.webhook_configured ? `секрет уже настроен: ${bitrix24.webhook_url_masked || '***'}` : 'https://.../rest/{user_id}/{webhook_code}/'}
                onChange=${(e) => updateBitrix24({ webhook_url: e.target.value })}
              />
              <div className="muted">Bitrix24: Приложения → Разработчикам → Other → Inbound webhook, scope CRM.</div>
            </div>
            ${bitrix24.auth_mode === 'oauth' ? html`
              <div className="field">
                <label>OAuth access token</label>
                <input
                  className="input"
                  type="password"
                  value=${bitrix24.access_token || ''}
                  placeholder=${bitrix24.access_token_configured ? `секрет уже настроен: ${bitrix24.access_token_masked || '***'}` : 'access_token'}
                  onChange=${(e) => updateBitrix24({ access_token: e.target.value })}
                />
              </div>
              <div className="field">
                <label>client_id</label>
                <input className="input" type="text" value=${bitrix24.client_id || ''} onChange=${(e) => updateBitrix24({ client_id: e.target.value })} />
              </div>
              <div className="field">
                <label>client_secret</label>
                <input
                  className="input"
                  type="password"
                  value=${bitrix24.client_secret || ''}
                  placeholder=${bitrix24.client_secret_configured ? `секрет уже настроен: ${bitrix24.client_secret_masked || '***'}` : 'client_secret'}
                  onChange=${(e) => updateBitrix24({ client_secret: e.target.value })}
                />
              </div>
              <div className="field">
                <label>refresh_token</label>
                <input
                  className="input"
                  type="password"
                  value=${bitrix24.refresh_token || ''}
                  placeholder=${bitrix24.refresh_token_configured ? `секрет уже настроен: ${bitrix24.refresh_token_masked || '***'}` : 'refresh_token'}
                  onChange=${(e) => updateBitrix24({ refresh_token: e.target.value })}
                />
              </div>
            ` : null}
            <div className="field">
              <label>Сущность</label>
              <select
                className="select"
                value=${bitrix24.selected_entity || 'lead'}
                onChange=${(e) => updateBitrix24({ selected_entity: e.target.value })}
              >
                <option value="lead">Лиды</option>
                <option value="deal">Сделки</option>
              </select>
            </div>
            <div className="field">
              <label>Лимит dry-run / export</label>
              <input
                className="input"
                type="number"
                min="1"
                max="5000"
                step="1"
                value=${bitrix24.dry_run_limit || 25}
                onChange=${(e) => updateBitrix24({ dry_run_limit: e.target.value })}
              />
            </div>
            <label className="chip"><input type="checkbox" checked=${!!bitrix24.export_contacts} onChange=${(e) => updateBitrix24({ export_contacts: e.target.checked })} />Контакты</label>
            <label className="chip"><input type="checkbox" checked=${!!bitrix24.export_leads} onChange=${(e) => updateBitrix24({ export_leads: e.target.checked })} />Лиды / сделки</label>
            <label className="chip"><input type="checkbox" checked=${!!bitrix24.export_timeline} onChange=${(e) => updateBitrix24({ export_timeline: e.target.checked })} />Timeline / рекомендации</label>
          </div>
          <div className="actions">
            <button className="btn btn-active" type="button" disabled=${bitrix24Busy} onClick=${saveBitrix24Settings}>${bitrix24Busy ? 'Выполняю…' : 'Сохранить Bitrix24'}</button>
            <button className="btn" type="button" disabled=${bitrix24Busy} onClick=${() => runBitrix24Action('test')}>Проверить подключение</button>
            <button className="btn" type="button" disabled=${bitrix24Busy} onClick=${() => runBitrix24Action('setup-dry')}>Dry-run полей</button>
            <button className="btn" type="button" disabled=${bitrix24Busy} onClick=${() => runBitrix24Action('setup')}>Подготовить поля</button>
            <button className="btn" type="button" disabled=${bitrix24Busy} onClick=${() => runBitrix24Action('dry-run')}>Dry-run экспорта</button>
            <button className="btn btn-active" type="button" disabled=${bitrix24Busy} onClick=${() => runBitrix24Action('run')}>Экспортировать</button>
          </div>
          ${bitrix24Result ? html`
            <div className="result-panel" style=${{ marginTop: '14px' }}>
              <div className="section-subtitle">${bitrix24Result.message || bitrix24Result.job?.message || 'Последний ответ Bitrix24 export'}</div>
              ${bitrix24Result.counts ? html`
                <div className="stats-grid">
                  ${Object.entries(bitrix24Result.counts).map(([key, value]) => html`
                    <div className="metric-card" key=${key}><span>${key}</span><strong>${value}</strong></div>
                  `)}
                </div>
              ` : null}
              ${bitrix24Result.job ? html`
                <div className="reset-progress">
                  <div className="progress-shell">
                    <div className="progress-fill" style=${{ width: `${Math.max(0, Math.min(100, Number(bitrix24Result.job.progress_percent || 0)))}%` }}></div>
                  </div>
                  <div className="muted">${bitrix24Result.job.progress_percent || 0}% · ${bitrix24Result.job.status || ''}</div>
                </div>
              ` : null}
              <pre className="log-lines" style=${{ whiteSpace: 'pre-wrap', maxHeight: '320px', overflow: 'auto' }}>${JSON.stringify(bitrix24Result.sample || bitrix24Result.check || bitrix24Result.errors || bitrix24Result.job || bitrix24Result.custom_fields || bitrix24Result.settings || {}, null, 2)}</pre>
            </div>
          ` : null}
        </section>

        <section className=${tabPanelClass('amocrm')}>
          <div className="section-title">amoCRM export</div>
          <div className="section-subtitle">
            Экспортирует GramLead контакты, сделки и заметки в amoCRM. Для подключения нужен OAuth access token или токены внешней интеграции amoCRM; секреты сохраняются на backend и не возвращаются во frontend.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>amoCRM subdomain</label>
              <input
                className="input"
                type="text"
                value=${amocrm.subdomain || ''}
                placeholder="company.amocrm.ru"
                onChange=${(e) => updateAmocrm({ subdomain: e.target.value })}
              />
              <div className="muted">Можно вставить полный URL, backend сохранит только домен аккаунта amoCRM.</div>
            </div>
            <div className="field">
              <label>Redirect URI</label>
              <input
                className="input"
                type="text"
                value=${amocrm.redirect_uri || ''}
                placeholder="https://example.com/amocrm/callback"
                onChange=${(e) => updateAmocrm({ redirect_uri: e.target.value })}
              />
            </div>
            <div className="field">
              <label>client_id</label>
              <input className="input" type="text" value=${amocrm.client_id || ''} onChange=${(e) => updateAmocrm({ client_id: e.target.value })} />
            </div>
            <div className="field">
              <label>client_secret</label>
              <input
                className="input"
                type="password"
                value=${amocrm.client_secret || ''}
                placeholder=${amocrm.client_secret_configured ? `секрет уже настроен: ${amocrm.client_secret_masked || '***'}` : 'client_secret'}
                onChange=${(e) => updateAmocrm({ client_secret: e.target.value })}
              />
            </div>
            <div className="field">
              <label>access_token</label>
              <input
                className="input"
                type="password"
                value=${amocrm.access_token || ''}
                placeholder=${amocrm.access_token_configured ? `секрет уже настроен: ${amocrm.access_token_masked || '***'}` : 'access_token'}
                onChange=${(e) => updateAmocrm({ access_token: e.target.value })}
              />
            </div>
            <div className="field">
              <label>refresh_token</label>
              <input
                className="input"
                type="password"
                value=${amocrm.refresh_token || ''}
                placeholder=${amocrm.refresh_token_configured ? `секрет уже настроен: ${amocrm.refresh_token_masked || '***'}` : 'refresh_token'}
                onChange=${(e) => updateAmocrm({ refresh_token: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Pipeline ID</label>
              <input className="input" type="text" value=${amocrm.selected_pipeline_id || ''} onChange=${(e) => updateAmocrm({ selected_pipeline_id: e.target.value })} />
            </div>
            <div className="field">
              <label>Status ID</label>
              <input className="input" type="text" value=${amocrm.selected_status_id || ''} onChange=${(e) => updateAmocrm({ selected_status_id: e.target.value })} />
            </div>
            <div className="field">
              <label>Responsible user ID</label>
              <input className="input" type="text" value=${amocrm.responsible_user_id || ''} onChange=${(e) => updateAmocrm({ responsible_user_id: e.target.value })} />
            </div>
            <div className="field">
              <label>Лимит dry-run / export</label>
              <input
                className="input"
                type="number"
                min="1"
                max="5000"
                step="1"
                value=${amocrm.dry_run_limit || 25}
                onChange=${(e) => updateAmocrm({ dry_run_limit: e.target.value })}
              />
            </div>
            <label className="chip"><input type="checkbox" checked=${!!amocrm.export_contacts} onChange=${(e) => updateAmocrm({ export_contacts: e.target.checked })} />Контакты</label>
            <label className="chip"><input type="checkbox" checked=${!!amocrm.export_companies} onChange=${(e) => updateAmocrm({ export_companies: e.target.checked })} />Компании</label>
            <label className="chip"><input type="checkbox" checked=${!!amocrm.export_leads} onChange=${(e) => updateAmocrm({ export_leads: e.target.checked })} />Сделки</label>
            <label className="chip"><input type="checkbox" checked=${!!amocrm.export_notes} onChange=${(e) => updateAmocrm({ export_notes: e.target.checked })} />Заметки</label>
            <label className="chip"><input type="checkbox" checked=${!!amocrm.export_tags} onChange=${(e) => updateAmocrm({ export_tags: e.target.checked })} />Теги</label>
          </div>
          <div className="actions">
            <button className="btn btn-active" type="button" disabled=${amocrmBusy} onClick=${saveAmocrmSettings}>${amocrmBusy ? 'Выполняю…' : 'Сохранить amoCRM'}</button>
            <button className="btn" type="button" disabled=${amocrmBusy} onClick=${() => runAmocrmAction('test')}>Проверить подключение</button>
            <button className="btn" type="button" disabled=${amocrmBusy} onClick=${() => runAmocrmAction('setup-dry')}>Dry-run полей</button>
            <button className="btn" type="button" disabled=${amocrmBusy} onClick=${() => runAmocrmAction('setup')}>Подготовить поля</button>
            <button className="btn" type="button" disabled=${amocrmBusy} onClick=${() => runAmocrmAction('dry-run')}>Dry-run экспорта</button>
            <button className="btn btn-active" type="button" disabled=${amocrmBusy} onClick=${() => runAmocrmAction('run')}>Экспортировать</button>
          </div>
          ${amocrmResult ? html`
            <div className="result-panel" style=${{ marginTop: '14px' }}>
              <div className="section-subtitle">${amocrmResult.message || amocrmResult.job?.message || 'Последний ответ amoCRM export'}</div>
              ${amocrmResult.counts ? html`
                <div className="stats-grid">
                  ${Object.entries(amocrmResult.counts).map(([key, value]) => html`
                    <div className="metric-card" key=${key}><span>${key}</span><strong>${value}</strong></div>
                  `)}
                </div>
              ` : null}
              ${amocrmResult.job ? html`
                <div className="reset-progress">
                  <div className="progress-shell">
                    <div className="progress-fill" style=${{ width: `${Math.max(0, Math.min(100, Number(amocrmResult.job.progress_percent || 0)))}%` }}></div>
                  </div>
                  <div className="muted">${amocrmResult.job.progress_percent || 0}% · ${amocrmResult.job.status || ''}</div>
                </div>
              ` : null}
              <pre className="log-lines" style=${{ whiteSpace: 'pre-wrap', maxHeight: '320px', overflow: 'auto' }}>${JSON.stringify(amocrmResult.sample || amocrmResult.check || amocrmResult.errors || amocrmResult.job || amocrmResult.custom_fields || amocrmResult.settings || {}, null, 2)}</pre>
            </div>
          ` : null}
        </section>

        ${false ? html`<section className=${tabPanelClass('data')}>
          <div className="section-title">Источники данных / Plugins</div>
          <div className="section-subtitle">
            Подключайте готовые SQLite/DuckDB базы как read-only источники. Они получают namespace selector и дальше идут через общий слой сообщений, Sync, LLM и Deals без доступа к root/license данным.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>Plugin</label>
              <select
                className="select"
                value=${dataSourceForm.source_type}
                onChange=${(e) => setDataSourceForm((prev) => ({ ...prev, source_type: e.target.value }))}
              >
                ${(dataSourcePlugins.length ? dataSourcePlugins : [{ type: 'sqlite', display_name: 'SQLite' }]).map((plugin) => html`
                  <option key=${plugin.type} value=${plugin.type}>${plugin.display_name || plugin.type}</option>
                `)}
              </select>
              <div className="muted">
                Capability лицензии: <code>data_source_plugins</code>
                ${licenseStatus?.license_capabilities?.data_source_plugins ? ' включён' : ' ожидает включения в лицензии'}.
              </div>
            </div>
            <div className="field">
              <label>Название источника</label>
              <input
                className="input"
                type="text"
                value=${dataSourceForm.source_name}
                placeholder="например CRM SQLite snapshot"
                onChange=${(e) => setDataSourceForm((prev) => ({ ...prev, source_name: e.target.value }))}
              />
            </div>
            <div className="field" style=${{ gridColumn: '1 / -1' }}>
              <label>Путь к базе или DSN</label>
              <input
                className="input"
                type="text"
                value=${dataSourceForm.path}
                placeholder="/data/client/imports/crm.sqlite или /data/client/imports/messages.duckdb"
                onChange=${(e) => setDataSourceForm((prev) => ({ ...prev, path: e.target.value }))}
              />
              <div className="muted">Секреты не показываются после сохранения; для SQLite/DuckDB сейчас используется локальный путь внутри Docker data boundary.</div>
            </div>
          </div>
          <div className="actions">
            <button className="btn" type="button" disabled=${dataSourceBusy} onClick=${testDataSourceConnection}>
              ${dataSourceBusy ? 'Проверяю…' : 'Проверить подключение'}
            </button>
            <button className="btn btn-active" type="button" disabled=${dataSourceBusy} onClick=${registerDataSource}>
              ${dataSourceBusy ? 'Подключаю…' : 'Подключить источник'}
            </button>
            <button className="btn" type="button" disabled=${dataSourceBusy} onClick=${loadDataSources}>Обновить список</button>
          </div>
          <div className="model-list" style=${{ marginTop: '14px' }}>
            ${dataSources.length ? dataSources.map((source) => html`
              <div className="model-row" key=${source.source_id} style=${{ gridTemplateColumns: '150px 1fr 120px 150px' }}>
                <strong>${source.source_type}</strong>
                <span>${source.source_name || source.source_id}</span>
                <span className=${`badge ${source.enabled ? 'badge-green' : 'badge-yellow'}`}>${source.enabled ? 'активен' : 'отключён'}</span>
                <button className="btn" type="button" disabled=${dataSourceBusy || !source.enabled} onClick=${() => disconnectDataSource(source.source_id)}>
                  Отключить
                </button>
              </div>
            `) : html`
              <div className="muted">Подключенных plugin sources пока нет.</div>
            `}
          </div>
        </section>` : null}

        ${settings.show_license_email_settings ? html`<section className=${tabPanelClass('license')}>
          <div className="section-title">Email лицензий клиента</div>
          <div className="section-subtitle">
            Здесь клиент указывает почту, через которую сможет получать invite-license от x-files-root. Пароль/app-password сохраняется как локальный секрет и не возвращается обратно в браузер.
          </div>
          <div className="form-grid">
            <label className="chip" style=${{ gridColumn: '1 / -1' }}>
              <input
                type="checkbox"
                checked=${!!settings.license_email_enabled}
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_enabled: e.target.checked }))}
              />
              Включить получение invite-license через email
            </label>
            <div className="field">
              <label>IMAP/почтовый сервер</label>
              <input
                className="input"
                type="text"
                value=${settings.license_email_host || ''}
                placeholder="например imap.mail.ru"
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_host: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Порт</label>
              <input
                className="input"
                type="number"
                min="1"
                max="65535"
                step="1"
                value=${settings.license_email_port || 993}
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_port: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>SMTP сервер для activation receipt</label>
              <input
                className="input"
                type="text"
                value=${settings.license_email_smtp_host || ''}
                placeholder="например smtp.mail.ru"
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_smtp_host: e.target.value }))}
              />
              <div className="muted">Если оставить пустым, backend попробует заменить imap.* на smtp.*.</div>
            </div>
            <div className="field">
              <label>SMTP порт</label>
              <input
                className="input"
                type="number"
                min="1"
                max="65535"
                step="1"
                value=${settings.license_email_smtp_port || 465}
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_smtp_port: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Email/login клиента</label>
              <input
                className="input"
                type="email"
                value=${settings.license_email_login || ''}
                placeholder="client@example.com"
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_login: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Пароль или app-password</label>
              <input
                className="input"
                type="password"
                value=${settings.license_email_password || ''}
                placeholder=${settings.license_email_password_configured ? 'секрет уже настроен' : 'app-password почты'}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  license_email_password: e.target.value,
                  license_email_clear_password: false,
                }))}
              />
              <div className="muted">
                Статус: <span className=${`badge ${settings.license_email_password_configured ? 'badge-green' : 'badge-yellow'}`}>
                  ${settings.license_email_password_configured ? 'секрет настроен' : 'секрет не задан'}
                </span>
              </div>
            </div>
            <div className="field">
              <label>Папка входящих</label>
              <input
                className="input"
                type="text"
                value=${settings.license_email_inbox_folder || 'INBOX'}
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_inbox_folder: e.target.value }))}
              />
            </div>
            <label className="chip">
              <input
                type="checkbox"
                checked=${!!settings.license_email_allow_activation_receipt}
                onChange=${(e) => setSettings((prev) => ({ ...prev, license_email_allow_activation_receipt: e.target.checked }))}
              />
              Разрешить отправлять activation receipt владельцу продукта
            </label>
            <label className="chip">
              <input
                type="checkbox"
                checked=${!!settings.license_email_clear_password}
                onChange=${(e) => setSettings((prev) => ({
                  ...prev,
                  license_email_clear_password: e.target.checked,
                  license_email_password: '',
                }))}
              />
              Очистить сохранённый email-секрет
            </label>
            <div className="actions" style=${{ gridColumn: '1 / -1' }}>
              <button
                className="btn"
                type="button"
                disabled=${emailImporting || saving}
                onClick=${importLicenseFromEmail}
              >
                ${emailImporting ? 'Проверяю почту…' : 'Проверить почту и применить invite-license'}
              </button>
              <span className="muted">
                ${settings.license_email_last_import_at
                  ? `Последний email-импорт: ${settings.license_email_last_import_at}`
                  : 'Email-импорт ещё не запускался'}
              </span>
            </div>
          </div>
        </section>` : null}

        <section className=${tabPanelClass('llm')}>
          <div className="section-title">OpenRouter API</div>
          <div className="section-subtitle">
            Ключ хранится в локальном runtime-state, а не в исходниках. По умолчанию показываются free-модели; платные можно включить отдельной галочкой.
          </div>
          <div className="form-grid">
            <div className="field">
              <label>API key</label>
              <input
                className="input"
                type="password"
                value=${settings.openrouter_api_key || ''}
                placeholder="sk-or-v1-..."
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_api_key: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Модель по умолчанию</label>
              <select
                className="select"
                value=${settings.openrouter_model}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_model: normalizeModelId(e.target.value) }))}
              >
                ${selectModels.map((model) => html`
                  <option key=${model.id} value=${model.id}>${model.name || model.id} · ${model.id}</option>
                `)}
              </select>
            </div>
            <div className="field">
              <label>LLM по умолчанию</label>
              <select
                className="select"
                value=${settings.llm_provider || 'openrouter'}
                onChange=${(e) => setSettings((prev) => ({ ...prev, llm_provider: e.target.value }))}
              >
                <option value="openrouter">OpenRouter</option>
                <option value="local">Local LLM / LM Studio</option>
              </select>
              <div className="muted">Используется в анализе чатов, если на странице не выбран другой режим.</div>
            </div>
            <div className="field">
              <label>LM Studio URL</label>
              <input
                className="input"
                type="text"
                value=${settings.lmstudio_base_url || ''}
                placeholder="http://127.0.0.1:1234/v1"
                onChange=${(e) => setSettings((prev) => ({ ...prev, lmstudio_base_url: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>LM Studio модель</label>
              <input
                className="input"
                type="text"
                value=${settings.lmstudio_model || ''}
                placeholder="local-model"
                onChange=${(e) => setSettings((prev) => ({ ...prev, lmstudio_model: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Платная OpenRouter модель</label>
              <input
                className="input"
                type="text"
                value=${settings.openrouter_paid_model || ''}
                placeholder="openai/gpt-5-chat"
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_paid_model: normalizeModelId(e.target.value) }))}
              />
              <label className="chip" style=${{ marginTop: '8px' }}>
                <input
                  type="checkbox"
                  checked=${!!settings.openrouter_paid_model_enabled}
                  onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_paid_model_enabled: e.target.checked }))}
                />
                Разрешить платную модель в анализе чатов
              </label>
            </div>
            <div className="field">
              <label>Поиск моделей</label>
              <input
                className="input"
                type="text"
                value=${modelQuery}
                placeholder="например gpt, llama, qwen…"
                onChange=${(e) => setModelQuery(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Показ моделей</label>
              <label className="chip">
                <input
                  type="checkbox"
                  checked=${!!settings.openrouter_show_paid_models}
                  onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_show_paid_models: e.target.checked }))}
                />
                Показывать платные модели
              </label>
            </div>
            <div className="field">
              <label>PII в OpenRouter</label>
              <label className="chip">
                <input
                  type="checkbox"
                  checked=${!!settings.openrouter_allow_pii}
                  onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_allow_pii: e.target.checked }))}
                />
                Разрешить отправлять телефоны/email в LLM
              </label>
              <div className="muted">По умолчанию выключено: телефоны и email маскируются перед запросами к OpenRouter.</div>
            </div>
            <div className="field">
              <label>PII в логах</label>
              <label className="chip">
                <input
                  type="checkbox"
                  checked=${!!settings.runtime_log_mask_pii}
                  onChange=${(e) => setSettings((prev) => ({ ...prev, runtime_log_mask_pii: e.target.checked }))}
                />
                Маскировать телефоны/email в runtime-логах
              </label>
              <div className="muted">Оставляйте включённым, чтобы логи можно было безопасно читать на Dashboard и Logs.</div>
            </div>
            <div className="field">
              <label>OpenRouter timeout, секунд</label>
              <input
                className="input"
                type="number"
                min="5"
                max="300"
                step="5"
                value=${settings.openrouter_timeout_sec}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_timeout_sec: e.target.value }))}
              />
              <div className="muted">По умолчанию 300 секунд. Если ответ всё равно не пришёл, в popup остаётся кнопка “Повторить”.</div>
            </div>
          </div>
          <div className="model-list">
            ${modelsLoading ? html`<div className="model-row"><div>Загружаю модели…</div></div>` : null}
            ${!modelsLoading && models.length === 0 ? html`<div className="model-row"><div>Под фильтр модели не нашлись.</div></div>` : null}
            ${!modelsLoading ? models.slice(0, 20).map((model) => html`
              <div className="model-row" key=${model.id}>
                <div>
                  <div><strong>${model.name || model.id}</strong></div>
                  <div className="muted">${model.id}</div>
                </div>
                <div><span className=${`badge ${model.free ? 'badge-green' : 'badge-yellow'}`}>${model.free ? 'free' : 'paid'}</span></div>
                <button
                  type="button"
                  className=${`btn ${settings.openrouter_model === model.id ? 'btn-active' : ''}`}
                  onClick=${() => setSettings((prev) => ({ ...prev, openrouter_model: model.id }))}
                >
                  ${settings.openrouter_model === model.id ? 'Выбрана' : 'Выбрать'}
                </button>
              </div>
            `) : null}
          </div>
        </section>

        ${settings.show_contact_qualification_prompt_settings ? html`<section className=${tabPanelClass('llm')}>
          <div className="section-title">Шаблоны промтов для квалификации контактов</div>
          <div className="section-subtitle">
            Эти шаблоны показываются в popup на странице Контакты. Результаты сохраняются в backend-state и потом используются фильтром “Квалифицированные”.
          </div>
          <div className="model-list">
            ${normalizeContactPrompts(settings.contact_qualification_prompts).map((prompt, index) => html`
              <div className="model-row" key=${prompt.id} style=${{ gridTemplateColumns: '220px 1fr 96px', alignItems: 'start' }}>
                <div className="field">
                  <label>Название</label>
                  <input
                    className="input"
                    type="text"
                    value=${prompt.title}
                    onChange=${(e) => setSettings((prev) => {
                      const prompts = normalizeContactPrompts(prev.contact_qualification_prompts);
                      prompts[index] = { ...prompts[index], title: e.target.value, id: normalizePromptId(prompts[index].id, e.target.value, prompts[index].prompt) };
                      return { ...prev, contact_qualification_prompts: prompts };
                    })}
                  />
                </div>
                <div className="field">
                  <label>Промт</label>
                  <textarea
                    className="input"
                    style=${{ minHeight: '92px', resize: 'vertical' }}
                    value=${prompt.prompt}
                    onChange=${(e) => setSettings((prev) => {
                      const prompts = normalizeContactPrompts(prev.contact_qualification_prompts);
                      prompts[index] = { ...prompts[index], prompt: e.target.value, id: normalizePromptId(prompts[index].id, prompts[index].title, e.target.value) };
                      return { ...prev, contact_qualification_prompts: prompts };
                    })}
                  />
                  <div className="muted">ID: <code>${prompt.id}</code></div>
                </div>
                <button
                  className="btn"
                  type="button"
                  onClick=${() => setSettings((prev) => {
                    const prompts = normalizeContactPrompts(prev.contact_qualification_prompts);
                    if (prompts.length <= 1) return prev;
                    prompts.splice(index, 1);
                    return { ...prev, contact_qualification_prompts: prompts };
                  })}
                  disabled=${normalizeContactPrompts(settings.contact_qualification_prompts).length <= 1}
                >Удалить</button>
              </div>
            `)}
          </div>
          <div className="actions">
            <button
              className="btn"
              type="button"
              onClick=${() => setSettings((prev) => ({
                ...prev,
                contact_qualification_prompts: [
                  ...normalizeContactPrompts(prev.contact_qualification_prompts),
                  {
                    id: normalizePromptId('', 'Новый шаблон', 'Опиши вывод по сообщениям контакта'),
                    title: 'Новый шаблон',
                    prompt: 'Опиши вывод по сообщениям контакта',
                  },
                ],
              }))}
            >Добавить шаблон</button>
          </div>
        </section>` : null}

        <section className=${tabPanelClass('llm')}>
          <div className="section-title">Параметры модели</div>
          <div className="section-subtitle">Эти значения будут использоваться как параметры по умолчанию для запросов к OpenRouter.</div>
          <div className="form-grid">
            <div className="field">
              <label>temperature</label>
              <input className="input" type="number" min="0" max="2" step="0.05" value=${settings.openrouter_temperature}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_temperature: e.target.value }))} />
            </div>
            <div className="field">
              <label>top_p</label>
              <input className="input" type="number" min="0" max="1" step="0.05" value=${settings.openrouter_top_p}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_top_p: e.target.value }))} />
            </div>
            <div className="field">
              <label>max_tokens</label>
              <input className="input" type="number" min="1" max="262144" step="128" value=${settings.openrouter_max_tokens}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_max_tokens: e.target.value }))} />
            </div>
            <div className="field">
              <label>frequency_penalty</label>
              <input className="input" type="number" min="-2" max="2" step="0.05" value=${settings.openrouter_frequency_penalty}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_frequency_penalty: e.target.value }))} />
            </div>
            <div className="field">
              <label>presence_penalty</label>
              <input className="input" type="number" min="-2" max="2" step="0.05" value=${settings.openrouter_presence_penalty}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_presence_penalty: e.target.value }))} />
            </div>
            <div className="field">
              <label>Давность сообщений для дат мероприятий</label>
              <input
                className="input"
                type="number"
                min="1"
                max="3650"
                step="1"
                value=${settings.openrouter_event_date_message_days}
                onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_event_date_message_days: e.target.value }))}
              />
              <div className="muted">OpenRouter получает только сообщения не старше этого количества дней. По умолчанию 30.</div>
            </div>
          </div>
          <div className="actions">
            <button className="btn btn-active" onClick=${saveSettings} disabled=${saving}>${saving ? 'Сохранение…' : 'Сохранить'}</button>
            <span className="muted">Текущая модель: <strong>${settings.openrouter_model}</strong></span>
          </div>
        </section>
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Settings page');
      return;
    }
    ReactDOM.createRoot(rootNode).render(html`<${SettingsPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
