/* History, prompt and paging helpers for react.index.js legacy entrypoint */
'use strict';

(function initReactIndexHistory() {
  window.BackfrontIndexHistory = function BackfrontIndexHistory(deps) {
    const {
      React,
      html,
      DetailPopup,
      AnalysisFormattedText,
      logFileHref,
      formatEta,
      normalizeChatAnswerPrompts,
      CHAT_PROMPT_DEFAULTS,
    } = deps;

  function RecommendationHistoryTable({ store, state, history, rows, onOpenDetail, onRepeatRequest }) {
    const sourceRows = Array.isArray(rows) ? rows : (Array.isArray(history) ? history : []);
    if (!sourceRows.length) {
      return html`<div className="chat-analysis-empty">Истории пока нет. Выберите пользователя и нажмите “рекомендация”.</div>`;
    }
    return html`
      <table className="chat-analysis-history-table">
        <thead>
          <tr><th>Кому</th><th>Контекст</th><th>Результат</th><th>Действия</th></tr>
        </thead>
        <tbody>
          ${sourceRows.map((item) => html`
            <tr key=${item.analysis_id}>
              <td>
                <strong>${item.sender_name || item.sender_key || 'Чат целиком'}</strong>
                <div className="muted">${item.provider} · ${item.model}</div>
                <a className="muted" href=${logFileHref({ message: item.result || item.error || '', details: item, kind: item.error ? 'error' : 'response', ts: item.finished_at || item.created_at }, 0, 'recommendation-history')} download=${`recommendation-${item.analysis_id || 'log'}.log`} target="_blank" rel="noreferrer">log файл</a>
              </td>
              <td>
                <div>${item.messages_count || 0} сообщ.</div>
                <div className="muted">${item.tokens_estimate || 0} токенов</div>
              </td>
              <td>
                ${item.error ? html`<div className="analysis-error">${item.error}</div>` : null}
                ${item.result ? html`<div className="analysis-result-compact"><${AnalysisFormattedText} text=${item.result} /></div>` : null}
              </td>
              <td>
                <button className="btn" type="button" onClick=${() => onOpenDetail?.(item)}>Детально</button>
                <button className="btn" type="button" onClick=${() => store.copyChatAnalysisToComposer?.(item.result || '')}>Скопировать</button>
                <button className="btn" type="button" disabled=${state.running} onClick=${() => onRepeatRequest?.(item)}>Повторить</button>
              </td>
            </tr>
          `)}
        </tbody>
      </table>
    `;
  }

  function ChatHistoryPager({ store, state, history, popup = false }) {
    const [page, setPage] = React.useState(1);
    const [pageSize, setPageSize] = React.useState(2);
    const [detailItem, setDetailItem] = React.useState(null);
    const [repeatItem, setRepeatItem] = React.useState(null);
    const rows = Array.isArray(history) ? history : [];
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const visibleRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
    React.useEffect(() => { setPage(1); }, [rows.length, pageSize]);
    return html`
      <div className=${popup ? 'analysis-history-scroll' : ''}>
        <div className="history-pager-head">
          <div className="muted">Показано ${rows.length ? `${(safePage - 1) * pageSize + 1}-${Math.min(rows.length, safePage * pageSize)} из ${rows.length}` : '0 из 0'}</div>
          <div className="row" style=${{ gap: '6px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <select className="btn btn-compact" value=${String(pageSize)} onChange=${(e) => setPageSize(Number(e.target.value) || 2)}>
              <option value="2">2 строки</option>
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
            </select>
            <button className="btn btn-compact" type="button" disabled=${safePage <= 1} onClick=${() => setPage((value) => Math.max(1, value - 1))}>Назад</button>
            <span className="chip">${safePage} / ${totalPages}</span>
            <button className="btn btn-compact" type="button" disabled=${safePage >= totalPages} onClick=${() => setPage((value) => Math.min(totalPages, value + 1))}>Вперёд</button>
          </div>
        </div>
        <${RecommendationHistoryTable} store=${store} state=${state} rows=${visibleRows} onOpenDetail=${setDetailItem} onRepeatRequest=${setRepeatItem} />
        <${DetailPopup}
          open=${!!detailItem}
          title="Детали рекомендации"
          subtitle=${detailItem ? `${detailItem.sender_name || detailItem.sender_key || 'Чат'} · ${detailItem.provider || ''} · ${detailItem.model || ''}` : ''}
          onClose=${() => setDetailItem(null)}
          body=${detailItem ? html`
            <div className="detail-popup-stack">
              <a className="btn" href=${logFileHref({ message: detailItem.result || detailItem.error || '', details: detailItem, kind: detailItem.error ? 'error' : 'response', ts: detailItem.finished_at || detailItem.created_at }, 0, 'recommendation-detail')} download=${`recommendation-${detailItem.analysis_id || 'detail'}.log`} target="_blank" rel="noreferrer">Открыть log файл</a>
              ${detailItem.error ? html`<div className="analysis-error">${detailItem.error}</div>` : null}
              <article className="analysis-history-card"><${AnalysisFormattedText} text=${detailItem.result || ''} /></article>
            </div>
          ` : null}
        />
        <${RepeatRequestModal}
          open=${!!repeatItem}
          item=${repeatItem}
          state=${state}
          onClose=${() => setRepeatItem(null)}
          onRun=${(draft) => store.repeatChatAnalysis?.(draft)}
        />
      </div>
    `;
  }

  function AnalysisHistoryPager({ store, state, history, compact = false }) {
    const [page, setPage] = React.useState(1);
    const [pageSize, setPageSize] = React.useState(2);
    const [detailItem, setDetailItem] = React.useState(null);
    const [repeatItem, setRepeatItem] = React.useState(null);
    const rows = Array.isArray(history) ? history : [];
    const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
    const safePage = Math.min(Math.max(1, page), totalPages);
    const visibleRows = rows.slice((safePage - 1) * pageSize, safePage * pageSize);
    React.useEffect(() => { setPage(1); }, [rows.length, pageSize]);
    if (!rows.length) {
      return html`<div className="chat-analysis-empty">Истории пока нет. Запустите первый анализ.</div>`;
    }
    return html`
      <div className="analysis-history-scroll">
        <div className="history-pager-head">
          <div className="muted">Показано ${(safePage - 1) * pageSize + 1}-${Math.min(rows.length, safePage * pageSize)} из ${rows.length}</div>
          <div className="row" style=${{ gap: '6px', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <select className="btn btn-compact" value=${String(pageSize)} onChange=${(e) => setPageSize(Number(e.target.value) || 2)}>
              <option value="2">2 записи</option>
              <option value="5">5 записей</option>
              <option value="10">10 записей</option>
            </select>
            <button className="btn btn-compact" type="button" disabled=${safePage <= 1} onClick=${() => setPage((value) => Math.max(1, value - 1))}>Назад</button>
            <span className="chip">${safePage} / ${totalPages}</span>
            <button className="btn btn-compact" type="button" disabled=${safePage >= totalPages} onClick=${() => setPage((value) => Math.min(totalPages, value + 1))}>Вперёд</button>
          </div>
        </div>
        <div className="analysis-history-list">
          ${visibleRows.map((item) => html`
            <article className="analysis-history-card" key=${item.analysis_id}>
              <div className="row">
                <div>
                  <strong>${item.mode}</strong>
                  <span className="muted"> · ${item.provider} · ${item.model} · сообщений: ${item.messages_count} · токенов: ${item.tokens_estimate}</span>
                  <div><a className="muted" href=${logFileHref({ message: item.result || item.error || '', details: item, kind: item.error ? 'error' : 'response', ts: item.finished_at || item.created_at }, 0, 'analysis-history')} download=${`analysis-${item.analysis_id || 'log'}.log`} target="_blank" rel="noreferrer">log файл</a></div>
                </div>
                <div className="row" style=${{ justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                  <button className="btn" type="button" onClick=${() => setDetailItem(item)}>Детально</button>
                  <button className="btn" type="button" disabled=${state.running} onClick=${() => setRepeatItem(item)}>Повторить</button>
                </div>
              </div>
              <div className="muted">${item.finished_at || item.created_at}</div>
              ${item.error ? html`<div className="analysis-error">${item.error}</div>` : null}
              ${item.result && !compact ? html`<${AnalysisFormattedText} text=${item.result} />` : null}
            </article>
          `)}
        </div>
        <${DetailPopup}
          open=${!!detailItem}
          title="Детали анализа"
          subtitle=${detailItem ? `${detailItem.mode || ''} · ${detailItem.provider || ''} · ${detailItem.model || ''}` : ''}
          onClose=${() => setDetailItem(null)}
          body=${detailItem ? html`
            <div className="detail-popup-stack">
              <a className="btn" href=${logFileHref({ message: detailItem.result || detailItem.error || '', details: detailItem, kind: detailItem.error ? 'error' : 'response', ts: detailItem.finished_at || detailItem.created_at }, 0, 'analysis-detail')} download=${`analysis-${detailItem.analysis_id || 'detail'}.log`} target="_blank" rel="noreferrer">Открыть log файл</a>
              ${detailItem.error ? html`<div className="analysis-error">${detailItem.error}</div>` : null}
              <article className="analysis-history-card"><${AnalysisFormattedText} text=${detailItem.result || ''} /></article>
            </div>
          ` : null}
        />
        <${RepeatRequestModal}
          open=${!!repeatItem}
          item=${repeatItem}
          state=${state}
          onClose=${() => setRepeatItem(null)}
          onRun=${(draft) => store.repeatChatAnalysis?.(draft)}
        />
      </div>
    `;
  }

  function RepeatRequestModal({ open, item, state, onClose, onRun }) {
    const [draft, setDraft] = React.useState(() => ({ ...(item || {}) }));
    React.useEffect(() => {
      if (open) setDraft({ ...(item || {}) });
    }, [open, item]);
    if (!open || !item) return null;

    const running = !!state?.running;
    const percent = running ? Math.max(4, Math.min(99, Number(state?.progressPercent || 10))) : 0;
    const update = (patch) => setDraft((current) => ({ ...current, ...patch }));
    const submit = () => onRun?.({
      ...item,
      ...draft,
      message_limit: Math.max(1, Number(draft.message_limit || draft.messages_count || 10)),
      token_budget: Math.max(100, Number(draft.token_budget || 4000)),
      prompt: String(draft.prompt || '').trim(),
      provider: String(draft.provider || 'openrouter').trim(),
      model: String(draft.model || '').trim(),
    });

    return html`
      <${DetailPopup}
        open=${open}
        title="Повторить запрос"
        subtitle=${`${item.sender_name || item.sender_key || 'Чат'} · можно изменить промт и параметры`}
        onClose=${onClose}
        body=${html`
          <div className="detail-popup-stack repeat-request-modal">
            ${running ? html`
              <div className="analysis-progress">
                <div className="row">
                  <strong>Повторный запрос выполняется</strong>
                  <span className="muted">${Math.round(percent)}% · ETA ${formatEta(state?.progressEtaSec || 0)}</span>
                </div>
                <div className="muted" style=${{ marginTop: '6px' }}>${state?.progressStatus || 'Ожидаю ответ LLM…'}</div>
                <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${percent}%` }}></div></div>
              </div>
            ` : null}
            <div className="repeat-request-card">
              <div className="repeat-request-card-title">Параметры запроса</div>
              <div className="prompt-edit-grid">
              <label>
                <span className="muted">Режим</span>
                <select className="input" value=${draft.mode || 'last_messages'} onChange=${(event) => update({ mode: event.target.value })}>
                  <option value="last_messages">Последние сообщения</option>
                  <option value="all">Все сообщения / пользователь</option>
                  <option value="selected">Выбранные сообщения</option>
                </select>
              </label>
              <label>
                <span className="muted">X сообщений</span>
                <input className="input" type="number" min="1" value=${draft.message_limit || draft.messages_count || 10} onChange=${(event) => update({ message_limit: event.target.value })} />
              </label>
              <label>
                <span className="muted">Y токенов</span>
                <input className="input" type="number" min="100" value=${draft.token_budget || 4000} onChange=${(event) => update({ token_budget: event.target.value })} />
              </label>
              <label>
                <span className="muted">Провайдер</span>
                <select className="input" value=${draft.provider || 'openrouter'} onChange=${(event) => update({ provider: event.target.value })}>
                  <option value="openrouter">OpenRouter</option>
                  <option value="local">LM Studio</option>
                </select>
              </label>
              <label>
                <span className="muted">Модель</span>
                <input className="input" value=${draft.model || ''} onChange=${(event) => update({ model: event.target.value })} />
              </label>
              </div>
            </div>
            <label className="repeat-request-card repeat-request-prompt-field">
              <div className="repeat-request-label-row">
                <span className="repeat-request-card-title" style=${{ marginBottom: 0 }}>Запрос / промт</span>
                <span className="muted">${String(draft.prompt || '').length} символов</span>
              </div>
              <textarea
                className="input repeat-request-textarea"
                value=${draft.prompt || ''}
                placeholder="Отредактируйте промт перед повторным запуском LLM..."
                onChange=${(event) => update({ prompt: event.target.value })}
              ></textarea>
            </label>
            <div className="repeat-request-actions">
              <button className="btn btn-active" type="button" disabled=${running} onClick=${submit}>
                ${running ? 'Ожидаю LLM…' : 'Повторить в LLM'}
              </button>
              <button className="btn" type="button" onClick=${onClose}>Закрыть</button>
            </div>
          </div>
        `}
      />
    `;
  }

  function PromptPickerModal({ open, prompts, sender, selected, onClose, onSelect, onManagePrompts }) {
    if (!open || !sender) return null;
    const rows = normalizeChatAnswerPrompts(prompts);
    return html`
      <div className="prompt-picker-modal-backdrop" role="presentation" onClick=${onClose}>
        <div className="prompt-picker-modal" role="dialog" aria-modal="true" onClick=${(event) => event.stopPropagation()}>
          <div className="row" style=${{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h2>Выберите промт</h2>
              <div className="muted">${sender.sender_name || sender.sender_username || sender.sender_key}</div>
            </div>
            <div className="row" style=${{ gap: '8px', justifyContent: 'flex-end' }}>
              <button className="btn" type="button" onClick=${onManagePrompts}>Промты</button>
              <button className="btn" type="button" onClick=${onClose}>Закрыть</button>
            </div>
          </div>
          <div className="prompt-picker-list">
            ${rows.map((prompt) => html`
              <article className="prompt-picker-item" key=${prompt.id}>
                <div className="prompt-picker-item-head">
                  <div>
                    <strong>${prompt.title}</strong>
                    <div className="muted">${prompt.provider || 'openrouter'} · ${prompt.model || 'model по умолчанию'}</div>
                  </div>
                  <button
                    className=${`btn ${selected?.id === prompt.id ? 'btn-active' : ''}`}
                    type="button"
                    onClick=${() => onSelect(prompt)}
                  >
                    ${selected?.id === prompt.id ? 'Выбран' : 'Выбрать'}
                  </button>
                </div>
                <div className="prompt-picker-body">${prompt.prompt}</div>
              </article>
            `)}
          </div>
        </div>
      </div>
    `;
  }

  function chatPromptHistoryKey(chatName) {
    return `xfiles.llmAnswerHistory.${chatName || 'global'}`;
  }

  function readPromptHistory(chatName) {
    try {
      const raw = localStorage.getItem(chatPromptHistoryKey(chatName));
      const parsed = JSON.parse(raw || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      return [];
    }
  }

  function writePromptHistory(chatName, items) {
    try {
      localStorage.setItem(chatPromptHistoryKey(chatName), JSON.stringify((items || []).slice(0, 50)));
    } catch (_) {}
  }

  const CHAT_PANEL_LAYOUT_KEY = 'xfiles.chatPanelLayout.v1';

  function readChatPanelLayout() {
    try {
      const parsed = JSON.parse(localStorage.getItem(CHAT_PANEL_LAYOUT_KEY) || '{}');
      const main = Number(parsed.main || 0);
      const ai = Number(parsed.ai || 0);
      if (main >= 360 && ai >= 300) return { main, ai };
    } catch (_) {}
    return { main: 0, ai: 0 };
  }

  function writeChatPanelLayout(layout) {
    try {
      localStorage.setItem(CHAT_PANEL_LAYOUT_KEY, JSON.stringify(layout || {}));
    } catch (_) {}
  }

  function chatPanelLayoutStyle(layout) {
    const main = Number(layout?.main || 0);
    const ai = Number(layout?.ai || 0);
    if (main < 360 || ai < 300) return {};
    return {
      '--chat-main-width': `${main}px`,
      '--chat-ai-width': `${ai}px`,
    };
  }

  async function chatApiJson(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    const response = await fetch(url, { cache: 'no-store', ...options, headers });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`HTTP ${response.status} ${text}`);
    }
    return response.json();
  }

  async function savePromptSettingsToServer(draft, currentSettings = null) {
    const normalized = normalizeChatAnswerPrompts(draft);
    let settings = currentSettings || {};
    try {
      settings = await chatApiJson('/api/payme/settings');
    } catch (_) {}
    const saved = await chatApiJson('/api/payme/settings', {
      method: 'POST',
      body: JSON.stringify({ ...settings, llm_answer_prompts: normalized }),
    });
    try {
      window.dispatchEvent(new CustomEvent('xfiles:prompts-updated', { detail: saved }));
    } catch (_) {}
    return saved;
  }

  function usersPagingKey(chatName) {
    return `xfiles.index.chatUsersPaging.${chatName || 'global'}`;
  }

  function readUsersPaging(chatName) {
    try {
      const parsed = JSON.parse(localStorage.getItem(usersPagingKey(chatName)) || '{}');
      const pageSize = [2, 5, 10, 15, 20].includes(Number(parsed.pageSize)) ? Number(parsed.pageSize) : 2;
      return { page: Math.max(1, Number(parsed.page || 1)), pageSize };
    } catch (_) {
      return { page: 1, pageSize: 2 };
    }
  }

  function writeUsersPaging(chatName, paging) {
    try {
      localStorage.setItem(usersPagingKey(chatName), JSON.stringify({
        page: Math.max(1, Number(paging?.page || 1)),
        pageSize: [2, 5, 10, 15, 20].includes(Number(paging?.pageSize)) ? Number(paging.pageSize) : 2,
      }));
    } catch (_) {}
  }

  const PROMPT_SETTINGS_PAGE_SIZE = 5;

  function PromptSettingsModal({ open, prompts, saving, onClose, onSave }) {
    const [draft, setDraft] = React.useState(() => normalizeChatAnswerPrompts(prompts));
    const [page, setPage] = React.useState(1);
    React.useEffect(() => {
      if (open) {
        setDraft(normalizeChatAnswerPrompts(prompts));
        setPage(1);
      }
    }, [open, prompts]);
    React.useEffect(() => {
      const total = Math.max(1, Math.ceil(draft.length / PROMPT_SETTINGS_PAGE_SIZE));
      setPage((prev) => Math.min(Math.max(1, prev), total));
    }, [draft.length]);

    if (!open) return null;

    const updatePrompt = (index, patch) => {
      setDraft((prev) => prev.map((item, itemIndex) => (
        itemIndex === index ? { ...item, ...patch } : item
      )));
    };
    const setDefault = (index) => {
      setDraft((prev) => prev.map((item, itemIndex) => ({ ...item, is_default: itemIndex === index })));
    };
    const addPrompt = () => {
      setDraft((prev) => {
        const next = [
          ...prev,
          {
          ...CHAT_PROMPT_DEFAULTS[0],
          id: `prompt_${Date.now()}`,
          title: 'Новый промт',
          is_default: false,
          prompt: 'Сформулируй вариант ответа по контексту выбранного чата.',
          },
        ];
        setPage(Math.max(1, Math.ceil(next.length / PROMPT_SETTINGS_PAGE_SIZE)));
        return next;
      });
    };
    const removePrompt = (index) => {
      setDraft((prev) => {
        if (prev.length <= 1) return prev;
        const next = prev.filter((_, itemIndex) => itemIndex !== index);
        if (!next.some((item) => item.is_default)) next[0].is_default = true;
        return next;
      });
    };
    const promptTotalPages = Math.max(1, Math.ceil(draft.length / PROMPT_SETTINGS_PAGE_SIZE));
    const promptPage = Math.min(Math.max(1, page), promptTotalPages);
    const promptStart = (promptPage - 1) * PROMPT_SETTINGS_PAGE_SIZE;
    const promptEnd = Math.min(draft.length, promptStart + PROMPT_SETTINGS_PAGE_SIZE);
    const visiblePrompts = draft.slice(promptStart, promptEnd);
    const renderPromptPaging = () => html`
      <div className="prompt-settings-pager">
        <span className="muted">Показано ${draft.length ? `${promptStart + 1}-${promptEnd}` : '0'} из ${draft.length}</span>
        <button className="btn" type="button" disabled=${promptPage <= 1} onClick=${() => setPage((prev) => Math.max(1, prev - 1))}>Назад</button>
        <span className="chip prompt-settings-page-chip">${promptPage}/${promptTotalPages}</span>
        <button className="btn" type="button" disabled=${promptPage >= promptTotalPages} onClick=${() => setPage((prev) => Math.min(promptTotalPages, prev + 1))}>Далее</button>
      </div>
    `;

    return html`
      <div
        className="prompt-settings-backdrop"
        onClick=${onClose}
      >
        <div
          className="prompt-settings-modal"
          onClick=${(event) => event.stopPropagation()}
        >
          <div className="prompt-settings-head">
            <div>
              <div className="prompt-settings-title">Промты ответов для чата</div>
              <div className="muted">Редактируйте библиотеку ответов: название, сам промт, модель и параметры LLM. Выбранный default подставляется в рекомендации.</div>
            </div>
            <button className="btn" type="button" onClick=${onClose}>Закрыть</button>
          </div>
          <div className="prompt-settings-body">
            <div className="prompt-settings-toolbar">
              ${renderPromptPaging()}
              <button className="btn" type="button" onClick=${addPrompt}>Добавить промт</button>
            </div>
            <div className="prompt-settings-list">
	              ${visiblePrompts.map((prompt, itemIndex) => {
	                const index = promptStart + itemIndex;
	                return html`
                  <article key=${prompt.id} className=${`prompt-settings-card ${prompt.is_default ? 'is-default' : ''}`}>
                    <div className="prompt-settings-card-top">
                      <label className="chip prompt-settings-default">
                        <input type="radio" checked=${prompt.is_default} onChange=${() => setDefault(index)} />
                        default
                      </label>
                      <label className="prompt-settings-title-field">
                        <span className="prompt-settings-label-row">
                          <span className="muted">Название промта</span>
                          <span className="muted">${String(prompt.title || '').length} символов</span>
                        </span>
                        <input
                          className="input prompt-settings-title-input"
                          value=${prompt.title}
                          onChange=${(e) => updatePrompt(index, { title: e.target.value })}
                          placeholder="Например: Ответ 1 · мягкое знакомство"
                        />
                        <span className="muted">ID: <code>${prompt.id}</code></span>
                      </label>
                      <button className="btn prompt-settings-delete" type="button" disabled=${draft.length <= 1} onClick=${() => removePrompt(index)}>Удалить</button>
                    </div>
                    <div className="prompt-settings-llm-grid">
                      <label>
                        <span className="muted">Провайдер</span>
                        <select className="input" value=${prompt.provider} onChange=${(e) => updatePrompt(index, { provider: e.target.value })}>
                          <option value="openrouter">OpenRouter</option>
                          <option value="local">LM Studio</option>
                        </select>
                      </label>
                      <label className="prompt-settings-model-field">
                        <span className="muted">Модель</span>
                        <input className="input" value=${prompt.model} onChange=${(e) => updatePrompt(index, { model: e.target.value })} placeholder="model id" />
                      </label>
                      <label>
                        <span className="muted">temperature</span>
                        <input className="input" type="number" step="0.05" min="0" max="2" value=${prompt.temperature} onChange=${(e) => updatePrompt(index, { temperature: e.target.value })} />
                      </label>
                      <label>
                        <span className="muted">top_p</span>
                        <input className="input" type="number" step="0.05" min="0" max="1" value=${prompt.top_p} onChange=${(e) => updatePrompt(index, { top_p: e.target.value })} />
                      </label>
                      <label>
                        <span className="muted">max_tokens</span>
                        <input className="input" type="number" min="1" max="262144" value=${prompt.max_tokens} onChange=${(e) => updatePrompt(index, { max_tokens: e.target.value })} />
                      </label>
                    </div>
                    <label className="prompt-settings-text-field">
                      <span className="prompt-settings-label-row">
                        <span className="muted">Текст промта</span>
                        <span className="muted">${String(prompt.prompt || '').length} символов</span>
                      </span>
                      <textarea
                        className="input prompt-settings-textarea"
                        value=${prompt.prompt}
                        onChange=${(e) => updatePrompt(index, { prompt: e.target.value })}
                        placeholder="Опишите тон, цель ответа, ограничения и формат результата..."
                      />
                    </label>
                  </article>
	              `})}
	            </div>
            <div className="prompt-settings-footer">
	              ${renderPromptPaging()}
              <button className="btn btn-active" type="button" disabled=${saving} onClick=${() => onSave(draft)}>
                ${saving ? 'Сохраняю…' : 'Сохранить промты'}
              </button>
	            </div>
	          </div>
        </div>
      </div>
    `;
  }


    return {
      ChatHistoryPager,
      AnalysisHistoryPager,
      RepeatRequestModal,
      PromptPickerModal,
      readPromptHistory,
      writePromptHistory,
      chatApiJson,
      savePromptSettingsToServer,
      readUsersPaging,
      writeUsersPaging,
      PromptSettingsModal,
      readChatPanelLayout,
      writeChatPanelLayout,
      chatPanelLayoutStyle
    };
  };
})();
