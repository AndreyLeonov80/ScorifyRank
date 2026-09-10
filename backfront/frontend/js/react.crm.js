/* React CRM page powered by legacy crmApp store */
'use strict';

(function mountReactCrmPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.crmApp) {
    console.error('[React] crmApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { HtmlBlock, StatusPanel, ErrorBox, PageHeader, TablePaginationFooter, LoadingNotice, DealActionButton, cleanDealText, firstNonEmpty } = window.BackfrontReactShared;

  function CrmFieldCell({ store, row, fieldType }) {
    const values = store.outreachFieldValues(row, fieldType);
    if (!values.length) return html`<span className="subtle">—</span>`;
    return html`
      <div className="crm-field-stack">
        ${values.map((value) => {
          const busyKey = store.outreachButtonKey(row, fieldType, value);
          const busy = store.outreachBusyKey === busyKey;
          const selected = store.isOutreachSelected(row, fieldType, value);
          const displayValue = fieldType === 'message' ? store.previewText(value, 220) : value;
          return html`
            <span className=${`crm-field-chip ${selected ? 'crm-field-chip-selected' : ''}`} key=${`${fieldType}:${value}`}>
              <span>${displayValue}</span>
              <button
                type="button"
                className=${`field-add-btn ${selected ? 'field-remove-btn' : ''}`}
                title=${selected ? `Удалить ${store.outreachFieldLabel(fieldType)} из enReach` : `Добавить ${store.outreachFieldLabel(fieldType)} в enReach`}
                disabled=${busy}
                onClick=${() => store.toggleOutreachField(row, fieldType, value)}
              >
                ${busy ? '…' : (selected ? '-' : '+')}
              </button>
            </span>
          `;
        })}
      </div>
    `;
  }

  function CrmRow({ store, row }) {
    const contactName = firstNonEmpty([row.full_name, row.sender_name, row.sender_username, store.senderLabel(row)]);
    const company = Array.isArray(row.companies) ? (row.companies[0] || '') : '';
    const dealPayload = {
      title: firstNonEmpty([
        contactName ? `CRM: ${contactName}` : '',
        company ? `CRM: ${company}` : '',
        row.lead ? `CRM: ${row.lead}` : '',
        `CRM signal #${row.message_id}`,
      ]),
      stage: 'lead',
      score: 35,
      probability: 0.25,
      contact_key: firstNonEmpty([row.sender_username, row.sender_name, `${row.lead}:${row.message_id}`]),
      contact_name: contactName,
      company,
      source: 'crm',
      source_chat: firstNonEmpty([row.lead, row.source_selector]),
      source_message_id: row.message_id != null ? String(row.message_id) : '',
      need: cleanDealText(row.text || '', 4000),
      product_match: [
        row.job_title,
        row.city,
        ...(Array.isArray(row.companies) ? row.companies : []),
      ].filter(Boolean).join(' · '),
      next_action: 'Квалифицировать CRM-сигнал и подготовить первое сообщение',
      notes: `Создано из CRM. Источники: ${store.matchSourcesLabel(row) || '—'}`,
    };
    return html`
      <tr>
        <td>
          <div>${window.fmtDate ? window.fmtDate(row.date_utc, true) : (row.date_utc || '—')}</div>
          <div className="subtle">#${row.message_id}</div>
        </td>
        <td>
          <div className="font-semibold">${row.lead}</div>
          <div className="subtle cell-text">${store.senderLabel(row)}</div>
          <div className="subtle cell-text">${store.leadLabel(row)}</div>
        </td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="fio" /></td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="job_title" /></td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="company" /></td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="contact" /></td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="city" /></td>
        <td className="cell-text"><${CrmFieldCell} store=${store} row=${row} fieldType="message" /></td>
        <td className="cell-text">
          <div>${store.matchSourcesLabel(row)}</div>
          ${store.fieldProvenanceLabel(row)
            ? html`<div className="subtle cell-text">${store.fieldProvenanceLabel(row)}</div>`
            : null}
        </td>
        <td>
          <${DealActionButton}
            payload=${dealPayload}
            label="Создать сделку"
            title="Создать сделку из CRM-сигнала"
          />
        </td>
      </tr>
    `;
  }

  function CrmPage() {
    const store = useLegacyStore(window.crmApp);
    const [booted, setBooted] = React.useState(false);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] CRM init failed:', error);
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
          title="CRM"
          subtitle="Автоматическое распознавание ФИО, должностей, компаний, телефонов, email и городов прямо из сообщений."
          active="crm"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Поиск по ФИО, компании, телефону, email, тексту…"
              value=${store.ui.query}
              onChange=${(e) => {
                store.ui.query = e.target.value;
                debounceReload();
              }}
            />
            <input
              className="input"
              style=${{ minWidth: '220px' }}
              type="text"
              placeholder="Фильтр по чату или selector…"
              value=${store.ui.leadFilter}
              onChange=${(e) => {
                store.ui.leadFilter = e.target.value;
                debounceReload();
              }}
            />
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
            <button className="btn" onClick=${() => store.triggerRefresh()} disabled=${store.refreshing}>
              ${store.refreshing ? 'Запуск…' : 'Обновить CRM'}
            </button>
          </div>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.autoRefreshEnabled} onChange=${(e) => { store.ui.autoRefreshEnabled = e.target.checked; store.saveAutoRefreshConfig(); }} /> Автообновление</label>
            <select
              className="select"
              value=${String(store.ui.autoRefreshIntervalSec)}
              onChange=${(e) => {
                store.ui.autoRefreshIntervalSec = Number(e.target.value);
                store.saveAutoRefreshConfig();
              }}
            >
              <option value="30">30 сек</option>
              <option value="60">1 мин</option>
              <option value="300">5 мин</option>
              <option value="900">15 мин</option>
              <option value="1800">30 мин</option>
            </select>
            <span className="subtle">В кеше: <strong>${store.cacheStatus?.total_rows ?? store.totalRows}</strong></span>
          </div>
        </section>

        <section className="toolbar" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyName} onChange=${(e) => { store.ui.onlyName = e.target.checked; store.resetPage(); }} /> Только с ФИО</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyPhone} onChange=${(e) => { store.ui.onlyPhone = e.target.checked; store.resetPage(); }} /> Только с телефонами</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyEmail} onChange=${(e) => { store.ui.onlyEmail = e.target.checked; store.resetPage(); }} /> Только с email</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyCompany} onChange=${(e) => { store.ui.onlyCompany = e.target.checked; store.resetPage(); }} /> Только с компаниями</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyCity} onChange=${(e) => { store.ui.onlyCity = e.target.checked; store.resetPage(); }} /> Только с городом</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.onlyTitle} onChange=${(e) => { store.ui.onlyTitle = e.target.checked; store.resetPage(); }} /> Только с должностью</label>
          </div>
        </section>

        <${ErrorBox} error=${store.error} tag="section" />

        <section className="panel" style=${{ padding: '14px 16px' }}>
          <${StatusPanel} config=${store.statusPanelConfig()} />
        </section>

        <section className="panel">
          <div className="section-title">Распознанные CRM-элементы</div>
          <div className="section-subtitle subtle">Показываются только те сообщения, где нашлось хотя бы одно CRM-поле.</div>

          <div className="table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Собираю CRM-поля из кеша…" details="CRM читает уже сохранённые сообщения и результаты OCR; Telegram-запросы нужны только фоновым задачам." />` : null}
            ${!store.loading && store.filteredRows().length === 0 ? html`<div className="empty">Под текущие фильтры CRM-записи не нашлись.</div>` : null}

            ${store.filteredRows().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Чат / Sender</th>
                    <th>ФИО</th>
                    <th>Должность</th>
                    <th>Компании</th>
                    <th>Контакты</th>
                    <th>Город</th>
                    <th>Сообщение</th>
                    <th>Источник</th>
                    <th>Сделка</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.pagedRows().map((row) => html`<${CrmRow} key=${`${row.lead}:${row.message_id}`} store=${store} row=${row} />`)}
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
      console.error('[React] #app root was not found for CRM page');
      return;
    }

    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${CrmPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
