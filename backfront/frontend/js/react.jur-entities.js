/* React jur entities page powered by jurEntitiesApp store */
'use strict';

(function mountReactJurEntitiesPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.jurEntitiesApp) {
    console.error('[React] jurEntitiesApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, OutreachToggle, LoadingNotice, DealActionButton, cleanDealText, firstNonEmpty } = window.BackfrontReactShared;

  function JurEntityRow({ store, row }) {
    const payload = {
      field_type: 'jur_entity',
      field_label: 'ЮР.ЛИЦА.',
      value: String(row.file_name || row.file_key || '').trim(),
      lead: store.channel || 'baza_directorov',
      source_selector: store.channel || 'baza_directorov',
      date_utc: row.message_date_utc,
      text: row.caption_preview || row.structure_summary || row.file_name,
    };
    const captionPayload = {
      field_type: 'message',
      field_label: 'Сообщение',
      value: String(row.caption_preview || '').trim(),
      lead: store.channel || 'baza_directorov',
      source_selector: store.channel || 'baza_directorov',
      date_utc: row.message_date_utc,
      text: row.caption_preview,
    };
    const captionText = String(row.caption_preview || row.structure_summary || row.file_name || '').trim();
    const dealPayload = {
      title: firstNonEmpty([
        row.file_name ? `ЮР.ЛИЦА: ${row.file_name}` : '',
        captionText ? `ЮР.ЛИЦА: ${captionText}` : '',
        row.file_key ? `ЮР.ЛИЦА: ${row.file_key}` : '',
      ]),
      stage: 'lead',
      score: row.parser_enabled ? 35 : 22,
      probability: row.parser_enabled ? 0.24 : 0.16,
      contact_key: firstNonEmpty([row.file_key, row.file_name]),
      contact_name: row.file_name || '',
      source: 'jur_entities',
      source_chat: store.channel || 'baza_directorov',
      source_message_id: firstNonEmpty([row.message_id, row.message_date_utc, row.file_key]),
      need: cleanDealText(captionText, 4000),
      product_match: [
        row.structure_summary ? `Структура: ${row.structure_summary}` : '',
        row.parser_enabled ? 'В парсере' : 'Не в парсере',
      ].filter(Boolean).join(' · '),
      next_action: 'Проверить XLSX как источник компаний и выбрать подходящий сценарий сделки',
      notes: `Создано из ЮР.ЛИЦА. Файл: ${row.file_name || row.file_key || '—'}`,
    };
    return html`
      <tr>
        <td>${row.message_date_utc ? (window.fmtDate ? window.fmtDate(row.message_date_utc, true) : row.message_date_utc) : '—'}</td>
        <td>
          <div className="title-main">${row.file_name}</div>
          <div className="meta"><code>${row.file_key}</code></div>
        </td>
        <td>${store.formatBytes(row.size_bytes)}</td>
        <td>
          ${row.file_path ? html`
            <a className="btn" href=${row.file_path} target="_blank" rel="noreferrer">Открыть</a>
          ` : html`<span className="subtle">—</span>`}
        </td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
            <${OutreachToggle} store=${store} payload=${captionPayload} title="Добавить подпись в enReach" />
            <div className="preview">${row.caption_preview || '—'}</div>
          </div>
        </td>
        <td>
          <div className="structure-cell">
            <span className=${`badge ${store.structureBadgeClass(row)}`}>${store.structureBadgeText(row)}</span>
            <div className="meta structure-summary">${row.structure_summary || 'Структура ещё не определена'}</div>
          </div>
        </td>
        <td><span className=${`badge ${store.parserBadgeClass(row)}`}>${store.parserBadgeText(row)}</span></td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            <${OutreachToggle} store=${store} payload=${payload} title="Добавить ЮР.ЛИЦА. в enReach" />
            <${DealActionButton}
              payload=${dealPayload}
              label="Создать сделку"
              title="Создать сделку из XLSX/подписи ЮР.ЛИЦА."
            />
            ${!row.parser_enabled ? html`
              <button
                className="btn btn-active"
                onClick=${() => store.addToParser(row)}
                disabled=${store.isRowBusy(row, 'add')}
              >
                ${store.isRowBusy(row, 'add') ? 'Добавление…' : 'Добавить в парсер'}
              </button>
            ` : html`
              <button
                className="btn btn-danger"
                onClick=${() => store.removeFromParser(row)}
                disabled=${store.isRowBusy(row, 'remove')}
              >
                ${store.isRowBusy(row, 'remove') ? 'Удаление…' : 'Удалить из парсера'}
              </button>
            `}
          </div>
        </td>
      </tr>
    `;
  }

  function JurEntitiesPage() {
    const store = useLegacyStore(window.jurEntitiesApp);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 200);

    React.useEffect(() => {
      store.init?.().catch((error) => {
        console.error('[React] Jur entities init failed:', error);
        store.error = String(error?.message || error);
      });
    }, [store]);

    return html`
      <div className="page">
        <${PageHeader}
          title="ЮР.ЛИЦА."
          subtitle="Excel-файлы из канала baza_directorov. Таблица отсортирована по убыванию даты, с управлением добавлением в парсер."
          active="jur-entities"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Поиск по названию файла или подписи…"
              value=${store.ui.query}
              onChange=${(e) => { store.ui.query = e.target.value; debounceReload(); }}
            />
            <select
              className="select"
              value=${String(store.ui.pageSize)}
              onChange=${(e) => { store.ui.pageSize = Number(e.target.value); store.resetPage(); }}
            >
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <button className="btn" onClick=${() => store.syncFiles()} disabled=${store.syncing}>
              ${store.syncing ? 'Синхронизация…' : 'Скачать XLSX'}
            </button>
          </div>

          <div className="toolbar-group">
            <span className="badge badge-pending">${store.channel}</span>
            <span className="subtle">Последняя синхронизация: <strong>${store.syncLabel()}</strong></span>
          </div>
        </section>

        <section className="toolbar" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group segmented">
            <button className=${`btn ${store.ui.parserFilter === 'all' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setParserFilter('all')}>Все</button>
            <button className=${`btn ${store.ui.parserFilter === 'selected' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setParserFilter('selected')}>В парсере</button>
            <button className=${`btn ${store.ui.parserFilter === 'unselected' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setParserFilter('unselected')}>Не в парсере</button>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Файлы XLSX</div>
          <div className="section-subtitle">Канал: <code>${store.channel}</code>. Новые файлы скачиваются по кнопке выше.</div>
          <div className="table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Загружаю список XLSX-файлов…" details="ЮР.ЛИЦА. читает локальный кеш файлов; скачивание из Telegram уважает общие лимиты и cooldown." />` : null}
            ${!store.loading && store.rows.length === 0 ? html`<div className="empty">Пока нет загруженных XLSX-файлов. Нажмите «Скачать XLSX».</div>` : null}
            ${store.rows.length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th style=${{ width: '190px' }}>Дата</th>
                    <th>Файл</th>
                    <th style=${{ width: '120px' }}>Размер</th>
                    <th style=${{ width: '140px' }}>Файл</th>
                    <th>Подпись</th>
                    <th style=${{ width: '220px' }}>Структура</th>
                    <th style=${{ width: '140px' }}>Статус</th>
                    <th style=${{ width: '220px' }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.pagedRows().map((row) => html`<${JurEntityRow} key=${row.file_key} store=${store} row=${row} />`)}
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

        <${ErrorBox} error=${store.error || store.syncError} />
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Jur Entities page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${JurEntitiesPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
