/* React first-start setup wizard */
'use strict';

(function mountSetupWizardPage() {
  if (!window.React || !window.ReactDOM || !window.htm) {
    console.error('[React] Runtime libraries are not loaded for setup wizard');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const API_BASE = window.API_BASE || (window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : `http://${window.location.hostname || '127.0.0.1'}:${window.location.port || '8001'}`);

  const DEFAULT_MODEL = 'openai/gpt-oss-120b:free';

  function defaultOcrServiceUrl() {
    const host = window.location.hostname || '127.0.0.1';
    return `http://${host}:8010`;
  }

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const response = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      let detail = '';
      try {
        const data = await response.json();
        detail = data?.detail ? ` — ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}` : '';
      } catch (_) {
        detail = '';
      }
      throw new Error(`HTTP ${response.status}${detail}`);
    }
    return response.json();
  }

  async function apiPostJson(url, payload, options = {}) {
    if (window.BackfrontApi?.apiPostJson) {
      return window.BackfrontApi.apiPostJson(url, payload, options);
    }
    return apiJson(url, {
      ...options,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      body: JSON.stringify(payload || {}),
    });
  }

  function statusClass(ok, checked) {
    if (ok) return 'ok';
    return checked ? 'bad' : 'warn';
  }

  function StatusItem({ title, description, ok, checked }) {
    const cls = statusClass(ok, checked);
    return html`
      <div className=${`status-item ${cls}`}>
        <div className="check">${ok ? '✓' : checked ? '!' : '…'}</div>
        <div>
          <div style=${{ fontWeight: 800 }}>${title}</div>
          <div className="subtle">${description}</div>
        </div>
      </div>
    `;
  }

  function authCodeDeliveryText(runtime) {
    const delivery = String(runtime?.auth_code_delivery_type || '').toLowerCase();
    const nextType = runtime?.auth_code_next_type || '';
    const timeout = Number(runtime?.auth_code_timeout_sec || 0);
    const backendMessage = String(runtime?.auth_code_message || '').trim();
    if (backendMessage) return backendMessage;
    if (delivery.includes('sms')) return 'Telegram отправил SMS-код.';
    if (delivery.includes('call')) return 'Telegram отправляет код звонком.';
    if (delivery.includes('app')) {
      const suffix = nextType && timeout
        ? ` Следующий способ (${nextType}) можно запросить примерно через ${timeout} сек.`
        : '';
      return `Telegram отправил код в приложение Telegram на этом аккаунте. Проверьте Telegram на телефоне/десктопе.${suffix}`;
    }
    if (runtime?.auth_step === 'code' && !runtime?.auth_code_hash_present) {
      return 'Код был запрошен до перезапуска backend. Запросите код заново.';
    }
    return '';
  }

  function telegramAuthActionMessage(data, fallback) {
    const statusMessage = String(data?.status?.auth_code_message || '').trim();
    if (statusMessage) return statusMessage;
    return data?.message || fallback;
  }

  function SetupWizard() {
    const [settings, setSettings] = React.useState({
      setup_wizard_completed: false,
      telegram_api_id: '',
      telegram_api_hash: '',
      telegram_phone: '',
      telegram_client_backend: 'telethon',
      openrouter_api_key: '',
      openrouter_model: DEFAULT_MODEL,
      ocr_images_enabled: false,
      ocr_service_url: defaultOcrServiceUrl(),
    });
    const [runtime, setRuntime] = React.useState(null);
    const [message, setMessage] = React.useState('');
    const [error, setError] = React.useState('');
    const [busy, setBusy] = React.useState('');
    const [code, setCode] = React.useState('');
    const [password, setPassword] = React.useState('');
    const [openrouterChecked, setOpenrouterChecked] = React.useState(false);
    const [openrouterOk, setOpenrouterOk] = React.useState(false);
    const [telegramApiChecked, setTelegramApiChecked] = React.useState(false);

    async function refreshRuntime() {
      const data = await apiJson(`${API_BASE}/api/payme/runtime-status`);
      setRuntime(data);
      return data;
    }

    async function loadInitial() {
      setError('');
      try {
        const [settingsData, runtimeData] = await Promise.all([
          apiJson(`${API_BASE}/api/payme/settings`),
          apiJson(`${API_BASE}/api/payme/runtime-status`),
        ]);
        setSettings((prev) => ({
          ...prev,
          ...settingsData,
          telegram_api_id: String(settingsData.telegram_api_id || ''),
          telegram_api_hash: String(settingsData.telegram_api_hash || ''),
          telegram_phone: String(settingsData.telegram_phone || ''),
          openrouter_api_key: String(settingsData.openrouter_api_key || ''),
          openrouter_model: String(settingsData.openrouter_model || DEFAULT_MODEL),
          ocr_images_enabled: false,
          ocr_service_url: String(settingsData.ocr_service_url || defaultOcrServiceUrl()),
        }));
        setRuntime(runtimeData);
        setTelegramApiChecked(Boolean(settingsData.telegram_api_configured));
        setMessage('Мастер готов. Заполните поля и проверьте подключения.');
      } catch (err) {
        setError(`Не удалось загрузить мастер: ${err.message}. Попробуйте обновить страницу.`);
      }
    }

    React.useEffect(() => {
      loadInitial();
    }, []);

    async function saveSettings(overrides = {}) {
      const next = { ...settings, ...overrides };
      const payload = {
        ...next,
        telegram_api_id: String(next.telegram_api_id || '').trim(),
        telegram_api_hash: String(next.telegram_api_hash || '').trim(),
        telegram_phone: String(next.telegram_phone || '').trim(),
        openrouter_api_key: String(next.openrouter_api_key || '').trim(),
        openrouter_model: String(next.openrouter_model || DEFAULT_MODEL).trim() || DEFAULT_MODEL,
        ocr_images_enabled: Boolean(next.ocr_images_enabled),
        ocr_service_url: String(next.ocr_service_url || '').trim().replace(/\/+$/g, ''),
      };
      const data = await apiPostJson(`${API_BASE}/api/payme/settings`, payload);
      setSettings((prev) => ({
        ...prev,
        ...data,
        openrouter_api_key: payload.openrouter_api_key,
        telegram_api_hash: payload.telegram_api_hash,
        telegram_phone: payload.telegram_phone,
        ocr_service_url: payload.ocr_service_url,
      }));
      return data;
    }

    async function saveTelegramApi() {
      setBusy('telegram-api');
      setError('');
      try {
        const payload = {
          api_id: String(settings.telegram_api_id || '').trim(),
          api_hash: String(settings.telegram_api_hash || '').trim(),
        };
        const data = await apiPostJson(`${API_BASE}/api/payme/auth/api-credentials`, payload);
        setRuntime(data.status);
        setTelegramApiChecked(true);
        setMessage(data.message || 'Telegram api_id/api_hash сохранены.');
      } catch (err) {
        setTelegramApiChecked(true);
        setError(`Telegram API не проверен: ${err.message}. Проверьте api_id/api_hash, при сетевой ошибке включите VPN и нажмите Повторить.`);
      } finally {
        setBusy('');
      }
    }

    async function requestTelegramCode() {
      setBusy('telegram-phone');
      setError('');
      try {
        await saveSettings({ setup_wizard_completed: false });
        const data = await apiPostJson(`${API_BASE}/api/payme/auth/phone`, {
          phone: String(settings.telegram_phone || '').trim(),
        });
        setRuntime(data.status);
        setMessage(telegramAuthActionMessage(data, 'Код отправлен в Telegram.'));
      } catch (err) {
        setError(`Не удалось отправить код: ${err.message}. Проверьте номер, включите VPN и нажмите Повторить.`);
      } finally {
        setBusy('');
      }
    }

    async function resendTelegramCode(options = {}) {
      const resetSession = Boolean(options.resetSession);
      setBusy(resetSession ? 'telegram-reset-code' : 'telegram-resend');
      setError('');
      try {
        await saveSettings({ setup_wizard_completed: false });
        const data = await apiPostJson(`${API_BASE}/api/payme/auth/phone/resend`, {
          phone: String(settings.telegram_phone || '').trim(),
          force_sms: !resetSession,
          reset_session: resetSession,
        });
        setRuntime(data.status);
        setMessage(telegramAuthActionMessage(data, 'Код запрошен повторно.'));
      } catch (err) {
        setError(`Не удалось запросить код повторно: ${err.message}. Проверьте Telegram, VPN и таймер повторной отправки.`);
      } finally {
        setBusy('');
      }
    }

    async function submitTelegramCode() {
      setBusy('telegram-code');
      setError('');
      try {
        const data = await apiPostJson(`${API_BASE}/api/payme/auth/code`, { code });
        setRuntime(data.status);
        setMessage(data.message || 'Код принят.');
      } catch (err) {
        setError(`Код не принят: ${err.message}. Проверьте код из Telegram и попробуйте ещё раз.`);
      } finally {
        setBusy('');
      }
    }

    async function submitTelegramPassword() {
      setBusy('telegram-password');
      setError('');
      try {
        const data = await apiPostJson(`${API_BASE}/api/payme/auth/password`, { password });
        setRuntime(data.status);
        setMessage(data.message || 'Telegram авторизован.');
      } catch (err) {
        setError(`Пароль 2FA не принят: ${err.message}. Проверьте пароль и попробуйте ещё раз.`);
      } finally {
        setBusy('');
      }
    }

    async function checkOpenRouter() {
      setBusy('openrouter');
      setError('');
      setOpenrouterChecked(false);
      try {
        await saveSettings({ setup_wizard_completed: false });
        const params = new URLSearchParams({ include_paid: 'false', query: settings.openrouter_model || '' });
        const data = await apiJson(`${API_BASE}/api/payme/openrouter/models?${params.toString()}`);
        setOpenrouterChecked(true);
        setOpenrouterOk(data.source === 'openrouter');
        setMessage(data.source === 'openrouter'
          ? 'OpenRouter отвечает, модель можно использовать.'
          : `${data.message || 'OpenRouter не ответил, показан fallback.'} Если нужен LLM-анализ, включите VPN и повторите проверку.`);
      } catch (err) {
        setOpenrouterChecked(true);
        setOpenrouterOk(false);
        setError(`OpenRouter не проверен: ${err.message}. Часто помогает включить VPN и нажать Повторить.`);
      } finally {
        setBusy('');
      }
    }

    async function finishWizard() {
      setBusy('finish');
      setError('');
      try {
        await saveSettings({
          setup_wizard_completed: true,
          ocr_images_enabled: Boolean(settings.ocr_images_enabled),
          ocr_service_url: String(settings.ocr_service_url || defaultOcrServiceUrl()).trim(),
        });
        window.location.href = '/import.html';
      } catch (err) {
        setError(`Не удалось завершить мастер: ${err.message}`);
      } finally {
        setBusy('');
      }
    }

    const telegramApiOk = Boolean(settings.telegram_api_id && settings.telegram_api_hash && runtime?.telegram_api_configured);
    const telegramOk = runtime?.auth_status === 'authorized';
    const telegramNeedsCode = runtime?.auth_step === 'code';
    const telegramNeedsPassword = runtime?.auth_step === 'password';
    const pendingPhone = runtime?.pending_phone || settings.telegram_phone || '';
    const authCodeDelivery = authCodeDeliveryText(runtime);
    const resendTimeout = Number(runtime?.auth_code_timeout_sec || 0);
    const canAskNextDelivery = telegramNeedsCode && !busy && Boolean(pendingPhone);
    const canFinish = telegramApiOk && telegramOk;
    const telegramRuntimeFacts = [
      ['session file', runtime?.session_file_exists ? 'есть' : 'нет'],
      ['authorized', runtime?.telegram_authorized === true ? 'да' : runtime?.telegram_authorized === false ? 'нет' : 'не проверено'],
      ['worker', runtime?.worker_connected ? 'подключён' : 'не активен'],
      ['sync', runtime?.sync_paused ? `пауза${runtime?.sync_pause_reason ? `: ${runtime.sync_pause_reason}` : ''}` : (runtime?.sync_reading ? `читает${runtime?.sync_reading_stage ? `: ${runtime.sync_reading_stage}` : ''}` : 'ожидает')],
    ];

    return html`
      <div className="page">
        <div className="hero">
          <div>
            <div className="title">Стартовый мастер X-Files</div>
            <div className="subtle">
              Заполните клиентские ключи и проверьте подключения. В поставке нет данных разработки: Telegram-сессия, api_id/api_hash и OpenRouter задаются вами при первом запуске.
            </div>
          </div>
          <span className=${`badge ${canFinish ? 'badge-ok' : 'badge-warn'}`}>
            ${canFinish ? 'готово к запуску' : 'первичная настройка'}
          </span>
        </div>

        <div className="layout">
          <aside className="panel">
            <div className="panel-body">
              <div className="section-title">Что проверяется</div>
              <div className="subtle" style=${{ marginBottom: '12px' }}>
                Если соединение не проходит, включите VPN и нажмите “Повторить”.
              </div>
              <div className="status-list">
                <${StatusItem}
                  title="Telegram api_id/api_hash"
                  description=${telegramApiOk ? 'Ключи сохранены и применены.' : 'Нужны ключи из my.telegram.org → API development tools.'}
                  ok=${telegramApiOk}
                  checked=${telegramApiChecked}
                />
                <${StatusItem}
                  title="Авторизация Telegram"
                  description=${runtime?.auth_message || 'Проверяем статус Telegram.'}
                  ok=${telegramOk}
                  checked=${Boolean(runtime)}
                />
                <${StatusItem}
                  title="OpenRouter"
                  description=${openrouterOk ? 'API отвечает.' : 'Можно проверить сейчас или сделать позже в настройках.'}
                  ok=${openrouterOk}
                  checked=${openrouterChecked}
                />
                <${StatusItem}
                  title="OCR изображений"
                  description=${settings.ocr_images_enabled ? `Будет использоваться ${settings.ocr_service_url || defaultOcrServiceUrl()}` : 'По умолчанию выключен в клиентской поставке.'}
                  ok=${!settings.ocr_images_enabled || Boolean(settings.ocr_service_url)}
                  checked=${true}
                />
              </div>
            </div>
          </aside>

          <main className="panel">
            ${message ? html`<div className="section"><div className="notice">${message}</div></div>` : null}
            ${error ? html`
              <div className="section">
                <div className="error">${error}</div>
                <div className="actions">
                  <button className="btn btn-primary" type="button" onClick=${loadInitial}>Повторить</button>
                  <span className="subtle">Рекомендация: если Telegram/OpenRouter не отвечают, включите VPN и повторите проверку.</span>
                </div>
              </div>
            ` : null}

            <section className="section">
              <div className="section-title">1. Telegram API</div>
              <div className="subtle">Получите api_id и api_hash в my.telegram.org → API development tools. В клиентской поставке они не предзаполнены.</div>
              <div className="form-grid">
                <div className="field">
                  <label>Telegram api_id</label>
                  <input className="input" value=${settings.telegram_api_id || ''} inputMode="numeric" placeholder="например 12345678" onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_api_id: e.target.value }))} />
                </div>
                <div className="field">
                  <label>Telegram api_hash</label>
                  <input className="input" value=${settings.telegram_api_hash || ''} type="password" placeholder="api_hash" onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_api_hash: e.target.value }))} />
                </div>
              </div>
              <div className="actions">
                <button className="btn btn-primary" type="button" disabled=${busy === 'telegram-api'} onClick=${saveTelegramApi}>
                  ${busy === 'telegram-api' ? 'Проверяем…' : 'Сохранить и проверить Telegram API'}
                </button>
              </div>
            </section>

            <section className="section">
              <div className="section-title">2. Телефон Telegram</div>
              <div className="subtle">Введите номер в международном формате. Код и пароль 2FA вводятся здесь же, если Telegram их запросит.</div>
              ${telegramNeedsCode && pendingPhone ? html`
                <div className="notice">Код запрошен для номера ${pendingPhone}. Если это не ваш номер, измените телефон и нажмите «Получить код» ещё раз.</div>
              ` : null}
              ${telegramNeedsCode && authCodeDelivery ? html`
                <div className="notice">${authCodeDelivery}</div>
              ` : null}
              <div className="form-grid">
                <div className="field">
                  <label>Мобильный телефон</label>
                  <input className="input" value=${settings.telegram_phone || ''} type="tel" placeholder="+79991234567" onChange=${(e) => setSettings((prev) => ({ ...prev, telegram_phone: e.target.value }))} />
                </div>
                ${telegramNeedsCode ? html`
                  <div className="field">
                    <label>Код из Telegram</label>
                    <input className="input" value=${code} placeholder="12345" onChange=${(e) => setCode(e.target.value)} />
                  </div>
                ` : null}
                ${telegramNeedsPassword ? html`
                  <div className="field">
                    <label>Пароль 2FA</label>
                    <input className="input" type="password" value=${password} placeholder="Пароль двухфакторной защиты" onChange=${(e) => setPassword(e.target.value)} />
                  </div>
                ` : null}
              </div>
              <div className="actions">
                <button className="btn btn-primary" type="button" disabled=${!telegramApiOk || busy === 'telegram-phone'} onClick=${requestTelegramCode}>
                  ${busy === 'telegram-phone' ? 'Отправляем…' : 'Получить код'}
                </button>
                ${telegramNeedsCode ? html`
                  <button className="btn btn-primary" type="button" disabled=${!code || busy === 'telegram-code'} onClick=${submitTelegramCode}>
                    ${busy === 'telegram-code' ? 'Проверяем код…' : 'Отправить код'}
                  </button>
                  <button className="btn" type="button" disabled=${!canAskNextDelivery || busy === 'telegram-resend'} onClick=${() => resendTelegramCode({ resetSession: false })}>
                    ${busy === 'telegram-resend' ? 'Запрашиваем…' : resendTimeout ? 'Запросить SMS/другой способ' : 'Отправить код заново'}
                  </button>
                  <button className="btn" type="button" disabled=${busy === 'telegram-reset-code'} onClick=${() => resendTelegramCode({ resetSession: true })}>
                    ${busy === 'telegram-reset-code' ? 'Сбрасываем…' : 'Сбросить код и запросить заново'}
                  </button>
                ` : null}
                ${telegramNeedsPassword ? html`
                  <button className="btn btn-primary" type="button" disabled=${!password || busy === 'telegram-password'} onClick=${submitTelegramPassword}>
                    ${busy === 'telegram-password' ? 'Проверяем пароль…' : 'Отправить пароль 2FA'}
                  </button>
                ` : null}
                <span className="subtle">Статус: ${runtime?.auth_status || 'ожидаем проверки'}</span>
              </div>
              ${runtime ? html`
                <div className="notice" style=${{ marginTop: '12px' }}>
                  <div style=${{ fontWeight: 800, marginBottom: '8px' }}>Диагностика Telegram runtime</div>
                  <div style=${{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px' }}>
                    ${telegramRuntimeFacts.map(([label, value]) => html`
                      <div style=${{ border: '1px solid #dbe4f0', borderRadius: '12px', padding: '10px', background: '#fff' }}>
                        <div className="subtle">${label}</div>
                        <div style=${{ fontWeight: 800 }}>${value}</div>
                      </div>
                    `)}
                  </div>
                  ${runtime.sync_status_detail ? html`<div className="subtle" style=${{ marginTop: '8px' }}>${runtime.sync_status_detail}</div>` : null}
                </div>
              ` : null}
            </section>

            <section className="section">
              <div className="section-title">3. OpenRouter и OCR</div>
              <div className="subtle">OpenRouter нужен для LLM-анализа. OCR изображений в клиентской поставке выключен по умолчанию.</div>
              <div className="form-grid">
                <div className="field">
                  <label>OpenRouter API key</label>
                  <input className="input" type="password" value=${settings.openrouter_api_key || ''} placeholder="sk-or-..." onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_api_key: e.target.value }))} />
                </div>
                <div className="field">
                  <label>Модель по умолчанию</label>
                  <input className="input" value=${settings.openrouter_model || DEFAULT_MODEL} onChange=${(e) => setSettings((prev) => ({ ...prev, openrouter_model: e.target.value }))} />
                </div>
                <div className="field">
                  <label>OCR service URL</label>
                  <input className="input" value=${settings.ocr_service_url || defaultOcrServiceUrl()} placeholder=${defaultOcrServiceUrl()} onChange=${(e) => setSettings((prev) => ({ ...prev, ocr_service_url: e.target.value }))} />
                </div>
                <label className="field" style=${{ justifyContent: 'end' }}>
                  <span style=${{ display: 'inline-flex', alignItems: 'center', gap: '10px', border: '1px solid #dbe4f0', borderRadius: '13px', padding: '12px', background: '#fff' }}>
                    <input type="checkbox" checked=${!!settings.ocr_images_enabled} onChange=${(e) => setSettings((prev) => ({ ...prev, ocr_images_enabled: e.target.checked }))} />
                    Включить OCR изображений
                  </span>
                </label>
              </div>
              <div className="actions">
                <button className="btn btn-primary" type="button" disabled=${busy === 'openrouter'} onClick=${checkOpenRouter}>
                  ${busy === 'openrouter' ? 'Проверяем…' : 'Проверить OpenRouter'}
                </button>
              </div>
            </section>

            <section className="section">
              <div className="section-title">4. Завершение</div>
              <div className="subtle">После завершения мастер откроет Import, чтобы вы выбрали чаты и каналы для сканирования.</div>
              <div className="actions">
                <button className="btn btn-success" type="button" disabled=${!canFinish || busy === 'finish'} onClick=${finishWizard}>
                  ${busy === 'finish' ? 'Сохраняем…' : 'Завершить настройку и открыть Import'}
                </button>
                ${!canFinish ? html`<span className="subtle">Для продолжения нужен Telegram API и успешная авторизация Telegram.</span>` : null}
              </div>
            </section>
          </main>
        </div>
      </div>
    `;
  }

  ReactDOM.createRoot(document.getElementById('app')).render(html`<${SetupWizard} />`);
})();
