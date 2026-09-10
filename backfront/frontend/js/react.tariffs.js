/* React tariffs calculator page */
'use strict';

(function mountReactTariffsPage() {
  if (!window.React || !window.ReactDOM || !window.htm || !window.BackfrontReactShared) {
    console.error('[React] Runtime libraries are not loaded for Tariffs page');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const { PageHeader } = window.BackfrontReactShared;
  const API_BASE = window.API_BASE || (window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : 'http://localhost:8001');

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const response = await fetch(url, {
      cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });
    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`HTTP ${response.status}${text ? ` — ${text}` : ''}`);
    }
    return await response.json();
  }

  const PLAN_DEFS = [
    {
      key: 'free',
      title: 'Free-demo',
      price: 0,
      subtitle: 'попробовать ценность без риска',
      limits: { channels: 1, groups: 0, personal: 1, bots: 0, llmOps: 200, ocrImages: 0, contacts: 50, users: 1 },
      includes: [
        '1 канал и 1 личная переписка',
        'базовый LLM-анализ сообщений',
        'Dashboard, Чаты, CRM-lite, enReach-lite',
        'ручной отбор сигналов кнопками +/−',
      ],
    },
    {
      key: 'start',
      title: 'Start',
      price: 4900,
      subtitle: 'для личного отдела продаж',
      limits: { channels: 10, groups: 10, personal: 10, bots: 3, llmOps: 3000, ocrImages: 200, contacts: 1000, users: 1 },
      includes: [
        'до 10 активных источников каждого типа',
        'CRM, контакты, события и enReach',
        'OCR изображений в малом объёме',
        'настройки OpenRouter и промтов',
      ],
    },
    {
      key: 'growth',
      title: 'Growth',
      price: 19900,
      subtitle: 'для регулярной лидогенерации',
      limits: { channels: 100, groups: 100, personal: 100, bots: 25, llmOps: 25000, ocrImages: 3000, contacts: 20000, users: 3 },
      includes: [
        'до 100 источников каждого типа',
        'сделки, потребности, календарь, маршруты',
        'квалификация контактов через LLM',
        'группы частоты сканирования A/B/C/D',
      ],
    },
    {
      key: 'business',
      title: 'Business',
      price: 69900,
      subtitle: 'для команды и воронки продаж',
      limits: { channels: 500, groups: 500, personal: 500, bots: 100, llmOps: 150000, ocrImages: 20000, contacts: 150000, users: 10 },
      includes: [
        'массовая работа с источниками',
        'ЮР.ЛИЦА, remote OCR, API, PostgreSQL',
        'командные роли и аудит действий',
        'приоритетные фоновые очереди',
      ],
    },
    {
      key: 'enterprise',
      title: 'Enterprise',
      price: null,
      subtitle: 'когда нужна своя revenue-machine',
      limits: { channels: Infinity, groups: Infinity, personal: Infinity, bots: Infinity, llmOps: Infinity, ocrImages: Infinity, contacts: Infinity, users: Infinity },
      includes: [
        'без фиксированных лимитов в договоре',
        'white-label / demo-docker / внедрение',
        'интеграции CRM/ERP/CMS и свой контур данных',
        'SLA, сопровождение и кастомные пайплайны',
      ],
    },
  ];

  const PLAN_ORDER = PLAN_DEFS.map((plan) => plan.key);

  const MODULES = [
    { key: 'dashboard', title: 'Dashboard и мониторинг', minPlan: 'free', desc: 'здоровье backend, Telegram, DuckDB, OCR, логи и статус задач' },
    { key: 'telegramSync', title: 'Telegram sync', minPlan: 'free', desc: 'получение истории и новых сообщений без повторного перечитывания всего архива' },
    { key: 'duckdb', title: 'DuckDB аналитика', minPlan: 'free', desc: 'быстрый поиск и аналитические таблицы поверх jsonl-первоисточника' },
    { key: 'crm', title: 'CRM-извлечение', minPlan: 'free', desc: 'ФИО, телефоны, email, компании, должности, города и текст сообщения' },
    { key: 'enreach', title: 'enReach очередь', minPlan: 'free', desc: 'ручной плюс/минус отбор полезных сигналов для дальнейшего outreach' },
    { key: 'events', title: 'Мероприятия + даты', minPlan: 'start', desc: 'поиск событий и LLM-определение даты мероприятия' },
    { key: 'contacts', title: 'Контакты и квалификация', minPlan: 'growth', desc: 'профиль автора, все сообщения, LLM-анализ потребностей и первое сообщение' },
    { key: 'deals', title: 'Сделки и pipeline', minPlan: 'growth', desc: 'сделки, next action, expected value, приоритизация и audit trail' },
    { key: 'calendar', title: 'Календарь', minPlan: 'growth', desc: 'календарный вид событий с popup и подробным сообщением' },
    { key: 'routes', title: 'Маршруты и карта', minPlan: 'growth', desc: 'адреса Москвы из сообщений, справочник адресов, точки на карте' },
    { key: 'mediaOcr', title: 'Media/OCR изображений', minPlan: 'growth', desc: 'скачивание только изображений, OCR, CRM-поля из текста картинки' },
    { key: 'jurEntities', title: 'ЮР.ЛИЦА и XLSX', minPlan: 'business', desc: 'скачивание xlsx, анализ структуры, добавление файлов в парсер' },
    { key: 'remoteOcr', title: 'Отдельный OCR-сервис', minPlan: 'business', desc: 'gramlead-ocr на второй машине по API, чтобы не грузить основной Docker' },
    { key: 'team', title: 'Команда и роли', minPlan: 'business', desc: 'несколько пользователей, права, аудит и рабочие очереди' },
    { key: 'postgres', title: 'PostgreSQL операции', minPlan: 'business', desc: 'операционные сущности: сделки, задания, квалификации, настройки' },
    { key: 'apiIntegrations', title: 'API и интеграции', minPlan: 'business', desc: 'подключение CRM/ERP/CMS, экспорт и webhooks' },
    { key: 'whiteLabel', title: 'White-label / demo-docker', minPlan: 'enterprise', desc: 'брендирование, тиражирование, клиентские демо-контуры' },
    { key: 'customPipelines', title: 'Кастомные revenue-пайплайны', minPlan: 'enterprise', desc: 'специальные агенты, скоринг, маршруты продаж и SLA под бизнес' },
  ];

  const DEFAULT_FEATURES = MODULES.reduce((acc, module) => {
    acc[module.key] = module.minPlan === 'free';
    return acc;
  }, {});

  const PRESETS = {
    free: {
      channels: 1,
      groups: 0,
      personal: 1,
      bots: 0,
      llmOps: 200,
      ocrImages: 0,
      contacts: 50,
      users: 1,
      features: DEFAULT_FEATURES,
    },
    start: {
      channels: 10,
      groups: 5,
      personal: 10,
      bots: 1,
      llmOps: 3000,
      ocrImages: 100,
      contacts: 800,
      users: 1,
      features: MODULES.reduce((acc, module) => {
        acc[module.key] = ['free', 'start'].includes(module.minPlan);
        return acc;
      }, {}),
    },
    growth: {
      channels: 80,
      groups: 60,
      personal: 60,
      bots: 10,
      llmOps: 20000,
      ocrImages: 2000,
      contacts: 12000,
      users: 3,
      features: MODULES.reduce((acc, module) => {
        acc[module.key] = ['free', 'start', 'growth'].includes(module.minPlan);
        return acc;
      }, {}),
    },
    business: {
      channels: 300,
      groups: 300,
      personal: 250,
      bots: 60,
      llmOps: 120000,
      ocrImages: 12000,
      contacts: 90000,
      users: 8,
      features: MODULES.reduce((acc, module) => {
        acc[module.key] = module.minPlan !== 'enterprise';
        return acc;
      }, {}),
    },
  };

  function tierIndex(key) {
    return Math.max(0, PLAN_ORDER.indexOf(key));
  }

  function formatMoney(value) {
    if (value == null) return 'по договору';
    if (!value) return '0 ₽';
    return `${Number(value).toLocaleString('ru-RU')} ₽`;
  }

  function clampNumber(value, min = 0, max = 1000000) {
    const number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.max(min, Math.min(max, Math.round(number)));
  }

  function findPlan(key) {
    return PLAN_DEFS.find((plan) => plan.key === key) || PLAN_DEFS[0];
  }

  function pickPlan(config) {
    let requiredIndex = 0;
    const reasons = [];

    const applyLimit = (field, label) => {
      const value = Number(config[field] || 0);
      for (let index = 0; index < PLAN_DEFS.length; index += 1) {
        if (value <= PLAN_DEFS[index].limits[field]) {
          if (index > requiredIndex) {
            requiredIndex = index;
          }
          const plan = PLAN_DEFS[index];
          if (index > 0) {
            reasons.push(`${label}: ${value.toLocaleString('ru-RU')} → минимум ${plan.title}`);
          }
          return;
        }
      }
      requiredIndex = PLAN_DEFS.length - 1;
      reasons.push(`${label}: ${value.toLocaleString('ru-RU')} → нужен Enterprise`);
    };

    ['channels', 'groups', 'personal', 'bots', 'llmOps', 'ocrImages', 'contacts', 'users'].forEach((field) => {
      const labels = {
        channels: 'каналы',
        groups: 'группы',
        personal: 'личные переписки',
        bots: 'боты',
        llmOps: 'LLM-анализы в месяц',
        ocrImages: 'OCR изображений в месяц',
        contacts: 'контакты в базе',
        users: 'пользователи',
      };
      applyLimit(field, labels[field]);
    });

    MODULES.forEach((module) => {
      if (!config.features[module.key]) return;
      const index = tierIndex(module.minPlan);
      if (index > requiredIndex) {
        requiredIndex = index;
      }
      if (index > 0) {
        reasons.push(`${module.title}: минимум ${findPlan(module.minPlan).title}`);
      }
    });

    const plan = PLAN_DEFS[requiredIndex] || PLAN_DEFS[PLAN_DEFS.length - 1];
    if (!reasons.length) {
      reasons.push('Вы укладываетесь в Free-demo: 1 канал, 1 личная переписка и базовый LLM-анализ.');
    }
    return { plan, reasons: Array.from(new Set(reasons)).slice(0, 8) };
  }

  function calcUsage(config) {
    return {
      sources: Number(config.channels || 0) + Number(config.groups || 0) + Number(config.personal || 0) + Number(config.bots || 0),
      selectedModules: MODULES.filter((module) => config.features[module.key]),
    };
  }

  function buildProposalText(config, plan, reasons) {
    const usage = calcUsage(config);
    return [
      `Рекомендованный тариф: ${plan.title}`,
      `Стоимость платформы: ${formatMoney(plan.price)} / месяц`,
      `Источники: ${usage.sources} всего (${config.channels} каналов, ${config.groups} групп, ${config.personal} личных, ${config.bots} ботов)`,
      `LLM-анализов: ${Number(config.llmOps || 0).toLocaleString('ru-RU')} / месяц`,
      `OCR изображений: ${Number(config.ocrImages || 0).toLocaleString('ru-RU')} / месяц`,
      `Контактов в базе: ${Number(config.contacts || 0).toLocaleString('ru-RU')}`,
      `Пользователей: ${Number(config.users || 0).toLocaleString('ru-RU')}`,
      '',
      'Включённые модули:',
      ...usage.selectedModules.map((module) => `- ${module.title}`),
      '',
      'Почему такой тариф:',
      ...reasons.map((reason) => `- ${reason}`),
      '',
      'Примечание: стоимость OpenRouter/LLM API считается отдельно по вашему API-ключу, если модель платная.',
    ].join('\n');
  }

  function NumberControl({ label, value, onChange, help, step = 1, max = 1000000 }) {
    return html`
      <label className="metric-card">
        <div className="metric-label">${label}</div>
        <input
          className="input"
          type="number"
          min="0"
          max=${max}
          step=${step}
          value=${value}
          onChange=${(event) => onChange(clampNumber(event.target.value, 0, max))}
        />
        <div className="metric-help">${help}</div>
      </label>
    `;
  }

  function TariffsPage() {
    const [config, setConfig] = React.useState(PRESETS.free);
    const [saved, setSaved] = React.useState('');
    const [licenseStatus, setLicenseStatus] = React.useState(null);
    const [licenseMenus, setLicenseMenus] = React.useState(null);
    const [licenseLoading, setLicenseLoading] = React.useState(true);
    const [licenseError, setLicenseError] = React.useState('');
    const [inviteJson, setInviteJson] = React.useState('');
    const [inviteCode, setInviteCode] = React.useState('');
    const [activating, setActivating] = React.useState(false);
    const { plan, reasons } = pickPlan(config);
    const usage = calcUsage(config);
    const proposalText = buildProposalText(config, plan, reasons);
    const planIndex = tierIndex(plan.key);
    const nextPlan = PLAN_DEFS[planIndex + 1] || null;
    const licenseLimitEntries = Object.entries(licenseStatus?.limits || {})
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .slice(0, 8);
    const menuItems = Array.isArray(licenseMenus?.items) ? licenseMenus.items : [];
    const allowedMenuItems = menuItems.filter((item) => item.allowed);
    const lockedMenuItems = menuItems.filter((item) => !item.allowed);
    const allowedMenusCount = allowedMenuItems.length;
    const disabledMenusCount = lockedMenuItems.length;
    const allowedMenusPreview = allowedMenuItems.slice(0, 8).map((item) => item.label).join(', ');
    const disabledMenusPreview = lockedMenuItems.slice(0, 8).map((item) => item.label).join(', ');

    React.useEffect(() => {
      loadLicenseStatus();
    }, []);

    async function loadLicenseStatus() {
      setLicenseLoading(true);
      setLicenseError('');
      try {
        const [statusData, menusData] = await Promise.all([
          apiJson(`${API_BASE}/api/payme/license/status`),
          apiJson(`${API_BASE}/api/payme/license/menus`).catch(() => null),
        ]);
        setLicenseStatus(statusData);
        setLicenseMenus(menusData);
      } catch (err) {
        setLicenseError(String(err?.message || err));
      } finally {
        setLicenseLoading(false);
      }
    }

    async function activateLicense() {
      setActivating(true);
      setLicenseError('');
      try {
        const payload = inviteJson.trim()
          ? { invite_license_json: inviteJson.trim(), invite_code: inviteCode.trim() }
          : { invite_license_json: '', invite_code: inviteCode.trim() };
        const data = await apiJson(`${API_BASE}/api/payme/license/activate`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        setLicenseStatus(data.status);
        const menusData = await apiJson(`${API_BASE}/api/payme/license/menus`).catch(() => null);
        setLicenseMenus(menusData);
        setInviteJson('');
        setInviteCode('');
      } catch (err) {
        setLicenseError(String(err?.message || err));
      } finally {
        setActivating(false);
      }
    }

    const updateField = (field, value) => {
      setConfig((current) => ({ ...current, [field]: value }));
      setSaved('');
    };

    const toggleFeature = (key) => {
      setConfig((current) => ({
        ...current,
        features: { ...current.features, [key]: !current.features[key] },
      }));
      setSaved('');
    };

    const applyPreset = (key) => {
      const preset = PRESETS[key] || PRESETS.free;
      setConfig({
        ...preset,
        features: { ...preset.features },
      });
      setSaved('');
    };

    const saveCalculation = () => {
      try {
        window.localStorage.setItem('xfiles.tariff.lastCalculation', proposalText);
        setSaved('Расчёт сохранён в браузере. Можно открыть страницу позже и вернуться к нему.');
      } catch (_error) {
        setSaved('Не получилось сохранить в браузере, но расчёт можно скопировать вручную ниже.');
      }
    };

    return html`
      <div className="page">
        <${PageHeader}
          title="Тарифы"
          subtitle="Калькулятор стоимости X-Files: выбирайте функционал, объёмы и смотрите, какой тариф нужен."
          active="tariffs"
        />

        <section className="panel">
          <div className="section-title">Текущая лицензия</div>
          <div className="section-subtitle">
            Здесь видно активный тариф клиента и можно применить invite-license. Если лицензии ещё нет, программа показывает free-demo/активацию, а данные клиента не удаляются.
          </div>
          <div className="summary-grid">
            <div className="metric-card">
              <div className="metric-label">Статус</div>
              <div className="price-title" style=${{ fontSize: '24px' }}>
                ${licenseLoading ? 'Загрузка...' : (licenseStatus?.status || 'missing')}
              </div>
              <div className="metric-help">
                ${licenseStatus?.message || licenseError || 'Статус лицензии пока не получен'}
              </div>
              <div className="pill-row" style=${{ marginTop: '12px' }}>
                <span className=${`pill ${licenseStatus?.ok ? 'pill-green' : 'pill-yellow'}`}>
                  ${licenseStatus?.ok ? 'активна' : 'нужна активация'}
                </span>
                ${licenseStatus?.plan ? html`<span className="pill">${licenseStatus.plan}</span>` : null}
                ${licenseStatus?.valid_until ? html`<span className="pill">до ${licenseStatus.valid_until}</span>` : null}
              </div>
              ${licenseStatus?.plan_title || licenseStatus?.days_remaining !== null && licenseStatus?.days_remaining !== undefined ? html`
                <div className="metric-help" style=${{ marginTop: '12px' }}>
                  ${licenseStatus?.plan_title ? html`Тариф: <strong>${licenseStatus.plan_title}</strong>. ` : null}
                  ${licenseStatus?.days_remaining !== null && licenseStatus?.days_remaining !== undefined ? html`Осталось дней: <strong>${licenseStatus.days_remaining}</strong>.` : null}
                </div>
              ` : null}
              ${licenseLimitEntries.length ? html`
                <div style=${{ marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px' }}>
                  ${licenseLimitEntries.map(([key, value]) => html`
                    <div key=${key} className="metric-help" style=${{ padding: '8px 10px', border: '1px solid #dbe7f3', borderRadius: '12px', background: '#f8fbff' }}>
                      <strong>${key}</strong><br />${String(value)}
                    </div>
                  `)}
                </div>
              ` : null}
              ${licenseStatus?.ok ? html`
                <div className="metric-help" style=${{ marginTop: '10px' }}>
                  Меню: доступно ${allowedMenusCount || 'по тарифу'}, закрыто для апгрейда ${disabledMenusCount}.
                  ${allowedMenusPreview ? html`<br />Доступно: ${allowedMenusPreview}${allowedMenusCount > 8 ? '...' : ''}` : null}
                  ${disabledMenusPreview ? html`<br />Открывается апгрейдом: ${disabledMenusPreview}${disabledMenusCount > 8 ? '...' : ''}` : null}
                </div>
              ` : null}
              ${lockedMenuItems.length ? html`
                <div style=${{ marginTop: '12px' }}>
                  <div className="metric-label">Что можно открыть апгрейдом</div>
                  <div className="pill-row">
                    ${lockedMenuItems.slice(0, 12).map((item) => html`
                      <span key=${item.key} className="pill pill-yellow">${item.label}</span>
                    `)}
                    ${lockedMenuItems.length > 12 ? html`<span className="pill">ещё ${lockedMenuItems.length - 12}</span>` : null}
                  </div>
                </div>
              ` : null}
            </div>
            <div className="metric-card">
              <div className="metric-label">Invite-license JSON</div>
              <input
                className="text-input"
                style=${{ margin: '8px 0 10px' }}
                placeholder="Invite-code клиента, если ZIP требует код"
                value=${inviteCode}
                onChange=${(event) => setInviteCode(event.target.value)}
              />
              <textarea
                className="copy-box"
                style=${{ minHeight: '132px' }}
                placeholder="Вставьте сюда содержимое license/invite-license.json или оставьте пустым, чтобы применить файл из /data/license/invite-license.json"
                value=${inviteJson}
                onChange=${(event) => setInviteJson(event.target.value)}
              ></textarea>
              <div className="preset-row" style=${{ marginTop: '10px' }}>
                <button className="btn btn-green" type="button" disabled=${activating} onClick=${activateLicense}>
                  ${activating ? 'Активирую...' : 'Активировать invite-license'}
                </button>
                <button className="btn btn-soft" type="button" disabled=${licenseLoading} onClick=${loadLicenseStatus}>Обновить статус</button>
              </div>
              ${licenseError ? html`<div className="footer-note" style=${{ color: '#b91c1c' }}>${licenseError}</div>` : null}
            </div>
          </div>
        </section>

        <section className="hero">
          <div className="price-card">
            <div className="eyebrow">Рекомендованный тариф</div>
            <div className="price-title">${plan.title}</div>
            <div className="subtle" style=${{ marginTop: '8px' }}>${plan.subtitle}</div>
            <div className="price-value">
              <div className="price-number">${formatMoney(plan.price)}</div>
              <div className="price-unit">${plan.price == null ? '' : '/ месяц'}</div>
            </div>
            <div className="price-note">
              ${plan.key === 'free'
                ? 'Минимальный free-demo: один канал, одна личная переписка и LLM-анализ, чтобы быстро понять, есть ли польза для продаж.'
                : 'Тариф растёт автоматически, когда вы добавляете больше источников, LLM-анализа, OCR, сделок, маршрутов или командной работы.'}
            </div>
            <div className="pill-row">
              <span className="pill pill-green">${usage.sources} источников</span>
              <span className="pill">${usage.selectedModules.length} модулей</span>
              <span className="pill pill-yellow">OpenRouter оплачивается отдельно</span>
              ${nextPlan ? html`<span className="pill">следующий шаг: ${nextPlan.title}</span>` : html`<span className="pill">индивидуальные условия</span>`}
            </div>
          </div>

          <aside className="side-card panel" style=${{ marginTop: 0 }}>
            <div className="section-title">Что входит прямо сейчас</div>
            <div className="section-subtitle">
              Простыми словами: это не “просто парсер”, а система, которая помогает найти сигнал, понять клиента и довести его до сделки.
            </div>
            <ul className="check-list" style=${{ padding: '0 18px 18px 36px' }}>
              ${plan.includes.map((item) => html`<li key=${item}>${item}</li>`)}
            </ul>
          </aside>
        </section>

        <section className="panel">
          <div className="section-title">Быстрый старт расчёта</div>
          <div className="section-subtitle">
            Начните с free-demo или сразу выберите похожий сценарий. Потом можно подкрутить каждую цифру руками.
          </div>
          <div className="preset-row">
            ${PLAN_DEFS.slice(0, 4).map((tier) => html`
              <button
                key=${tier.key}
                className=${`btn ${plan.key === tier.key ? 'btn-active' : 'btn-soft'}`}
                type="button"
                onClick=${() => applyPreset(tier.key)}
              >
                ${tier.title}
              </button>
            `)}
            <button className="btn btn-green" type="button" onClick=${saveCalculation}>Сохранить расчёт</button>
            ${saved ? html`<span className="subtle">${saved}</span>` : null}
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Объёмы использования</div>
          <div className="section-subtitle">
            Это главные ручки тарифа: сколько источников подключаете, сколько LLM/OCR анализа нужно и сколько людей работает в системе.
          </div>
          <div className="metrics-grid">
            <${NumberControl} label="Каналы" value=${config.channels} onChange=${(value) => updateField('channels', value)} help="публичные/частные каналы Telegram" />
            <${NumberControl} label="Группы" value=${config.groups} onChange=${(value) => updateField('groups', value)} help="чаты и сообщества" />
            <${NumberControl} label="Личные" value=${config.personal} onChange=${(value) => updateField('personal', value)} help="1-на-1 переписки с людьми" />
            <${NumberControl} label="Пользователи" value=${config.users} onChange=${(value) => updateField('users', value)} help="кто будет работать в интерфейсе" max=${200} />
            <${NumberControl} label="LLM / месяц" value=${config.llmOps} onChange=${(value) => updateField('llmOps', value)} help="квалификация, даты, первые сообщения, адреса" step=${100} />
            <${NumberControl} label="OCR / месяц" value=${config.ocrImages} onChange=${(value) => updateField('ocrImages', value)} help="изображения, которые надо распознать" step=${50} />
            <${NumberControl} label="Контакты" value=${config.contacts} onChange=${(value) => updateField('contacts', value)} help="авторы сообщений в базе" step=${100} />
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Функционал программы</div>
          <div className="section-subtitle">
            Включайте всё, что нужно бизнесу. Если функция тяжёлая или командная, калькулятор поднимет тариф выше.
          </div>
          <div className="module-grid">
            ${MODULES.map((module) => html`
              <button
                key=${module.key}
                type="button"
                className=${`module-card ${config.features[module.key] ? 'module-card-active' : ''}`}
                onClick=${() => toggleFeature(module.key)}
              >
                <div className="module-head">
                  <div className="module-title">${module.title}</div>
                  <span className="toggle" aria-hidden="true"></span>
                </div>
                <div className="module-desc">${module.desc}</div>
                <div className="module-tier">от тарифа ${findPlan(module.minPlan).title}</div>
              </button>
            `)}
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Почему выбран именно этот тариф</div>
          <div className="section-subtitle">
            Здесь видно не магию, а причину: какие лимиты или функции подняли тариф.
          </div>
          <div className="summary-grid">
            <div>
              <ul className="reason-list">
                ${reasons.map((reason) => html`<li key=${reason}>${reason}</li>`)}
              </ul>
            </div>
            <div>
              <textarea className="copy-box" readOnly value=${proposalText}></textarea>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Лестница тарифов</div>
          <div className="section-subtitle">
            Логика роста: сначала доказать пользу на маленьком объёме, потом расширять источники, LLM, OCR, команду и интеграции.
          </div>
          <div className="tier-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Тариф</th>
                  <th>Цена</th>
                  <th>Для кого</th>
                  <th>Лимиты</th>
                  <th>Ключевые возможности</th>
                </tr>
              </thead>
              <tbody>
                ${PLAN_DEFS.map((tier) => html`
                  <tr key=${tier.key} className=${tier.key === plan.key ? 'tier-current' : ''}>
                    <td>
                      <div className="tier-name">${tier.title}</div>
                      <div className="subtle">${tier.subtitle}</div>
                    </td>
                    <td><strong>${formatMoney(tier.price)}</strong>${tier.price == null ? '' : html`<div className="subtle">/ месяц</div>`}</td>
                    <td>
                      ${tier.key === 'free' ? 'первый тест, demo, личная проверка гипотезы' : null}
                      ${tier.key === 'start' ? 'один предприниматель или менеджер продаж' : null}
                      ${tier.key === 'growth' ? 'активная лидогенерация и регулярная квалификация' : null}
                      ${tier.key === 'business' ? 'команда продаж, много источников, системная воронка' : null}
                      ${tier.key === 'enterprise' ? 'собственный контур, SLA, внедрение и кастомные процессы' : null}
                    </td>
                    <td>
                      ${tier.key === 'enterprise'
                        ? 'лимиты задаются договором'
                        : html`
                          ${tier.limits.channels} каналов · ${tier.limits.personal} личных · ${tier.limits.llmOps.toLocaleString('ru-RU')} LLM · ${tier.limits.ocrImages.toLocaleString('ru-RU')} OCR
                          <div className="subtle">${tier.limits.contacts.toLocaleString('ru-RU')} контактов · ${tier.limits.users} пользователей</div>
                        `}
                    </td>
                    <td>
                      <ul className="check-list">
                        ${tier.includes.map((item) => html`<li key=${item}>${item}</li>`)}
                      </ul>
                    </td>
                  </tr>
                `)}
              </tbody>
            </table>
          </div>
          <div className="footer-note">
            Важно: это продуктовый калькулятор тарифа X-Files. Реальный счёт за LLM/OpenRouter зависит от выбранной модели, количества токенов и вашего API-ключа.
          </div>
        </section>
      </div>
    `;
  }

  function renderTariffsPage() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Tariffs page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${TariffsPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderTariffsPage, { once: true });
  } else {
    renderTariffsPage();
  }
})();
