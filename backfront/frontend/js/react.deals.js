/* React X-Files deals page */
'use strict';

(function mountReactDealsPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.BackfrontDealsUtils || !window.BackfrontDealsModals || !window.BackfrontDealsPipeline || !window.BackfrontDealsForms) {
    console.error('[React] Runtime libraries are not loaded for X-Files deals');
    return;
  }

  const { React, ReactDOM, html } = window.BackfrontReact;
  const {
    ErrorBox,
    PageHeader,
    TablePaginationFooter,
    LoadingNotice,
    DealActionButton,
    cleanDealText,
    firstNonEmpty,
  } = window.BackfrontReactShared;
  const {
    API_BASE,
    STAGES,
    LEAD_TEMPERATURES,
    CONTRACT_STATUSES,
    fmtMoney,
    fmtDate,
    slaLabel,
    slaClass,
    stageLabel,
    kanbanCardClass,
    auditActionLabel,
    auditChangesText,
    contractStatusLabel,
    downloadTextFile,
    apiJson,
  } = window.BackfrontDealsUtils();

  const {
    AssistantList,
    DealAssistantModal,
    DealContractModal,
  } = window.BackfrontDealsModals();

  const {
    DealsPipelinePanel,
  } = window.BackfrontDealsPipeline();

  const {
    DealCreateForm,
  } = window.BackfrontDealsForms();

  function DealsPage() {
    const [status, setStatus] = React.useState(null);
    const [rows, setRows] = React.useState([]);
    const [kanbanColumns, setKanbanColumns] = React.useState([]);
    const [kanbanTotal, setKanbanTotal] = React.useState(0);
    const [dailyRows, setDailyRows] = React.useState([]);
    const [auditRows, setAuditRows] = React.useState([]);
    const [auditTotal, setAuditTotal] = React.useState(0);
    const [dailyTotal, setDailyTotal] = React.useState(0);
    const [eventPlan, setEventPlan] = React.useState(null);
    const [opportunities, setOpportunities] = React.useState([]);
    const [opportunitiesTotal, setOpportunitiesTotal] = React.useState(0);
    const [total, setTotal] = React.useState(0);
    const [page, setPage] = React.useState(1);
    const [pageSize, setPageSize] = React.useState(5);
    const [query, setQuery] = React.useState(() => new URLSearchParams(window.location.search || '').get('query') || '');
    const [stage, setStage] = React.useState('all');
    const [dailySegment, setDailySegment] = React.useState('all');
    const [viewMode, setViewMode] = React.useState(() => localStorage.getItem('xfiles_deals_view') || 'table');
    const [loading, setLoading] = React.useState(true);
    const [kanbanLoading, setKanbanLoading] = React.useState(false);
    const [dailyLoading, setDailyLoading] = React.useState(true);
    const [eventPlanLoading, setEventPlanLoading] = React.useState(true);
    const [opportunitiesLoading, setOpportunitiesLoading] = React.useState(true);
    const [auditLoading, setAuditLoading] = React.useState(true);
    const [savingId, setSavingId] = React.useState('');
    const [assistantDeal, setAssistantDeal] = React.useState(null);
    const [assistant, setAssistant] = React.useState(null);
    const [assistantLoading, setAssistantLoading] = React.useState(false);
    const [assistantError, setAssistantError] = React.useState('');
    const [contractDeal, setContractDeal] = React.useState(null);
    const [contractKit, setContractKit] = React.useState(null);
    const [contractLoading, setContractLoading] = React.useState(false);
    const [contractSaving, setContractSaving] = React.useState(false);
    const [contractError, setContractError] = React.useState('');
    const [error, setError] = React.useState('');
    const [form, setForm] = React.useState({
      title: '',
      stage: 'lead',
      score: 20,
      expected_value: 0,
      probability: 0.2,
      margin: 1,
      contact_name: '',
      company: '',
      need: '',
      product_match: '',
      next_action: 'Квалифицировать потребность и выбрать следующий шаг',
    });

    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    const pageWindow = Array.from({ length: Math.min(5, totalPages) }, (_, index) => {
      const start = Math.max(1, Math.min(page - 2, totalPages - 4));
      return start + index;
    }).filter((value) => value <= totalPages);
    const rangeText = total
      ? `${(page - 1) * pageSize + 1}-${Math.min(page * pageSize, total)} из ${total}`
      : '0 из 0';

    const load = React.useCallback(async () => {
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: String(pageSize),
          query,
          stage,
        });
        const [statusData, pageData] = await Promise.all([
          apiJson(`${API_BASE}/api/payme/deals/status`),
          apiJson(`${API_BASE}/api/payme/deals?${params.toString()}`),
        ]);
        setStatus(statusData);
        setRows(Array.isArray(pageData?.items) ? pageData.items : []);
        setTotal(Number(pageData?.total || 0));
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось загрузить сделки'));
      } finally {
        setLoading(false);
      }
    }, [page, pageSize, query, stage]);

    const loadKanban = React.useCallback(async () => {
      setKanbanLoading(true);
      try {
        const params = new URLSearchParams({
          query,
          stage,
          limit_per_stage: '20',
        });
        const data = await apiJson(`${API_BASE}/api/payme/deals/kanban?${params.toString()}`);
        setKanbanColumns(Array.isArray(data?.items) ? data.items : []);
        setKanbanTotal(Number(data?.total || 0));
      } catch (err) {
        console.warn('[X-Files] deal kanban unavailable:', err);
        setKanbanColumns([]);
        setKanbanTotal(0);
      } finally {
        setKanbanLoading(false);
      }
    }, [query, stage]);

    const loadDailyContacts = React.useCallback(async () => {
      setDailyLoading(true);
      try {
        const params = new URLSearchParams({
          limit: '10',
          lead_temperature: dailySegment,
        });
        const data = await apiJson(`${API_BASE}/api/payme/deals/daily-contacts?${params.toString()}`);
        setDailyRows(Array.isArray(data?.items) ? data.items : []);
        setDailyTotal(Number(data?.total || 0));
      } catch (err) {
        console.warn('[X-Files] daily contacts unavailable:', err);
        setDailyRows([]);
        setDailyTotal(0);
      } finally {
        setDailyLoading(false);
      }
    }, [dailySegment]);

    const loadEventPlan = React.useCallback(async () => {
      setEventPlanLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/event-sales-plan?limit=10`);
        setEventPlan(data || null);
      } catch (err) {
        console.warn('[X-Files] event sales plan unavailable:', err);
        setEventPlan(null);
      } finally {
        setEventPlanLoading(false);
      }
    }, []);

    const loadAudit = React.useCallback(async () => {
      setAuditLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/audit?page_size=10&limit=200`);
        setAuditRows(Array.isArray(data?.items) ? data.items : []);
        setAuditTotal(Number(data?.total || 0));
      } catch (err) {
        console.warn('[X-Files] deal audit unavailable:', err);
        setAuditRows([]);
        setAuditTotal(0);
      } finally {
        setAuditLoading(false);
      }
    }, []);

    const loadOpportunities = React.useCallback(async () => {
      setOpportunitiesLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/opportunities?limit=8`);
        setOpportunities(Array.isArray(data?.items) ? data.items : []);
        setOpportunitiesTotal(Number(data?.total || 0));
      } catch (err) {
        console.warn('[X-Files] deal opportunities unavailable:', err);
        setOpportunities([]);
        setOpportunitiesTotal(0);
      } finally {
        setOpportunitiesLoading(false);
      }
    }, []);

    React.useEffect(() => {
      load();
    }, [load]);

    React.useEffect(() => {
      if (viewMode === 'kanban') {
        loadKanban();
      }
      localStorage.setItem('xfiles_deals_view', viewMode);
    }, [viewMode, loadKanban]);

    React.useEffect(() => {
      loadDailyContacts();
    }, [loadDailyContacts]);

    React.useEffect(() => {
      loadEventPlan();
    }, [loadEventPlan]);

    React.useEffect(() => {
      loadAudit();
    }, [loadAudit]);

    React.useEffect(() => {
      loadOpportunities();
    }, [loadOpportunities]);

    function dailyDealPayload(row) {
      const displayName = firstNonEmpty([row.display_name, row.sender_username, row.contact_key, 'Контакт']);
      const preview = cleanDealText(row.latest_message_preview || '', 4000);
      return {
        title: firstNonEmpty([
          `Контакт: ${displayName}`,
          row.latest_lead ? `Контакт из ${row.latest_lead}` : '',
        ]),
        stage: 'lead',
        score: Number(row.deal_score || 0),
        probability: Number(row.deal_score || 0) >= 70 ? 0.45 : Number(row.deal_score || 0) >= 45 ? 0.3 : 0.2,
        margin: 1,
        contact_key: row.contact_key || '',
        contact_name: displayName,
        source: 'contacts',
        source_chat: row.latest_lead || '',
        source_message_id: firstNonEmpty([row.last_message_at, row.contact_key]),
        need: preview,
        product_match: cleanDealText(row.best_product_hint || row.why || '', 1000),
        next_action: row.next_action || 'Квалифицировать контакт и подготовить первое касание',
        notes: cleanDealText(
          [
            `Первое сообщение: ${row.first_message || ''}`,
            `Score: fit ${row.fit_score || 0}, intent ${row.intent_score || 0}, urgency ${row.urgency_score || 0}, pay ${row.ability_to_pay_score || 0}`,
            `Карточка: ${row.qualification_card || ''}`,
            `Не хватает: ${row.missing_qualification || ''}`,
          ].join('\n'),
          4000,
        ),
      };
    }

    function eventDealPayload(row) {
      const who = firstNonEmpty([row.who_to_write, row.sender_name, row.sender_username, row.lead, 'контакт события']);
      const sourceChat = firstNonEmpty([row.lead, row.source_selector, 'events']);
      const messageId = row.message_id != null ? String(row.message_id) : row.id || '';
      const routePart = row.route_address ? `Офлайн-точка: ${row.route_address}` : '';
      const groupPart = row.group_outreach_plan || '';
      return {
        title: firstNonEmpty([
          row.event_date ? `Событие ${row.event_date}: ${row.topic || row.lead || who}` : '',
          `Событие: ${row.topic || row.lead || who}`,
        ]),
        stage: 'lead',
        score: Number(row.score || 0),
        probability: Number(row.probability || 0.25),
        margin: Number(row.margin || 1),
        contact_key: row.contact_key || who,
        contact_name: who,
        source: 'events',
        source_chat: sourceChat,
        source_message_id: messageId,
        need: cleanDealText(row.message || row.message_preview || '', 4000),
        product_match: cleanDealText(row.product_match || row.offer || '', 1200),
        next_action: row.next_action || 'Написать по событийному поводу',
        next_action_at: row.next_action_at || '',
        notes: cleanDealText(
          [
            `Тема: ${row.topic || '—'}`,
            `Дата события: ${row.event_date || 'не определена'}`,
            `Окно касания: ${row.sales_window_label || '—'}`,
            routePart,
            groupPart,
            `Участники/контакты: ${(row.participants || []).join(', ') || '—'}`,
          ].filter(Boolean).join('\n'),
          4000,
        ),
      };
    }

    async function createDeal(event) {
      event.preventDefault();
      setSavingId('new');
      setError('');
      try {
        await apiJson(`${API_BASE}/api/payme/deals`, {
          method: 'POST',
          body: JSON.stringify(form),
        });
        setForm((prev) => ({ ...prev, title: '', contact_name: '', company: '', need: '', product_match: '' }));
        setPage(1);
        await load();
        await loadKanban();
        await loadAudit();
        await loadOpportunities();
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось создать сделку'));
      } finally {
        setSavingId('');
      }
    }

    async function patchDeal(row, patch) {
      setSavingId(row.id);
      setError('');
      try {
        await apiJson(`${API_BASE}/api/payme/deals/${encodeURIComponent(row.id)}`, {
          method: 'PATCH',
          body: JSON.stringify(patch),
        });
        await load();
        await loadKanban();
        await loadAudit();
        await loadOpportunities();
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось обновить сделку'));
      } finally {
        setSavingId('');
      }
    }

    async function deleteDeal(row) {
      setSavingId(row.id);
      setError('');
      try {
        await apiJson(`${API_BASE}/api/payme/deals/${encodeURIComponent(row.id)}`, { method: 'DELETE' });
        await load();
        await loadKanban();
        await loadAudit();
        await loadOpportunities();
      } catch (err) {
        setError(String(err?.message || err || 'Не удалось удалить сделку'));
      } finally {
        setSavingId('');
      }
    }

    async function openAssistant(row) {
      setAssistantDeal(row);
      setAssistant(null);
      setAssistantError('');
      setAssistantLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/${encodeURIComponent(row.id)}/assistant`);
        setAssistant(data);
      } catch (err) {
        setAssistantError(String(err?.message || err || 'Не удалось подготовить переговорный brief'));
      } finally {
        setAssistantLoading(false);
      }
    }

    async function openContractKit(row) {
      setContractDeal(row);
      setContractKit(null);
      setContractError('');
      setContractLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/${encodeURIComponent(row.id)}/contract-kit`);
        setContractKit(data);
      } catch (err) {
        setContractError(String(err?.message || err || 'Не удалось собрать КП и договорный чеклист'));
      } finally {
        setContractLoading(false);
      }
    }

    async function updateContractStatus(statusValue) {
      if (!contractDeal) return;
      setContractSaving(true);
      setContractError('');
      try {
        const data = await apiJson(`${API_BASE}/api/payme/deals/${encodeURIComponent(contractDeal.id)}/contract-status`, {
          method: 'PATCH',
          body: JSON.stringify({ contract_status: statusValue }),
        });
        setContractKit(data);
        await loadAudit();
      } catch (err) {
        setContractError(String(err?.message || err || 'Не удалось обновить статус договора'));
      } finally {
        setContractSaving(false);
      }
    }

    function downloadContractProposal() {
      if (!contractDeal || !contractKit) return;
      const safeName = String(contractDeal.title || contractDeal.id || 'deal')
        .toLowerCase()
        .replace(/[^a-zа-яё0-9_-]+/gi, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 80) || contractDeal.id;
      downloadTextFile(`kp-${safeName}.md`, contractKit.proposal_document || contractKit.short_proposal || '');
    }

    async function applyAssistantRecommendation() {
      if (!assistantDeal || !assistant) return;
      await patchDeal(assistantDeal, {
        score: Number(assistant.recommended_score || assistantDeal.score || 0),
        next_action: assistant.recommended_next_action || assistantDeal.next_action || '',
      });
      setAssistantDeal(null);
      setAssistant(null);
    }

    return html`
      <div className="page">
        <${PageHeader}
          title="X-Files Deals"
          subtitle="Revenue operating system & engine: сделки, квалификация, следующий шаг и ожидаемая прибыль."
          active="deals"
        />

        ${status?.postgresql_waiting && !status?.postgresql_available
          ? html`
            <section className="panel" style=${{ borderColor: '#fed7aa', background: 'rgba(255,251,235,.86)', marginBottom: '12px' }}>
              <h3>PostgreSQL подключается</h3>
              <p className="subtle">${status.message || 'Операционное хранилище временно недоступно.'}</p>
              <p className="subtle">Пока backend ждёт PostgreSQL, таблицы сделок показывают локальный кеш state.json, поэтому страница не должна быть пустой.</p>
            </section>
          `
          : null}

        <section className="cards-grid">
          <div className=${`card ${status?.postgresql_available ? 'tone-green' : 'tone-yellow'}`}>
            <div className="card-label">Хранилище</div>
            <div className="card-value">${status?.storage === 'postgresql' ? 'PostgreSQL' : 'state.json'}</div>
            <div className="card-sub">${status?.message || 'Загружаю статус'}</div>
          </div>
          <div className="card tone-green">
            <div className="card-label">Всего сделок</div>
            <div className="card-value">${status?.total || 0}</div>
            <div className="card-sub">активных ${status?.active || 0} · won ${status?.won || 0} · lost ${status?.lost || 0}</div>
          </div>
          <div className="card tone-green">
            <div className="card-label">Потенциал</div>
            <div className="card-value">${fmtMoney(status?.expected_value)} ₽</div>
            <div className="card-sub">сумма открытых возможностей</div>
          </div>
          <div className="card tone-green">
            <div className="card-label">Ожидаемая прибыль</div>
            <div className="card-value">${fmtMoney(status?.expected_profit)} ₽</div>
            <div className="card-sub">value × probability × margin</div>
          </div>
          <div className=${`card ${(status?.overdue || 0) > 0 ? 'tone-red' : (status?.due_soon || 0) > 0 ? 'tone-yellow' : 'tone-green'}`}>
            <div className="card-label">SLA / просрочки</div>
            <div className="card-value">${status?.overdue || 0}</div>
            <div className="card-sub">просрочено · скоро ${status?.due_soon || 0} · в норме ${status?.sla_green || 0}</div>
          </div>
          <div className="card tone-green">
            <div className="card-label">Audit log</div>
            <div className="card-value">${auditTotal || 0}</div>
            <div className="card-sub">последние ручные действия по сделкам</div>
          </div>
        </section>

        <${ErrorBox} error=${error || status?.last_error} tag="section" />

        ${!loading && !error && Number(status?.total || 0) === 0 ? html`
          <section className="panel">
            <div className="empty">
              Данных по сделкам пока нет. Это нормально для новой поставки: сделки появятся после добавления CRM/enReach-сигналов или ручного создания первой сделки.
            </div>
          </section>
        ` : null}

        <section className="panel">
          <div className="section-title">Лучшие сделочные возможности</div>
          <div className="section-subtitle">
            Система ранжирует сделки из кеша по ожидаемой прибыли, срочности, стадии и цене часа внимания.
            ${opportunitiesTotal ? ` Всего активных возможностей: ${opportunitiesTotal}.` : ''}
          </div>
          <div className="opportunity-list">
            ${opportunitiesLoading && !opportunities.length ? html`
              <${LoadingNotice} message="Считаю лучшие возможности…" details="Без Telegram и LLM: беру готовые сделки из кеша и сортирую по деньгам/срочности." />
            ` : null}
            ${!opportunitiesLoading && !opportunities.length ? html`
              <div className="empty compact-empty">Пока нет активных сделочных возможностей. Создайте сделку или переведите лид из enReach.</div>
            ` : null}
            ${opportunities.map((item) => html`
              <article className="opportunity-card" key=${item.id}>
                <div className="opportunity-rank">#${item.rank || '—'}</div>
                <div className="opportunity-main">
                  <div className="opportunity-head">
                    <div>
                      <div className="opportunity-title">${item.title || item.who || 'Сделочная возможность'}</div>
                      <div className="subtle">${item.who || 'контакт'}${item.company ? ` · ${item.company}` : ''}${item.source_chat ? ` · ${item.source_chat}` : ''}</div>
                    </div>
                    <div className="opportunity-score">
                      <span className=${`score-pill ${Number(item.priority_score || 0) >= 75 ? 'score-hot' : Number(item.priority_score || 0) >= 50 ? 'score-warm' : 'score-cold'}`}>
                        ${item.priority_score || 0}/100
                      </span>
                      <div className="subtle">${item.stage_label || stageLabel(item.stage)}</div>
                    </div>
                  </div>
                  <div className="opportunity-grid">
                    <div>
                      <div className="card-label">Что нужно</div>
                      <div className="opportunity-text">${item.need || 'Потребность нужно уточнить.'}</div>
                    </div>
                    <div>
                      <div className="card-label">Что предложить</div>
                      <div className="opportunity-text">${item.offer || 'Короткая диагностика и следующий шаг.'}</div>
                    </div>
                    <div>
                      <div className="card-label">Когда писать</div>
                      <div className="opportunity-text">${item.when_to_write || 'сегодня'}</div>
                    </div>
                    <div>
                      <div className="card-label">Первое сообщение</div>
                      <div className="opportunity-text">${item.first_message || item.next_action || 'Подготовить персональное касание.'}</div>
                    </div>
                  </div>
                  <div className="opportunity-foot">
                    <span className="badge badge-active">${fmtMoney(item.expected_profit)} ₽ expected profit</span>
                    <span className="badge">${fmtMoney(item.profit_per_user_hour)} ₽/час</span>
                    <span className="badge">${Math.round(Number(item.probability || 0) * 100)}% вероятность</span>
                    <span className="badge">${item.why_now || 'есть сигнал'}</span>
                  </div>
                </div>
              </article>
            `)}
          </div>
        </section>

        <section className="panel">
          <div className="section-title">10 контактов, которым стоит написать сегодня</div>
          <div className="section-subtitle">
            Рекомендации считаются из кеша контактов/DuckDB без Telegram-запросов: score, причина, первое касание и следующий шаг.
            ${dailyTotal ? ` Всего кандидатов: ${dailyTotal}.` : ''}
          </div>
          <div className="toolbar" style=${{ padding: '12px 0 14px' }}>
            <div className="toolbar-group segmented">
              ${LEAD_TEMPERATURES.map(([value, label]) => html`
                <button
                  key=${value}
                  className=${`btn ${dailySegment === value ? 'btn-active' : ''}`}
                  onClick=${() => setDailySegment(value)}
                >${label}</button>
              `)}
            </div>
          </div>
          <div className="table-wrap daily-table-wrap">
            ${dailyLoading && !dailyRows.length ? html`<${LoadingNotice} message="Готовлю список контактов…" details="Читаю кеш контактов, квалификации и уже созданные сделки." />` : null}
            ${!dailyLoading && !dailyRows.length ? html`<div className="empty">Пока нет контактов для сегодняшнего outreach. Обновите кеш контактов или добавьте источники в сканирование.</div>` : null}
            ${dailyRows.length ? html`
              <table className="daily-table">
                <thead>
                  <tr>
                    <th>Контакт</th>
                    <th>Score</th>
                    <th>Почему сейчас</th>
                    <th>Квалификация</th>
                    <th>Первое сообщение</th>
                    <th>Следующее действие</th>
                    <th>Сделка</th>
                  </tr>
                </thead>
                <tbody>
                  ${dailyRows.map((row) => html`
                    <tr key=${row.contact_key}>
                      <td>
                        <div className="font-semibold">${row.display_name || row.contact_key}</div>
                        <div className="subtle">${row.sender_username ? `@${row.sender_username}` : row.contact_key}</div>
                        <div className="subtle">${row.latest_lead || 'без чата'} · ${fmtDate(row.last_message_at)}</div>
                      </td>
                      <td>
                        <span className=${`score-pill ${Number(row.deal_score || 0) >= 70 ? 'score-hot' : Number(row.deal_score || 0) >= 45 ? 'score-warm' : 'score-cold'}`}>
                          ${row.deal_score || 0}/100
                        </span>
                        <div className="subtle">${row.lead_temperature_label || 'Нужно больше данных'}</div>
                        <div className="subtle">${row.total_messages || 0} сообщ. · ${row.qualification_count || 0} анализ</div>
                        <div className="subtle">
                          fit ${row.fit_score || 0} · intent ${row.intent_score || 0} · urgency ${row.urgency_score || 0} · pay ${row.ability_to_pay_score || 0}
                        </div>
                      </td>
                      <td className="cell-text">
                        <div>${row.why_now || row.why || 'есть контактная история'}</div>
                        <div className="subtle">${row.score_explanation || ''}</div>
                      </td>
                      <td className="cell-text">
                        <div>${row.qualification_card || row.best_product_hint || 'Профиль появится после сообщений контакта.'}</div>
                        <div className="subtle">Не хватает: ${row.missing_qualification || '—'}</div>
                      </td>
                      <td className="cell-text">${row.first_message || '—'}</td>
                      <td className="cell-text">${row.next_action || '—'}</td>
                      <td>
                        ${row.has_deal ? html`
                          <div className="badge badge-active">сделка уже есть</div>
                          <div className="subtle">${row.deal_title || row.deal_id || ''}</div>
                        ` : html`
                          <${DealActionButton}
                            payload=${() => dailyDealPayload(row)}
                            label="Создать сделку"
                            title="Создать сделку из рекомендации"
                            onDone=${() => { load(); loadKanban(); loadDailyContacts(); loadAudit(); loadOpportunities(); }}
                          />
                        `}
                      </td>
                    </tr>
                  `)}
                </tbody>
              </table>
            ` : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-title">События, календарь и маршруты как источник сделок</div>
          <div className="section-subtitle">
            Поводы считаются из кеша мероприятий и справочника адресов маршрутов: кому написать, какой оффер уместен,
            когда лучше касаться до/после события и где можно собрать день офлайн-встреч.
          </div>
          <div className="cards-grid compact-cards">
            <div className="card tone-green">
              <div className="card-label">События</div>
              <div className="card-value">${eventPlan?.total_events || 0}</div>
              <div className="card-sub">источник поводов для касаний</div>
            </div>
            <div className="card tone-green">
              <div className="card-label">С датой</div>
              <div className="card-value">${eventPlan?.events_with_dates || 0}</div>
              <div className="card-sub">готовы для календарных окон</div>
            </div>
            <div className="card tone-yellow">
              <div className="card-label">С маршрутом</div>
              <div className="card-value">${eventPlan?.events_with_routes || 0}</div>
              <div className="card-sub">можно планировать офлайн-встречи</div>
            </div>
            <div className="card tone-yellow">
              <div className="card-label">Групповой outreach</div>
              <div className="card-value">${eventPlan?.group_outreach_candidates || 0}</div>
              <div className="card-sub">события с несколькими контактами</div>
            </div>
          </div>
          <div className="table-wrap daily-table-wrap">
            ${eventPlanLoading && !(eventPlan?.items || []).length ? html`<${LoadingNotice} message="Готовлю событийные поводы…" details="Читаю кеш мероприятий и маршрутов без новых запросов к Telegram." />` : null}
            ${!eventPlanLoading && !(eventPlan?.items || []).length ? html`<div className="empty">Пока нет событийных поводов. Проверьте кеш мероприятий и дату события.</div>` : null}
            ${(eventPlan?.items || []).length ? html`
              <table className="daily-table">
                <thead>
                  <tr>
                    <th>Событие</th>
                    <th>Окно касания</th>
                    <th>Кому / участники</th>
                    <th>Оффер</th>
                    <th>Маршрут</th>
                    <th>Сделка</th>
                  </tr>
                </thead>
                <tbody>
                  ${(eventPlan?.items || []).map((row) => html`
                    <tr key=${row.id}>
                      <td className="cell-text">
                        <div className="font-semibold">${row.lead || 'событие'} · ${row.topic || 'повод'}</div>
                        <div className="subtle">дата события: ${row.event_date || 'не определена'} · сообщение: ${fmtDate(row.message_date)}</div>
                        <div>${row.message_preview || row.message || '—'}</div>
                      </td>
                      <td>
                        <span className=${`sla-badge ${row.sales_window_label === 'после события' ? 'sla-yellow' : 'sla-green'}`}>
                          ${row.sales_window_label || 'сейчас'}
                        </span>
                        <div className="subtle">${fmtDate(row.next_action_at)}</div>
                        <div className="cell-text">${row.next_action || 'написать по событию'}</div>
                      </td>
                      <td className="cell-text">
                        <div className="font-semibold">${row.who_to_write || 'контакт события'}</div>
                        <div className="subtle">${row.related_contacts_count || 0} связанных контактов</div>
                        <div className="subtle">${(row.participants || []).join(', ') || '—'}</div>
                        ${row.group_outreach_plan ? html`<div className="badge badge-active">групповой план</div>` : null}
                      </td>
                      <td className="cell-text">
                        <div>${row.product_match || row.offer || 'диагностика потребности'}</div>
                        <div className="subtle">score ${row.score || 0}/100 · ${Math.round(Number(row.probability || 0) * 100)}% · маржа ${Math.round(Number(row.margin || 1) * 100)}%</div>
                      </td>
                      <td className="cell-text">
                        ${row.route_address ? html`
                          <div className="font-semibold">${row.route_address}</div>
                          <div className="subtle">можно связать с днём встреч</div>
                        ` : html`<div className="subtle">адрес не найден</div>`}
                      </td>
                      <td>
                        ${row.has_deal ? html`
                          <div className="badge badge-active">сделка уже есть</div>
                          <div className="subtle">${row.deal_title || row.deal_id || ''}</div>
                        ` : html`
                          <${DealActionButton}
                            payload=${() => eventDealPayload(row)}
                            label="Создать сделку"
                            title="Создать сделку из события"
                            onDone=${() => { load(); loadKanban(); loadEventPlan(); loadAudit(); loadOpportunities(); }}
                          />
                        `}
                      </td>
                    </tr>
                  `)}
                </tbody>
              </table>
            ` : null}
          </div>
          ${(eventPlan?.meeting_days || []).length ? html`
            <div className="section-title" style=${{ marginTop: '18px' }}>Дни встреч по маршрутам</div>
            <div className="section-subtitle">Адреса объединяются по справочнику маршрутов: сколько лидов рядом, сколько событий и контактов можно подготовить в один день.</div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Адрес</th>
                    <th>Лиды / события / контакты</th>
                    <th>GPS</th>
                    <th>День встреч</th>
                    <th>Подготовка</th>
                  </tr>
                </thead>
                <tbody>
                  ${(eventPlan?.meeting_days || []).map((row) => html`
                    <tr key=${row.address_key}>
                      <td>
                        <div className="font-semibold">${row.address}</div>
                        <div className="subtle">${row.messages_count || 0} сообщений рядом</div>
                      </td>
                      <td>
                        <div>${row.leads_count || 0} лидов · ${row.events_count || 0} событий · ${row.contacts_count || 0} контактов</div>
                      </td>
                      <td>
                        <span className=${`badge ${row.gps_ready ? 'badge-active' : ''}`}>${row.gps_ready ? 'GPS готов' : 'геокодировать'}</span>
                        <div className="subtle">${row.lat && row.lon ? `${row.lat}, ${row.lon}` : ''}</div>
                      </td>
                      <td>${row.suggested_day || 'завтра'}</td>
                      <td className="cell-text">${row.action || 'собрать список встреч и сообщений'}</td>
                    </tr>
                  `)}
                </tbody>
              </table>
            </div>
          ` : null}
        </section>

        <${DealCreateForm}
          form=${form}
          setForm=${setForm}
          createDeal=${createDeal}
          savingId=${savingId}
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <div className="view-tabs" role="tablist" aria-label="Вид сделок">
              <button
                type="button"
                className=${`view-tab ${viewMode === 'table' ? 'view-tab-active' : ''}`}
                onClick=${() => setViewMode('table')}
              >
                Таблица
              </button>
              <button
                type="button"
                className=${`view-tab ${viewMode === 'kanban' ? 'view-tab-active' : ''}`}
                onClick=${() => setViewMode('kanban')}
              >
                Kanban
              </button>
            </div>
            <input className="input" placeholder="Поиск по сделкам, контактам, потребностям…" value=${query} onChange=${(e) => { setQuery(e.target.value); setPage(1); }} />
            <select className="select" value=${stage} onChange=${(e) => { setStage(e.target.value); setPage(1); }}>
              <option value="all">Все стадии</option>
              ${STAGES.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select>
            <select className="select" value=${String(pageSize)} onChange=${(e) => { setPageSize(Number(e.target.value || 5)); setPage(1); }}>
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <button className="btn" onClick=${() => { load(); loadKanban(); loadEventPlan(); loadOpportunities(); }} disabled=${loading || kanbanLoading}>
              ${loading || kanbanLoading ? 'Обновляю…' : 'Обновить'}
            </button>
          </div>
        </section>

        <${DealsPipelinePanel}
          viewMode=${viewMode}
          kanbanTotal=${kanbanTotal}
          kanbanLoading=${kanbanLoading}
          kanbanColumns=${kanbanColumns}
          rows=${rows}
          loading=${loading}
          savingId=${savingId}
          patchDeal=${patchDeal}
          openAssistant=${openAssistant}
          openContractKit=${openContractKit}
          deleteDeal=${deleteDeal}
          rangeText=${rangeText}
          page=${page}
          totalPages=${totalPages}
          pageWindow=${pageWindow}
          setPage=${setPage}
        />

        <section className="panel">
          <div className="section-title">Журнал действий</div>
          <div className="section-subtitle">Короткая история ручных операций: создание, изменение стадии, обновления экономики, удаление и создание из enReach.</div>
          <div className="audit-list">
            ${auditLoading && !auditRows.length ? html`<${LoadingNotice} message="Загружаю журнал…" details="Читаю последние действия пользователя по сделкам." />` : null}
            ${!auditLoading && !auditRows.length ? html`<div className="empty compact-empty">Действий пока нет. Журнал начнёт заполняться после создания или изменения сделки.</div>` : null}
            ${auditRows.map((item) => html`
              <div className="audit-row" key=${item.id}>
                <div>
                  <div className="font-semibold">${auditActionLabel(item.action)} · ${item.deal_title || item.deal_id || 'сделка'}</div>
                  <div className="subtle">${fmtDate(item.ts)} · ${item.source || 'ui'} · ${item.actor || 'user'}</div>
                </div>
                <div className="audit-meta">
                  <span className="badge">${item.before_stage || '—'} → ${item.after_stage || '—'}</span>
                  <div className="subtle">${auditChangesText(item.changes)}</div>
                </div>
              </div>
            `)}
          </div>
        </section>
        ${assistantDeal ? html`
          <${DealAssistantModal}
            deal=${assistantDeal}
            assistant=${assistant}
            loading=${assistantLoading}
            error=${assistantError}
            onClose=${() => { setAssistantDeal(null); setAssistant(null); setAssistantError(''); }}
            onApply=${applyAssistantRecommendation}
          />
        ` : null}
        ${contractDeal ? html`
          <${DealContractModal}
            deal=${contractDeal}
            kit=${contractKit}
            loading=${contractLoading}
            error=${contractError}
            saving=${contractSaving}
            onClose=${() => { setContractDeal(null); setContractKit(null); setContractError(''); }}
            onStatusChange=${updateContractStatus}
            onDownload=${downloadContractProposal}
          />
        ` : null}
      </div>
    `;
  }

  const rootNode = document.getElementById('app');
  if (!rootNode) return;
  ReactDOM.createRoot(rootNode).render(html`<${DealsPage} />`);
})();
