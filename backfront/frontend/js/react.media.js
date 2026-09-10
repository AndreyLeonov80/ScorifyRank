/* React media page powered by legacy mediaApp store */
'use strict';

(function mountReactMediaPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.mediaApp) {
    console.error('[React] mediaApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { HtmlBlock, StatusPanel, ErrorBox, PageHeader, TablePaginationFooter, TelegramCooldownBanner, LoadingNotice, DealActionButton, cleanDealText, firstNonEmpty } = window.BackfrontReactShared;

  function LeadConfigRow({ store, lead }) {
    return html`
      <tr>
        <td>
          <div className="font-semibold">${lead.name}</div>
          <div className="subtle">${lead.sync_status || ''}</div>
        </td>
        <td>${lead.source_selector || lead.name}</td>
        <td>
          <span className=${`badge ${store.isMediaEnabled(lead) ? 'badge-active' : 'badge-pending'}`}>
            ${store.isMediaEnabled(lead) ? 'Включено' : 'Выключено'}
          </span>
          ${store.isMediaEnabled(lead) ? html`
            <div style=${{ marginTop: '8px' }}>
              <span className=${`badge ${store.mediaLeadStatusClass(lead)}`}>${store.mediaLeadStatusLabel(lead)}</span>
            </div>
            <div className="subtle" style=${{ marginTop: '6px' }}>${store.mediaLeadStatusDetails(lead)}</div>
          ` : null}
        </td>
        <td>
          <div className="nav">
            ${!store.isMediaEnabled(lead) ? html`
              <button className="btn" onClick=${() => store.enableMediaLead(lead)} disabled=${store.isMediaActionBusy(lead, 'enable')}>
                ${store.isMediaActionBusy(lead, 'enable') ? '…' : 'Добавить'}
              </button>
            ` : html`
              <button className="btn btn-active" onClick=${() => store.enableMediaLead(lead)} disabled=${store.isMediaActionBusy(lead, 'enable')}>
                ${store.isMediaActionBusy(lead, 'enable') ? '…' : 'Переобработать'}
              </button>
              <button className="btn" onClick=${() => store.disableMediaLead(lead)} disabled=${store.isMediaActionBusy(lead, 'disable')}>
                ${store.isMediaActionBusy(lead, 'disable') ? '…' : 'Убрать'}
              </button>
            `}
            <button className="btn btn-danger" onClick=${() => store.clearMediaLead(lead)} disabled=${store.isMediaActionBusy(lead, 'clear')}>
              ${store.isMediaActionBusy(lead, 'clear') ? '…' : 'Очистить media'}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  function MediaAssetRow({ store, row }) {
    const previewText = store.imageTextPreview(row);
    const cachedText = store.imageTextCache(row);
    const expanded = store.imageTextExpanded(row);
    const loading = store.imageTextLoading(row);
    const error = store.imageTextError(row);
    const outreachBusy = store.isMediaOutreachBusy(row);
    const outreachSelected = store.isMediaOutreachSelected(row);
    const openHref = row.image_exists === false ? (row.text_path || row.media_path) : row.media_path;
    const outreachLabel = row.recognized
      ? (outreachBusy ? '…' : (outreachSelected ? '-' : '+'))
      : '+';
    const dealPayload = row.recognized ? async () => {
      const data = await store.ensureImageTextLoaded(row);
      const text = String(data?.text || row.ocr_preview || '').trim();
      if (!text) {
        throw new Error('OCR-текст пока пустой, сделку создать не из чего');
      }
      const categories = Array.isArray(data?.crm_categories) && data.crm_categories.length
        ? data.crm_categories.join(', ')
        : store.mediaOcrCategoryLabel(row);
      return {
        title: firstNonEmpty([
          row.lead ? `Media OCR: ${row.lead}` : '',
          row.file_name ? `Media OCR: ${row.file_name}` : '',
          text,
        ]),
        stage: 'lead',
        score: categories && categories !== 'Сообщение' ? 35 : 22,
        probability: categories && categories !== 'Сообщение' ? 0.24 : 0.16,
        contact_key: firstNonEmpty([row.lead, row.media_path, row.text_path]),
        contact_name: row.lead || '',
        source: 'media',
        source_chat: row.lead || '',
        source_message_id: firstNonEmpty([row.media_path, row.text_path, row.file_name]),
        need: cleanDealText(text, 4000),
        product_match: categories ? `OCR категории: ${categories}` : '',
        next_action: 'Проверить OCR-сигнал, извлечь контакт/потребность и выбрать сценарий касания',
        notes: `Создано из Media OCR. Файл: ${row.file_name || '—'}`,
      };
    } : null;
    return html`
      <tr>
        <td>
          ${row.image_exists === false ? html`
            <a className="thumb" href=${openHref} target="_blank" rel="noopener noreferrer" style=${{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              textAlign: 'center',
              color: '#64748b',
              textDecoration: 'none',
              padding: '8px',
              boxSizing: 'border-box',
            }}>
              OCR TXT<br />без изображения
            </a>
          ` : html`
            <a href=${row.media_path} target="_blank" rel="noopener noreferrer">
              <img className="thumb" src=${row.media_path} alt=${row.file_name} loading="lazy" />
            </a>
          `}
        </td>
        <td><div className="font-semibold">${row.lead}</div></td>
        <td>
          <div className="font-semibold">${row.file_name}</div>
          <div className="subtle">${store.formatBytes(row.size_bytes || 0)}</div>
        </td>
        <td><span className=${`badge ${store.imageStatusClass(row)}`}>${store.imageStatusLabel(row)}</span></td>
        <td>
          <div className="preview" style=${{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            <div style=${{ flex: '1 1 auto', minWidth: 0 }}>
              ${previewText ? store.previewText(previewText, 220) : (row.recognized ? 'OCR доступен по запросу' : 'Текст пока не распознан')}
            </div>
            ${row.recognized ? html`
              <button
                className=${`btn btn-round ${outreachSelected ? 'btn-danger' : 'btn-active'}`}
                style=${{ padding: '4px 10px', minWidth: '34px', justifyContent: 'center', flex: '0 0 auto' }}
                title=${outreachSelected ? 'Убрать OCR-текст из enReach' : 'Добавить OCR-текст в enReach'}
                disabled=${outreachBusy || loading}
                onClick=${() => store.toggleMediaOutreach(row)}
              >
                ${outreachLabel}
              </button>
            ` : null}
          </div>
          ${expanded && cachedText?.text ? html`
            <div className="subtle" style=${{ marginTop: '8px', whiteSpace: 'pre-wrap' }}>
              ${cachedText.text}
            </div>
          ` : null}
          ${expanded && error ? html`
            <div className="subtle" style=${{ marginTop: '8px', color: '#b91c1c' }}>
              ${error}
            </div>
          ` : null}
        </td>
        <td>${window.fmtDate ? window.fmtDate(row.modified_at, true) : (row.modified_at || '—')}</td>
        <td>
          <div className="nav">
            <button
              className=${`btn btn-round ${outreachSelected ? 'btn-danger' : 'btn-active'}`}
              title=${row.recognized ? 'Добавить OCR-текст и CRM-категорию в enReach' : 'OCR ещё не готов'}
              disabled=${!row.recognized || outreachBusy || loading}
              onClick=${() => store.toggleMediaOutreach(row)}
            >
              ${outreachLabel}
            </button>
            <${DealActionButton}
              payload=${dealPayload}
              label="Создать сделку"
              title=${row.recognized ? 'Создать сделку из полного OCR-текста' : 'OCR ещё не готов'}
            />
            <a className="btn" href=${openHref} target="_blank" rel="noopener noreferrer">${row.image_exists === false ? 'Открыть TXT' : 'Открыть'}</a>
            ${row.recognized ? html`
              <button className="btn" onClick=${() => store.toggleImageText(row)} disabled=${loading}>
                ${store.imageToggleTextLabel(row)}
              </button>
            ` : null}
            ${row.text_path ? html`<a className="btn" href=${row.text_path} target="_blank" rel="noopener noreferrer">TXT</a>` : null}
          </div>
        </td>
      </tr>
    `;
  }

  function MediaPage() {
    const store = useLegacyStore(window.mediaApp);
    const [booted, setBooted] = React.useState(false);
    const debounceImageReload = useDebouncedCallback(() => store.resetPage(), 300);
    const debounceLeadReload = useDebouncedCallback(() => store.loadLeads(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Media init failed:', error);
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
          title="Media"
          subtitle="По умолчанию скачивание media выключено. Здесь можно включать его только для выбранных чатов."
          active="media"
        />
        <${TelegramCooldownBanner} />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Фильтр по чату для media…"
              value=${store.ui.leadFilter}
              onChange=${(e) => { store.ui.leadFilter = e.target.value; debounceLeadReload(); }}
            />
            <button className="btn" onClick=${() => store.loadLeads()} disabled=${store.loading}>
              ${store.loading ? 'Обновление…' : 'Обновить чаты'}
            </button>
            <button className="btn btn-danger" onClick=${() => store.clearAllMedia()} disabled=${store.ocrLoading}>
              ${store.ocrLoading ? 'Очистка…' : 'Удалить все изображения'}
            </button>
          </div>
          <div className="toolbar-group">
            <span className="subtle">Media включено для: <strong>${(store.mediaConfig?.selected_leads || []).length}</strong></span>
          </div>
        </section>

        <${ErrorBox} error=${store.error} tag="section" />

        <section className="panel" style=${{ padding: '14px 16px' }}>
          <${StatusPanel} config=${store.statusPanelConfig()} />
        </section>

        <section className="panel media-leads-panel">
          <div className="section-title">Чаты для скачивания media</div>
          <div className="section-subtitle subtle">Сохраняются только изображения. Видео и прочие файлы больше не скачиваются.</div>
          <div className="toolbar" style=${{ padding: '0 16px 12px', justifyContent: 'space-between' }}>
            <div className="toolbar-group">
              <label className="chip"><input type="checkbox" checked=${store.ui.showChannels} onChange=${(e) => { store.ui.showChannels = e.target.checked; store.reloadLeadFilters(); }} /> Каналы</label>
              <label className="chip"><input type="checkbox" checked=${store.ui.showGroups} onChange=${(e) => { store.ui.showGroups = e.target.checked; store.reloadLeadFilters(); }} /> Группы</label>
              <label className="chip"><input type="checkbox" checked=${store.ui.showPrivate} onChange=${(e) => { store.ui.showPrivate = e.target.checked; store.reloadLeadFilters(); }} /> Личные</label>
            </div>

            <div className="toolbar-group segmented">
              <button className=${`btn ${store.ui.leadMembershipFilter === 'not_added' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setLeadMembershipFilter('not_added')}>Не добавленные</button>
              <button className=${`btn ${store.ui.leadMembershipFilter === 'added' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setLeadMembershipFilter('added')}>Добавленные</button>
              <button className=${`btn ${store.ui.leadMembershipFilter === 'all' ? 'btn-active' : 'btn-ghost'}`} onClick=${() => store.setLeadMembershipFilter('all')}>Все</button>
            </div>

            <div className="toolbar-group">
              <button
                className="btn btn-active"
                onClick=${() => store.enableAllMediaLeads()}
                disabled=${store.mediaBulkAdding || store.ui.leadMembershipFilter === 'added'}
              >
                ${store.mediaBulkAdding ? 'Добавляю…' : `Добавить все${store.visibleMediaNotAddedCount() ? ` (${store.visibleMediaNotAddedCount()} видно)` : ''}`}
              </button>
            </div>

            <div className="toolbar-group">
              <span className="subtle">Фильтр: <strong>${store.leadMembershipLabel()}</strong></span>
              <span className="subtle">Показано: <strong>${store.filteredLeadRows().length}</strong></span>
            </div>
          </div>
          <div className="table-wrap">
            ${store.filteredLeadRows().length === 0 ? html`<div className="empty">Чаты не найдены.</div>` : null}
            ${store.filteredLeadRows().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Чат</th>
                    <th>Selector</th>
                    <th>Media</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.filteredLeadRows().map((lead) => html`<${LeadConfigRow} key=${lead.name} store=${store} lead=${lead} />`)}
                </tbody>
              </table>
            ` : null}
          </div>
        </section>

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Поиск по картинкам, чату или OCR…"
              value=${store.ui.query}
              onChange=${(e) => {
                store.ui.query = e.target.value;
                debounceImageReload();
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
            <button className="btn" onClick=${() => store.loadRows()} disabled=${store.loading}>
              ${store.loading ? 'Обновление…' : 'Обновить изображения'}
            </button>
            <button className="btn" onClick=${() => store.runPendingOcr(true)} disabled=${store.ocrLoading}>
              ${store.ocrLoading ? 'OCR…' : 'Распознать нераспознанные'}
            </button>
          </div>
          <div className="toolbar-group">
            <span className=${`badge ${store.ocrBadgeClass()}`}>
              ${store.ocrBadgeText()}
            </span>
            <span className="subtle">Без txt: <strong>${store.ocrPendingCount()}</strong></span>
            <span className="subtle">Размер изображений: <strong>${store.mediaImagesSizeLabel()}</strong></span>
            <span className="subtle">Проверено media: <strong>${store.cacheStatus?.media_backfill_checked ?? 0}</strong></span>
            <span className="subtle">Скачано: <strong>${store.cacheStatus?.media_backfill_downloaded ?? 0}</strong></span>
            ${store.ocrStatus?.message ? html`<span className="subtle">${store.ocrStatus.message}</span>` : null}
          </div>
        </section>

        <section className="toolbar" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.showRecognizedOnly} onChange=${(e) => { store.ui.showRecognizedOnly = e.target.checked; if (store.ui.showRecognizedOnly) store.ui.showPendingOnly = false; store.resetPage(); }} /> Только с OCR</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.showPendingOnly} onChange=${(e) => { store.ui.showPendingOnly = e.target.checked; if (store.ui.showPendingOnly) store.ui.showRecognizedOnly = false; store.resetPage(); }} /> Только без OCR</label>
          </div>
        </section>

        <section className="panel media-assets-panel">
          <div className="section-title">Сохранённые изображения</div>
          <div className="table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Загружаю изображения и OCR-результаты…" details="Media читает сохранённые OCR-результаты; скачивание изображений выполняется отдельной фоновой очередью." />` : null}
            ${!store.loading && store.filteredRows().length === 0 ? html`<div className="empty">Под текущие фильтры изображения не нашлись.</div>` : null}

            ${store.filteredRows().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Превью</th>
                    <th>Чат</th>
                    <th>Файл</th>
                    <th>OCR</th>
                    <th>Распознанный текст</th>
                    <th>Дата</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.pagedRows().map((row) => html`<${MediaAssetRow} key=${row.media_path} store=${store} row=${row} />`)}
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
      console.error('[React] #app root was not found for Media page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${MediaPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
