/* React index page powered by legacy leadApp store */
'use strict';

(function mountReactIndexPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.BackfrontIndexUtils || !window.BackfrontIndexComponents || !window.leadApp) {
    console.error('[React] leadApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { PageNav, OutreachToggle, TelegramCooldownBanner, LoadingNotice, TablePaginationFooter } = window.BackfrontReactShared;
  const {
    formatEta,
    parseLlmPanelHtml,
    CHAT_PROMPT_DEFAULTS,
    normalizeChatPromptId,
    boundedNumber,
    normalizeChatAnswerPrompts,
    selectDefaultChatPrompt,
    normalizeAnalysisText,
  } = window.BackfrontIndexUtils;
  const {
    onEnter,
    ErrorPanel,
    AuthBanner,
    LeadRow,
    MessageBubble,
  } = window.BackfrontIndexComponents({ html, OutreachToggle });

  const {
    AnalysisFormattedText,
    DetailPopup,
    LlmLogRows,
    LlmLogNavigator,
    LlmLogPopupBody,
    logFileHref,
  } = window.BackfrontIndexDetail({ React, html, normalizeAnalysisText, formatEta });

  const {
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
    chatPanelLayoutStyle,
  } = window.BackfrontIndexHistory({
    React,
    html,
    DetailPopup,
    AnalysisFormattedText,
    logFileHref,
    formatEta,
    normalizeChatAnswerPrompts,
    CHAT_PROMPT_DEFAULTS,
  });

  function LlmPanel({ store }) {
    const progress = store.llmProgress || {};
    const parsed = parseLlmPanelHtml(store.llmHtml || '');
    const currentName = store.current?.name || '';
    const [settings, setSettings] = React.useState(null);
    const [promptModalOpen, setPromptModalOpen] = React.useState(false);
    const [promptSaving, setPromptSaving] = React.useState(false);
    const [answerHistory, setAnswerHistory] = React.useState([]);
    const [historyPage, setHistoryPage] = React.useState(1);
    const prompts = normalizeChatAnswerPrompts(settings?.llm_answer_prompts);
    const selectedPrompt = selectDefaultChatPrompt(prompts);
    const readyAnswers = parsed.answers.filter((answer) => !answer.isPlaceholder && answer.text);
    const timeoutSec = Math.max(5, Math.min(300, Number(settings?.openrouter_timeout_sec || store.settings?.openrouter_timeout_sec || 300)));
    const historyPageSize = 3;
    const totalHistoryPages = Math.max(1, Math.ceil(answerHistory.length / historyPageSize));
    const visibleHistory = answerHistory.slice((historyPage - 1) * historyPageSize, historyPage * historyPageSize);

    React.useEffect(() => {
      let cancelled = false;
      chatApiJson('/api/payme/settings')
        .then((data) => {
          if (!cancelled) setSettings(data);
        })
        .catch(() => {
          if (!cancelled) setSettings({ llm_answer_prompts: CHAT_PROMPT_DEFAULTS, openrouter_timeout_sec: 300 });
        });
      return () => { cancelled = true; };
    }, []);

    React.useEffect(() => {
      setAnswerHistory(readPromptHistory(currentName));
      setHistoryPage(1);
    }, [currentName]);

    React.useEffect(() => {
      if (!currentName || !readyAnswers.length) return;
      const signature = readyAnswers.map((answer) => answer.text).join('\n---\n');
      const currentHistory = readPromptHistory(currentName);
      if (currentHistory[0]?.signature === signature) return;
      const entry = {
        id: `${Date.now()}`,
        signature,
        created_at: new Date().toISOString(),
        prompt_id: selectedPrompt.id,
        prompt_title: selectedPrompt.title,
        provider: selectedPrompt.provider,
        model: selectedPrompt.model,
        answers: readyAnswers.map((answer) => ({
          title: answer.title,
          label: answer.label,
          text: answer.text,
        })),
      };
      const nextHistory = [entry, ...currentHistory].slice(0, 50);
      writePromptHistory(currentName, nextHistory);
      setAnswerHistory(nextHistory);
      setHistoryPage(1);
    }, [currentName, store.llmHtml, selectedPrompt.id]);

    const savePromptSettings = async (draft) => {
      const normalized = normalizeChatAnswerPrompts(draft);
      setPromptSaving(true);
      try {
        const saved = await savePromptSettingsToServer(normalized, settings || {});
        setSettings(saved);
        setPromptModalOpen(false);
      } catch (error) {
        console.error('[LLM prompts] save failed', error);
        window.toast ? window.toast('Не удалось сохранить промты: ' + (error.message || error), 'error') : null;
      } finally {
        setPromptSaving(false);
      }
    };

    const explainLlmError = (error) => {
      const raw = String(error || '').trim();
      if (!raw) return 'LLM не вернула ответ. Можно повторить запрос.';
      if (/HTTP\s*502|HTTP\s*503/i.test(raw)) {
        return 'OpenRouter или выбранная модель временно вернули ошибку 502/503. Программа не зависла: повторите запрос через несколько секунд или выберите другую модель в настройках.';
      }
      if (/HTTP\s*504|timeout|timed out/i.test(raw)) {
        return 'LLM не успела ответить за лимит ожидания. Можно повторить запрос или увеличить timeout OpenRouter в настройках.';
      }
      return raw;
    };
    if (store.llmRunning || progress.error) {
      const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
      const errorText = explainLlmError(progress.error);
      return html`
        <div id="llmBox" className="flex-1 overflow-auto" style=${{ minHeight: 0, padding: '16px' }}>
          <div style=${{
            border: `1px solid ${progress.error ? '#fecaca' : '#bfdbfe'}`,
            background: progress.error ? '#fff1f2' : 'linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%)',
            borderRadius: '18px',
            padding: '18px',
            boxShadow: '0 14px 36px rgba(15, 23, 42, 0.08)',
          }}>
            <div className="row" style=${{ alignItems: 'flex-start', gap: '12px' }}>
              <div>
                <div className="font-semibold">${progress.error ? 'LLM не ответила' : 'LLM готовит варианты ответов'}</div>
                <div className="muted">${progress.error ? errorText : (progress.status || 'Запрос отправлен, ожидаем результат…')}</div>
              </div>
              <span className=${`badge ${progress.error ? 'badge-yellow' : 'badge-blue'}`}>
                ${progress.error ? 'нужно повторить' : `${Math.round(percent)}%`}
              </span>
            </div>
            <div style=${{ height: '10px', background: '#dbeafe', borderRadius: '999px', overflow: 'hidden', marginTop: '14px' }}>
              <div style=${{
                width: `${percent}%`,
                height: '100%',
                background: progress.error ? '#f97316' : 'linear-gradient(90deg, #38bdf8, #22c55e)',
                transition: 'width .35s ease',
              }}></div>
            </div>
            <div className="row" style=${{ marginTop: '12px', gap: '10px', flexWrap: 'wrap' }}>
              <span className="chip">До лимита ожидания: ${formatEta(progress.etaSec)}</span>
              <span className="chip">Лимит OpenRouter: ${formatEta(progress.timeoutSec || 300)}</span>
              <span className="muted">Это не прогноз скорости: показываем максимум ожидания ответа LLM.</span>
              ${progress.error ? html`
                <button className="btn btn-active" type="button" onClick=${() => store.llmRun({ promptId: selectedPrompt.id })}>
                  Повторить
                </button>
              ` : null}
            </div>
          </div>
          <${PromptSettingsModal}
            open=${promptModalOpen}
            prompts=${prompts}
            saving=${promptSaving}
            onClose=${() => setPromptModalOpen(false)}
            onSave=${savePromptSettings}
          />
        </div>
      `;
    }

    return html`
      <div id="llmBox" className="flex-1 overflow-auto llm-workbench" style=${{ minHeight: 0, padding: '16px' }}>
        <section className="llm-workbench-hero">
          <div>
            <div className="llm-kicker">AI assistant</div>
            <h3>Структура сделки и рекомендованный ответ</h3>
            <p>Панель помогает быстро понять контекст источника и подготовить вариант ответа без ручного анализа.</p>
          </div>
          <div className="llm-token-pill">
            <strong>${parsed.tokens}</strong>
            <span>токенов</span>
          </div>
        </section>

        <section className="llm-workbench-card">
          <div className="llm-card-head">
            <div>
              <div className="font-semibold">Контекст анализа</div>
              <div className="muted">Выбранный чат: ${currentName || 'чат не выбран'}</div>
            </div>
            ${parsed.hasLegacyDraft ? html`<span className="badge badge-yellow">кэш обновлён в новом виде</span>` : null}
          </div>
          <div className="llm-filter-chips">
            <span className="chip">Промт: ${selectedPrompt.title}</span>
            <span className="chip">LLM: ${selectedPrompt.provider === 'local' ? 'LM Studio' : 'OpenRouter'}</span>
            <span className="chip">Модель: ${selectedPrompt.model}</span>
            <span className="chip">temperature: ${selectedPrompt.temperature}</span>
            <span className="chip">top_p: ${selectedPrompt.top_p}</span>
            <span className="chip">max_tokens: ${selectedPrompt.max_tokens}</span>
            <span className="chip">timeout: ${timeoutSec} сек</span>
          </div>
        </section>

        <section className="llm-workbench-card">
          <div className="llm-card-head">
            <div>
              <div className="font-semibold">Сгенерировать ответы</div>
              <div className="muted">Используется выбранный промт по умолчанию. Промт и настройки LLM можно поменять в popup.</div>
            </div>
            <button className="btn" type="button" onClick=${() => setPromptModalOpen(true)}>Настроить промты</button>
          </div>
          <button
            className="btn btn-active llm-primary-run"
            type="button"
            onClick=${() => store.llmRun({ promptId: selectedPrompt.id })}
          >
            Посчитать 3 рекомендованный ответ для промта
          </button>
        </section>

        <section className="llm-workbench-card">
          <div className="llm-card-head">
            <div>
              <div className="font-semibold">Готовые варианты</div>
              <div className="muted">История запросов по выбранному чату. На странице показываем до 3 запусков, чтобы правая панель не превращалась в длинную простыню.</div>
            </div>
            <div className="row" style=${{ gap: '6px' }}>
              <button className="btn" type="button" disabled=${historyPage <= 1} onClick=${() => setHistoryPage((page) => Math.max(1, page - 1))}>Назад</button>
              <span className="chip">${historyPage} / ${totalHistoryPages}</span>
              <button className="btn" type="button" disabled=${historyPage >= totalHistoryPages} onClick=${() => setHistoryPage((page) => Math.min(totalHistoryPages, page + 1))}>Вперёд</button>
            </div>
          </div>
          ${visibleHistory.length ? html`
            <div style=${{ display: 'grid', gap: '12px' }}>
              ${visibleHistory.map((entry) => html`
                <div key=${entry.id} style=${{ border: '1px solid #e2e8f0', borderRadius: '16px', padding: '12px', background: '#fff' }}>
                  <div className="row" style=${{ marginBottom: '10px', gap: '10px' }}>
                    <strong>${entry.prompt_title || 'Промт'}</strong>
                    <span className="muted">${window.fmtDate ? window.fmtDate(entry.created_at) : entry.created_at}</span>
                    <span className="chip">${entry.model || 'model'}</span>
                  </div>
                  <div className="llm-answer-grid">
                    ${(entry.answers || []).slice(0, 3).map((answer, index) => html`
                      <button
                        key=${`${entry.id}-${index}`}
                        type="button"
                        className="llm-answer-card llm-btn"
                        data-text=${answer.text}
                      >
                        <span>${answer.title || `Ответ ${index + 1}`}</span>
                        <strong>${answer.label || answer.text}</strong>
                      </button>
                    `)}
                  </div>
                </div>
              `)}
            </div>
          ` : html`
            <div className="llm-answer-grid">
              ${parsed.answers.map((answer) => html`
                <button
                  key=${answer.id}
                  type="button"
                  className=${`llm-answer-card llm-btn ${answer.isPlaceholder ? 'llm-answer-empty' : ''}`}
                  data-text=${answer.text}
                  disabled=${answer.isPlaceholder}
                >
                  <span>${answer.title}</span>
                  <strong>${answer.label}</strong>
                </button>
              `)}
            </div>
          `}
        </section>
        <${PromptSettingsModal}
          open=${promptModalOpen}
          prompts=${prompts}
          saving=${promptSaving}
          onClose=${() => setPromptModalOpen(false)}
          onSave=${savePromptSettings}
        />
      </div>
    `;
  }

  const {
    ChatAnalysisPanel,
    ChatAnalysisModal,
    openChatAnalysisModal,
    closeChatAnalysisModal,
  } = window.BackfrontIndexAnalysis({ React, html, formatEta, DetailPopup, LlmLogNavigator, AnalysisHistoryPager });
  const {
    ChatHeader,
    ChatMessagesWindow,
    ChatComposer,
  } = window.BackfrontIndexChat({ html, LoadingNotice, MessageBubble, openChatAnalysisModal });

  function ChatUsersPanel({ store, onOpenLog, onManagePrompts }) {
    const state = store.chatAnalysis || {};
    const stats = state.stats || {};
    const senders = Array.isArray(stats.by_sender) ? stats.by_sender : [];
    const history = Array.isArray(state.history) ? state.history : [];
    const currentName = store.current?.name || 'global';
    const [promptLibrary, setPromptLibrary] = React.useState(() => normalizeChatAnswerPrompts(CHAT_PROMPT_DEFAULTS));
    const [promptSender, setPromptSender] = React.useState(null);
    const [senderPaging, setSenderPaging] = React.useState(() => readUsersPaging(currentName));
    const [senderSort, setSenderSort] = React.useState({ key: 'tokens', dir: 'desc' });
    const [historyPopupOpen, setHistoryPopupOpen] = React.useState(false);
    const [usersPopupSize, setUsersPopupSize] = React.useState(null);
    const [answerPopupItem, setAnswerPopupItem] = React.useState(null);
    const [repeatItem, setRepeatItem] = React.useState(null);

    React.useEffect(() => {
      if (!store.current?.name) return;
      Promise.allSettled([store.loadChatAnalysisStats?.(), store.loadChatAnalysisHistory?.()]);
    }, [store.current?.name]);

    React.useEffect(() => {
      let cancelled = false;
      fetch('/api/payme/settings')
        .then((response) => (response.ok ? response.json() : null))
        .then((settings) => {
          if (!cancelled) setPromptLibrary(normalizeChatAnswerPrompts(settings?.llm_answer_prompts || CHAT_PROMPT_DEFAULTS));
        })
        .catch(() => {
          if (!cancelled) setPromptLibrary(normalizeChatAnswerPrompts(CHAT_PROMPT_DEFAULTS));
        });
      return () => {
        cancelled = true;
      };
    }, []);

    React.useEffect(() => {
      const handler = (event) => {
        setPromptLibrary(normalizeChatAnswerPrompts(event?.detail?.llm_answer_prompts || CHAT_PROMPT_DEFAULTS));
      };
      window.addEventListener('xfiles:prompts-updated', handler);
      return () => window.removeEventListener('xfiles:prompts-updated', handler);
    }, []);

    const selectedPromptFor = (sender) =>
      store.chatAnalysisPromptForSender?.(sender.sender_key) || selectDefaultChatPrompt(promptLibrary);

    React.useEffect(() => {
      setSenderPaging(readUsersPaging(currentName));
    }, [currentName]);

    React.useEffect(() => {
      const next = { ...senderPaging, page: 1 };
      setSenderPaging(next);
      writeUsersPaging(currentName, next);
    }, [senders.length]);

    const sortSenderRows = (rows) => {
      const factor = senderSort.dir === 'asc' ? 1 : -1;
      return [...rows].sort((a, b) => {
        const getValue = (row) => {
          if (senderSort.key === 'name') return String(row.sender_name || row.sender_username || row.sender_key || '').toLowerCase();
          if (senderSort.key === 'username') return String(row.sender_username || row.sender_id || '').toLowerCase();
          if (senderSort.key === 'messages') return Number(row.messages_count || 0);
          return Number(row.tokens || 0);
        };
        const av = getValue(a);
        const bv = getValue(b);
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * factor;
        return String(av).localeCompare(String(bv), 'ru') * factor;
      });
    };
    const toggleSenderSort = (key) => {
      setSenderSort((current) => ({
        key,
        dir: current.key === key && current.dir === 'desc' ? 'asc' : 'desc',
      }));
    };
    const sortMark = (key) => senderSort.key === key ? (senderSort.dir === 'desc' ? '↓' : '↑') : '↕';
    const sortedSenders = sortSenderRows(senders);
    const senderPage = Math.max(1, Number(senderPaging.page || 1));
    const senderPageSize = [2, 5, 10, 15, 20].includes(Number(senderPaging.pageSize)) ? Number(senderPaging.pageSize) : 2;
    const senderTotalPages = Math.max(1, Math.ceil(sortedSenders.length / senderPageSize));
    const safeSenderPage = Math.min(Math.max(1, senderPage), senderTotalPages);
    const senderStart = (safeSenderPage - 1) * senderPageSize;
    const visibleSenders = sortedSenders.slice(senderStart, senderStart + senderPageSize);
    const senderRangeText = senders.length
      ? `${senderStart + 1}-${Math.min(senderStart + senderPageSize, senders.length)} из ${senders.length}`
      : '0 из 0';
    const allLogRows = [
      ...(Array.isArray(state.progressLog) ? state.progressLog : []),
      ...(Array.isArray(store.llmProgress?.log) ? store.llmProgress.log : []),
    ];
    const isBusy = !!(state.running || state.refreshing);
    const openHistoryPopup = () => setHistoryPopupOpen(true);
    const openUsersPopup = (size) => setUsersPopupSize(size === 'full' ? 'full' : 'wide');
    const usersProgress = store.chatUsersRefresh || {};
    const setUsersPaging = (patch) => {
      const next = {
        page: Math.max(1, Number(patch.page ?? senderPaging.page ?? 1)),
        pageSize: [2, 5, 10, 15, 20].includes(Number(patch.pageSize ?? senderPaging.pageSize))
          ? Number(patch.pageSize ?? senderPaging.pageSize)
          : 2,
      };
      setSenderPaging(next);
      writeUsersPaging(currentName, next);
    };
    const latestAnswerFor = (sender) => {
      const key = String(sender?.sender_key || '').trim();
      if (!key) return null;
      return history.find((item) => String(item?.sender_key || '').trim() === key && item?.result && !item?.error) || null;
    };
    const copyAnswer = (item) => store.copyChatAnalysisToComposer?.(item?.result || '');
    const compactNumber = (value) => {
      const number = Number(value || 0);
      if (!Number.isFinite(number)) return '0';
      if (Math.abs(number) >= 1000000) return `${(number / 1000000).toFixed(number >= 10000000 ? 0 : 1).replace(/\.0$/, '')}m`;
      if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(number >= 10000 ? 0 : 1).replace(/\.0$/, '')}k`;
      return String(Math.round(number));
    };
    const renderUsersTableContent = () => html`
      ${usersProgress.running || usersProgress.status ? html`
        <div className="analysis-progress chat-users-refresh-progress">
          <div className="row">
            <strong>${usersProgress.running ? 'Обновление пользователей выполняется' : 'Обновление пользователей'}</strong>
            <span className="muted">${Math.round(Number(usersProgress.percent || 0))}%</span>
          </div>
          <div className="muted" style=${{ marginTop: '6px' }}>${usersProgress.status || 'Сверяю пользователей…'}</div>
          <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${Math.max(1, Number(usersProgress.percent || 0))}%` }}></div></div>
        </div>
      ` : null}
      ${senders.length ? html`
        <div className="chat-users-table-wrap">
          <table className="chat-users-table">
            <thead>
              <tr>
                <th><button type="button" onClick=${() => toggleSenderSort('name')}>Пользователь ${sortMark('name')}</button></th>
                <th><button type="button" onClick=${() => toggleSenderSort('username')}>ID / username ${sortMark('username')}</button></th>
                <th><button type="button" onClick=${() => toggleSenderSort('messages')}>Сообщений ${sortMark('messages')}</button></th>
                <th><button type="button" onClick=${() => toggleSenderSort('tokens')}>Токенов ${sortMark('tokens')}</button></th>
                <th>Промт</th>
                <th>Рекомендация</th>
                <th>Ответ</th>
              </tr>
            </thead>
            <tbody>
              ${visibleSenders.map((sender) => {
                const selectedPrompt = selectedPromptFor(sender);
                const isRunning = state.running && state.userRunningKey === sender.sender_key;
                const readyAnswer = latestAnswerFor(sender);
                return html`
                  <tr key=${sender.sender_key}>
                    <td><strong>${sender.sender_name || sender.sender_username || sender.sender_key}</strong></td>
                    <td>
                      ${sender.sender_username ? html`<div>@${sender.sender_username}</div>` : null}
                      <div className="muted">${sender.sender_id ? `id:${sender.sender_id}` : sender.sender_key}</div>
                    </td>
                    <td>${sender.messages_count || 0}</td>
                    <td>${sender.tokens || 0}</td>
                    <td>
                      <button className="btn btn-compact" type="button" onClick=${() => setPromptSender(sender)}>
                        ${selectedPrompt?.title || 'Выбрать промт'}
                      </button>
                    </td>
                    <td>
                      <button
                        className="btn btn-active btn-compact"
                        type="button"
                        disabled=${state.running || state.refreshing}
                        onClick=${() => {
                          onOpenLog?.();
                          store.runUserRecommendation?.(sender, selectedPrompt);
                        }}
                      >
                        ${isRunning ? 'Анализ...' : 'Рекомендация'}
                      </button>
                    </td>
                    <td>
                      ${readyAnswer ? html`
                        <button className="btn btn-compact" type="button" onClick=${() => setAnswerPopupItem(readyAnswer)}>
                          Открыть
                        </button>
                      ` : html`<span className="muted">—</span>`}
                    </td>
                  </tr>
                `;
              })}
            </tbody>
          </table>
        </div>
        <div className="chat-users-pagination muted">${senderRangeText}</div>
      ` : html`<div className="chat-analysis-empty">Пользователи появятся после загрузки сообщений.</div>`}
    `;
    const renderUsersToolbar = () => html`
      <div className="chat-users-toolbar">
        <div className="chat-users-actions">
          <button className="btn btn-compact" type="button" onClick=${() => openUsersPopup('wide')}>80%</button>
          <button className="btn btn-compact" type="button" onClick=${() => openUsersPopup('full')}>100%</button>
          <button className="btn btn-compact btn-active" type="button" disabled=${usersProgress.running || isBusy} onClick=${() => store.refreshChatUsers?.()}>
            ${usersProgress.running ? 'Обновляю пользователей…' : 'Обновить пользователей'}
          </button>
        </div>
        <div className="chat-users-pager">
        <select
          className="btn btn-compact"
          value=${String(senderPageSize)}
          onChange=${(event) => {
            setUsersPaging({ page: 1, pageSize: Number(event.target.value) || 2 });
          }}
        >
          <option value="2">2 строки</option>
          <option value="5">5 строк</option>
          <option value="10">10 строк</option>
          <option value="15">15 строк</option>
          <option value="20">20 строк</option>
        </select>
        <button className="btn btn-compact" type="button" title="Предыдущая страница пользователей" disabled=${safeSenderPage <= 1} onClick=${() => setUsersPaging({ page: safeSenderPage - 1 })}>Назад</button>
        <span className="chip">${safeSenderPage} / ${senderTotalPages}</span>
        <button className="btn btn-compact" type="button" title="Следующая страница пользователей" disabled=${safeSenderPage >= senderTotalPages} onClick=${() => setUsersPaging({ page: safeSenderPage + 1 })}>Вперёд</button>
        </div>
      </div>
    `;

    if (!store.current) {
      return html`
        <div className="chat-users-panel">
          <div className="chat-main-header row">
            <div>
              <div className="chat-main-title">Пользователи чата</div>
              <div className="muted">Выберите источник слева, чтобы увидеть авторов, токены и рекомендации.</div>
            </div>
          </div>
        </div>
      `;
    }

    return html`
      <div className="chat-users-panel">
        <section className="chat-analysis-history-section">
          <div className="chat-users-table-head">
            <div>
              <div className="chat-main-title">История рекомендаций</div>
              <div className="muted">По умолчанию показываем 2 записи; размер страницы можно увеличить.</div>
            </div>
            <div className="row" style=${{ gap: '8px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              <button className="btn btn-compact" type="button" onClick=${openHistoryPopup}>Открыть на 80%</button>
              <button className="btn btn-compact" type="button" onClick=${() => setHistoryPopupOpen('full')}>Открыть на 100%</button>
            </div>
          </div>
          <${ChatHistoryPager} store=${store} state=${state} history=${history} />
        </section>

        <section className="chat-users-table-section">
          <div className="chat-users-table-head">
            <div>
              <div className="chat-main-title">Пользователи</div>
              <div className="muted">Список авторов сообщений, локальная оценка токенов и быстрый запуск LLM-рекомендации.</div>
            </div>
            ${renderUsersToolbar()}
          </div>
          ${usersProgress.running || usersProgress.status ? html`
            <div className="analysis-progress chat-users-refresh-progress">
              <div className="row">
                <strong>${usersProgress.running ? 'Обновление пользователей выполняется' : 'Обновление пользователей'}</strong>
                <span className="muted">${Math.round(Number(usersProgress.percent || 0))}%</span>
              </div>
              <div className="muted" style=${{ marginTop: '6px' }}>${usersProgress.status || 'Сверяю пользователей…'}</div>
              <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${Math.max(1, Number(usersProgress.percent || 0))}%` }}></div></div>
            </div>
          ` : null}
          ${senders.length ? html`
            <div className="chat-users-table-wrap">
              <table className="chat-users-table chat-users-table-compact">
                <thead>
                  <tr>
                    <th><button type="button" onClick=${() => toggleSenderSort('name')}>Пользователь ${sortMark('name')}</button></th>
                    <th><button type="button" onClick=${() => toggleSenderSort('username')}>ID / username ${sortMark('username')}</button></th>
                    <th><button type="button" onClick=${() => toggleSenderSort('messages')}>Сообщений ${sortMark('messages')}</button></th>
                    <th><button type="button" onClick=${() => toggleSenderSort('tokens')}>Токенов ${sortMark('tokens')}</button></th>
                    <th>Промт</th>
                    <th>Рекомендация</th>
                    <th>Ответ</th>
                  </tr>
                </thead>
                <tbody>
                  ${visibleSenders.map((sender) => {
                    const selectedPrompt = selectedPromptFor(sender);
                    const isRunning = state.running && state.userRunningKey === sender.sender_key;
                    const readyAnswer = latestAnswerFor(sender);
                    return html`
                      <tr key=${sender.sender_key}>
                        <td>
                          <strong>${sender.sender_name || sender.sender_username || sender.sender_key}</strong>
                        </td>
                        <td>
                          ${sender.sender_username ? html`<div>@${sender.sender_username}</div>` : null}
                          <div className="muted">${sender.sender_id ? `id:${sender.sender_id}` : sender.sender_key}</div>
                        </td>
                        <td title=${String(sender.messages_count || 0)}>${compactNumber(sender.messages_count)}</td>
                        <td title=${String(sender.tokens || 0)}>${compactNumber(sender.tokens)}</td>
                        <td>
                          <button className="btn btn-compact" type="button" onClick=${() => setPromptSender(sender)}>
                            ${selectedPrompt?.title || 'Выбрать промт'}
                          </button>
                        </td>
                        <td>
                          <button
                            className="btn btn-active btn-compact"
                            type="button"
                            disabled=${state.running || state.refreshing}
                            onClick=${() => {
                              onOpenLog?.();
                              store.runUserRecommendation?.(sender, selectedPrompt);
                            }}
                          >
                            ${isRunning ? 'Анализ...' : 'Рекомендация'}
                          </button>
                        </td>
                        <td>
                          ${readyAnswer ? html`
                            <button className="btn btn-compact" type="button" onClick=${() => setAnswerPopupItem(readyAnswer)}>
                              Открыть
                            </button>
                          ` : html`<span className="muted">—</span>`}
                        </td>
                      </tr>
                    `;
                  })}
                </tbody>
              </table>
            </div>
            <div className="chat-users-pagination muted">${senderRangeText}</div>
          ` : html`<div className="chat-analysis-empty">Пользователи появятся после загрузки сообщений.</div>`}
        </section>

        <${PromptPickerModal}
          open=${!!promptSender}
          prompts=${promptLibrary}
          sender=${promptSender}
          selected=${promptSender ? selectedPromptFor(promptSender) : null}
          onClose=${() => setPromptSender(null)}
          onSelect=${(prompt) => {
            store.setChatAnalysisPromptForSender?.(promptSender?.sender_key, prompt);
            setPromptSender(null);
          }}
          onManagePrompts=${() => {
            setPromptSender(null);
            onManagePrompts?.();
          }}
        />
        <${DetailPopup}
          open=${historyPopupOpen}
          title="История рекомендаций"
          subtitle=${store.current ? `Чат: ${store.current.name}` : ''}
          onClose=${() => setHistoryPopupOpen(false)}
          size=${historyPopupOpen === 'full' ? 'full' : 'wide'}
          body=${html`<${ChatHistoryPager} store=${store} state=${state} history=${history} popup=${true} />`}
        />
        <${DetailPopup}
          open=${!!usersPopupSize}
          title="Пользователи"
          subtitle=${store.current ? `Чат: ${store.current.name}` : ''}
          onClose=${() => setUsersPopupSize(null)}
          size=${usersPopupSize === 'full' ? 'full' : 'wide'}
          body=${html`
            <div className="detail-popup-stack">
              ${renderUsersToolbar()}
              ${renderUsersTableContent()}
            </div>
          `}
        />
        <${DetailPopup}
          open=${!!answerPopupItem}
          title="Ответ"
          subtitle=${answerPopupItem ? `${answerPopupItem.sender_name || answerPopupItem.sender_key || 'Пользователь'} · ${answerPopupItem.provider || ''} · ${answerPopupItem.model || ''}` : ''}
          onClose=${() => setAnswerPopupItem(null)}
          body=${answerPopupItem ? html`
            <div className="detail-popup-stack">
              <div className="row" style=${{ justifyContent: 'flex-start', gap: '10px', flexWrap: 'wrap' }}>
                <button className="btn btn-active" type="button" onClick=${() => copyAnswer(answerPopupItem)}>
                  Скопировать в буфер и в сообщение
                </button>
                <button className="btn" type="button" disabled=${state.running || state.refreshing} onClick=${() => setRepeatItem(answerPopupItem)}>
                  Повторить
                </button>
              </div>
              <article className="analysis-history-card">
                <${AnalysisFormattedText} text=${answerPopupItem.result || ''} />
              </article>
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

  function ChatApp() {
    const store = useLegacyStore(window.leadApp);
    const [booted, setBooted] = React.useState(false);
    const [panelLayout, setPanelLayout] = React.useState(readChatPanelLayout);
    const [globalLogPopupOpen, setGlobalLogPopupOpen] = React.useState(false);
    const [globalPromptOpen, setGlobalPromptOpen] = React.useState(false);
    const [globalPromptSettings, setGlobalPromptSettings] = React.useState(null);
    const [globalPromptSaving, setGlobalPromptSaving] = React.useState(false);
    const gridRef = React.useRef(null);
    const debounceLeadReload = useDebouncedCallback(() => store.resetLeadPageAndLoad(), 300);
    const openGlobalLlmLog = () => setGlobalLogPopupOpen(true);
    const openGlobalPromptSettings = async () => {
      setGlobalPromptOpen(true);
      try {
        const settings = await chatApiJson('/api/payme/settings');
        setGlobalPromptSettings(settings);
      } catch (error) {
        console.warn('[Prompts] settings load failed:', error);
        setGlobalPromptSettings({ llm_answer_prompts: CHAT_PROMPT_DEFAULTS });
      }
    };
    const saveGlobalPromptSettings = async (draft) => {
      setGlobalPromptSaving(true);
      try {
        const saved = await savePromptSettingsToServer(draft, globalPromptSettings);
        setGlobalPromptSettings(saved);
        setGlobalPromptOpen(false);
      } catch (error) {
        console.error('[Prompts] save failed:', error);
        window.toast ? window.toast('Не удалось сохранить промты: ' + (error.message || error), 'error') : null;
      } finally {
        setGlobalPromptSaving(false);
      }
    };

    const startPanelResize = (event) => {
      const grid = gridRef.current;
      const middlePanel = grid?.querySelector('.chat-main-card');
      const rightPanel = grid?.querySelector('.chat-ai-card');
      if (!grid || !middlePanel || !rightPanel || window.innerWidth <= 1100) return;
      event.preventDefault();

      const middleRect = middlePanel.getBoundingClientRect();
      const rightRect = rightPanel.getBoundingClientRect();
      const left = middleRect.left;
      const right = rightRect.right;
      const minMiddle = 420;
      const minRight = 320;

      const apply = (clientX) => {
        const x = Math.min(right - minRight, Math.max(left + minMiddle, Number(clientX || 0)));
        const next = {
          main: Math.round(x - left),
          ai: Math.round(right - x),
        };
        setPanelLayout(next);
        writeChatPanelLayout(next);
      };
      const onMove = (moveEvent) => apply(moveEvent.clientX);
      const onUp = () => {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };

      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp, { once: true });
      apply(event.clientX);
    };

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Chat init failed:', error);
          store.error = String(error?.message || error);
        })
        .finally(() => {
          if (!cancelled) setBooted(true);
        });
      return () => {
        cancelled = true;
      };
    }, [store]);

    React.useLayoutEffect(() => {
      if (!store.current || store.messagesLoadingMore || store.loading) return;
      if (Number(store.messageScrollRatio || 1) < 0.95 && store.messages.length > store.messageChunkSize?.()) return;
      const box = document.getElementById('chatBox');
      if (!box) return;
      const pinToLatest = () => { box.scrollTop = box.scrollHeight; };
      pinToLatest();
      window.requestAnimationFrame(pinToLatest);
      window.requestAnimationFrame(() => window.requestAnimationFrame(pinToLatest));
    }, [store.current?.name, store.messages.length, store.loading, store.messagesLoadingMore]);

    const rootClassName = store.authBannerVisible() ? 'app-root auth-visible' : 'app-root';
    const globalLogRows = [
      ...(Array.isArray(store.chatAnalysis?.progressLog) ? store.chatAnalysis.progressLog : []),
      ...(Array.isArray(store.llmProgress?.log) ? store.llmProgress.log : []),
    ];
    const leadTotalPages = store.totalPages();
    const safeLeadPage = Math.min(Math.max(1, Number(store.ui.page || 1)), leadTotalPages);

    return html`
      <div className=${rootClassName}>
        <header className="chat-topbar row">
          <div className="chat-brand">
            <div className="chat-brand-title">X-Files</div>
            <div className="chat-brand-subtitle">revenue operating system & engine</div>
          </div>
          <div className="chat-topbar-right">
            <${PageNav} active="chats" />
            <button className="btn xfiles-nav-link" type="button" onClick=${openGlobalPromptSettings}>Промты</button>
            <button className="btn xfiles-nav-link" type="button" onClick=${openGlobalLlmLog}>Лог LLM</button>
          </div>
        </header>

        <div style=${{ padding: '8px 16px 0' }}>
          <${TelegramCooldownBanner} compact=${true} />
        </div>

        <${AuthBanner} store=${store} />

        <main className="app-grid" ref=${gridRef} style=${chatPanelLayoutStyle(panelLayout)}>
          <aside className="card panel chat-sidebar">
            <div className="chat-sidebar-head">
              <div>
                <div className="chat-section-title">Источники</div>
                <div className="muted">Выберите чат, чтобы увидеть сообщения и анализ.</div>
              </div>
              <span className="badge badge-pending">${store.totalLeads || 0}</span>
            </div>

            <div className="chat-sidebar-tools">
            <div className="chat-tools">
              <input
                className="w-full border rounded-lg px-3 py-2"
                type="text"
                placeholder="Фильтр по лидам…"
                value=${store.ui.leadFilter}
                onChange=${(e) => {
                  store.ui.leadFilter = e.target.value;
                  debounceLeadReload();
                }}
              />
              <button className="btn" onClick=${() => store.loadLeads()} title="Обновить список лидов">⟳</button>
              <button className="btn" onClick=${() => store.refreshChannels()} disabled=${store.sourceRefreshing} title="Перечитать выбранные источники и обновить каналы">
                <span>${store.sourceRefreshing ? '…' : 'Обновить каналы'}</span>
              </button>
            </div>

            <div className="chat-add-row">
              <input
                className="w-full border rounded-lg px-3 py-2"
                type="text"
                placeholder="@channel или numeric id"
                value=${store.sourceForm.selector}
                onChange=${(e) => { store.sourceForm.selector = e.target.value; }}
                onKeyDown=${onEnter(() => store.addChannel())}
              />
              <button className="btn" onClick=${() => store.addChannel()} disabled=${store.sourceRefreshing}>
                <span>${store.sourceRefreshing ? '…' : 'Добавить канал'}</span>
              </button>
            </div>

            <div className="chat-filter-grid">
              <label className="chip"><input type="checkbox" checked=${store.ui.showChannels} onChange=${(e) => { store.ui.showChannels = e.target.checked; store.resetLeadPageAndLoad(); }} /> Каналы</label>
              <label className="chip"><input type="checkbox" checked=${store.ui.showGroups} onChange=${(e) => { store.ui.showGroups = e.target.checked; store.resetLeadPageAndLoad(); }} /> Группы</label>
              <label className="chip"><input type="checkbox" checked=${store.ui.showPrivate} onChange=${(e) => { store.ui.showPrivate = e.target.checked; store.resetLeadPageAndLoad(); }} /> Личные</label>
              <select className="btn" value=${String(store.ui.pageSize)} onChange=${(e) => { store.ui.pageSize = Number(e.target.value); store.resetLeadPageAndLoad(); }}>
                <option value="5">5 строк</option>
                <option value="10">10 строк</option>
                <option value="20">20 строк</option>
                <option value="50">50 строк</option>
              </select>
            </div>

            <div className="chat-scan-tabs">
              <button className=${`btn ${store.ui.scanFilter === 'all' ? 'btn-active' : ''}`} onClick=${() => store.setScanFilter('all')}>Все</button>
              <button className=${`btn ${store.ui.scanFilter === 'scanning' ? 'btn-active' : ''}`} onClick=${() => store.setScanFilter('scanning')}>Сканируется</button>
              <button className=${`btn ${store.ui.scanFilter === 'not_scanning' ? 'btn-active' : ''}`} onClick=${() => store.setScanFilter('not_scanning')}>Не сканируется</button>
              <button className=${`btn ${store.ui.scanFilter === 'has_db' ? 'btn-active' : ''}`} onClick=${() => store.setScanFilter('has_db')}>Есть в базе</button>
            </div>
            </div>

            ${store.loading ? html`<${LoadingNotice} message="Загрузка лидов…" details="Список читается из backend-кеша; если Telegram ограничил запросы, ниже появится ETA." className="muted" compact=${true} />` : null}
            ${!store.loading && store.pagedLeads().length === 0 ? html`
              <div className="muted">
                Источники пока не найдены. Добавьте чат в “Импорт” или дождитесь фоновой синхронизации Telegram.
              </div>
            ` : null}

            <div className="lead-list">
              ${store.pagedLeads().map((lead) => html`<${LeadRow} key=${lead.name} store=${store} lead=${lead} />`)}
            </div>

            <${TablePaginationFooter}
              rangeText=${store.visibleRangeText()}
              page=${safeLeadPage}
              totalPages=${leadTotalPages}
              pageWindow=${store.pageWindow()}
              onPrev=${() => store.prevPage()}
              onNext=${() => store.nextPage()}
              onGo=${(page) => store.goToPage(page)}
              footerClassName="chat-users-pager"
              paginationClassName="chat-users-pager"
            />
          </aside>

          <section className="card panel chat-main-card">
            <${ChatHeader} store=${store} />
            <${ChatMessagesWindow} store=${store} />
            <${ChatComposer} store=${store} />
          </section>

          <div
            className="layout-resize-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Изменить ширину среднего и правого блока"
            title="Потяните, чтобы изменить ширину сообщений и LLM-панели"
            onPointerDown=${startPanelResize}
          ></div>

          <section className="card panel chat-ai-card">
            <div className="chat-main-header row">
              <div>
                <div className="chat-main-title">LLM · Структура сделки</div>
                <div className="muted">Сводка и рекомендации по выбранному источнику.</div>
              </div>
              <div className="muted">${store.current ? 'AI-анализ выбранного чата' : ''}</div>
            </div>

            <div className="chat-ai-body">
              <${ChatUsersPanel} store=${store} onOpenLog=${openGlobalLlmLog} onManagePrompts=${openGlobalPromptSettings} />
            </div>
          </section>
        </main>

        <${ChatAnalysisModal} store=${store} />
        <${DetailPopup}
          open=${globalLogPopupOpen}
          title="Лог LLM"
          subtitle=${store.current ? `Чат: ${store.current.name}` : 'Последний LLM лог текущей страницы'}
          onClose=${() => setGlobalLogPopupOpen(false)}
          body=${html`<${LlmLogNavigator} state=${store.chatAnalysis || {}} rows=${globalLogRows} scope="global-llm" />`}
        />
        <${PromptSettingsModal}
          open=${globalPromptOpen}
          prompts=${globalPromptSettings?.llm_answer_prompts || CHAT_PROMPT_DEFAULTS}
          saving=${globalPromptSaving}
          onClose=${() => setGlobalPromptOpen(false)}
          onSave=${saveGlobalPromptSettings}
        />
        <${ErrorPanel} error=${store.error} />
        ${!booted && !store.error ? html`<div className="muted" style=${{ padding: '0 16px 16px' }}>Инициализация React UI…</div>` : null}
      </div>
    `;
  }

  const root = document.getElementById('react-root');
  if (!root) {
    console.error('[React] Root container #react-root was not found');
    return;
  }
  ReactDOM.createRoot(root).render(html`<${ChatApp} />`);
})();
