/* Presentational components for react.index.js legacy entrypoint */
'use strict';

(function initReactIndexComponents() {
  window.BackfrontIndexComponents = function BackfrontIndexComponents(deps) {
    const { html, OutreachToggle } = deps;

    function onEnter(handler) {
      return (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          handler();
        }
      };
    }

    function ErrorPanel({ error }) {
      if (!error) return null;
      return html`
        <div className="px-4 pb-3 w-full">
          <div className="card" style=${{ borderColor: '#fecaca', background: '#fef2f2' }}>
            <div className="font-semibold" style=${{ color: '#991b1b' }}>Ошибка</div>
            <div className="text-sm">${error}</div>
          </div>
        </div>
      `;
    }

    function AuthBanner({ store }) {
      if (!store.authBannerVisible()) return null;
      const step = store.authStep();

      return html`
        <section className="auth-banner">
          <div className="auth-grid">
            <div>
              <div className="row" style=${{ justifyContent: 'flex-start', marginBottom: '8px' }}>
                <div className="auth-title">Авторизация Telegram</div>
                <span className=${`badge ${store.authBadgeClass()}`}>${store.authStatus?.auth_status || 'unknown'}</span>
              </div>
              <div className="text-sm">${store.authStatus?.auth_message || 'Проверяем статус Telegram…'}</div>
              ${store.authStatus?.last_error ? html`<div className="muted" style=${{ marginTop: '8px', color: '#b91c1c' }}>${store.authStatus.last_error}</div>` : null}
              ${store.authStatus?.auth_status === 'authorized'
                ? html`<div className="muted" style=${{ marginTop: '8px' }}>Веб-авторизация уже завершена, можно работать с каналами и чатами.</div>`
                : null}
              ${store.authStatus?.auth_status === 'session_present'
                ? html`<div className="muted" style=${{ marginTop: '8px' }}>Если сохранённая Telegram-сессия ещё валидна, она применится автоматически. Поля телефона и кода не нужны, пока система сама не попросит повторную авторизацию.</div>`
                : null}
              ${store.authNeedsUi()
                ? html`
                  <div className="muted" style=${{ marginTop: '8px' }}>
                    ${step === 'api'
                      ? 'Сначала сохраните api_id и api_hash из my.telegram.org → API development tools. После этого появится обычная авторизация по телефону.'
                      : 'Вместо консоли Docker используйте форму справа: номер телефона, затем код из Telegram и пароль 2FA только если его запросит Telegram.'}
                  </div>
                `
                : null}
            </div>

            ${store.authNeedsUi() ? html`
              <div>
                ${step === 'api' ? html`
                  <div>
                    <input
                      className="auth-input"
                      type="text"
                      inputMode="numeric"
                      value=${store.authForm.apiId}
                      placeholder="Telegram api_id"
                      onChange=${(e) => { store.authForm.apiId = e.target.value; }}
                      onKeyDown=${onEnter(() => store.submitApiCredentials())}
                    />
                    <input
                      className="auth-input"
                      type="password"
                      value=${store.authForm.apiHash}
                      placeholder="Telegram api_hash"
                      style=${{ marginTop: '10px' }}
                      onChange=${(e) => { store.authForm.apiHash = e.target.value; }}
                      onKeyDown=${onEnter(() => store.submitApiCredentials())}
                    />
                    <div className="auth-actions" style=${{ marginTop: '10px' }}>
                      <button className="btn" onClick=${() => store.submitApiCredentials()} disabled=${store.authLoading}>
                        <span>${store.authLoading ? 'Сохранение…' : 'Сохранить ключи'}</span>
                      </button>
                    </div>
                  </div>
                ` : null}

                ${step === 'phone' ? html`
                  <div>
                    <input
                      className="auth-input"
                      type="text"
                      value=${store.authForm.phone}
                      placeholder="+79991234567"
                      onChange=${(e) => { store.authForm.phone = e.target.value; }}
                      onKeyDown=${onEnter(() => store.submitPhoneAuth())}
                    />
                    <div className="auth-actions" style=${{ marginTop: '10px' }}>
                      <button className="btn" onClick=${() => store.submitPhoneAuth()} disabled=${store.authLoading}>
                        <span>${store.authLoading ? 'Отправка…' : 'Получить код'}</span>
                      </button>
                    </div>
                  </div>
                ` : null}

                ${step === 'code' ? html`
                  <div>
                    <input
                      className="auth-input"
                      type="text"
                      value=${store.authForm.code}
                      placeholder="Код из Telegram"
                      onChange=${(e) => { store.authForm.code = e.target.value; }}
                      onKeyDown=${onEnter(() => store.submitCodeAuth())}
                    />
                    <div className="auth-actions" style=${{ marginTop: '10px' }}>
                      <button className="btn" onClick=${() => store.submitCodeAuth()} disabled=${store.authLoading}>
                        <span>${store.authLoading ? 'Проверка…' : 'Подтвердить код'}</span>
                      </button>
                      <button className="btn" onClick=${() => store.submitPhoneAuth()} disabled=${store.authLoading}>Отправить код заново</button>
                    </div>
                  </div>
                ` : null}

                ${step === 'password' ? html`
                  <div>
                    <input
                      className="auth-input"
                      type="password"
                      value=${store.authForm.password}
                      placeholder="Пароль двухфакторной защиты"
                      onChange=${(e) => { store.authForm.password = e.target.value; }}
                      onKeyDown=${onEnter(() => store.submitPasswordAuth())}
                    />
                    <div className="auth-actions" style=${{ marginTop: '10px' }}>
                      <button className="btn" onClick=${() => store.submitPasswordAuth()} disabled=${store.authLoading}>
                        <span>${store.authLoading ? 'Проверка…' : 'Подтвердить пароль'}</span>
                      </button>
                    </div>
                  </div>
                ` : null}
              </div>
            ` : null}
          </div>
        </section>
      `;
    }

    function LeadRow({ store, lead }) {
      const isActive = store.current?.name === lead.name;
      const isFresh = store.leadHasFreshActivity(lead);
      const statusClass = store.leadStatusClass ? store.leadStatusClass(lead) : (!lead.in_source
        ? 'badge-archived'
        : (lead.sync_status === 'pending' ? 'badge-pending' : 'badge-active'));

      return html`
        <div className=${`lead-row ${isActive ? 'lead-row-active' : ''} ${isFresh ? 'lead-row-fresh' : ''}`}>
          <button
            className="lead-item"
            onClick=${() => store.openLead(lead)}
          >
            <div className="lead-head">
              <div>
                <div className="lead-title">${lead.name}</div>
                <div className="lead-meta-line">
                <span className=${`badge ${statusClass}`}>${store.leadStatusText(lead)}</span>
                  <span className="muted">${window.fmtDate ? window.fmtDate(lead.last_date_utc) : (lead.last_date_utc || '')}</span>
                </div>
              </div>
              <div className="lead-count">
                ${store.leadDeltaText(lead) ? html`<span className="lead-delta">${store.leadDeltaText(lead)}</span>` : null}
                <div className="muted">${lead.count} сооб.</div>
              </div>
            </div>
            <div className="lead-preview text-sm">${store.leadPreview(lead)}</div>
          </button>
          <div className="lead-actions">
            ${store.canActivateLead(lead) ? html`
              <button
                className="btn lead-side-btn"
                type="button"
                onClick=${() => store.activateLead(lead)}
                disabled=${store.isLeadActionBusy(lead, 'activate')}
                title="Включить Telegram-сканирование снова"
              >
                <span>${store.isLeadActionBusy(lead, 'activate') ? '…' : 'Включить сканирование'}</span>
              </button>
            ` : null}
          </div>
        </div>
      `;
    }

    function MessageBubble({ store, message }) {
      const senderLabel = message.sender_username
        ? `@${message.sender_username}`
        : (message.sender_name || message.role);
      const text = String(message.text || '').trim();
      const bodyText = text
        ? message.text
        : (message.has_media
          ? (message.media_path ? '[media]' : '[media без текста · файл не сохранён]')
          : '[пустое сообщение]');
      const payload = {
        field_type: 'message',
        field_label: 'Сообщение',
        value: String(bodyText || '').trim(),
        lead: store.current?.name || '',
        source_selector: store.current?.source_selector || store.current?.name || '',
        sender_name: message.sender_name,
        sender_username: message.sender_username,
        message_id: message.id,
        date_utc: message.date_utc,
        text: bodyText,
      };

      return html`
        <div className=${`bubble ${message.role === 'assistant' ? 'bubble-assistant' : 'bubble-user'}`}>
          <div className="row">
            <div className="muted">${window.fmtDate ? window.fmtDate(message.date_utc) : (message.date_utc || '')}</div>
            <div className="muted" style=${{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
              <span>${senderLabel}</span>
              ${message.optimistic ? html`
                <span className=${`message-send-status ${message.send_status === 'failed' ? 'is-failed' : ''}`}>
                  ${message.send_status === 'failed' ? 'не отправлено' : (message.send_status === 'sent' ? 'отправлено' : (message.send_status === 'checking' ? 'проверяем доставку…' : 'отправляется…'))}
                </span>
              ` : null}
              <label className="chip" title="Выбрать сообщение для LLM-анализа чата">
                <input
                  type="checkbox"
                  checked=${store.isMessageSelectedForAnalysis(message)}
                  onChange=${() => store.toggleAnalysisMessage(message)}
                />
                анализ
              </label>
            </div>
          </div>
          <div className="text-sm" style=${{ whiteSpace: 'pre-wrap' }}>${bodyText}</div>
          ${message.reply_to_msg_id ? html`<div className="muted">↩ reply_to: <span>${message.reply_to_msg_id}</span></div>` : null}
        </div>
      `;
    }

    return { onEnter, ErrorPanel, AuthBanner, LeadRow, MessageBubble };
  };
})();
