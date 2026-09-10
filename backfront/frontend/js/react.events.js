/* React events page powered by legacy eventsApp store */
'use strict';

(function mountReactEventsPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.eventsApp) {
    console.error('[React] eventsApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { HtmlBlock, StatusPanel, ErrorBox, PageHeader, TablePaginationFooter, OutreachToggle, LoadingNotice, DealActionButton, cleanDealText, firstNonEmpty } = window.BackfrontReactShared;

  function EventRow({ store, row }) {
    const payload = {
      field_type: 'event_message',
      field_label: 'Мероприятие',
      value: String(row.text || '').trim(),
      lead: row.lead,
      source_selector: row.source_selector,
      sender_name: row.sender_name,
      sender_username: row.sender_username,
      message_id: row.message_id,
      date_utc: row.date_utc,
      text: row.text,
    };
    const dealPayload = {
      title: firstNonEmpty([
        row.event_date ? `Мероприятие ${row.event_date}: ${row.lead}` : '',
        row.lead ? `Мероприятие: ${row.lead}` : '',
        `Мероприятие #${row.message_id}`,
      ]),
      stage: 'lead',
      score: row.event_date ? 45 : 30,
      probability: row.event_date ? 0.3 : 0.2,
      contact_key: firstNonEmpty([row.sender_username, row.sender_name, `${row.lead}:${row.message_id}`]),
      contact_name: firstNonEmpty([row.sender_name, row.sender_username]),
      source: 'events',
      source_chat: firstNonEmpty([row.lead, row.source_selector]),
      source_message_id: row.message_id != null ? String(row.message_id) : '',
      need: cleanDealText(row.text || '', 4000),
      product_match: [
        row.event_date ? `Дата события: ${row.event_date}` : '',
        Array.isArray(row.matched_keywords) ? `Ключевые слова: ${row.matched_keywords.join(', ')}` : '',
      ].filter(Boolean).join(' · '),
      next_action: 'Проверить мероприятие как повод для касания и выбрать релевантный оффер',
      notes: `Создано из Мероприятий. Дата LLM: ${row.event_date || 'не найдена'}`,
    };
    return html`
      <tr>
        <td>
          <div><strong>${row.lead}</strong></div>
          <div className="subtle">${row.source_selector || '—'}</div>
        </td>
        <td><span className="badge">${store.keywordsLabel(row)}</span></td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
            <${OutreachToggle} store=${store} payload=${payload} title="Добавить мероприятие в enReach" />
            <div className="message-text">${store.previewText(row.text)}</div>
          </div>
        </td>
        <td>
          <div><strong>${row.event_date || '—'}</strong></div>
          ${row.event_date_source ? html`<div className="subtle">${row.event_date_source === 'openrouter:none' ? 'дата не найдена LLM' : 'OpenRouter LLM'}</div>` : html`<div className="subtle">ожидает LLM</div>`}
        </td>
        <td>${row.sender_username ? `@${row.sender_username}` : (row.sender_name || '—')}</td>
        <td>${window.fmtDate ? window.fmtDate(row.date_utc, true) : (row.date_utc || '—')}</td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <${DealActionButton}
            payload=${dealPayload}
            label="Создать сделку"
            title="Создать сделку из события"
          />
            <button
              type="button"
              className="btn btn-danger"
              disabled=${store.deletingKey === store.eventRowKey(row)}
              onClick=${() => store.deleteEvent(row)}
              title="Удалить это мероприятие и такие же сообщения от этого источника"
            >
              ${store.deletingKey === store.eventRowKey(row) ? 'Удаляю…' : 'Удалить'}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  function EventsPage() {
    const store = useLegacyStore(window.eventsApp);
    const [booted, setBooted] = React.useState(false);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Events init failed:', error);
          store.error = String(error?.message || error);
        })
        .finally(() => {
          if (!cancelled) setBooted(true);
        });
      return () => {
        cancelled = true;
      };
    }, [store]);

    return html`
      <div className="page">
        <${PageHeader}
          title="Мероприятия"
          subtitle="Сообщения из разных каналов, где встречаются ключевые слова про события и мероприятия."
          active="events"
        />

        <section className="panel">
          <div className="settings-grid">
            <div>
              <div className="subtle" style=${{ marginBottom: '8px' }}>Ключевые слова. По одному в строке или через запятую.</div>
              <textarea
                className="textarea"
                value=${store.keywordsText}
                placeholder="мероприятие&#10;вебинар&#10;конференция"
                onChange=${(e) => { store.keywordsText = e.target.value; }}
              />
              <div className="toolbar-group" style=${{ marginTop: '12px' }}>
                <button className="btn btn-active" onClick=${() => store.saveKeywords()} disabled=${store.saving}>
                  ${store.saving ? 'Сохранение…' : 'Сохранить слова'}
                </button>
                <button className="btn" onClick=${() => store.triggerRefresh()} disabled=${store.refreshing}>
                  ${store.refreshing ? 'Запуск…' : 'Обновить таблицу'}
                </button>
              </div>
            </div>

            <div>
              <div className="toolbar-group">
                <input className="input" style=${{ minWidth: '260px' }} type="text" placeholder="Общий фильтр по тексту…" value=${store.ui.filter} onChange=${(e) => { store.ui.filter = e.target.value; debounceReload(); }} />
                <input className="input" style=${{ minWidth: '220px' }} type="text" placeholder="Фильтр по каналу…" value=${store.ui.leadFilter} onChange=${(e) => { store.ui.leadFilter = e.target.value; debounceReload(); }} />
                <input className="input" style=${{ minWidth: '220px' }} type="text" placeholder="Фильтр по отправителю…" value=${store.ui.senderFilter} onChange=${(e) => { store.ui.senderFilter = e.target.value; debounceReload(); }} />
                <input className="input" style=${{ minWidth: '220px' }} type="text" placeholder="Фильтр по ключевому слову…" value=${store.ui.keywordFilter} onChange=${(e) => { store.ui.keywordFilter = e.target.value; debounceReload(); }} />
                <input className="input" type="date" value=${store.ui.dateFrom} onChange=${(e) => { store.ui.dateFrom = e.target.value; store.resetPage(); }} />
                <input className="input" type="date" value=${store.ui.dateTo} onChange=${(e) => { store.ui.dateTo = e.target.value; store.resetPage(); }} />
                <select className="select" value=${String(store.ui.pageSize)} onChange=${(e) => { store.ui.pageSize = Number(e.target.value); store.resetPage(); }}>
                  <option value="5">5 строк</option>
                  <option value="10">10 строк</option>
                  <option value="20">20 строк</option>
                  <option value="50">50 строк</option>
                </select>
                <select className="select" value=${String(store.ui.limit)} onChange=${(e) => { store.ui.limit = Number(e.target.value); store.resetPage(); }}>
                  <option value="100">100 сообщений</option>
                  <option value="300">300 сообщений</option>
                  <option value="500">500 сообщений</option>
                  <option value="1000">1000 сообщений</option>
                </select>
                <label className="chip"><input type="checkbox" checked=${store.ui.autoRefreshEnabled} onChange=${(e) => { store.ui.autoRefreshEnabled = e.target.checked; store.saveAutoRefreshConfig(); }} /> Автообновление</label>
                <select className="select" value=${String(store.ui.autoRefreshIntervalSec)} onChange=${(e) => { store.ui.autoRefreshIntervalSec = Number(e.target.value); store.saveAutoRefreshConfig(); }}>
                  <option value="30">30 сек</option>
                  <option value="60">1 мин</option>
                  <option value="300">5 мин</option>
                  <option value="900">15 мин</option>
                  <option value="1800">30 мин</option>
                </select>
              </div>
              <div className="subtle" style=${{ marginTop: '12px' }}>
                Активные слова: <strong>${store.keywords.length ? store.keywords.join(', ') : '—'}</strong>
              </div>
            </div>
          </div>
        </section>

        <section className="panel" style=${{ padding: '14px 16px' }}>
          <${StatusPanel} config=${store.statusPanelConfig()} />
          <${HtmlBlock} htmlString=${store.renderEventDateStatusPanel()} />
        </section>

        <section className="panel">
          <div className="table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Загружаю сообщения по мероприятиям…" details="Страница читает кеш мероприятий; если кеш обновляется, прогресс виден в статусе анализа и Dashboard." />` : null}
            ${!store.loading && store.pagedRows().length === 0 ? html`<div className="empty">Совпадений по текущим ключевым словам пока нет.</div>` : null}

            ${store.pagedRows().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Канал</th>
                    <th>Ключевые слова</th>
                    <th>Сообщение</th>
                    <th>Дата мероприятия</th>
                    <th>Отправитель</th>
                    <th>Дата сообщения</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.pagedRows().map((row) => html`<${EventRow} key=${`${row.lead}-${row.message_id}`} store=${store} row=${row} />`)}
                </tbody>
              </table>
            ` : null}
          </div>
          <${TablePaginationFooter}
            rangeText=${store.visibleRangeText()}
            page=${store.ui.page}
            totalPages=${store.totalPages()}
            pageWindow=${store.pageWindow()}
            onPrev=${() => store.prevPage()}
            onNext=${() => store.nextPage()}
            onGo=${(page) => store.goToPage(page)}
            paginationClassName="nav"
          />
        </section>

        <${ErrorBox} error=${store.error} />
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Events page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${EventsPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
