/* React needs page: X-Files intent signals */
'use strict';

(function mountReactNeedsPage() {
  if (!window.React || !window.ReactDOM || !window.htm || !window.BackfrontReactShared) {
    console.error('[React] Runtime libraries are not loaded for Needs page');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const {
    PageHeader,
    ErrorBox,
    LoadingNotice,
    TablePaginationFooter,
    DataTable,
    FormGrid,
    FormField,
    DealActionButton,
    cleanDealText,
    firstNonEmpty,
  } = window.BackfrontReactShared;

  const TAG_OPTIONS = [
    ['all', 'Все сигналы'],
    ['urgent', 'Срочно'],
    ['budget', 'Есть деньги'],
    ['contractor', 'Ищет подрядчика'],
    ['recommendation', 'Просит рекомендацию'],
    ['complaint', 'Жалуется'],
    ['event', 'Планирует мероприятие'],
    ['hiring', 'Нанимает'],
    ['service_purchase', 'Покупает сервис'],
  ];

  const SOURCE_OPTIONS = [
    ['all', 'Все источники'],
    ['message', 'Сообщения'],
    ['enReach', 'enReach'],
    ['crm', 'CRM'],
    ['ocr', 'OCR'],
    ['event', 'Мероприятия'],
    ['route', 'Маршруты'],
    ['import', 'Import'],
  ];

  function buildPageWindow(page, totalPages) {
    const safeTotal = Math.max(1, Number(totalPages || 1));
    const safePage = Math.min(Math.max(1, Number(page || 1)), safeTotal);
    const start = Math.max(1, safePage - 2);
    const end = Math.min(safeTotal, start + 4);
    const items = [];
    for (let value = start; value <= end; value += 1) items.push(value);
    return items;
  }

  function formatDate(value) {
    const raw = String(value || '').trim();
    if (!raw) return '—';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return raw.slice(0, 19).replace('T', ' ');
    return date.toLocaleString('ru-RU', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  }

  function formatMoney(value) {
    const amount = Number(value || 0);
    if (!Number.isFinite(amount) || amount <= 0) return '';
    return amount.toLocaleString('ru-RU', {
      maximumFractionDigits: 0,
    });
  }

  function formatPercent(value) {
    const number = Number(value || 0);
    if (!Number.isFinite(number) || number <= 0) return '';
    return `${Math.round(number * 100)}%`;
  }

  function formatRange(page, pageSize, total) {
    const safeTotal = Number(total || 0);
    if (!safeTotal) return '0 из 0';
    const start = (Number(page || 1) - 1) * Number(pageSize || 5) + 1;
    const end = Math.min(safeTotal, start + Number(pageSize || 5) - 1);
    return `${start}-${end} из ${safeTotal}`;
  }

  async function apiJson(url, { timeoutMs = 18000 } = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, { timeoutMs });
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      const text = await response.text();
      let data = null;
      try {
        data = text ? JSON.parse(text) : null;
      } catch (_error) {
        data = null;
      }
      if (!response.ok) {
        const detail = data?.detail || text || response.statusText || 'API error';
        throw new Error(`HTTP ${response.status} ${response.statusText} — ${detail}`);
      }
      return data;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function needDealPayload(row) {
    const sourceMessageId = firstNonEmpty([
      row.message_id != null ? String(row.message_id) : '',
      row.id,
    ]);
    const titleBasis = firstNonEmpty([
      row.need,
      row.contact_name ? `Потребность: ${row.contact_name}` : '',
      row.lead ? `Потребность из ${row.lead}` : '',
      row.text,
    ]);
    const scoreProbability = Number(row.score || 0) >= 72 ? 0.45 : Number(row.score || 0) >= 48 ? 0.3 : 0.18;
    const productProbability = Number(row.product_match_probability || 0);
    const probability = Math.max(scoreProbability, productProbability);
    return {
      title: cleanDealText(titleBasis, 480),
      stage: 'lead',
      score: Math.max(0, Math.min(100, Number(row.score || 0))),
      expected_value: Number(row.product_expected_value_hint || 0),
      probability,
      margin: Number(row.product_margin || 1),
      contact_key: firstNonEmpty([row.contact_key, row.sender_username, row.contact_name, row.lead]),
      contact_name: row.contact_name || row.sender_username || '',
      company: row.company || '',
      source: 'needs',
      source_chat: firstNonEmpty([row.lead, row.source_selector, row.source_label]),
      source_message_id: sourceMessageId,
      need: cleanDealText(row.need || row.text, 4000),
      product_match: cleanDealText(row.product_match, 1200),
      next_action: cleanDealText(row.first_touch || 'Квалифицировать потребность и подготовить первое касание', 1600),
      notes: cleanDealText(
        `Создано из Потребностей. Источник: ${row.source_label || row.source}. Сигналы: ${(row.tag_labels || []).join(', ')}`,
        2000,
      ),
    };
  }

  function SignalBadges({ row }) {
    const labels = Array.isArray(row?.tag_labels) ? row.tag_labels : [];
    return html`
      <div className="badge-row">
        ${labels.slice(0, 4).map((label) => html`<span key=${label} className="badge">${label}</span>`)}
        ${row?.urgency_label ? html`<span className=${`badge score-${row.urgency_label === 'горячий' ? 'hot' : row.urgency_label === 'тёплый' ? 'warm' : 'cold'}`}>${row.urgency_label}</span>` : null}
      </div>
    `;
  }

  function NeedsTable({ rows, loading }) {
    if (loading && !rows.length) {
      return html`<${LoadingNotice} message="Загружаю потребности из DuckDB/enReach…" details="Открываем локальный кеш без повторного Telegram sync." />`;
    }
    if (!rows.length) {
      return html`<div className="empty">Покупательские сигналы под текущие фильтры пока не найдены.</div>`;
    }
    const columns = [
      {
        key: 'date',
        label: 'Дата',
        render: (row) => html`
          <strong>${formatDate(row.date_utc)}</strong>
          ${row.message_id != null ? html`<div className="muted">#${row.message_id}</div>` : null}
        `,
      },
      {
        key: 'source',
        label: 'Источник',
        render: (row) => html`
          <strong>${row.source_label || row.source || '—'}</strong>
          <div className="muted">${row.lead || row.source_selector || '—'}</div>
        `,
      },
      {
        key: 'contact',
        label: 'Контакт',
        render: (row) => html`
          <strong>${row.contact_name || row.sender_username || row.contact_key || '—'}</strong>
          ${row.company ? html`<div className="muted">${row.company}</div>` : null}
          ${row.has_deal ? html`<div className="deal-hint">уже есть сделка</div>` : null}
        `,
      },
      {
        key: 'signal',
        label: 'Сигнал',
        render: (row) => html`
          <div className="score-pill">${row.score || 0}</div>
          <${SignalBadges} row=${row} />
        `,
      },
      {
        key: 'need',
        label: 'Потребность',
        className: 'wide-cell',
        render: (row) => html`
          <strong>${row.need || '—'}</strong>
          ${row.pain ? html`<div className="muted">Боль: ${row.pain}</div>` : null}
          ${row.budget ? html`<div className="muted">Бюджет: ${row.budget}</div>` : null}
          ${row.deadline ? html`<div className="muted">Дедлайн: ${row.deadline}</div>` : null}
          ${row.objection ? html`<div className="muted">Возражение: ${row.objection}</div>` : null}
        `,
      },
      {
        key: 'offer',
        label: 'Что предложить',
        className: 'medium-cell',
        render: (row) => html`
          <strong>${row.product_match || 'быстрая диагностика потребности'}</strong>
          ${row.product_match_score ? html`<div className="muted">match score: ${row.product_match_score}</div>` : null}
          ${row.product_match_probability ? html`<div className="muted">вероятность закрытия: ${formatPercent(row.product_match_probability)}</div>` : null}
          ${row.product_expected_value_hint ? html`<div className="muted">оценка чека: ${formatMoney(row.product_expected_value_hint)} ₽</div>` : null}
          ${row.product_expected_profit_rank ? html`<div className="muted">ожидаемая прибыль: ${formatMoney(row.product_expected_profit_rank)} ₽</div>` : null}
          ${row.offer_recommendation ? html`<div className="muted">решение: ${row.offer_recommendation}</div>` : null}
          ${row.alternative_product ? html`<div className="muted">альтернатива: ${row.alternative_product}</div>` : null}
          ${row.do_not_sell_reason ? html`<div className="muted warning-text">не продавать если: ${row.do_not_sell_reason}</div>` : null}
        `,
      },
      {
        key: 'first_touch',
        label: 'Первое касание',
        className: 'medium-cell',
        render: (row) => row.pitch || row.first_touch || '—',
      },
      {
        key: 'actions',
        label: 'Действия',
        render: (row) => html`
          <${DealActionButton}
            payload=${() => needDealPayload(row)}
            label=${row.has_deal ? 'Открыть/не дублить' : 'Создать сделку'}
            doneLabel="Сделка создана"
            existingLabel="Сделка уже есть"
            title="Создать сделку из покупательского сигнала"
          />
        `,
      },
    ];
    return html`
      <${DataTable}
        columns=${columns}
        rows=${rows}
        getRowKey=${(row) => row.id}
        wrapperClassName="table-scroll"
        tableClassName="data-table"
        emptyMessage="Покупательские сигналы под текущие фильтры пока не найдены."
      />
    `;
  }

  function ManualNeedForm() {
    const [form, setForm] = React.useState({
      title: '',
      contact: '',
      company: '',
      source: '',
      need: '',
      product: '',
      nextAction: 'Квалифицировать потребность и подобрать оффер',
    });

    const payload = {
      title: firstNonEmpty([form.title, form.contact ? `Потребность: ${form.contact}` : '', form.need]),
      stage: 'lead',
      score: 30,
      probability: 0.2,
      contact_key: firstNonEmpty([form.contact, form.company, form.source]),
      contact_name: form.contact,
      company: form.company,
      source: 'needs',
      source_chat: form.source,
      source_message_id: firstNonEmpty([form.source, form.title, form.need]),
      need: cleanDealText(form.need, 4000),
      product_match: cleanDealText(form.product, 1200),
      next_action: cleanDealText(form.nextAction, 1200),
      notes: 'Создано вручную из страницы Потребности.',
    };

    function updateField(field, value) {
      setForm((current) => ({ ...current, [field]: value }));
    }

    return html`
      <section className="panel">
        <div className="section-title">Создать сделку вручную</div>
        <div className="section-subtitle">
          Если сигнал пришёл из звонка, встречи или внешнего источника, его можно сразу положить в pipeline.
        </div>
        <${FormGrid}>
          <${FormField} label="Название">
            <input className="input" value=${form.title} onChange=${(e) => updateField('title', e.target.value)} placeholder="Например: нужен подрядчик на CRM" />
          <//>
          <${FormField} label="Контакт">
            <input className="input" value=${form.contact} onChange=${(e) => updateField('contact', e.target.value)} placeholder="Имя, username или id" />
          <//>
          <${FormField} label="Компания">
            <input className="input" value=${form.company} onChange=${(e) => updateField('company', e.target.value)} placeholder="Компания, если известна" />
          <//>
          <${FormField} label="Источник">
            <input className="input" value=${form.source} onChange=${(e) => updateField('source', e.target.value)} placeholder="Чат, канал, событие или OCR" />
          <//>
          <${FormField} label="Потребность" wide=${true}>
            <textarea className="input" rows="5" value=${form.need} onChange=${(e) => updateField('need', e.target.value)} placeholder="Полный текст боли, задачи, запроса или сигнала покупки"></textarea>
          <//>
          <${FormField} label="Что предложить">
            <input className="input" value=${form.product} onChange=${(e) => updateField('product', e.target.value)} placeholder="Оффер, продукт или гипотеза" />
          <//>
          <${FormField} label="Следующее действие">
            <input className="input" value=${form.nextAction} onChange=${(e) => updateField('nextAction', e.target.value)} />
          <//>
        <//>
        <div className="hint">
          <${DealActionButton}
            payload=${payload}
            label="Создать сделку"
            title="Создать сделку из потребности"
          />
        </div>
      </section>
    `;
  }

  function NeedsPage() {
    const [rows, setRows] = React.useState([]);
    const [total, setTotal] = React.useState(0);
    const [page, setPage] = React.useState(1);
    const [pageSize, setPageSize] = React.useState(5);
    const [query, setQuery] = React.useState('');
    const [tag, setTag] = React.useState('all');
    const [source, setSource] = React.useState('all');
    const [generatedAt, setGeneratedAt] = React.useState('');
    const [autoCreatedDeals, setAutoCreatedDeals] = React.useState(0);
    const [loading, setLoading] = React.useState(false);
    const [error, setError] = React.useState('');

    const totalPages = Math.max(1, Math.ceil(Number(total || 0) / Number(pageSize || 5)));

    const loadRows = React.useCallback(async () => {
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: String(pageSize),
          query,
          tag,
          source,
        });
        const data = await apiJson(`/api/payme/needs/signals?${params.toString()}`);
        setRows(Array.isArray(data?.items) ? data.items : []);
        setTotal(Number(data?.total || 0));
        setGeneratedAt(data?.generated_at || '');
        setAutoCreatedDeals(Number(data?.auto_created_deals || 0));
      } catch (err) {
        const rawMessage = String(err?.message || err || '');
        if (err?.name === 'AbortError' || rawMessage.includes('aborted') || rawMessage.includes('signal is aborted')) {
          return;
        }
        console.error('[Needs] load failed:', err);
        setError(rawMessage || 'Не удалось загрузить потребности');
      } finally {
        setLoading(false);
      }
    }, [page, pageSize, query, tag, source]);

    React.useEffect(() => {
      loadRows();
    }, [loadRows]);

    function resetPageAnd(fn) {
      setPage(1);
      fn();
    }

    return html`
      <div className="page">
        <${PageHeader}
          title="Потребности"
          subtitle="Покупательские сигналы из сообщений, CRM, OCR, событий и enReach: боль → оффер → первое касание → сделка."
          active="needs"
        />

        <section className="panel">
          <div className="section-title">Intent-сигналы</div>
          <div className="section-subtitle">
            Данные читаются из локального DuckDB/enReach и не запускают повторный Telegram sync при открытии страницы.
            ${generatedAt ? html`<span> Последнее обновление: ${formatDate(generatedAt)}.</span>` : null}
            ${autoCreatedDeals > 0 ? html`<span className="auto-draft-note"> Автоматически создано draft-сделок: ${autoCreatedDeals}.</span>` : null}
          </div>
          <div className="toolbar panel-toolbar">
            <input
              className="input search-input"
              value=${query}
              onChange=${(event) => resetPageAnd(() => setQuery(event.target.value))}
              placeholder="Поиск по потребности, контакту, чату..."
            />
            <select className="input select-input" value=${tag} onChange=${(event) => resetPageAnd(() => setTag(event.target.value))}>
              ${TAG_OPTIONS.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select>
            <select className="input select-input" value=${source} onChange=${(event) => resetPageAnd(() => setSource(event.target.value))}>
              ${SOURCE_OPTIONS.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select>
            <select className="input select-input small" value=${pageSize} onChange=${(event) => resetPageAnd(() => setPageSize(Number(event.target.value) || 5))}>
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <button className="btn" type="button" onClick=${loadRows} disabled=${loading}>${loading ? 'Обновляю…' : 'Обновить'}</button>
          </div>
          <${ErrorBox} error=${error} />
          <${NeedsTable} rows=${rows} loading=${loading} />
          <${TablePaginationFooter}
            rangeText=${formatRange(page, pageSize, total)}
            page=${page}
            totalPages=${totalPages}
            pageWindow=${buildPageWindow(page, totalPages)}
            onPrev=${() => setPage((value) => Math.max(1, value - 1))}
            onNext=${() => setPage((value) => Math.min(totalPages, value + 1))}
            onGo=${(value) => setPage(value)}
          />
        </section>

        <${ManualNeedForm} />
      </div>
    `;
  }

  function renderNeedsPage() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Needs page');
      return;
    }
    ReactDOM.createRoot(rootNode).render(html`<${NeedsPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderNeedsPage, { once: true });
  } else {
    renderNeedsPage();
  }
})();
