/* Chat analysis panel for React index page */
'use strict';

(function initReactIndexAnalysis() {
  window.BackfrontIndexAnalysis = function BackfrontIndexAnalysis({ React, html, formatEta, DetailPopup, LlmLogNavigator, AnalysisHistoryPager }) {
  function ChatAnalysisPanel({ store }) {
    const [logPopupOpen, setLogPopupOpen] = React.useState(false);
    const [historyPopupOpen, setHistoryPopupOpen] = React.useState(false);
    const [promptPickerOpen, setPromptPickerOpen] = React.useState(false);
    const [promptRows, setPromptRows] = React.useState([]);
    const [promptLoading, setPromptLoading] = React.useState(false);
    if (!store.current) return null;
    const state = store.chatAnalysis || {};
    const stats = state.stats || {};
    const maxMessages = Number(store.maxAnalysisMessages ? store.maxAnalysisMessages() : 0);
    const selectedCount = store.selectedAnalysisMessageIds ? store.selectedAnalysisMessageIds().length : 0;
    const senderRows = Array.isArray(stats.by_sender) ? stats.by_sender.slice(0, 8) : [];
    const history = Array.isArray(state.history) ? state.history : [];
    const isBusy = !!(state.running || state.refreshing);
    const canRun = !isBusy && maxMessages > 0;
    const progressPercent = isBusy
      ? Math.max(8, Math.min(99, Number(state.progressPercent || state.progress_percent || state.progress || 35)))
      : 0;
    const etaText = isBusy
      ? (state.eta_text || state.eta || `лимит ожидания до ${formatEta(state.progressEtaSec || state.timeout_sec || 300)}`)
      : '';
    const progressTitle = state.refreshing ? 'Обновление анализа выполняется' : 'LLM анализ выполняется';
    const progressStatus = state.progressStatus || (state.refreshing ? 'Обновляю локальные данные…' : 'Ожидаем ответ LLM…');
    const openLogPopup = () => setLogPopupOpen(true);
    const openHistoryPopup = () => setHistoryPopupOpen(true);
    const normalizePrompts = window.BackfrontIndexUtils?.normalizeChatAnswerPrompts || ((rows) => Array.isArray(rows) ? rows : []);

    const patchAnalysis = (patch) => {
      store.chatAnalysis = { ...(store.chatAnalysis || {}), ...patch };
      if (typeof store.emit === 'function') store.emit();
    };
    const openPromptPicker = async () => {
      setPromptPickerOpen(true);
      setPromptLoading(true);
      try {
        const response = await fetch('/api/payme/settings', { cache: 'no-store' });
        const settings = response.ok ? await response.json() : {};
        setPromptRows(normalizePrompts(settings?.llm_answer_prompts));
      } catch (_) {
        setPromptRows(normalizePrompts(window.BackfrontIndexUtils?.CHAT_PROMPT_DEFAULTS || []));
      } finally {
        setPromptLoading(false);
      }
    };
    const selectPrompt = (prompt) => {
      if (!prompt) return;
      patchAnalysis({
        prompt: prompt.prompt || state.prompt || '',
        provider: prompt.provider || state.provider || 'openrouter',
        model: prompt.model || state.model || 'openai/gpt-oss-120b:free',
        selectedPromptId: prompt.id || '',
        selectedPromptTitle: prompt.title || '',
      });
      try {
        window.localStorage.setItem(`xfiles.chatAnalysisPrompt.${store.current?.name || 'global'}`, JSON.stringify(prompt));
      } catch (_) {}
      setPromptPickerOpen(false);
    };

    return html`
      <section className="chat-analysis-shell">
        <div className="chat-analysis-header">
          <div className="chat-analysis-heading">
            <div className="chat-analysis-title">Анализ чата</div>
            <div className="chat-analysis-subtitle">
              Сначала считаем объём локально, без LLM. Потом можно выбрать сообщения, промт и модель для анализа через OpenRouter или LM Studio.
            </div>
          </div>
          <button className="btn" type="button" disabled=${isBusy} onClick=${() => store.refreshChatAnalysis?.()}>
            ${state.refreshing ? 'Обновляю…' : 'Обновить анализ'}
          </button>
        </div>

        <div className="chat-analysis-stats">
          <div className="chat-analysis-stat"><span>Сообщений</span><strong>${stats.total_messages ?? '—'}</strong></div>
          <div className="chat-analysis-stat"><span>Токенов всего</span><strong>${stats.total_tokens ?? '—'}</strong></div>
          <div className="chat-analysis-stat"><span>Выбрано</span><strong>${selectedCount}</strong></div>
          <div className="chat-analysis-stat"><span>Максимум X</span><strong>${maxMessages || '—'}</strong></div>
        </div>

        ${senderRows.length ? html`
          <div className="chat-analysis-senders">
            <table className="analysis-table">
              <thead>
                <tr><th>Пользователь</th><th>Сообщений</th><th>Токенов</th></tr>
              </thead>
              <tbody>
                ${senderRows.map((sender) => html`
                  <tr key=${sender.sender_key}>
                    <td>
                      <strong>${sender.sender_name || sender.sender_username || sender.sender_key}</strong>
                      <div className="muted">${sender.sender_username ? `@${sender.sender_username}` : sender.sender_key}</div>
                    </td>
                    <td>${sender.messages_count}</td>
                    <td>${sender.tokens}</td>
                  </tr>
                `)}
              </tbody>
            </table>
          </div>
        ` : html`<div className="chat-analysis-empty">Статистика по пользователям появится после загрузки сообщений.</div>`}

        <div className="chat-analysis-form">
          <label className="analysis-field">
            <span>LLM-провайдер</span>
            <select className="analysis-select" value=${state.provider || 'openrouter'} onChange=${(e) => patchAnalysis({ provider: e.target.value })}>
              <option value="openrouter">OpenRouter</option>
              <option value="local">Local LLM / LM Studio</option>
            </select>
          </label>
          <label className="analysis-field">
            <span>Модель</span>
            <select
              className="analysis-select"
              value=${state.model || 'openai/gpt-oss-120b:free'}
              onChange=${(e) => patchAnalysis({ model: e.target.value })}
            >
              <option value="openai/gpt-oss-120b:free">OpenRouter free · gpt-oss-120b</option>
              <option value="openai/gpt-5-chat">OpenRouter paid · gpt-5-chat</option>
              <option value="local-model">LM Studio · local-model</option>
            </select>
          </label>
          <label className="analysis-field">
            <span>Что анализировать</span>
            <select className="analysis-select" value=${state.mode || 'last_messages'} onChange=${(e) => patchAnalysis({ mode: e.target.value })}>
              <option value="last_messages">Последние X сообщений</option>
              <option value="token_budget">До Y токенов от последних</option>
              <option value="selected">Только выбранные сообщения</option>
              <option value="all">Все сообщения</option>
            </select>
          </label>
          <label className="analysis-field">
            <span>X сообщений</span>
            <input
              className="analysis-input"
              type="number"
              min="1"
              value=${state.messageLimit || 10}
              onChange=${(e) => patchAnalysis({ messageLimit: Number(e.target.value || 10) })}
            />
          </label>
          <label className="analysis-field">
            <span>Y токенов</span>
            <input
              className="analysis-input"
              type="number"
              min="100"
              step="500"
              value=${state.tokenBudget || 4000}
              onChange=${(e) => patchAnalysis({ tokenBudget: Number(e.target.value || 4000) })}
            />
          </label>
        </div>

        <label className="analysis-field analysis-field--wide">
          <span className="row" style=${{ alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
            <span>Промт анализа${state.selectedPromptTitle ? ` · ${state.selectedPromptTitle}` : ''}</span>
            <button className="btn btn-compact" type="button" disabled=${isBusy} onClick=${openPromptPicker}>Выбрать из Промты</button>
          </span>
          <textarea
            className="analysis-textarea"
            rows="4"
            value=${state.prompt || ''}
            onChange=${(e) => patchAnalysis({ prompt: e.target.value })}
          />
        </label>

        <div className="analysis-actions">
          <button className="btn btn-active" type="button" disabled=${!canRun} onClick=${() => store.runChatAnalysis()}>
            ${state.running ? 'Ожидаем ответ LLM…' : 'Запустить анализ'}
          </button>
          ${state.lastPayload ? html`
            <button className="btn" type="button" disabled=${isBusy} onClick=${() => store.runChatAnalysis(state.lastPayload)}>
              Повторить
            </button>
          ` : null}
          <button className="btn" type="button" onClick=${openLogPopup}>Открыть лог LLM</button>
          <span className="muted">Лимит ожидания OpenRouter до 300 секунд. Это safety-timeout, а не прогноз скорости ответа.</span>
        </div>

        ${isBusy ? html`
          <div className="analysis-progress">
            <div className="row">
              <strong>${progressTitle}</strong>
              <span className="muted">${Math.round(progressPercent)}% · ${etaText}</span>
            </div>
            <div className="muted" style=${{ marginTop: '6px' }}>${progressStatus}</div>
            <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${progressPercent}%` }}></div></div>
          </div>
        ` : null}

        ${state.error ? html`<div className="analysis-error">${state.error}</div>` : null}

        <div className="analysis-history">
          <div className="row" style=${{ alignItems: 'center', marginTop: '18px' }}>
            <div className="chat-analysis-title chat-analysis-title-small">История анализа</div>
            <button className="btn btn-compact" type="button" onClick=${openHistoryPopup}>Открыть на 80%</button>
          </div>
          <${AnalysisHistoryPager} store=${store} state=${state} history=${history} compact=${true} />
        </div>
        <${DetailPopup}
          open=${logPopupOpen}
          title="Лог LLM"
          subtitle=${store.current ? `Чат: ${store.current.name}` : ''}
          onClose=${() => setLogPopupOpen(false)}
          body=${html`<${LlmLogNavigator} state=${state} rows=${state.progressLog || []} scope="chat-analysis" />`}
        />
        <${DetailPopup}
          open=${historyPopupOpen}
          title="История анализа"
          subtitle=${store.current ? `Чат: ${store.current.name}` : ''}
          onClose=${() => setHistoryPopupOpen(false)}
          body=${html`<${AnalysisHistoryPager} store=${store} state=${state} history=${history} />`}
        />
        <${DetailPopup}
          open=${promptPickerOpen}
          title="Выберите промт"
          subtitle="База промтов из раздела Промты"
          onClose=${() => setPromptPickerOpen(false)}
          body=${html`
            <div className="prompt-picker-list">
              ${promptLoading ? html`<div className="chat-analysis-empty">Загружаю промты…</div>` : null}
              ${!promptLoading && !promptRows.length ? html`<div className="chat-analysis-empty">Промты не найдены.</div>` : null}
              ${promptRows.map((prompt) => html`
                <article className="prompt-picker-item" key=${prompt.id}>
                  <div className="prompt-picker-item-head">
                    <div>
                      <strong>${prompt.title}</strong>
                      <div className="muted">${prompt.provider || 'openrouter'} · ${prompt.model || 'model по умолчанию'}</div>
                    </div>
                    <button
                      className=${`btn ${state.selectedPromptId === prompt.id ? 'btn-active' : ''}`}
                      type="button"
                      onClick=${() => selectPrompt(prompt)}
                    >
                      ${state.selectedPromptId === prompt.id ? 'Выбран' : 'Выбрать'}
                    </button>
                  </div>
                  <div className="prompt-picker-body">${prompt.prompt}</div>
                </article>
              `)}
            </div>
          `}
        />
      </section>
    `;
  }

  function openChatAnalysisModal(store) {
    store.ui = store.ui || {};
    store.ui.analysisModalOpen = true;
    if (typeof store.emit === 'function') store.emit();
    Promise.allSettled([
      store.loadChatAnalysisStats?.(),
      store.loadChatAnalysisHistory?.(),
    ]).finally(() => {
      if (typeof store.emit === 'function') store.emit();
    });
  }

  function closeChatAnalysisModal(store) {
    store.ui = store.ui || {};
    store.ui.analysisModalOpen = false;
    if (typeof store.emit === 'function') store.emit();
  }

  function ChatAnalysisModal({ store }) {
    if (!store.current || !store.ui?.analysisModalOpen) return null;
    return html`
      <div className="chat-analysis-modal-backdrop" role="presentation" onClick=${() => closeChatAnalysisModal(store)}>
        <div
          className="chat-analysis-modal"
          role="dialog"
          aria-modal="true"
          aria-label="Анализ чата"
          onClick=${(event) => event.stopPropagation()}
        >
          <div className="chat-analysis-modal-head">
            <div>
              <div className="chat-analysis-title">Анализ чата: ${store.current.name}</div>
              <div className="chat-analysis-subtitle">
                Локальная статистика, выбор сообщений, промт и запуск LLM-анализа в отдельном рабочем окне.
              </div>
            </div>
            <button className="btn" type="button" onClick=${() => closeChatAnalysisModal(store)}>
              Закрыть
            </button>
          </div>
          <div className="chat-analysis-modal-body">
            <${ChatAnalysisPanel} store=${store} />
          </div>
        </div>
      </div>
    `;
  }


    return {
      ChatAnalysisPanel,
      ChatAnalysisModal,
      openChatAnalysisModal,
      closeChatAnalysisModal,
    };
  };
})();
