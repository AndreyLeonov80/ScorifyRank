/* React grid page powered by legacy gridApp store */
'use strict';

(function mountReactGridPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.gridApp) {
    console.error('[React] gridApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { ErrorBox, PageHeader, TablePaginationFooter, TelegramCooldownBanner, LoadingNotice, VirtualizedRows } = window.BackfrontReactShared;

  function scanLimitLabel(value, unit) {
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric === 0) return 'безлимит';
    if (Number.isFinite(numeric) && numeric > 0) return `${Math.trunc(numeric)} ${unit}`;
    return 'по умолчанию';
  }

  function formatAge(value) {
    const time = Date.parse(value || '');
    if (!Number.isFinite(time)) return 'нет данных';
    const diff = Math.max(0, Date.now() - time);
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return 'только что';
    if (minutes < 60) return `${minutes}м назад`;
    const hours = Math.floor(minutes / 60);
    if (hours < 48) return `${hours}ч назад`;
    return `${Math.floor(hours / 24)}д назад`;
  }

  function readProgress(lead) {
    const read = Math.max(0, Number(lead?.read_messages_count ?? lead?.count ?? 0));
    const total = Math.max(read, Number(lead?.total_messages_estimate ?? read));
    const remaining = Math.max(0, Number(lead?.remaining_messages_estimate ?? Math.max(0, total - read)));
    const percent = Math.max(0, Math.min(100, Number(lead?.read_progress_percent ?? (total ? (read / total) * 100 : 0))));
    return { read, total, remaining, percent };
  }

  function ProgressCell({ item }) {
    const progress = readProgress(item);
    return html`
      <div className="sync-progress-cell">
        <div className="sync-progress-top">
          <strong>${Math.round(progress.percent)}%</strong>
          <span>${progress.read.toLocaleString('ru-RU')} / ${progress.total.toLocaleString('ru-RU')}</span>
        </div>
        <div className="sync-progress-track"><div className="sync-progress-bar" style=${{ width: `${progress.percent}%` }}></div></div>
        <div className="muted">осталось ${progress.remaining.toLocaleString('ru-RU')}</div>
      </div>
    `;
  }

  function jsonlDownloadHref(lead) {
    return `${window.BackfrontApi?.PAYME_API || '/api/payme'}/leads/${encodeURIComponent(lead?.name || '')}/jsonl`;
  }

  function BulkImportLimitDialog({ store }) {
    const dialog = store.bulkLimitDialog || {};
    if (!dialog.visible) return null;
    const title = dialog.mode === 'limited' ? 'Вернуть лимит сканирования' : 'Лимиты сканирования для всех источников';
    return html`
      <div className="modal-backdrop" role="presentation" onClick=${() => store.closeBulkLimitDialog()}>
        <div className="modal" style=${{ width: 'min(760px, 92vw)' }} onClick=${(event) => event.stopPropagation()}>
          <div className="modal-header">
            <div>
              <h2>${title}</h2>
              <p className="muted">Настройки применятся ко всем выбранным источникам и после сохранения запустят получение данных из Telegram.</p>
            </div>
            <button className="btn" onClick=${() => store.closeBulkLimitDialog()} disabled=${store.bulkUnlimitedBusy}>Закрыть</button>
          </div>
          <div className="modal-body">
            <label className="chip" style=${{ width: 'fit-content' }}>
              <input
                type="checkbox"
                checked=${!!dialog.unlimited}
                onChange=${(e) => {
                  store.bulkLimitDialog = {
                    ...store.bulkLimitDialog,
                    unlimited: e.target.checked,
                  };
                }}
              />
              Безлимит по времени и количеству сообщений
            </label>
            <div className="toolbar" style=${{ paddingLeft: 0, paddingRight: 0 }}>
              <label className="field">
                <span>Месяцев истории</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  disabled=${!!dialog.unlimited}
                  value=${dialog.import_history_months || 1}
                  onChange=${(e) => {
                    store.bulkLimitDialog = {
                      ...store.bulkLimitDialog,
                      import_history_months: Math.max(1, Number(e.target.value || 1)),
                    };
                  }}
                />
              </label>
              <label className="field">
                <span>Сообщений на источник</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  disabled=${!!dialog.unlimited}
                  value=${dialog.import_message_limit || 1000}
                  onChange=${(e) => {
                    store.bulkLimitDialog = {
                      ...store.bulkLimitDialog,
                      import_message_limit: Math.max(1, Number(e.target.value || 1000)),
                    };
                  }}
                />
              </label>
            </div>
            <div className="muted">
              Безлимит сохраняется как 0 месяцев / 0 сообщений. Ограниченный режим вернёт указанные значения для всех источников.
            </div>
          </div>
          <div className="modal-footer">
            <button className="btn" onClick=${() => store.closeBulkLimitDialog()} disabled=${store.bulkUnlimitedBusy}>Отмена</button>
            <button className="btn btn-danger" onClick=${() => store.applyBulkImportLimits()} disabled=${store.bulkUnlimitedBusy}>
              ${store.bulkUnlimitedBusy ? 'Применяю…' : 'Применить'}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function PersonalImportLimitDialog({ store }) {
    const dialog = store.personalLimitDialog || {};
    if (!dialog.visible) return null;
    return html`
      <div className="modal-backdrop" role="presentation" onClick=${() => store.closePersonalLimitDialog()}>
        <div className="modal" style=${{ width: 'min(680px, 92vw)' }} onClick=${(event) => event.stopPropagation()}>
          <div className="modal-header">
            <div>
              <h2>Персональный лимит источника</h2>
              <p className="muted">${dialog.title || dialog.selector}</p>
            </div>
            <button className="btn" onClick=${() => store.closePersonalLimitDialog()} disabled=${store.bulkUnlimitedBusy}>Закрыть</button>
          </div>
          <div className="modal-body">
            <div className="toolbar" style=${{ paddingLeft: 0, paddingRight: 0 }}>
              <label className="field">
                <span>Месяцев истории</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  value=${dialog.import_history_months ?? 1}
                  onChange=${(e) => {
                    store.personalLimitDialog = {
                      ...store.personalLimitDialog,
                      import_history_months: Math.max(0, Number(e.target.value || 0)),
                    };
                  }}
                />
              </label>
              <label className="field">
                <span>Сообщений на источник</span>
                <input
                  className="input"
                  type="number"
                  min="0"
                  value=${dialog.import_message_limit ?? 1000}
                  onChange=${(e) => {
                    store.personalLimitDialog = {
                      ...store.personalLimitDialog,
                      import_message_limit: Math.max(0, Number(e.target.value || 0)),
                    };
                  }}
                />
              </label>
            </div>
            <div className="muted">0 означает безлимит для выбранного источника.</div>
          </div>
          <div className="modal-footer">
            <button className="btn" onClick=${() => store.closePersonalLimitDialog()} disabled=${store.bulkUnlimitedBusy}>Отмена</button>
            <button className="btn btn-danger" onClick=${() => store.applyPersonalImportLimits()} disabled=${store.bulkUnlimitedBusy}>
              ${store.bulkUnlimitedBusy ? 'Применяю…' : 'Применить'}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function GridRow({ store, lead }) {
    const preview = store.leadPreview(lead);
    const historyLimit = lead.import_history_months ?? lead.import_history_limit_months ?? store.settings?.import_default_history_months;
    const messageLimit = lead.import_message_limit ?? lead.import_messages_limit ?? store.settings?.import_default_message_limit;
    return html`
      <tr className=${lead.telegram_active ? 'row-active-sync' : (store.leadHasFreshActivity(lead) ? 'row-fresh' : '')}>
        <td>
          <div className="lead-name">
            <span>${lead.name}</span>
          </div>
          <div className="lead-meta">
            ${lead.has_jsonl ? html`<a href=${jsonlDownloadHref(lead)} download=${lead.file || `${lead.name}.jsonl`}>${lead.file || `${lead.name}.jsonl`}</a>` : (lead.file || 'jsonl ещё нет')}
          </div>
          <div className="lead-meta">в кеше: ${(Number(lead.count || 0)).toLocaleString('ru-RU')} · sync: ${formatAge(lead.last_sync_at || lead.last_live_update_at)}</div>
        </td>
        <td>
          <span className=${`badge ${store.leadStatusClass(lead)}`}>${store.leadStatusText(lead)}</span>
          ${lead.telegram_active ? html`<div className="muted">сейчас читает: ${lead.telegram_active_stage || 'telegram'}</div>` : null}
        </td>
        <td>
          <select
            className="select"
            value=${lead.scan_group || 'C'}
            title=${store.groupFrequency(lead) || 'Частота группы'}
            disabled=${store.isLeadActionBusy(lead, 'group')}
            onChange=${(e) => store.setLeadGroup(lead, e.target.value)}
          >
            ${store.scanGroups().map((group) => html`
              <option key=${group.id} value=${group.id}>${group.label || group.id}</option>
            `)}
          </select>
          <div className="muted">${store.groupFrequency(lead)}</div>
        </td>
        <td>
          <div className="count-cell">
            <span className="count-main">${lead.count}</span>
            ${store.leadDeltaText(lead) ? html`<span className="delta">${store.leadDeltaText(lead)}</span>` : null}
          </div>
        </td>
        <td><${ProgressCell} item=${lead} /></td>
        <td>${scanLimitLabel(historyLimit, 'мес.')}</td>
        <td>${scanLimitLabel(messageLimit, 'сообщ.')}</td>
        <td>
          <div className="lead-preview">${preview}</div>
        </td>
        <td>
          <div>${lead.last_date_utc ? window.fmtDate(lead.last_date_utc, true) : '—'}</div>
        </td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button className="btn" onClick=${() => store.openLeadChat(lead)}>Открыть чат</button>
            <button
              className="btn"
              onClick=${() => store.openPersonalLimitDialog(lead)}
              disabled=${store.isLeadActionBusy(lead, 'limit')}
              title="Изменить лимит истории и сообщений только для этого источника"
            >
              Лимит
            </button>
            ${store.canActivateLead(lead) ? html`
              <button
                className="btn btn-active"
                onClick=${() => store.activateLead(lead)}
                disabled=${store.isLeadActionBusy(lead, 'activate')}
              >
                ${store.isLeadActionBusy(lead, 'activate') ? 'Включаю…' : 'Включить сканирование'}
              </button>
            ` : null}
          </div>
        </td>
      </tr>
    `;
  }

  function GridPage() {
    const store = useLegacyStore(window.gridApp);
    const [booted, setBooted] = React.useState(false);
    const debounceReload = useDebouncedCallback(() => store.resetPage(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Grid init failed:', error);
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
          title="Sync"
          subtitle="Таблица источников Telegram для синхронизации с realtime-обновлением, фильтром и пагинацией."
          active="grid"
          titleWrapClassName="title-wrap"
          statusSlot=${store.telegramSyncHumanLabel()}
        />
        <${TelegramCooldownBanner} />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Фильтр по названию, source selector или превью…"
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

            <select
              className="select"
              value=${store.ui.statusFilter || 'all'}
              onChange=${(e) => store.setStatusFilter(e.target.value)}
              title="Фильтр по статусу чтения"
            >
              <option value="all">Все статусы</option>
              <option value="reading">Читает сейчас</option>
              <option value="waiting">Ожидает расписания</option>
              <option value="pending">Ждёт первую выгрузку</option>
              <option value="error">Ошибки / cooldown</option>
              <option value="archived">Не сканируется, есть база</option>
              <option value="empty">Нет кеша</option>
            </select>

            <select
              className="select"
              value=${store.ui.groupFilter || 'all'}
              onChange=${(e) => store.setGroupFilter(e.target.value)}
              title="Фильтр по scan-группе"
            >
              <option value="all">Все группы</option>
              ${store.scanGroups().map((group) => html`<option key=${group.id} value=${group.id}>${group.label || group.id}</option>`)}
            </select>

            <button
              className="btn btn-danger"
              onClick=${() => store.openBulkLimitDialog('unlimited')}
              disabled=${store.bulkUnlimitedBusy || store.loading}
              title="Для всех выбранных источников ставит безлимитное время истории и безлимит сообщений"
            >
              Безлимит всем источникам
            </button>
            <button
              className="btn"
              onClick=${() => store.openBulkLimitDialog('limited')}
              disabled=${store.bulkUnlimitedBusy || store.loading}
              title="Вернуть ограничение по времени истории и числу сообщений для всех источников"
            >
              Вернуть лимит
            </button>
            <button
              className="btn btn-danger"
              onClick=${() => store.toggleTelegramSyncPause()}
              disabled=${store.telegramSyncPauseBusy}
              title=${store.telegramSyncPaused()
                ? 'Продолжить сканирование Telegram источников'
                : 'Поставить сканирование Telegram источников на паузу: запросы в Telegram остановятся'}
            >
              ${store.telegramSyncPauseBusy
                ? 'Применяю...'
                : store.telegramSyncPaused()
                  ? 'Продолжить'
                  : 'Пауза'}
            </button>
          </div>

          <div className="toolbar-group">
            <span className=${`badge ${store.realtimeClass()}`}>${store.realtimeLabel()}</span>
            <span className="subtle">Последнее обновление: <strong>${store.lastUpdatedAt ? window.fmtDate(store.lastUpdatedAt, true) : '—'}</strong></span>
          </div>
        </section>

        <section className="toolbar grid-filter-status-row" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.showChannels} onChange=${(e) => { store.ui.showChannels = e.target.checked; store.resetPage(); }} /> Каналы</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.showGroups} onChange=${(e) => { store.ui.showGroups = e.target.checked; store.resetPage(); }} /> Группы</label>
            <label className="chip"><input type="checkbox" checked=${store.ui.showPrivate} onChange=${(e) => { store.ui.showPrivate = e.target.checked; store.resetPage(); }} /> Личные</label>
          </div>
          <div className="toolbar-group">
            <span className="badge badge-active">Показаны только сканируемые</span>
            <span className="subtle">Отключённые источники остаются в JSONL/DuckDB, но не отображаются в Sync.</span>
          </div>
        </section>

        <section className="panel">
          <div className="table-wrap">
            ${store.loading && store.leads.length === 0 ? html`<${LoadingNotice} message="Загружаю список сканируемых каналов…" details="Sync берёт только активные источники из backend-кеша, отключённые остаются в базе и не показываются здесь." />` : null}
            ${!store.loading && store.filteredLeads().length === 0 ? html`<div className="empty">По текущему фильтру источники не найдены.</div>` : null}

            ${store.filteredLeads().length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Канал</th>
                    <th>Статус</th>
                    <th>Группа</th>
                    <th>Сообщения</th>
                    <th>Прогресс чтения</th>
                    <th>Лимит времени</th>
                    <th>Лимит сообщений</th>
                    <th>Последнее сообщение</th>
                    <th>Последняя дата</th>
                    <th style=${{ width: '220px' }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <${VirtualizedRows}
                    items=${store.pagedLeads()}
                    maxRows=${store.ui.pageSize}
                    getKey=${(lead) => lead.name}
                    renderItem=${(lead) => html`<${GridRow} store=${store} lead=${lead} />`}
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
        <${BulkImportLimitDialog} store=${store} />
        <${PersonalImportLimitDialog} store=${store} />
        <footer className="subtle" style=${{ padding: '0 20px 16px' }}>
          Источник данных: <code>/api/payme/leads</code> и <code>/api/payme/stream/leads</code>.
        </footer>
        ${!booted && !store.error ? html`<div className="subtle" style=${{ padding: '0 20px 16px' }}>Инициализация React UI…</div>` : null}
      </div>
    `;
  }

  const root = document.getElementById('react-root');
  if (!root) {
    console.error('[React] Root container #react-root was not found');
    return;
  }

  ReactDOM.createRoot(root).render(html`<${GridPage} />`);
})();
