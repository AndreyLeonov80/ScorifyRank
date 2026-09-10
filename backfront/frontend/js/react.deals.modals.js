/* Deals page modal components */
'use strict';

(function initReactDealsModals() {
  window.BackfrontDealsModals = function BackfrontDealsModals() {
    const { html } = window.BackfrontReact;
    const { LoadingNotice } = window.BackfrontReactShared;
    const { CONTRACT_STATUSES, fmtMoney, fmtDate, contractStatusLabel } = window.BackfrontDealsUtils();

  function AssistantList({ items }) {
    const rows = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!rows.length) return html`<div className="subtle">Пока нет данных для этого блока.</div>`;
    return html`
      <ul className="assistant-list">
        ${rows.map((item, index) => html`<li key=${index}>${item}</li>`)}
      </ul>
    `;
  }

  function DealAssistantModal({ deal, assistant, loading, error, onClose, onApply }) {
    return html`
      <div className="deal-assistant-backdrop" role="presentation" onClick=${onClose}>
        <div className="deal-assistant-modal" role="dialog" aria-modal="true" aria-label="Переговорный помощник" onClick=${(event) => event.stopPropagation()}>
          <div className="deal-assistant-head">
            <div>
              <div className="deal-assistant-title">Переговорный помощник</div>
              <div className="subtle">${deal?.title || 'Сделка'} · ${deal?.contact_name || deal?.company || deal?.contact_key || 'контакт'}</div>
            </div>
            <button className="btn" onClick=${onClose}>Закрыть</button>
          </div>
          <div className="deal-assistant-body">
            ${error ? html`<div className="error-box compact-empty">${error}</div>` : null}
            ${loading ? html`<${LoadingNotice} message="Готовлю brief…" details="Читаю сделку и сообщения контакта из backend-кеша, без массового пересчёта архива." />` : null}
            ${assistant && !loading ? html`
              <div className="assistant-hero">
                <div>
                  <div className="card-label">Контакт</div>
                  <div className="assistant-value">${assistant.who || '—'}</div>
                  <div className="subtle">${assistant.contact_summary || ''}</div>
                </div>
                <div>
                  <div className="card-label">Рекомендация</div>
                  <div className="assistant-value">${assistant.recommended_score || 0}/100</div>
                  <div className="subtle">${assistant.recommended_next_action || 'назначить следующий шаг'}</div>
                </div>
                <div>
                  <div className="card-label">История</div>
                  <div className="assistant-value">${assistant.source_messages || 0}</div>
                  <div className="subtle">сообщений использовано</div>
                </div>
              </div>
              <section className="assistant-section assistant-next">
                <div className="assistant-section-title">Следующее лучшее сообщение</div>
                <div className="assistant-message">${assistant.next_best_message || '—'}</div>
                <button className="btn btn-active" onClick=${onApply}>Применить score и next action к сделке</button>
              </section>
              <div className="assistant-grid">
                <section className="assistant-section">
                  <div className="assistant-section-title">Что обсуждал</div>
                  <${AssistantList} items=${assistant.discussed} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">Чего хочет / что болит</div>
                  <${AssistantList} items=${assistant.wants} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">Что может купить</div>
                  <div className="assistant-message">${assistant.can_buy || '—'}</div>
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">Что спросить для быстрой квалификации</div>
                  <${AssistantList} items=${assistant.qualification_questions} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">Agenda звонка / встречи</div>
                  <${AssistantList} items=${assistant.call_agenda} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">5-минутный brief перед звонком</div>
                  <${AssistantList} items=${assistant.five_minute_brief} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">История в 10 bullets</div>
                  <${AssistantList} items=${assistant.ten_bullets} />
                </section>
                <section className="assistant-section">
                  <div className="assistant-section-title">Что нельзя писать</div>
                  <${AssistantList} items=${assistant.do_not_write} />
                </section>
              </div>
              <section className="assistant-section">
                <div className="assistant-section-title">Вероятные возражения и ответы</div>
                <div className="assistant-objections">
                  ${(assistant.objections || []).map((item, index) => html`
                    <div className="assistant-objection" key=${index}>
                      <div className="font-semibold">${item.objection || 'Возражение'}</div>
                      <div className="subtle">${item.reply || 'Ответ пока не сформирован'}</div>
                    </div>
                  `)}
                </div>
              </section>
            ` : null}
          </div>
        </div>
      </div>
    `;
  }

  function DealContractModal({ deal, kit, loading, error, saving, onClose, onStatusChange, onDownload }) {
    const missing = Array.isArray(kit?.missing_fields) ? kit.missing_fields : [];
    const metrics = kit?.metrics || {};
    return html`
      <div className="deal-assistant-backdrop" role="presentation" onClick=${onClose}>
        <div className="deal-assistant-modal contract-modal" role="dialog" aria-modal="true" aria-label="КП и договор" onClick=${(event) => event.stopPropagation()}>
          <div className="deal-assistant-head">
            <div>
              <div className="deal-assistant-title">КП / договор</div>
              <div className="subtle">${deal?.title || 'Сделка'} · ${deal?.contact_name || deal?.company || deal?.contact_key || 'контакт'}</div>
            </div>
            <button className="btn" onClick=${onClose}>Закрыть</button>
          </div>
          <div className="deal-assistant-body">
            ${error ? html`<div className="error-box compact-empty">${error}</div>` : null}
            ${loading ? html`<${LoadingNotice} message="Собираю КП и чеклист…" details="Использую только сделку, audit log, шаблоны и справочник ЮР.ЛИЦА." />` : null}
            ${kit && !loading ? html`
              <div className="assistant-hero contract-hero">
                <div>
                  <div className="card-label">Статус договора</div>
                  <select className="select contract-status-select" value=${kit.contract_status || 'needs_data'} disabled=${saving} onChange=${(event) => onStatusChange(event.target.value)}>
                    ${CONTRACT_STATUSES.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
                  </select>
                  <div className="subtle">Текущий статус: ${contractStatusLabel(kit.contract_status)}</div>
                </div>
                <div>
                  <div className="card-label">Не хватает</div>
                  <div className="assistant-value">${missing.length}</div>
                  <div className="subtle">${missing.length ? missing.join(', ') : 'можно отправлять КП'}</div>
                </div>
                <div>
                  <div className="card-label">ЮР.ЛИЦА</div>
                  <div className="assistant-value">${(kit.jur_matches || []).length}</div>
                  <div className="subtle">потенциальных совпадений</div>
                </div>
              </div>

              <section className="assistant-section assistant-next">
                <div className="assistant-section-title">КП в 1 экран</div>
                <div className="assistant-message">${kit.short_proposal || '—'}</div>
              </section>

              <div className="assistant-grid">
                <section className="assistant-section">
                  <div className="assistant-section-title">Чеклист перед договором</div>
                  <div className="contract-checklist">
                    ${(kit.checklist || []).map((item) => html`
                      <div className=${`contract-check ${item.ok ? 'contract-check-ok' : 'contract-check-missing'}`} key=${item.key}>
                        <span>${item.ok ? '✓' : '!'}</span>
                        <div>
                          <div className="font-semibold">${item.label}</div>
                          <div className="subtle">${item.value || 'нужно уточнить'}</div>
                        </div>
                      </div>
                    `)}
                  </div>
                </section>

                <section className="assistant-section">
                  <div className="assistant-section-title">Среднее время закрытия</div>
                  <div className="contract-metrics">
                    <div>
                      <div className="card-label">qualified → КП</div>
                      <div className="assistant-value">${metrics.qualified_to_proposal?.label || 'нет истории'}</div>
                      <div className="subtle">sample ${metrics.qualified_to_proposal?.sample || 0}</div>
                    </div>
                    <div>
                      <div className="card-label">КП → договор</div>
                      <div className="assistant-value">${metrics.proposal_to_contract?.label || 'нет истории'}</div>
                      <div className="subtle">sample ${metrics.proposal_to_contract?.sample || 0}</div>
                    </div>
                  </div>
                </section>

                <section className="assistant-section">
                  <div className="assistant-section-title">Шаблоны</div>
                  <div className="contract-template-list">
                    ${(kit.templates || []).map((item) => html`
                      <div className="contract-template" key=${item.id}>
                        <span className="badge">${item.kind}</span>
                        <div>
                          <div className="font-semibold">${item.title}</div>
                          <div className="subtle">${item.description}</div>
                        </div>
                      </div>
                    `)}
                  </div>
                </section>

                <section className="assistant-section">
                  <div className="assistant-section-title">Связанные ЮР.ЛИЦА</div>
                  ${(kit.jur_matches || []).length ? html`
                    <div className="contract-template-list">
                      ${kit.jur_matches.map((item) => html`
                        <div className="contract-template" key=${item.file_key}>
                          <span className="badge">${item.score || 1}</span>
                          <div>
                            <div className="font-semibold">${item.file_name}</div>
                            <div className="subtle">${item.channel} · ${item.caption_preview || 'без подписи'}</div>
                          </div>
                        </div>
                      `)}
                    </div>
                  ` : html`<div className="subtle">Совпадений пока нет. Можно открыть ЮР.ЛИЦА и добавить файлы в парсер.</div>`}
                </section>
              </div>

              <section className="assistant-section">
                <div className="contract-doc-head">
                  <div>
                    <div className="assistant-section-title">Расширенное КП</div>
                    <div className="subtle">Markdown-документ можно сохранить и дальше перенести в DOCX/PDF.</div>
                  </div>
                  <button className="btn btn-active" onClick=${onDownload}>Скачать КП .md</button>
                </div>
                <pre className="contract-doc">${kit.proposal_document || '—'}</pre>
              </section>
            ` : null}
          </div>
        </div>
      </div>
    `;
  }

    return { AssistantList, DealAssistantModal, DealContractModal };
  };
})();
