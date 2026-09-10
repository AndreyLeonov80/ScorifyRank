/* Shared React UI components for Backfront pages */
'use strict';

(function initBackfrontReactShared() {
  const legacyRuntime = window.BackfrontReact || null;
  const fallbackReact = window.React || null;
  const fallbackHtm = window.htm || null;
  const reactApi = legacyRuntime?.React || fallbackReact;
  const htmlApi = legacyRuntime?.html || (fallbackReact && fallbackHtm ? fallbackHtm.bind(fallbackReact.createElement) : null);

  if (!reactApi || !htmlApi) {
    console.error('[React] Shared components require BackfrontReact runtime');
    return;
  }

  const React = reactApi;
  const html = htmlApi;
  const PROJECT_NAME = 'X-Files';
  const PROJECT_SUBTITLE = 'revenue operating system & engine';
  const APP_VERSION = String(window.XFILES_APP_VERSION || '1.00');
  const APP_RELEASE_AT = String(window.XFILES_RELEASE_AT || '2026-05-27 10:20 MSK');
  function boolFromGlobalOrStorage(globalNames, storageKey, defaultValue = false) {
    try {
      for (const name of globalNames) {
        if (typeof window[name] !== 'undefined') {
          return ['1', 'true', 'yes', 'on'].includes(String(window[name]).toLowerCase());
        }
      }
      const stored = storageKey ? window.localStorage?.getItem(storageKey) : null;
      if (stored != null) return ['1', 'true', 'yes', 'on'].includes(String(stored).toLowerCase());
    } catch (_) {}
    return Boolean(defaultValue);
  }
  const NAV_GROUPS = [
    {
      tone: 1,
      items: [
        { key: 'chats', href: '/index.html', label: 'Чаты', icon: '✉' },
        { key: 'contacts', href: '/contacts.html', label: 'Контакты', icon: '☎' },
        { key: 'import', href: '/import.html', label: 'Импорт', icon: '↓' },
        { key: 'grid', href: '/grid.html', label: 'Sync', icon: '⇄' },
        { key: 'calendar', href: '/calendar.html', label: 'Календарь', icon: '▣' },
      ],
    },
  ];

  const EXT_NAV_ITEMS = [
    { key: 'dashboard', href: '/dashboard.html', label: 'Dashboard', icon: '▣', tone: 5 },
    { key: 'logs', href: '/logs.html', label: 'Логи', icon: '≡', tone: 5 },
    { key: 'media', href: '/media.html', label: 'Media', icon: '▧', tone: 6 },
    { key: 'settings', href: '/settings.html', label: 'Настройки', icon: '⚙', tone: 6 },
    { key: 'telegram-logout', href: '#', label: 'Выйти', icon: '⎋', tone: 6, action: 'logoutTelegram' },
  ];

  const EXT0_NAV_ITEMS = [
    { key: 'needs', href: '/needs.html', label: 'Потребности', icon: '◇', tone: 1 },
    { key: 'crm', href: '/crm.html', label: 'CRM', icon: '◎', tone: 1 },
    { key: 'outreach', href: '/outreach.html', label: 'enReach', icon: '+', tone: 1 },
    { key: 'outreach-future', href: '/outreach-future.html', label: 'outReach', icon: '↗', tone: 1 },
    { key: 'events', href: '/events.html', label: 'Мероприятия', icon: '★', tone: 3 },
    { key: 'routes', href: '/routes.html', label: 'Маршруты', icon: '⌖', tone: 4 },
    { key: 'jur-entities', href: '/jur-entities.html', label: 'ЮР. Лица', icon: '§', tone: 0 },
  ];

  const EXT1_NAV_ITEMS = [
    { key: 'tariffs', href: '/tariffs.html', label: 'Тарифы', icon: '◆', tone: 6 },
    { key: 'producers-match', href: '/producers-match.html', label: 'Продюсеры мэтч сделок', icon: '☍' },
    { key: 'autodeal-10pl-xpl', href: '/autodeal-10pl-xpl.html', label: '10PL & xPL = m&a автозаказ', icon: '⇄' },
    { key: 'buypower', href: '/buypower.html', label: 'BuyPower', icon: '▲' },
    { key: 'data-sources', href: '/data-sources.html', label: 'Источники данных', icon: '◫' },
    { key: 'gramlead-earnings', href: '/gramlead-earnings.html', label: 'Как зарабатывать', icon: '☼' },
    { key: 'licenses', href: '/licenses.html', label: 'Лицензии', icon: '◇' },
    { key: 'sales-department', href: '/sales-department.html', label: 'Отдел продаж', icon: '♜' },
    { key: 'my-products', href: '/my-products.html', label: 'Мои продукты', icon: '◈' },
    { key: 'sales-systems-100', href: '/sales-systems-100.html', label: '100 систем продаж', icon: '⑩' },
    { key: 'ai-agent-chat', href: '/ai-agent-chat.html', label: 'Чат с ИИ-агентами', icon: '✦' },
  ];

  const LEGACY_MENU_ALIASES = { enreach: 'outreach' };
  const SAFE_FALLBACK_MENU_KEYS = new Set([
    'chats',
    'import',
    'grid',
    'dashboard',
    'settings',
    'telegram-logout',
  ]);
  function normalizeMenuKey(key) {
    const raw = String(key || '').trim();
    return LEGACY_MENU_ALIASES[raw] || raw;
  }

  function normalizeMenuKeys(keys) {
    return new Set((Array.isArray(keys) ? keys : []).map(normalizeMenuKey).filter(Boolean));
  }

  function inferredDisabledMenus(menuState) {
    const disabled = normalizeMenuKeys(menuState?.disabled_menus);
    normalizeMenuKeys(menuState?.default_disabled_menus).forEach((key) => disabled.add(key));
    return disabled;
  }

  const API_BASE_INFO = (() => {
    if (window.BackfrontApi?.getApiCandidates) {
      const candidates = window.BackfrontApi.getApiCandidates();
      return {
        base: candidates[0] || '',
        candidates,
        isLocal: ['localhost', '127.0.0.1', '::1', '[::1]'].includes(window.location.hostname || '') || window.location.protocol === 'file:',
      };
    }

    const protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
    const host = window.location.hostname || '127.0.0.1';
    const explicitBase = String(window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL || '').trim().replace(/\/$/, '');
    const origin = explicitBase || (
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : `${protocol}//${host}${window.location.port ? ':' + window.location.port : ':8001'}`
    );
    const isLocal = ['localhost', '127.0.0.1', '::1', '[::1]'].includes(host) || window.location.protocol === 'file:';
    const candidates = [origin];
    if (isLocal) {
      candidates.push(`${protocol}//${host}:8001`, `${protocol}//127.0.0.1:8001`, `${protocol}//localhost:8001`);
    }
    return { base: origin, candidates: Array.from(new Set(candidates)), isLocal };
  })();

  window.API_BASE = window.API_BASE || API_BASE_INFO.base;
  window.API_BASE_CANDIDATES = window.API_BASE_CANDIDATES || API_BASE_INFO.candidates;

  const PAGE_SIZE_OPTIONS = [5, 10, 20, 50, 100];

  function PageSizeOptions() {
    return PAGE_SIZE_OPTIONS.map((value) => html`<option key=${value} value=${String(value)}>${value} строк</option>`);
  }

  function VirtualizedRows({ items = [], renderItem, getKey = null, maxRows = 100 }) {
    const rows = Array.isArray(items) ? items : [];
    const safeLimit = Math.max(1, Math.min(Number(maxRows || 100), 500));
    return rows.slice(0, safeLimit).map((item, index) => {
      const key = typeof getKey === 'function' ? getKey(item, index) : index;
      return React.createElement(React.Fragment, { key }, renderItem(item, index));
    });
  }

  function ApiBaseBadge() {
    return html`
      <span className="xfiles-api-badge" title=${`API подключен к: ${API_BASE_INFO.base}`}>
        API: ${API_BASE_INFO.base.replace(/^https?:\/\//, '')}
      </span>
    `;
  }

  async function checkCurrentApiBase(path = '/api/payme/settings', timeoutMs = 5000) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), Math.max(1000, Number(timeoutMs || 5000)));
    try {
      const response = await fetch(`${API_BASE_INFO.base.replace(/\/$/, '')}${path}`, {
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        signal: controller.signal,
      });
      window.clearTimeout(timer);
      return { ok: response.ok, status: response.status, base: API_BASE_INFO.base };
    } catch (error) {
      window.clearTimeout(timer);
      return {
        ok: false,
        status: 0,
        base: API_BASE_INFO.base,
        error: `Backend недоступен по адресу текущей страницы: ${API_BASE_INFO.base}. Проверьте контейнер, порт 8001 и firewall.`,
      };
    }
  }


  function HtmlBlock({ htmlString, className = '', style = undefined }) {
    return React.createElement('div', {
      className,
      style,
      dangerouslySetInnerHTML: { __html: htmlString || '' },
    });
  }

  function StatusPanel({ config = {}, className = '', style = undefined }) {
    const htmlString = window.BackfrontStatusPanel?.renderUnifiedStatusPanel
      ? window.BackfrontStatusPanel.renderUnifiedStatusPanel(config)
      : '';
    return React.createElement(HtmlBlock, { htmlString, className, style });
  }

  function ErrorBox({ error, tag = 'div', className = 'error-box' }) {
    if (!error) return null;
    return React.createElement(tag, { className }, error);
  }

  function fmtLocalTs(input) {
    if (!input) return '—';
    const date = new Date(input);
    if (Number.isNaN(date.getTime())) return String(input);
    const pad = (value) => String(value).padStart(2, '0');
    return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()}, ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  function fmtRemaining(seconds) {
    const value = Math.max(0, Number(seconds || 0));
    if (value <= 0) return 'сейчас';
    if (value < 60) return `${Math.ceil(value)}с`;
    if (value < 3600) return `${Math.ceil(value / 60)}м`;
    return `${Math.ceil(value / 3600)}ч`;
  }

  function TelegramCooldownBanner({ compact = false }) {
    const [status, setStatus] = React.useState(null);

    React.useEffect(() => {
      let cancelled = false;
      let timer = null;

      const load = async () => {
        try {
          const response = await fetch('/api/payme/dashboard/summary?limit=3', {
            headers: { Accept: 'application/json' },
            cache: 'no-store',
          });
          if (!response.ok) return;
          const payload = await response.json();
          if (!cancelled) {
            setStatus({
              floodWait: payload?.telegram?.flood_wait || payload?.telegram_flood_wait || null,
              rateLimits: payload?.telegram?.rate_limits || payload?.telegram_rate_limits || {},
              syncControl: payload?.telegram?.sync_control || payload?.telegram_sync_control || {},
            });
          }
        } catch (_) {
          if (!cancelled) setStatus(null);
        }
      };

      load();
      timer = window.setInterval(load, 15000);
      return () => {
        cancelled = true;
        if (timer) window.clearInterval(timer);
      };
    }, []);

    const floodWait = status?.floodWait || null;
    const operationCooldowns = Object.values(status?.rateLimits?.operation_cooldowns || {})
      .filter((entry) => entry && (entry.active || entry.status === 'risk_rate_limited' || entry.status === 'cooldown'))
      .sort((a, b) => Number(b.remaining_sec || 0) - Number(a.remaining_sec || 0));
    const cooldown = operationCooldowns[0] || null;
    const syncControl = status?.syncControl || {};
    const activeFloodWait = Boolean(floodWait?.active);
    const isPaused = Boolean(syncControl?.paused);
    if (!activeFloodWait && !cooldown && !isPaused) return null;

    const isRisk = String(cooldown?.status || '').includes('risk');
    const borderColor = activeFloodWait || isRisk ? '#fecaca' : isPaused ? '#bfdbfe' : '#fed7aa';
    const background = activeFloodWait || isRisk ? '#fff1f2' : isPaused ? '#eff6ff' : '#fffbeb';
    const color = activeFloodWait || isRisk ? '#991b1b' : isPaused ? '#1d4ed8' : '#92400e';
    const title = activeFloodWait ? 'Telegram FloodWait' : isPaused ? 'Telegram sync на паузе' : 'Telegram cooldown';
    const until = activeFloodWait
      ? (floodWait?.can_fetch_after || floodWait?.until)
      : (cooldown?.can_fetch_after || cooldown?.retry_after);
    const remaining = activeFloodWait ? floodWait?.remaining_sec : cooldown?.remaining_sec;
    const details = activeFloodWait
      ? (floodWait?.reason || 'Telegram временно ограничил запросы')
      : isPaused
        ? (syncControl?.reason || 'Остановлено вручную без остановки Docker')
        : `${cooldown?.operation || 'operation'} · ${cooldown?.context || cooldown?.reason || 'backoff активен'}`;

    return html`
      <section
        style=${{
          margin: compact ? '8px 0' : '10px 0 12px',
          padding: compact ? '8px 10px' : '10px 14px',
          border: `1px solid ${borderColor}`,
          borderRadius: '14px',
          background,
          color,
          display: 'flex',
          gap: '10px',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <strong>${title}</strong>
          ${isPaused && !activeFloodWait && !cooldown
            ? html`<span style=${{ marginLeft: '8px' }}>с ${fmtLocalTs(syncControl?.paused_at)}</span>`
            : html`
                <span style=${{ marginLeft: '8px' }}>пауза ${fmtRemaining(remaining)}</span>
                <span style=${{ marginLeft: '8px' }}>до ${fmtLocalTs(until)}</span>
              `}
        </div>
        <div style=${{ opacity: 0.9 }}>${details}</div>
      </section>
    `;
  }

  function LoadingNotice({
    message = 'Загружаю данные…',
    details = '',
    className = 'empty',
    compact = false,
  }) {
    const [status, setStatus] = React.useState(null);

    React.useEffect(() => {
      let cancelled = false;
      let timer = null;

      const load = async () => {
        try {
          const response = await fetch('/api/payme/dashboard/summary?limit=3', {
            headers: { Accept: 'application/json' },
            cache: 'no-store',
          });
          if (!response.ok) return;
          const payload = await response.json();
          if (!cancelled) {
            setStatus({
              floodWait: payload?.telegram?.flood_wait || payload?.telegram_flood_wait || null,
              rateLimits: payload?.telegram?.rate_limits || payload?.telegram_rate_limits || {},
              syncControl: payload?.telegram?.sync_control || payload?.telegram_sync_control || {},
            });
          }
        } catch (_) {
          if (!cancelled) setStatus(null);
        }
      };

      load();
      timer = window.setInterval(load, 10000);
      return () => {
        cancelled = true;
        if (timer) window.clearInterval(timer);
      };
    }, []);

    const floodWait = status?.floodWait || null;
    const operationCooldowns = Object.values(status?.rateLimits?.operation_cooldowns || {})
      .filter((entry) => entry && (entry.active || entry.status === 'risk_rate_limited' || entry.status === 'cooldown'))
      .sort((a, b) => Number(b.remaining_sec || 0) - Number(a.remaining_sec || 0));
    const cooldown = operationCooldowns[0] || null;
    const syncControl = status?.syncControl || {};
    const activeFloodWait = Boolean(floodWait?.active);
    const isPaused = Boolean(syncControl?.paused);
    const hasCooldown = Boolean(cooldown);

    let reason = details || 'Backend готовит данные из кеша/DuckDB или ждёт ответ Telegram API.';
    let eta = 'ETA появится здесь, если Telegram вернёт FloodWait/cooldown.';
    if (activeFloodWait) {
      reason = floodWait?.reason || 'Telegram временно ограничил запросы.';
      eta = `Можно продолжить после ${fmtLocalTs(floodWait?.can_fetch_after || floodWait?.until)} · осталось ${fmtRemaining(floodWait?.remaining_sec)}`;
    } else if (hasCooldown) {
      reason = `${cooldown?.operation || 'Telegram operation'} · ${cooldown?.context || cooldown?.reason || 'backoff активен'}`;
      eta = `Повтор после ${fmtLocalTs(cooldown?.can_fetch_after || cooldown?.retry_after)} · осталось ${fmtRemaining(cooldown?.remaining_sec)}`;
    } else if (isPaused) {
      reason = syncControl?.reason || 'Telegram sync остановлен вручную без остановки Docker.';
      eta = 'Ожидание ручного возобновления Telegram sync.';
    }

    return html`
      <div className=${className}>
        <div><strong>${message}</strong></div>
        <div className="subtle" style=${{ marginTop: compact ? '2px' : '6px' }}>Причина: ${reason}</div>
        <div className="subtle" style=${{ marginTop: '2px' }}>${eta}</div>
      </div>
    `;
  }

  function useMenuEntitlements() {
    const [state, setState] = React.useState(null);

    React.useEffect(() => {
      let cancelled = false;
      const apiJson = window.BackfrontApi?.apiJson || null;
      async function loadMenus() {
        try {
          let payload;
          if (typeof apiJson === 'function') {
            payload = await apiJson('/api/payme/license/menus', {
              timeoutMs: 5000,
              dedupeKey: 'license:menus',
              cacheKey: 'license:menus:v1',
              cacheTtlMs: 60000,
              persistCache: true,
              staleWhileRevalidate: true,
              onRevalidate: (fresh) => {
                if (!cancelled) setState(fresh);
              },
            });
          } else {
            const response = await fetch('/api/payme/license/menus', {
              headers: { Accept: 'application/json' },
              cache: 'no-store',
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            payload = await response.json();
          }
          if (!cancelled) setState(payload);
        } catch (_) {
          if (!cancelled) setState({ failed: true });
        }
      }
      loadMenus();
      const timer = window.setInterval(loadMenus, 60000);
      return () => {
        cancelled = true;
        window.clearInterval(timer);
      };
    }, []);

    return state;
  }

  function filterNavItems(items, menuState) {
    if (!menuState || menuState.failed || !Array.isArray(menuState.effective_allowed_menus)) {
      return items.filter((item) => SAFE_FALLBACK_MENU_KEYS.has(normalizeMenuKey(item.key)));
    }
    const allowed = normalizeMenuKeys(menuState.effective_allowed_menus);
    const disabled = inferredDisabledMenus(menuState);
    return items.filter((item) => {
      const key = normalizeMenuKey(item.key);
      return allowed.has(key) && !disabled.has(key);
    });
  }

  function ExtNavGroup({ active, items, label = 'Ext' }) {
    const extItems = Array.isArray(items) ? items : EXT_NAV_ITEMS;
    const extActive = extItems.some((item) => item.key === active);
    const [open, setOpen] = React.useState(false);
    const rootRef = React.useRef(null);

    React.useEffect(() => {
      function handleClickOutside(event) {
        if (!rootRef.current || rootRef.current.contains(event.target)) return;
        setOpen(false);
      }
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return html`
      <div
        ref=${rootRef}
        className="xfiles-ext-root"
      >
        <button
          type="button"
          className=${`btn xfiles-nav-link ${extActive ? 'btn-active' : ''}`}
          aria-expanded=${open ? 'true' : 'false'}
          onClick=${() => setOpen((value) => !value)}
        >
          ${label}
        </button>
        ${open ? html`
          <div className="xfiles-ext-menu">
            ${extItems.map((item) => item.action ? html`
              <button
                key=${item.key}
                type="button"
                className=${`btn xfiles-ext-link ${item.tone ? `xfiles-ext-link-${item.tone}` : ''} ${active === item.key ? 'btn-active' : ''}`}
                style=${{ justifyContent: 'flex-start' }}
                onClick=${() => {
                  setOpen(false);
                  const action = window.BackfrontActions && window.BackfrontActions[item.action];
                  if (typeof action === 'function') action();
                }}
              >
                <span className="xfiles-nav-icon" aria-hidden="true">${item.icon || '•'}</span>
                <span>${item.label}</span>
              </button>
            ` : html`
              <a
                key=${item.key}
                className=${`btn xfiles-ext-link ${item.tone ? `xfiles-ext-link-${item.tone}` : ''} ${active === item.key ? 'btn-active' : ''}`}
                href=${item.href}
                style=${{ justifyContent: 'flex-start' }}
                onClick=${() => setOpen(false)}
              >
                <span className="xfiles-nav-icon" aria-hidden="true">${item.icon || '•'}</span>
                <span>${item.label}</span>
              </a>
            `)}
          </div>
        ` : null}
      </div>
    `;
  }

  function ensurePageNavStyles() {
    if (typeof document === 'undefined' || document.getElementById('xfiles-page-nav-styles')) return;
    const style = document.createElement('style');
    style.id = 'xfiles-page-nav-styles';
    style.textContent = `
      .xfiles-nav-groups{display:flex;align-items:center;justify-content:flex-end;gap:5px;flex-wrap:nowrap;max-width:100%;overflow:visible;padding-bottom:2px;position:relative;z-index:100}
      .xfiles-nav-cluster{display:inline-flex;align-items:center;gap:3px;padding:3px;border-radius:15px;border:1px solid rgba(148,163,184,.2);white-space:nowrap;flex:0 0 auto}
      .xfiles-nav-cluster-0{background:linear-gradient(135deg,#ffffff,#f8fafc)}
      .xfiles-nav-cluster-1{background:linear-gradient(135deg,#eff6ff,#f0fdfa)}
      .xfiles-nav-cluster-2{background:linear-gradient(135deg,#fff7ed,#fffbeb)}
      .xfiles-nav-cluster-3{background:linear-gradient(135deg,#fefce8,#fff7ed)}
      .xfiles-nav-cluster-4{background:linear-gradient(135deg,#ecfeff,#f0f9ff)}
      .xfiles-nav-cluster-5{background:linear-gradient(135deg,#f8fafc,#eef2ff)}
      .xfiles-nav-cluster-6{background:linear-gradient(135deg,#f5f3ff,#fdf2f8)}
      .xfiles-nav-link{gap:4px;font-weight:500!important;padding:7px 8px;white-space:nowrap;font-size:13px}
      .xfiles-nav-link:not(.btn-active){background:rgba(255,255,255,.82)}
      .xfiles-nav-link .xfiles-nav-icon{font-size:13px;line-height:1;opacity:.78}
      .xfiles-ext-root{position:relative;display:inline-flex;align-items:center;flex:0 0 auto}
      .xfiles-ext-menu{position:absolute;top:calc(100% + 8px);right:0;min-width:280px;max-width:min(360px,90vw);max-height:70vh;overflow:auto;padding:10px;border-radius:16px;border:1px solid #dbeafe;background:#fff;box-shadow:0 16px 40px rgba(15,23,42,.14);z-index:9999;display:flex;flex-direction:column;gap:8px}
      .xfiles-ext-link{gap:8px;font-weight:500!important;background:#fff;white-space:nowrap}
      .xfiles-ext-link-5{background:linear-gradient(135deg,#f8fafc,#eef2ff)}
      .xfiles-ext-link-6{background:linear-gradient(135deg,#f5f3ff,#fdf2f8)}
      .xfiles-api-badge{display:inline-flex;align-items:center;max-width:360px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border:1px solid #bfdbfe;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:700}
      .xfiles-title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
      .xfiles-version-badge{display:inline-flex;align-items:center;border:1px solid #dbeafe;background:#eff6ff;color:#1d4ed8;border-radius:999px;padding:4px 9px;font-size:12px;font-weight:800;line-height:1}
    `;
    document.head.appendChild(style);
  }

  function PageNav({ active }) {
    ensurePageNavStyles();
    const menuState = useMenuEntitlements();
    const groups = NAV_GROUPS
      .map((group) => ({ ...group, items: filterNavItems(group.items, menuState) }))
      .filter((group) => group.items.length);
    const extItems = filterNavItems(EXT_NAV_ITEMS, menuState);
    const ext0Items = filterNavItems(EXT0_NAV_ITEMS, menuState);
    const ext1Items = filterNavItems(EXT1_NAV_ITEMS, menuState);
    return html`
      <nav className="nav xfiles-nav-groups">
        ${groups.map((group) => html`
          <span key=${`group-${group.tone}`} className=${`xfiles-nav-cluster xfiles-nav-cluster-${group.tone}`}>
            ${group.items.map((item) => html`
              <a
                key=${item.key}
                className=${`btn xfiles-nav-link ${active === item.key ? 'btn-active' : ''}`}
                href=${item.href}
                title=${item.label}
              >
                <span className="xfiles-nav-icon" aria-hidden="true">${item.icon || '•'}</span>
                <span>${item.label}</span>
              </a>
            `)}
          </span>
        `)}
        ${extItems.length ? html`<${ExtNavGroup} active=${active} items=${extItems} label="Ext" />` : null}
        ${ext0Items.length ? html`<${ExtNavGroup} active=${active} items=${ext0Items} label="Ext0" />` : null}
        ${ext1Items.length ? html`<${ExtNavGroup} active=${active} items=${ext1Items} label="Ext1" />` : null}
      </nav>
    `;
  }

  function PageHeader({ title, subtitle, active, titleWrapClassName = '', statusSlot = null }) {
    return html`
      <header className="topbar">
        <div className=${titleWrapClassName}>
          <div className="xfiles-title-row">
            <div className="title">${title}</div>
            <span className="xfiles-version-badge" title=${`Версия программы ${APP_VERSION}; Docker release ${APP_RELEASE_AT}`}>${APP_VERSION}</span>
            <span className="xfiles-release-meta">${APP_RELEASE_AT}</span>
            ${statusSlot ? html`<span className="xfiles-header-status">${statusSlot}</span>` : null}
          </div>
          ${subtitle ? html`<div className="subtle">${subtitle}</div>` : null}
          <div style=${{ marginTop: '8px' }}><${ApiBaseBadge} /></div>
        </div>
        <${PageNav} active=${active} />
      </header>
    `;
  }

  function Pagination({ page, totalPages, pageWindow, onPrev, onNext, onGo, className = 'pagination' }) {
    return html`
      <div className=${className}>
        <button className="btn" onClick=${onPrev} disabled=${page <= 1}>Назад</button>
        ${pageWindow.map((pageNumber) => html`
          <button
            key=${pageNumber}
            className=${`btn ${pageNumber === page ? 'btn-active' : ''}`}
            onClick=${() => onGo(pageNumber)}
          >
            ${pageNumber}
          </button>
        `)}
        <button className="btn" onClick=${onNext} disabled=${page >= totalPages}>Вперёд</button>
      </div>
    `;
  }

  function TablePaginationFooter({
    rangeText,
    page,
    totalPages,
    pageWindow,
    onPrev,
    onNext,
    onGo,
    footerClassName = 'footer',
    paginationClassName = 'pagination',
  }) {
    return html`
      <div className=${footerClassName}>
        <div className="subtle">Показано <strong>${rangeText}</strong></div>
        <${Pagination}
          page=${page}
          totalPages=${totalPages}
          pageWindow=${pageWindow}
          onPrev=${onPrev}
          onNext=${onNext}
          onGo=${onGo}
          className=${paginationClassName}
        />
      </div>
    `;
  }

  function DataTable({
    columns = [],
    rows = [],
    getRowKey = (row, index) => row?.id ?? index,
    wrapperClassName = 'table-wrap',
    tableClassName = '',
    emptyMessage = 'Нет данных для отображения.',
  }) {
    const safeRows = Array.isArray(rows) ? rows : [];
    const safeColumns = Array.isArray(columns) ? columns : [];
    if (!safeRows.length) return html`<div className="empty">${emptyMessage}</div>`;
    return html`
      <div className=${wrapperClassName}>
        <table className=${tableClassName}>
          <thead>
            <tr>
              ${safeColumns.map((column) => html`<th key=${column.key || column.label}>${column.label}</th>`)}
            </tr>
          </thead>
          <tbody>
            ${safeRows.map((row, index) => html`
              <tr key=${getRowKey(row, index)}>
                ${safeColumns.map((column) => html`
                  <td key=${column.key || column.label} className=${column.className || ''}>
                    ${typeof column.render === 'function' ? column.render(row, index) : row?.[column.key] ?? '—'}
                  </td>
                `)}
              </tr>
            `)}
          </tbody>
        </table>
      </div>
    `;
  }

  function Modal({
    open = true,
    onClose,
    title = '',
    subtitle = '',
    ariaLabel = '',
    children,
    className = 'modal',
    backdropClassName = 'modal-backdrop',
    headerClassName = 'modal-head',
    titleClassName = 'modal-title',
    bodyClassName = 'modal-body',
    closeLabel = 'Закрыть',
  }) {
    if (!open) return null;
    return html`
      <div className=${backdropClassName} role="presentation" onClick=${onClose}>
        <div
          className=${className}
          role="dialog"
          aria-modal="true"
          aria-label=${ariaLabel || title || closeLabel}
          onClick=${(event) => event.stopPropagation()}
        >
          <div className=${headerClassName}>
            <div>
              ${title ? html`<div className=${titleClassName}>${title}</div>` : null}
              ${subtitle ? html`<div className="subtle">${subtitle}</div>` : null}
            </div>
            <button className="btn" type="button" onClick=${onClose}>${closeLabel}</button>
          </div>
          <div className=${bodyClassName}>${children}</div>
        </div>
      </div>
    `;
  }

  function FormGrid({ children, className = 'form-grid' }) {
    return html`<div className=${className}>${children}</div>`;
  }

  function FormField({ label, wide = false, children }) {
    return html`
      <label className=${wide ? 'wide' : ''}>
        <span className="label">${label}</span>
        ${children}
      </label>
    `;
  }

  function OutreachToggle({ store, payload, title = 'Добавить в enReach' }) {
    const normalizedPayload = payload || {};
    React.useEffect(() => {
      store?.ensureOutreachSelections?.();
    }, [store]);

    if (!store?.toggleOutreachPayload || !normalizedPayload.value) return null;

    const selected = store.isOutreachPayloadSelected?.(normalizedPayload);
    const busyKey = store.outreachPayloadBusyKey?.(normalizedPayload);
    const busy = !!busyKey && store.outreachBusyKey === busyKey;
    const label = selected ? '-' : '+';
    const actionTitle = selected ? 'Удалить из enReach' : title;

    return html`
      <button
        type="button"
        title=${actionTitle}
        aria-label=${actionTitle}
        disabled=${busy}
        onClick=${(event) => {
          event.preventDefault();
          event.stopPropagation();
          store.toggleOutreachPayload(normalizedPayload);
        }}
        style=${{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '26px',
          height: '26px',
          minWidth: '26px',
          borderRadius: '999px',
          border: selected ? '1px solid #fecaca' : '1px solid #86efac',
          background: selected ? '#fff1f2' : '#dcfce7',
          color: selected ? '#be123c' : '#15803d',
          fontWeight: 900,
          fontSize: '17px',
          lineHeight: 1,
          cursor: busy ? 'wait' : 'pointer',
          opacity: busy ? 0.65 : 1,
        }}
      >
        ${busy ? '…' : label}
      </button>
    `;
  }

  function apiBaseCandidates() {
    return API_BASE_INFO.candidates;
  }

  function withApiBase(path, base) {
    const target = String(path || '');
    if (/^https?:\/\//i.test(target)) return target;
    return `${String(base || '').replace(/\/$/, '')}/${target.replace(/^\//, '')}`;
  }

  async function postJsonWithFallback(path, payload = {}, options = {}) {
    const method = String(options.method || 'POST').toUpperCase();
    let lastError = null;
    for (const base of apiBaseCandidates()) {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), Math.max(2000, Number(options.timeoutMs || 15000)));
      try {
        const response = await fetch(withApiBase(path, base), {
          method,
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            ...(options.headers || {}),
          },
          body: payload == null ? undefined : JSON.stringify(payload),
          cache: 'no-store',
          signal: controller.signal,
        });
        window.clearTimeout(timer);
        const text = await response.text();
        let data = null;
        if (text) {
          try {
            data = JSON.parse(text);
          } catch (_) {
            data = { detail: text };
          }
        }
        if (!response.ok) {
          throw new Error(`HTTP ${response.status} ${response.statusText}${data?.detail ? ` — ${typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)}` : ''}`);
        }
        return data;
      } catch (error) {
        window.clearTimeout(timer);
        lastError = error;
      }
    }
    throw lastError || new Error('API недоступен');
  }

  function cleanDealText(value, maxLen = 8000) {
    const text = String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
    if (!text) return '';
    return text.length > maxLen ? `${text.slice(0, Math.max(0, maxLen - 1)).trim()}…` : text;
  }

  function firstNonEmpty(values = []) {
    for (const value of values) {
      const text = cleanDealText(value, 500);
      if (text) return text;
    }
    return '';
  }

  function DealActionButton({
    payload = null,
    endpoint = '/api/payme/deals',
    method = 'POST',
    label = 'Создать сделку',
    doneLabel = 'Сделка создана',
    existingLabel = 'Сделка уже есть',
    errorLabel = 'Ошибка сделки',
    className = 'btn',
    title = 'Создать сделку в X-Files',
    onDone = null,
  }) {
    const [state, setState] = React.useState('idle');
    const [message, setMessage] = React.useState('');

    const endpointText = String(endpoint || '');
    const needsDealPayload = endpointText === '/api/payme/deals' || /\/api\/payme\/deals$/i.test(endpointText);
    const payloadIsFactory = typeof payload === 'function';
    const disabled = state === 'saving' || (needsDealPayload && !payloadIsFactory && !payload?.title);
    const buttonLabel = state === 'saving'
      ? 'Создаю…'
      : state === 'done'
        ? doneLabel
        : state === 'existing'
          ? existingLabel
          : state === 'error'
            ? errorLabel
            : label;

    async function handleClick(event) {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      if (disabled) return;
      setState('saving');
      setMessage('');
      try {
        const requestPayload = payloadIsFactory ? await payload() : payload;
        if (needsDealPayload && !requestPayload?.title) {
          throw new Error('Не хватает данных для создания сделки');
        }
        const data = await postJsonWithFallback(endpoint, requestPayload || {}, { method, timeoutMs: 18000 });
        const text = String(data?.message || '').toLowerCase();
        setState(text.includes('уже') ? 'existing' : 'done');
        setMessage(data?.message || '');
        if (typeof onDone === 'function') onDone(data);
        window.setTimeout(() => {
          setState('idle');
          setMessage('');
        }, 2200);
      } catch (error) {
        console.error('[X-Files] Deal action failed:', error);
        setState('error');
        setMessage(String(error?.message || error || 'Не удалось создать сделку'));
        window.setTimeout(() => {
          setState('idle');
          setMessage('');
        }, 3200);
      }
    }

    return html`
      <span style=${{ display: 'inline-flex', flexDirection: 'column', gap: '4px', alignItems: 'flex-start' }}>
        <button
          type="button"
          className=${`${className} ${state === 'done' || state === 'existing' ? 'btn-active' : ''}`}
          title=${message || title}
          disabled=${disabled}
          onClick=${handleClick}
        >
          ${buttonLabel}
        </button>
        ${message ? html`<span className="subtle" style=${{ maxWidth: '220px' }}>${message}</span>` : null}
      </span>
    `;
  }

  window.BackfrontReactShared = {
    PROJECT_NAME,
    PROJECT_SUBTITLE,
    APP_VERSION,
    API_BASE_INFO,
    PAGE_SIZE_OPTIONS,
    HtmlBlock,
    StatusPanel,
    ErrorBox,
    ExtNavGroup,
    PageNav,
    PageHeader,
    PageSizeOptions,
    ApiBaseBadge,
    checkCurrentApiBase,
    TelegramCooldownBanner,
    LoadingNotice,
    DataTable,
    Modal,
    FormGrid,
    FormField,
    Pagination,
    TablePaginationFooter,
    VirtualizedRows,
    OutreachToggle,
    DealActionButton,
    cleanDealText,
    firstNonEmpty,
  };
})();
