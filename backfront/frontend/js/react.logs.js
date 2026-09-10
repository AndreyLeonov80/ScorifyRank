/* React logs page */
'use strict';

(function mountReactLogsPage() {
  if (!window.React || !window.ReactDOM || !window.htm || !window.BackfrontReactShared) {
    console.error('[React] Runtime libraries are not loaded for Logs');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const { PageNav } = window.BackfrontReactShared;

  const browserHost = window.location.hostname || '127.0.0.1';
  const apiProtocol = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? window.location.protocol
    : 'http:';
  const explicitApiBase = String(window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL || '').trim().replace(/\/$/, '');
  const pageOrigin = explicitApiBase || ((window.location.origin && window.location.origin !== 'null')
    ? window.location.origin
    : `${apiProtocol}//${browserHost}${window.location.port ? `:${window.location.port}` : ''}`);
  const API_BASE = pageOrigin;
  const API_BASE_CANDIDATES = [
    API_BASE,
  ];
  if (['localhost', '127.0.0.1', '::1', '[::1]'].includes(browserHost) || window.location.protocol === 'file:') {
    API_BASE_CANDIDATES.push(
      `${apiProtocol}//${browserHost}:8001`,
      `${apiProtocol}//127.0.0.1:8001`,
      `${apiProtocol}//localhost:8001`,
    );
  }
  const API_BASE_CANDIDATES_UNIQUE = Array.from(new Set(API_BASE_CANDIDATES));
  const LOG_LIMIT = 3;
  const LOG_FETCH_LIMIT = 40;
  const REALTIME_STREAM_URL = `${API_BASE}/api/payme/stream/realtime`;
  const RUNTIME_LOGS_URL = `${API_BASE}/api/payme/runtime-logs`;
  const STATUS_URL = `${API_BASE}/api/payme/runtime-status`;
  const SERVER_STATUS_URL = `${API_BASE}/api/payme/server-status`;
  const SYSTEM_METRICS_URL = `${API_BASE}/api/payme/system-metrics`;

  function fmtTs(ts) {
    try {
      return ts ? new Date(ts).toLocaleString('ru-RU') : '—';
    } catch (_) {
      return ts || '—';
    }
  }

  function fmtDuration(totalSec) {
    const sec = Math.max(0, Number(totalSec || 0));
    const hours = Math.floor(sec / 3600);
    const minutes = Math.floor((sec % 3600) / 60);
    const seconds = sec % 60;
    if (hours > 0) return `${hours}ч ${minutes}м ${seconds}с`;
    if (minutes > 0) return `${minutes}м ${seconds}с`;
    return `${seconds}с`;
  }

  function fmtNum(value, digits = 1) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toFixed(digits) : '0.0';
  }

  function meterClass(percent) {
    const value = Number(percent || 0);
    if (value >= 85) return 'meter meter-bad';
    if (value >= 70) return 'meter meter-warn';
    return 'meter';
  }

  function taskBadgeClass(status) {
    if (status === 'running') return 'badge badge-running';
    if (status === 'error') return 'badge badge-error';
    if (status === 'disabled') return 'badge badge-disabled';
    if (status === 'stale') return 'badge badge-stale';
    return 'badge badge-idle';
  }

  function taskStatusText(status) {
    if (status === 'running') return 'В работе';
    if (status === 'error') return 'Ошибка';
    if (status === 'disabled') return 'Выключено';
    if (status === 'stale') return 'Нужен refresh';
    return 'Готово';
  }

  function statusToneClass(kind, paused) {
    if (paused) return 'paused';
    if (kind === 'green') return 'status-green';
    if (kind === 'yellow') return 'status-yellow';
    return 'status-red';
  }

  function sourceClass(source) {
    if (source === 'stdout') return 'src src-stdout';
    if (source === 'stderr') return 'src src-stderr';
    return 'src src-system';
  }

  function logToneClass(message) {
    const text = String(message || '').toLowerCase();
    if (
      text.includes('floodwait')
      || text.includes('peerflood')
      || text.includes('userprivacyrestricted')
      || text.includes('risk_blocked')
      || text.includes('blocked_privacy')
      || text.includes('risk_rate_limited')
    ) {
      return 'row row-risk';
    }
    if (
      text.includes('429')
      || text.includes('rate-limit')
      || text.includes('cooldown')
      || text.includes('backoff')
    ) {
      return 'row row-warn';
    }
    return 'row';
  }

  function withFallbackApiBase(url, base) {
    try {
      const original = new URL(url, window.location.href);
      const fallbackBase = new URL(base);
      original.protocol = fallbackBase.protocol;
      original.hostname = fallbackBase.hostname;
      original.port = fallbackBase.port;
      return original.toString();
    } catch (_) {
      return url;
    }
  }

  async function apiJson(url) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url);
    }

    let lastError = null;
    for (const base of API_BASE_CANDIDATES_UNIQUE) {
      const candidateUrl = withFallbackApiBase(url, base);
      try {
        const response = await fetch(candidateUrl, { cache: 'no-store' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error('Сервер недоступен');
  }

  function MetricCard({ label, value, sub, percent }) {
    return html`
      <div className="metric-card">
        <div className="metric-label">${label}</div>
        <div className="metric-value">${value}</div>
        <div className="metric-sub">${sub}</div>
        <div className=${meterClass(percent)}><span style=${{ width: `${Math.max(0, Math.min(100, Number(percent || 0)))}%` }}></span></div>
      </div>
    `;
  }

  function TaskRow({ task }) {
    const progress = Math.max(0, Math.min(100, Number(task.progress_percent || 0)));
    const meta = [
      task.progress_total > 0 ? `Прогресс: ${task.progress_current} / ${task.progress_total}` : '',
      task.total_rows ? `Строк кеша: ${task.total_rows}` : '',
      task.current_item ? `Текущий: ${task.current_item}` : '',
      task.next_refresh_at ? `Следующее автообновление: ${fmtTs(task.next_refresh_at)}` : '',
      task.last_refresh_at ? `Последнее обновление: ${fmtTs(task.last_refresh_at)}` : '',
    ].filter(Boolean);
    return html`
      <div className="task-row">
        <div className="task-top">
          <div>
            <div className="task-name">${task.label || task.kind || 'Задача'}</div>
            <div className="task-summary">${task.summary || '—'}</div>
          </div>
          <div className=${taskBadgeClass(task.status)}>${taskStatusText(task.status)}</div>
        </div>
        <div className=${meterClass(progress)} style=${{ marginTop: '10px' }}><span style=${{ width: `${progress}%` }}></span></div>
        <div className="task-meta">${meta.map((item, idx) => html`<span key=${`meta-${idx}`}>${item}</span>`)}</div>
        ${task.last_error ? html`<div className="task-error">${task.last_error}</div>` : null}
      </div>
    `;
  }

  function LogRow({ item }) {
    return html`
      <div className=${logToneClass(item.message)}>
        <div className="ts">${fmtTs(item.ts)}</div>
        <div className=${sourceClass(item.source)}>${item.source}</div>
        <div className="msg">${item.message}</div>
      </div>
    `;
  }

  function LogsPage() {
    const [items, setItems] = React.useState([]);
    const [afterId, setAfterId] = React.useState(0);
    const [paused, setPaused] = React.useState(false);
    const [isVisible, setIsVisible] = React.useState(typeof document === 'undefined' ? true : !document.hidden);
    const [streamConnected, setStreamConnected] = React.useState(false);
    const [usingPollingFallback, setUsingPollingFallback] = React.useState(false);
    const [lastPollNewCount, setLastPollNewCount] = React.useState(0);
    const [updatedAt, setUpdatedAt] = React.useState(null);
    const [authStatus, setAuthStatus] = React.useState(null);
    const [authError, setAuthError] = React.useState('');
    const [serverStatus, setServerStatus] = React.useState(null);
    const [serverError, setServerError] = React.useState('');
    const [systemMetrics, setSystemMetrics] = React.useState(null);
    const [metricsError, setMetricsError] = React.useState('');
    const [apiUrl, setApiUrl] = React.useState(REALTIME_STREAM_URL);

    const latestItem = items.length ? items[0] : null;

    const statusModel = React.useMemo(() => {
      if (paused) return { tone: 'yellow', text: 'Автообновление на паузе' };
      if (!isVisible) return { tone: 'yellow', text: 'Вкладка неактивна, автообновление замедлено' };
      if (streamConnected) return { tone: 'green', text: 'Подключены к live stream сервера' };
      if (usingPollingFallback) return { tone: 'yellow', text: 'Live stream недоступен, включён polling' };
      if (!latestItem) return { tone: 'red', text: 'Ожидаем новые сообщения' };
      if (lastPollNewCount <= 0) return { tone: 'red', text: 'Ожидаем новые сообщения' };
      return { tone: 'green', text: `Новые сообщения пришли: ${lastPollNewCount}` };
    }, [paused, isVisible, streamConnected, usingPollingFallback, latestItem, lastPollNewCount]);

    const authBadge = React.useMemo(() => {
      if (!authStatus) return { className: 'badge badge-warn', text: authError || 'Проверяю авторизацию…', sub: 'Ждём ответ приложения.' };
      const className =
        authStatus.auth_status === 'authorized' ? 'badge badge-ok'
          : authStatus.auth_status === 'needs_api_credentials' ? 'badge badge-bad'
          : authStatus.auth_status === 'needs_auth' ? 'badge badge-bad'
            : 'badge badge-warn';
      const sub = authStatus.connected
        ? 'Соединение с Telegram активно.'
        : (authStatus.auth_status === 'needs_api_credentials'
          ? 'Нужно указать api_id и api_hash из my.telegram.org.'
          : (authStatus.session_file_exists
            ? 'Файл сессии найден, но активное подключение ещё не подтверждено.'
            : 'Файл сессии не найден, для входа нужен запуск из консоли.'));
      return { className, text: authStatus.auth_message || 'Статус неизвестен', sub };
    }, [authStatus, authError]);

    const serverBadge = React.useMemo(() => {
      if (!serverStatus) return { className: serverError ? 'badge badge-bad' : 'badge badge-warn', text: serverError ? 'Сервер недоступен' : 'Проверяю сервер…', sub: serverError || 'Ждём ответ приложения.' };
      return {
        className: 'badge badge-ok',
        text: serverStatus.mode === 'docker' ? 'Сервер работает в Docker' : 'Сервер работает локально',
        sub: serverStatus.mode === 'docker'
          ? 'Если в Docker Desktop пусто в Containers, значит контейнер сейчас не запущен или уже завершился. Image сам по себе код не исполняет.'
          : 'Сейчас приложение работает локальным процессом, поэтому в Docker Desktop может быть пусто, даже если image gramlead существует.',
      };
    }, [serverStatus, serverError]);

    const trimmedItems = React.useMemo(() => {
      const next = [...items].sort((a, b) => {
        const ta = Date.parse(a.ts || '');
        const tb = Date.parse(b.ts || '');
        if (!Number.isNaN(ta) && !Number.isNaN(tb) && tb !== ta) return tb - ta;
        return Number(b.id || 0) - Number(a.id || 0);
      });
      return next.slice(0, LOG_FETCH_LIMIT);
    }, [items]);
    const backendItems = React.useMemo(
      () => trimmedItems.filter((item) => String(item.channel || 'backend') === 'backend').slice(0, LOG_LIMIT),
      [trimmedItems],
    );
    const telegramItems = React.useMemo(
      () => trimmedItems.filter((item) => String(item.channel || 'backend') === 'telegram').slice(0, LOG_LIMIT),
      [trimmedItems],
    );

    const loadRuntimeStatus = React.useCallback(async () => {
      try {
        const data = await apiJson(STATUS_URL);
        setAuthStatus(data);
        setAuthError('');
      } catch (error) {
        setAuthStatus(null);
        setAuthError(error.message || String(error));
      }
    }, []);

    const loadServerStatus = React.useCallback(async () => {
      try {
        const data = await apiJson(SERVER_STATUS_URL);
        setServerStatus(data);
        setServerError('');
      } catch (error) {
        setServerStatus(null);
        setServerError(`Не удалось получить status: ${error.message || error}`);
      }
    }, []);

    const loadSystemMetrics = React.useCallback(async () => {
      try {
        const data = await apiJson(`${SYSTEM_METRICS_URL}?history_points=60`);
        setSystemMetrics(data);
        setMetricsError('');
      } catch (error) {
        setMetricsError(`Не удалось загрузить метрики и задачи: ${error.message || error}`);
      }
    }, []);

    const tick = React.useCallback(async (forceFull = false) => {
      if ((paused || !isVisible) && !forceFull) return;
      const query = new URLSearchParams({ minutes: '60', limit: String(LOG_FETCH_LIMIT) });
      if (!forceFull && afterId > 0) query.set('after_id', String(afterId));
      try {
        const data = await apiJson(`${RUNTIME_LOGS_URL}?${query.toString()}`);
        const rows = Array.isArray(data) ? data : [];
        setItems((prev) => forceFull ? rows : prev.concat(rows));
        const nextAfter = rows.length
          ? Math.max(forceFull ? 0 : afterId, ...rows.map((item) => Number(item.id || 0)))
          : (forceFull
            ? Math.max(0, ...((Array.isArray(data) ? data : []).map((item) => Number(item.id || 0))))
            : afterId);
        setAfterId(nextAfter);
        setLastPollNewCount(forceFull ? (rows.length ? 1 : 0) : rows.length);
        setUsingPollingFallback(true);
        setUpdatedAt(new Date());
      } catch (_) {
        /* handled by status indicators / fallback polling */
      }
    }, [paused, isVisible, afterId]);

    React.useEffect(() => {
      function handleVisibility() {
        setIsVisible(!document.hidden);
      }
      document.addEventListener('visibilitychange', handleVisibility);
      window.addEventListener('focus', handleVisibility);
      window.addEventListener('blur', handleVisibility);
      return () => {
        document.removeEventListener('visibilitychange', handleVisibility);
        window.removeEventListener('focus', handleVisibility);
        window.removeEventListener('blur', handleVisibility);
      };
    }, []);

    React.useEffect(() => {
      let cancelled = false;
      let timer = null;
      let authTimer = null;
      let serverTimer = null;
      let metricsTimer = null;
      let stream = null;
      function applyMonitorSnapshot(snapshot) {
        if (snapshot?.runtime) {
          setAuthStatus(snapshot.runtime);
          setAuthError('');
        }
        if (snapshot?.server) {
          setServerStatus(snapshot.server);
          setServerError('');
        }
        if (snapshot?.system) {
          setSystemMetrics(snapshot.system);
          setMetricsError('');
        }
      }

      const client = window.BackfrontRealtime;
      if (isVisible && client?.startTypedRealtimeStreamConsumer) {
        stream = client.startTypedRealtimeStreamConsumer({
          baseUrl: REALTIME_STREAM_URL,
          baseCandidates: API_BASE_CANDIDATES_UNIQUE,
          types: ['runtime_log', 'monitor'],
          historyPoints: 60,
          onState: ({ state, url }) => {
            if (cancelled) return;
            if (url) setApiUrl(url);
            setStreamConnected(state === 'connected');
            setUsingPollingFallback(state === 'error');
          },
          onEnvelope: (envelope) => {
            if (cancelled) return;
            if (envelope?.type === 'monitor_snapshot' && envelope?.payload) {
              applyMonitorSnapshot(envelope.payload);
            }
          },
          onError: () => {
            if (!cancelled) {
              setStreamConnected(false);
              setUsingPollingFallback(true);
            }
          },
        });
      } else {
        setStreamConnected(false);
        setUsingPollingFallback(true);
      }

      if (isVisible) {
        tick(true);
        loadRuntimeStatus();
        loadServerStatus();
        loadSystemMetrics();
      }

      timer = setInterval(() => {
        if (!document.hidden) tick(true);
      }, document.hidden ? 15000 : 1000);
      authTimer = setInterval(() => {
        if (!document.hidden && !streamConnected) loadRuntimeStatus();
      }, document.hidden ? 60000 : 15000);
      serverTimer = setInterval(() => {
        if (!document.hidden && !streamConnected) loadServerStatus();
      }, document.hidden ? 60000 : 15000);
      metricsTimer = setInterval(() => {
        if (!document.hidden && !streamConnected) loadSystemMetrics();
      }, document.hidden ? 60000 : 15000);

      return () => {
        cancelled = true;
        if (timer) clearInterval(timer);
        if (authTimer) clearInterval(authTimer);
        if (serverTimer) clearInterval(serverTimer);
        if (metricsTimer) clearInterval(metricsTimer);
        if (stream) {
          try { stream.close(); } catch (_) {}
        }
      };
    }, [tick, loadRuntimeStatus, loadServerStatus, loadSystemMetrics, streamConnected, isVisible]);

    return html`
      <div className="page">
        <div className="top">
          <div>
            <div className="title">Логи Сервера</div>
            <div className="sub">Показываются два отдельных светлых лога: backend и данные Telegram в реальном времени.</div>
          </div>
          <div className=${`actions ${statusToneClass(statusModel.tone, paused)}`}>
            <${PageNav} active="logs" />
            <span className="status-dot"></span>
            <span className="sub">${statusModel.text}</span>
            <span className="badge badge-ok">Backend: ${backendItems.length} · Telegram: ${telegramItems.length}</span>
            <button className="btn" onClick=${() => setPaused((prev) => !prev)}>${paused ? 'Продолжить' : 'Пауза'}</button>
            <button className="btn" onClick=${() => { setAfterId(0); tick(true); }}>Обновить сейчас</button>
          </div>
        </div>

        <div className="info-grid">
          <div className="info-card">
            <div className="info-title">Как запускать в консоли</div>
            <div className="sub">Если нужна авторизация Telegram, запускайте контейнер так, чтобы можно было ввести телефон, код и 2FA в консоли Docker.</div>
            <div className="cmd">${`cd /Volumes/aiapi/Desktop/gramlead/code/pre-prod-1/backfront\nAPP_LICENSE_SECRET='local-test-secret' bash ./run-docker.sh`}</div>
            <div className="sub" style=${{ marginTop: '10px' }}>Полная пересборка и запуск:</div>
            <div className="cmd">${`cd /Volumes/aiapi/Desktop/gramlead/code/pre-prod-1/backfront\nDOCKER_PLATFORM=linux/arm64 FORCE_REBUILD=1 RUN_OCR_SERVICE=0 APP_LICENSE_SECRET='local-test-secret' ./run-docker.sh`}</div>
          </div>

          <div className="info-card">
            <div className="info-title">Статус сервера и Telegram</div>
            <div className=${serverBadge.className}>${serverBadge.text}</div>
            <div className="sub" style=${{ marginTop: '10px' }}>${serverBadge.sub}</div>
            <div className="meta-list">
              <div className="meta-item"><span>Режим</span><strong>${serverStatus?.mode || '—'}</strong></div>
              <div className="meta-item"><span>PID</span><strong>${serverStatus?.pid || '—'}</strong></div>
              <div className="meta-item"><span>Хост</span><strong>${serverStatus?.hostname || '—'}</strong></div>
              <div className="meta-item"><span>Uptime</span><strong>${serverStatus ? fmtDuration(serverStatus.uptime_sec) : '—'}</strong></div>
            </div>
            <div style=${{ marginTop: '14px' }}>
              <div className=${authBadge.className}>${authBadge.text}</div>
              <div className="sub" style=${{ marginTop: '10px' }}>${authBadge.sub}</div>
            </div>
          </div>
        </div>

        <div className="panel monitor-panel">
          <div className="stats">
            <div className="stat">Монитор<strong>${systemMetrics ? fmtTs(systemMetrics.ts) : (metricsError ? 'Ошибка' : 'Ждём данные…')}</strong></div>
            <div className="stat">Интервал sampler<strong>${systemMetrics ? `${fmtNum(systemMetrics.sampler_interval_sec || 0, 0)}с` : '—'}</strong></div>
            <div className="stat">Открытых файлов<strong>${systemMetrics?.open_files ?? '—'}</strong></div>
            <div className="stat">Потоков<strong>${systemMetrics?.threads ?? '—'}</strong></div>
          </div>
          <div className="monitor-grid">
            <${MetricCard}
              label="CPU"
              value=${systemMetrics ? `${fmtNum(systemMetrics.cpu_percent)}%` : '—'}
              sub=${systemMetrics ? `Load avg: ${(systemMetrics.load_avg || []).join(' / ') || '—'}` : '—'}
              percent=${systemMetrics?.cpu_percent || 0}
            />
            <${MetricCard}
              label="RAM"
              value=${systemMetrics ? `${fmtNum(systemMetrics.memory_percent)}%` : '—'}
              sub=${systemMetrics ? `${fmtNum(systemMetrics.memory_used_mb, 0)} MB / ${fmtNum(systemMetrics.memory_total_mb, 0)} MB` : '—'}
              percent=${systemMetrics?.memory_percent || 0}
            />
            <${MetricCard}
              label="Процесс"
              value=${systemMetrics ? `${fmtNum(systemMetrics.process_cpu_percent)}% CPU` : '—'}
              sub=${systemMetrics ? `${fmtNum(systemMetrics.process_memory_mb, 0)} MB RSS` : '—'}
              percent=${systemMetrics?.process_cpu_percent || 0}
            />
            <${MetricCard}
              label="Disk"
              value=${systemMetrics ? `${fmtNum(Number(systemMetrics.disk_total_gb || 0) > 0 ? (Number(systemMetrics.disk_used_gb || 0) / Number(systemMetrics.disk_total_gb || 1)) * 100 : 0)}%` : '—'}
              sub=${systemMetrics ? `${fmtNum(systemMetrics.disk_used_gb)} GB / ${fmtNum(systemMetrics.disk_total_gb)} GB` : '—'}
              percent=${systemMetrics ? (Number(systemMetrics.disk_total_gb || 0) > 0 ? (Number(systemMetrics.disk_used_gb || 0) / Number(systemMetrics.disk_total_gb || 1)) * 100 : 0) : 0}
            />
          </div>
          <div className="tasks-wrap">
            <div className="tasks-head">
              <div>
                <div className="info-title" style=${{ margin: 0 }}>Фоновые задачи</div>
                <div className="sub">Backend-кеши и сервисные операции. Прогресс виден по мере готовности.</div>
              </div>
            </div>
            <div className="tasks-list">
              ${metricsError
                ? html`<div className="empty" style=${{ padding: '16px 0' }}>${metricsError}</div>`
                : ((systemMetrics?.tasks || []).length
                  ? systemMetrics.tasks.map((task, idx) => html`<${TaskRow} key=${`task-${idx}`} task=${task} />`)
                  : html`<div className="empty" style=${{ padding: '16px 0' }}>Ждём состояние задач…</div>`)}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="stats">
            <div className="stat">Backend логов<strong>${backendItems.length}</strong></div>
            <div className="stat">Telegram логов<strong>${telegramItems.length}</strong></div>
            <div className="stat">Последнее обновление<strong>${updatedAt ? updatedAt.toLocaleTimeString('ru-RU') : '—'}</strong></div>
            <div className="stat">Последний лог<strong>${latestItem ? fmtTs(latestItem.ts) : '—'}</strong></div>
            <div className="stat">Источник<strong>${apiUrl}</strong></div>
          </div>
          <div className="info-grid">
            <div>
              <div className="info-title" style=${{ marginBottom: '10px' }}>Лог backend</div>
              <div className="log-list">
                ${backendItems.length
                  ? backendItems.map((item, idx) => html`<${LogRow} key=${`backend-log-${idx}-${item.id || item.ts || idx}`} item=${item} />`)
                  : html`<div className="empty">Backend-логи ещё не пришли.</div>`}
              </div>
            </div>
            <div>
              <div className="info-title" style=${{ marginBottom: '10px' }}>Лог данных Telegram</div>
              <div className="log-list">
                ${telegramItems.length
                  ? telegramItems.map((item, idx) => html`<${LogRow} key=${`telegram-log-${idx}-${item.id || item.ts || idx}`} item=${item} />`)
                  : html`<div className="empty">Telegram-логи ещё не пришли.</div>`}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Logs page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${LogsPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
