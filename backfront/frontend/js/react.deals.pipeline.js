/* React X-Files deals pipeline table and kanban components */
'use strict';

(function initBackfrontDealsPipeline() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.BackfrontDealsUtils) {
    console.error('[React] Runtime libraries are not loaded for deals pipeline');
    return;
  }

  const { html } = window.BackfrontReact;
  const { TablePaginationFooter, LoadingNotice } = window.BackfrontReactShared;
  const {
    STAGES,
    fmtMoney,
    fmtDate,
    slaLabel,
    slaClass,
    stageLabel,
    kanbanCardClass,
  } = window.BackfrontDealsUtils();

  function DealsPipelinePanel({
    viewMode,
    kanbanTotal,
    kanbanLoading,
    kanbanColumns,
    rows,
    loading,
    savingId,
    patchDeal,
    openAssistant,
    openContractKit,
    deleteDeal,
    rangeText,
    page,
    totalPages,
    pageWindow,
    setPage,
  }) {
    return html`
        <section className="panel">
          <div className="section-title">Pipeline сделок</div>
          <div className="section-subtitle">
            ${viewMode === 'kanban'
              ? `Kanban показывает сделки по стадиям: ${kanbanTotal || 0} найдено, до 20 карточек на колонку. Смена стадии сохраняется сразу и попадает в audit log.`
              : 'Первый рабочий слой X-Files: сделки можно вести вручную, а дальше сюда будут автоматически попадать квалифицированные потребности, enReach и outReach-сценарии.'}
          </div>

          ${viewMode === 'kanban' ? html`
            <div className="kanban-scroll">
              ${kanbanLoading && !kanbanColumns.length ? html`<${LoadingNotice} message="Готовлю kanban…" details="Группирую сделки по стадиям из PostgreSQL/state без пересчёта архива." />` : null}
              ${!kanbanLoading && !kanbanTotal ? html`<div className="empty">Сделок пока нет. Создайте первую сделку выше или позже переведите элемент из enReach в сделку.</div>` : null}
              ${kanbanColumns.length ? html`
                <div className="kanban-board">
                  ${kanbanColumns.map((column) => html`
                    <div className="kanban-column" key=${column.stage}>
                      <div className="kanban-header">
                        <div className="kanban-title-row">
                          <div className="kanban-title">${column.label || stageLabel(column.stage)}</div>
                          <span className="badge">${column.total || 0}</span>
                        </div>
                        <div className="kanban-meta">
                          <span>${fmtMoney(column.expected_profit)} ₽ expected</span>
                          ${column.overdue ? html`<span className="sla-badge sla-red">${column.overdue} проср.</span>` : null}
                          ${column.due_soon ? html`<span className="sla-badge sla-yellow">${column.due_soon} скоро</span>` : null}
                        </div>
                      </div>
                      <div className="kanban-list">
                        ${!column.items.length ? html`<div className="kanban-empty">В этой стадии пока пусто.</div>` : null}
                        ${column.items.map((row) => html`
                          <article className=${kanbanCardClass(row)} key=${row.id}>
                            <div className="kanban-card-title">${row.title}</div>
                            <div className="subtle">${row.contact_name || row.company || row.contact_key || 'контакт не указан'}</div>
                            <div className=${`sla-badge ${slaClass(row.sla_status)}`}>${slaLabel(row.sla_status)}</div>
                            <div className="kanban-card-text">${row.need || row.next_action || 'Потребность пока не описана'}</div>
                            <div className="kanban-meta">
                              <span>${fmtMoney(row.expected_profit)} ₽</span>
                              <span>${Math.round(Number(row.probability || 0) * 100)}%</span>
                              <span>${Math.round(Number(row.margin ?? 1) * 100)}% маржа</span>
                              <span>${row.score || 0}/100</span>
                            </div>
                            <div className="kanban-card-text">
                              <strong>Следующее:</strong> ${row.next_action || 'назначить следующий шаг'}
                            </div>
                            <div className="kanban-actions">
                              <select className="select compact" value=${row.stage} disabled=${savingId === row.id} onChange=${(e) => patchDeal(row, { stage: e.target.value })}>
                                ${STAGES.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
                              </select>
                              <button className="btn" disabled=${savingId === row.id} onClick=${() => openAssistant(row)}>
                                Помощник
                              </button>
                              <button className="btn" disabled=${savingId === row.id} onClick=${() => openContractKit(row)}>
                                КП/Договор
                              </button>
                              <button className="btn btn-danger" disabled=${savingId === row.id} onClick=${() => deleteDeal(row)}>
                                ${savingId === row.id ? '…' : 'Удалить'}
                              </button>
                            </div>
                          </article>
                        `)}
                        ${column.total > column.items.length ? html`
                          <div className="kanban-empty">Ещё ${column.total - column.items.length} сделок скрыто. Используйте фильтр стадии или таблицу для полного списка.</div>
                        ` : null}
                      </div>
                    </div>
                  `)}
                </div>
              ` : null}
            </div>
          ` : html`
            <div className="table-wrap">
              ${loading && !rows.length ? html`<${LoadingNotice} message="Загружаю сделки…" details="Сначала читаю PostgreSQL, если он настроен; иначе мгновенно использую state.json." />` : null}
              ${!loading && !rows.length ? html`<div className="empty">Сделок пока нет. Создайте первую сделку выше или позже переведите элемент из enReach в сделку.</div>` : null}
              ${rows.length ? html`
                <table>
                  <thead>
                    <tr>
                      <th>Сделка</th>
                      <th>Стадия</th>
                      <th>Контакт</th>
                      <th>Экономика</th>
                      <th>Потребность / оффер</th>
                      <th>Следующий шаг</th>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${rows.map((row) => html`
                      <tr key=${row.id} className=${`deal-row deal-row-${row.sla_status || 'green'}`}>
                        <td>
                          <div className="font-semibold">${row.title}</div>
                          <div className="subtle">${row.source || 'manual'} ${row.source_chat ? `· ${row.source_chat}` : ''}</div>
                          <div className="subtle">обновлено ${fmtDate(row.updated_at)}</div>
                        </td>
                        <td>
                          <select className="select compact" value=${row.stage} disabled=${savingId === row.id} onChange=${(e) => patchDeal(row, { stage: e.target.value })}>
                            ${STAGES.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
                          </select>
                          <div className="subtle">score ${row.score || 0}/100</div>
                          <div className=${`sla-badge ${slaClass(row.sla_status)}`}>${slaLabel(row.sla_status)}</div>
                          <div className="subtle">${row.sla_reason || ''}</div>
                        </td>
                        <td>
                          <div>${row.contact_name || '—'}</div>
                          <div className="subtle">${row.company || row.contact_key || ''}</div>
                        </td>
                        <td>
                          <div><strong>${fmtMoney(row.expected_profit)} ₽</strong></div>
                          <div className="subtle">${fmtMoney(row.expected_value)} ₽ × ${Math.round(Number(row.probability || 0) * 100)}% × ${Math.round(Number(row.margin ?? 1) * 100)}% маржа</div>
                        </td>
                        <td className="cell-text">
                          <div>${row.need || '—'}</div>
                          ${row.product_match ? html`<div className="subtle" style=${{ marginTop: '8px' }}>${row.product_match}</div>` : null}
                        </td>
                        <td className="cell-text">
                          <div>${row.next_action || '—'}</div>
                          <div className="subtle">SLA ${row.sla_hours || 0} ч · дедлайн ${fmtDate(row.sla_deadline_at)}</div>
                          <div className="subtle">без изменений ${row.stale_hours || 0} ч</div>
                        </td>
                        <td>
                          <div className="deal-actions">
                            <button className="btn" disabled=${savingId === row.id} onClick=${() => openAssistant(row)}>
                              Помощник
                            </button>
                            <button className="btn" disabled=${savingId === row.id} onClick=${() => openContractKit(row)}>
                              КП/Договор
                            </button>
                            <button className="btn btn-danger" disabled=${savingId === row.id} onClick=${() => deleteDeal(row)}>
                              ${savingId === row.id ? '…' : 'Удалить'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    `)}
                  </tbody>
                </table>
              ` : null}
            </div>
            <${TablePaginationFooter}
              rangeText=${rangeText}
              page=${page}
              totalPages=${totalPages}
              pageWindow=${pageWindow}
              onPrev=${() => setPage(Math.max(1, page - 1))}
              onNext=${() => setPage(Math.min(totalPages, page + 1))}
              onGo=${setPage}
            />
          `}
        </section>

    `;

  }

  window.BackfrontDealsPipeline = function BackfrontDealsPipeline() {
    return { DealsPipelinePanel };
  };
})();
