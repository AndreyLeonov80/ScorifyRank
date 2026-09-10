/* Chat layout components for React index page */
'use strict';

(function initReactIndexChat() {
  window.BackfrontIndexChat = function BackfrontIndexChat({ html, LoadingNotice, MessageBubble, openChatAnalysisModal }) {
    function ChatHeader({ store }) {
      return html`
        <div className="chat-main-header row">
          <div>
            <div className="chat-main-title">${store.current ? `Чат: ${store.current.name}` : 'Выберите чат слева'}</div>
            <div className="muted">${store.current ? `${store.current.count || 0} сообщений · данные из backend-кеша` : 'Сообщения и выбор для LLM появятся здесь.'}</div>
          </div>
          <div className="row">
            <button
              className=${`btn ${!store.current ? 'hidden' : ''}`}
              onClick=${() => openChatAnalysisModal(store)}
              title="Открыть настройки и историю анализа чата"
            >
              Анализ чата
            </button>
            <button className=${`btn ${!store.current ? 'hidden' : ''}`} onClick=${() => store.reloadMessages()} title="Обновить чат">⟳ Обновить</button>
            <button
              className=${`btn ${!store.current ? 'hidden' : ''}`}
              onClick=${() => store.toggleStream()}
              title=${store.ui.autoStream ? 'Отключить автообновление' : 'Включить автообновление'}
            >
              ${store.ui.autoStream ? 'Стрим: вкл' : 'Стрим: выкл'}
            </button>
          </div>
        </div>
      `;
    }

    function ChatMessagesWindow({ store }) {
      return html`
        <div id="chatBox" className="chat-box" onScroll=${(event) => store.handleChatScroll?.(event)}>
          ${store.current ? html`
            <div className="chat-scroll-meter">
              <div className="row">
                <span>${store.messageScrollProgressText?.()}</span>
                <span>${store.messagesLoadingMore ? 'Подгружаю из кеша…' : `${store.messageScrollProgressPercent?.()}%`}</span>
              </div>
              <div className="chat-scroll-meter-track">
                <div className="chat-scroll-meter-bar" style=${{ width: `${Math.max(1, Number(store.messageScrollProgressPercent?.() || 0))}%` }}></div>
              </div>
            </div>
          ` : null}
          ${store.loading && store.current ? html`<${LoadingNotice} message="Загрузка сообщений…" details=${`Сообщения читаются из JSONL/DuckDB-кеша. ${store.messageLoadEtaText?.() || ''}`} className="muted" compact=${true} />` : null}
          ${store.messagesLoadingMore ? html`<${LoadingNotice} message="Подгружаю предыдущие сообщения…" details=${`Берём следующую порцию из локального backend-кеша. ${store.messageLoadEtaText?.() || ''}`} className="muted" compact=${true} />` : null}
          ${!store.current ? html`<div className="chat-empty"><div><strong>Выберите источник слева</strong><br/><span>Здесь будет живая история сообщений и выбор сообщений для LLM-анализа.</span></div></div>` : null}
          ${!store.loading && store.current && store.messages.length === 0 ? html`<div className="muted">Сообщений пока нет.</div>` : null}
          ${store.visibleMessages().map((message) => html`<${MessageBubble} key=${message.id} store=${store} message=${message} />`)}
        </div>
      `;
    }

    function ChatComposer({ store }) {
      const resizeComposer = (textarea) => {
        if (!textarea) return;
        textarea.style.height = 'auto';
        const nextHeight = Math.min(180, Math.max(48, textarea.scrollHeight || 48));
        textarea.style.height = `${nextHeight}px`;
      };
      const submit = () => {
        const input = document.getElementById('msgInput');
        resizeComposer(input);
        store.sendMessage();
      };
      return html`
        <div className="chat-composer">
          <textarea
            id="msgInput"
            className="chat-message-input"
            rows="1"
            placeholder="Введите сообщение…"
            onInput=${(event) => resizeComposer(event.currentTarget)}
            onKeyDown=${(event) => {
              if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
              event.preventDefault();
              submit();
            }}
          ></textarea>
          <button className="btn chat-send-button" onClick=${submit} title="Отправить">Отправить</button>
        </div>
      `;
    }

    return { ChatHeader, ChatMessagesWindow, ChatComposer };
  };
})();
