/* Shared dashboard runtime utilities */
'use strict';

(function initReactDashboardUtils() {
  window.BackfrontDashboardUtils = function BackfrontDashboardUtils() {
  const browserHost = window.location.hostname || '127.0.0.1';
  const apiProtocol = (window.location.protocol === 'http:' || window.location.protocol === 'https:') ? window.location.protocol : 'http:';
  const explicitApiBase = String(window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL || '').trim().replace(/\/$/, '');
  const pageOrigin = explicitApiBase || ((window.location.origin && window.location.origin !== 'null')
    ? window.location.origin
    : `${apiProtocol}//${browserHost}${window.location.port ? `:${window.location.port}` : ''}`);
  const API_BASE = pageOrigin;
  const DASHBOARD_ACTIVITY_LIMIT = 3;
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

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;');
  }

  function fmtTs(value) {
    if (!value) return '—';
    try { return new Date(value).toLocaleString('ru-RU'); } catch (_) { return String(value); }
  }

  function fmtNum(value, digits = 1) {
    const num = Number(value || 0);
    return Number.isFinite(num) ? num.toFixed(digits) : '0.0';
  }

  function fmtRub(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num) || num <= 0) return '0 ₽';
    return `${Math.round(num).toLocaleString('ru-RU')} ₽`;
  }

  function fmtBytes(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num) || num <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = num;
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    return `${size.toFixed(size >= 100 || idx === 0 ? 0 : size >= 10 ? 1 : 2)} ${units[idx]}`;
  }

  function fmtMaybeNumber(value, digits = 1) {
    if (value == null || value === '') return '—';
    const num = Number(value);
    return Number.isFinite(num) ? num.toFixed(digits) : '—';
  }

  function ageSeconds(value) {
    if (!value) return null;
    const ts = new Date(value).getTime();
    if (!Number.isFinite(ts)) return null;
    return Math.max(0, Math.round((Date.now() - ts) / 1000));
  }

  function fmtAge(value) {
    const seconds = ageSeconds(value);
    if (seconds == null) return '—';
    if (seconds < 60) return `${seconds}с назад`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}м назад`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)}ч назад`;
    return `${Math.round(seconds / 86400)}д назад`;
  }

  function fmtFutureDuration(seconds) {
    const safeSeconds = Math.max(0, Math.round(Number(seconds || 0)));
    if (safeSeconds < 60) return `через ${safeSeconds}с`;
    if (safeSeconds < 3600) return `через ${Math.round(safeSeconds / 60)}м`;
    if (safeSeconds < 86400) return `через ${Math.round(safeSeconds / 3600)}ч`;
    return `через ${Math.round(safeSeconds / 86400)}д`;
  }

  function estimateDuckdbTargets(duckdbSync) {
    const progress = Number(duckdbSync?.progress_percent || 0);
    const startedAt = duckdbSync?.progress_started_at ? new Date(duckdbSync.progress_started_at).getTime() : NaN;
    const updatedAt = duckdbSync?.progress_updated_at ? new Date(duckdbSync.progress_updated_at).getTime() : Date.now();
    if (!duckdbSync?.running || !Number.isFinite(progress) || progress <= 0 || !Number.isFinite(startedAt) || startedAt <= 0) {
      return null;
    }
    const nowTs = Date.now();
    const effectiveNow = Number.isFinite(updatedAt) && updatedAt > 0 ? Math.max(updatedAt, nowTs) : nowTs;
    const elapsedSec = Math.max(1, Math.round((effectiveNow - startedAt) / 1000));
    const percentPerSec = progress / elapsedSec;
    if (!Number.isFinite(percentPerSec) || percentPerSec <= 0) {
      return null;
    }

    function buildTarget(targetPercent) {
      const clampedTarget = Math.max(0, Math.min(100, Number(targetPercent || 0)));
      const remainingPercent = clampedTarget - progress;
      if (remainingPercent <= 0) {
        return {
          targetPercent: clampedTarget,
          etaText: 'Уже достигнуто',
          etaAtText: fmtTs(effectiveNow),
        };
      }
      const secondsLeft = Math.max(1, Math.round(remainingPercent / percentPerSec));
      const etaAt = new Date(effectiveNow + (secondsLeft * 1000));
      return {
        targetPercent: clampedTarget,
        etaText: fmtFutureDuration(secondsLeft),
        etaAtText: fmtTs(etaAt.toISOString()),
      };
    }

    return [buildTarget(50), buildTarget(80), buildTarget(100)];
  }

  function toneClass(tone) {
    return tone === 'red' ? 'tone-red' : tone === 'yellow' ? 'tone-yellow' : 'tone-green';
  }

  function badgeClass(tone) {
    return tone === 'red' ? 'badge badge-red' : tone === 'yellow' ? 'badge badge-yellow' : 'badge badge-green';
  }

  function toneByPercent(value, warn = 70, bad = 85) {
    const num = Number(value || 0);
    if (num >= bad) return 'red';
    if (num >= warn) return 'yellow';
    return 'green';
  }

  function toneByRuntime(runtime) {
    if (!runtime) return 'yellow';
    if (runtime.auth_status === 'authorized' && runtime.connected) return 'green';
    if (runtime.auth_status === 'needs_api_credentials') return 'red';
    if (runtime.auth_status === 'needs_auth') return 'red';
    return 'yellow';
  }

  function toneByAnalysis(status) {
    if (!status) return 'yellow';
    if (status.last_error) return 'red';
    if (status.running || status.stale_reason) return 'yellow';
    if (status.cache_ready || Number(status.total_rows || 0) > 0) return 'green';
    return 'yellow';
  }

  function isDuckdbReady(status) {
    if (!status) return false;
    if (status.cache_ready) return true;
    const indexed = Number(status.source_files_indexed || 0);
    const total = Number(status.source_files_total || 0);
    const rows = Number(status.message_rows || 0);
    return rows > 0 && total > 0 && indexed >= total;
  }

  function toneByTaskList(tasks) {
    const rows = Array.isArray(tasks) ? tasks : [];
    if (rows.some((task) => task?.status === 'error')) return 'red';
    if (rows.some((task) => task?.status === 'stale' || task?.status === 'running')) return 'yellow';
    return 'green';
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

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const timeoutMs = Math.max(250, Number(options.timeoutMs || 0));
    let lastError = null;
    for (const base of API_BASE_CANDIDATES_UNIQUE) {
      const candidateUrl = withFallbackApiBase(url, base);
      let controller = null;
      let timeoutId = null;
      try {
        controller = timeoutMs > 0 ? new AbortController() : null;
        if (controller) {
          timeoutId = window.setTimeout(() => {
            try { controller.abort(); } catch (_) {}
          }, timeoutMs);
        }
        const response = await fetch(candidateUrl, {
          cache: 'no-store',
          signal: controller ? controller.signal : undefined,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } catch (error) {
        lastError = error;
      } finally {
        if (timeoutId) window.clearTimeout(timeoutId);
      }
    }
    throw lastError || new Error('Сервер недоступен');
  }

  async function apiPostJson(url, options = {}) {
    if (window.BackfrontApi?.apiPostJson) {
      const hasPayload = Object.prototype.hasOwnProperty.call(options || {}, 'payload');
      const { payload, ...requestOptions } = options || {};
      return window.BackfrontApi.apiPostJson(url, hasPayload ? payload : undefined, requestOptions);
    }

    const timeoutMs = Math.max(250, Number(options.timeoutMs || 8000));
    const hasPayload = Object.prototype.hasOwnProperty.call(options, 'payload');
    let lastError = null;
    for (const base of API_BASE_CANDIDATES_UNIQUE) {
      const candidateUrl = withFallbackApiBase(url, base);
      let controller = null;
      let timeoutId = null;
      try {
        controller = new AbortController();
        timeoutId = window.setTimeout(() => {
          try { controller.abort(); } catch (_) {}
        }, timeoutMs);
        const response = await fetch(candidateUrl, {
          method: 'POST',
          cache: 'no-store',
          headers: {
            Accept: 'application/json',
            ...(hasPayload ? { 'Content-Type': 'application/json' } : {}),
          },
          body: hasPayload ? JSON.stringify(options.payload || {}) : undefined,
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } catch (error) {
        lastError = error;
      } finally {
        if (timeoutId) window.clearTimeout(timeoutId);
      }
    }
    throw lastError || new Error('Сервер недоступен');
  }

  async function apiJsonOptional(url, options = {}) {
    try {
      return await apiJson(url, options);
    } catch (_) {
      return null;
    }
  }

  async function loadFallbackDashboardSummary(limit) {
    const safeLimit = Math.max(1, Number(limit || 5));
    const [
      runtime,
      server,
      system,
      duckdbSync,
    ] = await Promise.all([
      apiJsonOptional(`${API_BASE}/api/payme/runtime-status`, { timeoutMs: 8000 }),
      apiJsonOptional(`${API_BASE}/api/payme/server-status`, { timeoutMs: 8000 }),
      apiJsonOptional(`${API_BASE}/api/payme/system-metrics?history_points=30`, { timeoutMs: 8000 }),
      apiJsonOptional(`${API_BASE}/api/payme/duckdb/status`, { timeoutMs: 12000 }),
    ]);

    const duckdb = duckdbSync?.status || duckdbSync || null;

    return {
      ts: new Date().toISOString(),
      runtime,
      server,
      system: system || { history: [], tasks: [] },
      duckdb_sync: duckdb,
      duckdb,
      crm: null,
      events: null,
      contacts: null,
      media: null,
      import_sync: null,
      telegram: {
        flood_wait: null,
        sync_control: null,
      },
      telegram_flood_wait: null,
      telegram_sync_control: null,
      storage: {
        jsonl_bytes: Number(duckdb?.jsonl_bytes || 0),
        duckdb_bytes: Number(duckdb?.duckdb_bytes || 0),
        parquet_bytes: Number(duckdb?.parquet_bytes || 0),
        parquet_files: Number(duckdb?.parquet_files || 0),
        media_images_bytes: 0,
      },
      counts: {
        leads: 0,
        dialogs: 0,
        contacts: 0,
        crm: 0,
        events: 0,
        images: 0,
        runtime_logs: 0,
        backend_logs: 0,
        telegram_logs: 0,
      },
      previews: {
        leads: [],
        dialogs: [],
        contacts: [],
        crm: [],
        events: [],
        images: [],
        runtime_logs: [],
        backend_logs: [],
        telegram_logs: [],
      },
    };
  }


    return {
      API_BASE,
      DASHBOARD_ACTIVITY_LIMIT,
      escapeHtml,
      fmtTs,
      fmtNum,
      fmtRub,
      fmtBytes,
      fmtMaybeNumber,
      ageSeconds,
      fmtAge,
      fmtFutureDuration,
      estimateDuckdbTargets,
      toneClass,
      badgeClass,
      toneByPercent,
      toneByRuntime,
      toneByAnalysis,
      isDuckdbReady,
      toneByTaskList,
      apiJson,
      apiPostJson,
      apiJsonOptional,
      loadFallbackDashboardSummary
    };
  };
})();
