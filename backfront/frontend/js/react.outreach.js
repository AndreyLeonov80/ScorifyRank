/* React enReach page powered by outreachApp store */
'use strict';

(function mountReactOutreachPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.outreachApp) {
    console.error('[React] outreachApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, LoadingNotice, DealActionButton } = window.BackfrontReactShared;

  function OutreachRow({ store, row }) {
    const dealUrl = row.deal_id ? `/deals.html?query=${encodeURIComponent(row.deal_title || row.deal_id)}` : '';
    return html`
      <tr>
        <td>
          <div>${window.fmtDate ? window.fmtDate(row.created_at, true) : (row.created_at || '—')}</div>
          <div className="subtle">источник: ${window.fmtDate ? window.fmtDate(row.date_utc, true) : (row.date_utc || '—')}</div>
        </td>
        <td>
          <span className="badge badge-new">${row.field_label || store.fieldTypeLabel(row.field_type)}</span>
        </td>
        <td className="cell-text value-cell">${row.value}</td>
        <td className="cell-text">
          <div className="font-semibold">${row.lead || '—'}</div>
          <div className="subtle">${row.source_selector || ''}</div>
          <div className="subtle">${store.senderLabel(row)}</div>
          ${row.message_id ? html`<div className="subtle">#${row.message_id}</div>` : null}
          ${row.deal_id ? html`
            <div className="subtle" style=${{ marginTop: '6px' }}>
              Сделка: <strong>${row.deal_title || row.deal_id}</strong>
              ${row.deal_stage_label ? html` · ${row.deal_stage_label}` : null}
            </div>
          ` : html`<div className="subtle" style=${{ marginTop: '6px' }}>Сделка ещё не создана</div>`}
        </td>
        <td className="cell-text">${store.previewText(row.text, 260)}</td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
            ${row.deal_id ? html`
              <a className="btn btn-active" href=${dealUrl} title="Открыть страницу сделок">
                Открыть сделку
              </a>
            ` : html`
              <${DealActionButton}
                endpoint=${`/api/payme/deals/from-outreach/${encodeURIComponent(row.id)}`}
                payload=${{}}
                label="Создать сделку"
                title="Создать сделку из enReach"
                onDone=${() => store.loadRows(true)}
              />
            `}
            <button
              type="button"
              className="btn btn-active"
              disabled=${store.creatingSequenceId === row.id}
              onClick=${() => store.createOutreachSequence(row)}
              title="Подготовить ручную outReach-последовательность без автоотправки"
            >
              ${store.creatingSequenceId === row.id ? 'Готовлю…' : 'Создать outReach'}
            </button>
            <button
              type="button"
              className="btn"
              disabled=${store.deletingId === row.id}
              onClick=${() => store.deleteItem(row)}
            >
              ${store.deletingId === row.id ? 'Удаляю…' : 'Удалить'}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  function OutreachPage() {
    const store = useLegacyStore(window.outreachApp);
    const [booted, setBooted] = React.useState(false);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] enReach init failed:', error);
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
          title="enReach"
          subtitle="Очередь выбранных CRM-полей, сообщений, контактов и сущностей для будущего анализа, воронок и сделок."
          active="outreach"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              type="text"
              placeholder="Поиск по значению, чату, sender или сообщению…"
              value=${store.ui.query}
              onChange=${(e) => {
                store.ui.query = e.target.value;
                debounceReload();
              }}
            />
            <select
              className="select"
              value=${store.ui.fieldType}
              onChange=${(e) => {
                store.ui.fieldType = e.target.value;
                store.resetPage();
              }}
            >
              <option value="all">Все поля</option>
              <option value="fio">ФИО</option>
              <option value="job_title">Должность</option>
              <option value="company">Компании</option>
              <option value="contact">Контакты</option>
              <option value="city">Город</option>
              <option value="message">Сообщение</option>
              <option value="event_message">Мероприятие</option>
              <option value="chat">Чат</option>
              <option value="media">Media</option>
              <option value="telegram_contact">Контакт</option>
              <option value="import_dialog">Import</option>
              <option value="jur_entity">ЮР.ЛИЦА.</option>
            </select>
            <select
              className="select"
              value=${String(store.ui.pageSize)}
              onChange=${(e) => {
                store.ui.pageSize = Number(e.target.value);
                store.resetPage();
              }}
            >
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <button className="btn" onClick=${() => store.loadRows(true)} disabled=${store.loading}>
              ${store.loading ? 'Обновляю…' : 'Обновить enReach'}
            </button>
          </div>
          <div className="subtle">В очереди: <strong>${store.totalRows}</strong></div>
        </section>

        <${ErrorBox} error=${store.error} tag="section" />

        <section className="panel">
          <div className="section-title">Элементы для enReach</div>
          <div className="section-subtitle">
            Нажимайте <strong>+</strong> на страницах CRM, Чаты, Sync, Мероприятия, Media, Контакты, Import или ЮР.ЛИЦА. Значения попадут сюда и дальше будут доступны для анализа первых сообщений и воронки сделок.
          </div>

          <div className="table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Загружаю очередь enReach…" details="Очередь enReach читается из локального runtime-кеша и не должна блокироваться Telegram." />` : null}
            ${!store.loading && store.filteredRows().length === 0 ? html`<div className="empty">Пока нет элементов в enReach. Нажмите + рядом с нужным сообщением, контактом или CRM-полем.</div>` : null}

            ${store.filteredRows().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Добавлено</th>
                    <th>Поле</th>
                    <th>Значение</th>
                    <th>Контекст</th>
                    <th>Первое сообщение</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.filteredRows().map((row) => html`<${OutreachRow} key=${row.id} store=${store} row=${row} />`)}
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
          />
        </section>
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for enReach page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${OutreachPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
