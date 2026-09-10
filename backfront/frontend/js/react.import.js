/* React import page powered by legacy telegramImportApp store */
'use strict';

(function mountReactImportPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.telegramImportApp) {
    console.error('[React] telegramImportApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, TelegramCooldownBanner, LoadingNotice, VirtualizedRows } = window.BackfrontReactShared;

  function formatEta(seconds) {
    const value = Math.max(0, Math.round(Number(seconds || 0)));
    if (!value) return 'ETA: почти готово';
    const minutes = Math.floor(value / 60);
    const rest = value % 60;
    if (!minutes) return `ETA: ${rest} сек`;
    return `ETA: ${minutes} мин ${String(rest).padStart(2, '0')} сек`;
  }

  function ImportProgressPopup({ progress }) {
    if (!progress?.visible) return null;
    const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    return html`
      <div className="import-progress-backdrop" role="presentation">
        <section className="import-progress-popup" role="dialog" aria-modal="true" aria-live="polite">
          <div className="import-progress-head">
            <div>
              <div className="import-progress-title">${progress.kind === 'filter' ? 'Фильтр Import' : 'Импорт Telegram'}</div>
              <div className="subtle">${progress.kind === 'initial' ? 'Первый запуск Import' : progress.kind === 'filter' ? 'Переключаю список' : 'Операция Import'}</div>
            </div>
            <span className=${`badge ${progress.running ? 'badge-warn' : 'badge-active'}`}>${progress.running ? 'выполняется' : 'готово'}</span>
          </div>
          <div className="import-progress-status">${progress.status || 'Подключаюсь к Telegram...'}</div>
          <div className="import-progress-detail">${progress.detail || 'Backend обновляет данные и готовит таблицу.'}</div>
          <div className="import-progress-meta">
            <strong>${Math.round(percent)}%</strong>
            <span>${formatEta(progress.etaSec)}</span>
          </div>
          <div className="import-progress-track">
            <div className="import-progress-bar" style=${{ width: `${Math.max(2, percent)}%` }}></div>
          </div>
        </section>
      </div>
    `;
  }

  function DialogRow({ store, dialog }) {
    const [historyMonths, setHistoryMonths] = React.useState(dialog.import_history_months ?? store.settings.import_default_history_months ?? 1);
    const [messageLimit, setMessageLimit] = React.useState(dialog.import_message_limit ?? store.settings.import_default_message_limit ?? 1000);
    React.useEffect(() => {
      setHistoryMonths(dialog.import_history_months ?? store.settings.import_default_history_months ?? 1);
      setMessageLimit(dialog.import_message_limit ?? store.settings.import_default_message_limit ?? 1000);
    }, [dialog.import_history_months, dialog.import_message_limit, store.settings.import_default_history_months, store.settings.import_default_message_limit]);
    const preview = store.previewText(dialog.last_text_preview || '');
    const fullText = String(dialog.last_text_full || dialog.last_text_preview || '').trim();
    return html`
      <tr className=${store.rowClass(dialog)}>
        <td>
          <input
            type="checkbox"
            checked=${store.isSelected(dialog.selector)}
            onChange=${() => store.toggleSelected(dialog.selector)}
            disabled=${store.importing || store.removingAll}
          />
        </td>
        <td>
          <div className="title-cell">
            <div className="title-main">${dialog.title}</div>
            <div className="meta">${dialog.username ? `@${dialog.username}` : 'без username'}</div>
          </div>
        </td>
        <td>
          <span className=${`badge ${store.chatTypeClass(dialog)}`}>${store.chatTypeLabel(dialog)}</span>
        </td>
        <td><code>${dialog.selector}</code></td>
        <td>${dialog.unread_count}</td>
        <td>
          <div className="toolbar-group" style=${{ gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="subtle" style=${{ display: 'grid', gap: '3px' }} title="Сколько месяцев истории брать для этого источника">
              История, мес.
              <input
                className="input"
                type="number"
                min="0"
                max=${dialog.import_max_history_months || store.importMaxHistoryMonths() || undefined}
                value=${historyMonths}
                onChange=${(e) => setHistoryMonths(store.clampImportHistoryMonths(e.target.value))}
                style=${{ width: '76px', padding: '8px 10px' }}
              />
              <span className="meta">${(dialog.import_max_history_months || store.importMaxHistoryMonths()) === 0 ? '0 = безлимит' : `макс. ${dialog.import_max_history_months || store.importMaxHistoryMonths()}`}</span>
            </label>
            <label className="subtle" style=${{ display: 'grid', gap: '3px' }} title="Сколько последних сообщений брать для этого источника">
              Сообщений
              <input
                className="input"
                type="number"
                min="0"
                max=${dialog.import_max_message_limit || store.importMaxMessageLimit() || undefined}
                value=${messageLimit}
                onChange=${(e) => setMessageLimit(store.clampImportMessageLimit(e.target.value))}
                style=${{ width: '104px', padding: '8px 10px' }}
              />
              <span className="meta">${(dialog.import_max_message_limit || store.importMaxMessageLimit()) === 0 ? '0 = безлимит' : `макс. ${dialog.import_max_message_limit || store.importMaxMessageLimit()}`}</span>
            </label>
            <button
              className="btn btn-small"
              onClick=${() => store.saveDialogImportSettings(dialog, {
                import_history_months: historyMonths,
                import_message_limit: messageLimit,
              })}
              disabled=${store.isRowBusy(dialog)}
              title="Сохранить лимиты импорта для этого источника"
            >
              ${store.isRowBusy(dialog) && store.rowBusyAction === 'settings' ? '…' : 'OK'}
            </button>
          </div>
        </td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
            <div className="preview">${preview || '—'}</div>
          </div>
        </td>
        <td>${dialog.last_date_utc ? (window.fmtDate ? window.fmtDate(dialog.last_date_utc, true) : dialog.last_date_utc) : '—'}</td>
        <td>
          <span className=${`badge ${dialog.is_already_added ? 'badge-active' : 'badge-archived'}`}>${dialog.is_already_added ? 'added' : 'new'}</span>
          ${dialog.is_archived ? html`<span className="badge badge-pending">archived</span>` : null}
        </td>
        <td>
          <div className="row-actions">
            ${!dialog.is_already_added ? html`
              <button
                className="btn btn-active"
                onClick=${() => store.addDialog(dialog)}
                disabled=${store.isRowBusy(dialog) || store.importing}
              >
                ${store.isRowBusy(dialog) && store.rowBusyAction === 'add' ? 'Добавление…' : 'Добавить'}
              </button>
            ` : html`
              <button
                className="btn btn-danger"
                onClick=${() => store.removeDialog(dialog)}
                disabled=${store.isRowBusy(dialog) || store.importing}
              >
                ${store.isRowBusy(dialog) && store.rowBusyAction === 'remove' ? 'Удаление…' : 'Удалить'}
              </button>
            `}
          </div>
        </td>
      </tr>
    `;
  }

  function ImportPage() {
    const store = useLegacyStore(window.telegramImportApp);
    const [booted, setBooted] = React.useState(false);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 200);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Import init failed:', error);
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
	        <${ImportProgressPopup} progress=${store.importProgress} />
	        <${PageHeader}
          title="Импорт из Telegram"
          subtitle="Список ваших диалогов из авторизованного аккаунта Telegram с массовым добавлением в программу."
          active="import"
        />
        <${TelegramCooldownBanner} />

        ${store.cacheWarning ? html`
          <section className="toolbar toolbar-compact" style=${{
            borderColor: '#fde68a',
            background: 'rgba(255,251,235,.9)',
            color: '#92400e',
          }}>
            <strong>Показываю кэш Import.</strong>
            <span>${store.cacheWarning}</span>
          </section>
        ` : null}

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Поиск по названию, @username, selector или превью…"
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
            <button className="btn btn-active" onClick=${() => store.syncTelegramImportData()} disabled=${store.syncingImport || store.loading || store.importing}>
              ${store.syncingImport ? 'Синхронизация…' : 'Синхронизировать'}
            </button>
            <button className="btn btn-danger" onClick=${() => store.deleteSelectedDialogs()} disabled=${!store.selectedCount() || store.importing || store.removingAll || store.loading}>
              ${store.removingAll ? 'Удаление…' : 'Удалить все выбранные'}
            </button>
          </div>

          <div className="toolbar-group">
            <span className=${`badge ${store.authStatus?.auth_status === 'authorized' ? 'badge-active' : 'badge-pending'}`}>
              ${store.authStatus?.auth_status || 'unknown'}
            </span>
            <span className="subtle">Выбрано: <strong>${store.selectedCount()}</strong></span>
          </div>
        </section>

        <section className="toolbar" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.showChannels} onChange=${(e) => { store.ui.showChannels = e.target.checked; store.resetPage(); }} /> Каналы</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.showGroups} onChange=${(e) => { store.ui.showGroups = e.target.checked; store.resetPage(); }} /> Группы</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.showPrivate} onChange=${(e) => { store.ui.showPrivate = e.target.checked; store.resetPage(); }} /> Личные</label>
          </div>

          <div className="toolbar-group segmented">
            <button aria-pressed=${store.ui.membershipFilter === 'not_added'} className=${`btn ${store.ui.membershipFilter === 'not_added' ? 'btn-active import-filter-active' : 'btn-ghost'}`} onClick=${() => store.setMembershipFilter('not_added')}>Не добавленные</button>
            <button aria-pressed=${store.ui.membershipFilter === 'added'} className=${`btn ${store.ui.membershipFilter === 'added' ? 'btn-active import-filter-active' : 'btn-ghost'}`} onClick=${() => store.setMembershipFilter('added')}>Добавленные</button>
            <button aria-pressed=${store.ui.membershipFilter === 'all'} className=${`btn ${store.ui.membershipFilter === 'all' ? 'btn-active import-filter-active' : 'btn-ghost'}`} onClick=${() => store.setMembershipFilter('all')}>Все</button>
          </div>

          <div className="toolbar-group sort-group">
            <span className="subtle">Сортировка</span>
            <select className="select" value=${store.ui.sortBy} onChange=${(e) => { store.ui.sortBy = e.target.value; store.resetPage(); }}>
              <option value="last_date_desc">Последняя дата: сначала новые</option>
              <option value="last_date_asc">Последняя дата: сначала старые</option>
            </select>
          </div>
        </section>

        <section className="panel">
          <div className="table-wrap">
            ${store.loading && store.dialogs.length === 0 ? html`<${LoadingNotice} message="Загружаю список диалогов из Telegram…" details="Backend читает кеш диалогов или аккуратно обращается к Telegram с учётом лимитов." />` : null}
            ${!store.loading && store.filteredDialogs().length === 0 ? html`<div className="empty">Под текущие фильтры диалоги не нашлись.</div>` : null}

            ${store.filteredDialogs().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th style=${{ width: '56px' }}>Выбор</th>
                    <th>Диалог</th>
                    <th>Тип</th>
                    <th>Selector</th>
                    <th>Unread</th>
                    <th>Лимиты</th>
                    <th>Последнее сообщение</th>
                    <th>Последняя дата</th>
                    <th>Статус</th>
                    <th style=${{ width: '180px' }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <${VirtualizedRows}
                    items=${store.pagedDialogs()}
                    maxRows=${store.ui.pageSize}
                    getKey=${(dialog) => dialog.id || dialog.selector}
                    renderItem=${(dialog) => html`<${DialogRow} store=${store} dialog=${dialog} />`}
                  />
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

        <${ErrorBox} error=${store.error} />

        <footer className="subtle" style=${{ padding: '0 20px 16px' }}>
          Источник данных: <code>/api/payme/telegram/dialogs</code> и <code>/api/payme/telegram/dialogs/import</code>.
        </footer>
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Import page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${ImportPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
