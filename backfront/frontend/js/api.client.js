/* Shared Backfront API client for legacy HTML and React pages */
'use strict';

(function initBackfrontApiClient() {
  if (window.BackfrontApi?.apiJson) return;

  const DEFAULT_BACKEND_PORT = '8009';
  const LEGACY_BACKEND_PORT = '8001';
  const inflightControllers = new Map();
  const inflightRequests = new Map();
  const responseCache = new Map();

  function normalizeBaseUrl(value) {
    return String(value || '').trim().replace(/\/+$/, '');
  }

  function apiProtocol() {
    return window.location.protocol === 'https:' ? 'https:' : 'http:';
  }

  function isLocalHost(host) {
    return ['localhost', '127.0.0.1', '::1', '[::1]'].includes(String(host || ''));
  }

  function unique(values) {
    return Array.from(new Set(values.filter(Boolean).map(normalizeBaseUrl).filter(Boolean)));
  }

  function getApiCandidates() {
    const host = window.location.hostname || '127.0.0.1';
    const protocol = apiProtocol();
    const explicit = normalizeBaseUrl(window.XFILES_API_BASE || window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL);
    const origin = normalizeBaseUrl(
      window.location.origin && window.location.origin !== 'null'
        ? window.location.origin
        : `${protocol}//${host}${window.location.port ? ':' + window.location.port : ''}`,
    );
    const backendPort = String(window.XFILES_BACKEND_PORT || DEFAULT_BACKEND_PORT).trim();
    const legacyPort = String(window.XFILES_LEGACY_BACKEND_PORT || LEGACY_BACKEND_PORT).trim();
    const candidates = [explicit, origin];

    if (isLocalHost(host) || window.location.protocol === 'file:') {
      if (backendPort) {
        candidates.push(
          `${protocol}//${host}:${backendPort}`,
          `${protocol}//127.0.0.1:${backendPort}`,
          `${protocol}//localhost:${backendPort}`,
        );
      }
      if (legacyPort && legacyPort !== backendPort) {
        candidates.push(
          `${protocol}//${host}:${legacyPort}`,
          `${protocol}//127.0.0.1:${legacyPort}`,
          `${protocol}//localhost:${legacyPort}`,
        );
      }
    }

    return unique(candidates);
  }

  function withFallbackApiBase(url, base) {
    const normalizedBase = normalizeBaseUrl(base);
    const rawUrl = String(url || '');
    try {
      const original = new URL(rawUrl, window.location.href);
      const fallbackBase = new URL(normalizedBase);
      original.protocol = fallbackBase.protocol;
      original.hostname = fallbackBase.hostname;
      original.port = fallbackBase.port;
      return original.toString();
    } catch (_) {
      const path = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`;
      return `${normalizedBase}${path}`;
    }
  }

  function isApiRequest(url) {
    try {
      return new URL(String(url || ''), window.location.href).pathname.startsWith('/api/');
    } catch (_) {
      return String(url || '').startsWith('/api/');
    }
  }

  function cacheStorageKey(cacheKey) {
    return cacheKey ? `backfront.api.cache.${cacheKey}` : '';
  }

  function normalizeApiErrorDetail(detail) {
    if (detail == null || detail === '') return '';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === 'string') return item;
          const location = Array.isArray(item?.loc) ? item.loc.join('.') : '';
          const message = String(item?.msg || item?.message || '').trim();
          return [location, message].filter(Boolean).join(': ');
        })
        .filter(Boolean)
        .join('; ');
    }
    if (typeof detail === 'object') {
      return String(detail.message || detail.msg || JSON.stringify(detail));
    }
    return String(detail);
  }

  function getCachedApiResponse(cacheKey, cacheTtlMs, persistCache = false) {
    if (!cacheKey || !cacheTtlMs) return null;
    const now = Date.now();
    const cached = responseCache.get(cacheKey);
    if (cached && now - cached.ts <= cacheTtlMs) return cached.value;
    if (cached) responseCache.delete(cacheKey);
    if (!persistCache) return null;

    try {
      const raw = window.sessionStorage?.getItem(cacheStorageKey(cacheKey));
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || now - Number(parsed.ts || 0) > cacheTtlMs) {
        window.sessionStorage?.removeItem(cacheStorageKey(cacheKey));
        return null;
      }
      return parsed.value;
    } catch (_) {
      return null;
    }
  }

  function setCachedApiResponse(cacheKey, cacheTtlMs, value, persistCache = false) {
    if (!cacheKey || !cacheTtlMs) return;
    const payload = { ts: Date.now(), value };
    responseCache.set(cacheKey, payload);
    if (!persistCache) return;
    try {
      window.sessionStorage?.setItem(cacheStorageKey(cacheKey), JSON.stringify(payload));
    } catch (_) {}
  }

  async function apiJson(url, options = {}) {
    const {
      timeoutMs = 8000,
      requestKey = '',
      cacheKey = '',
      cacheTtlMs = 0,
      persistCache = false,
      forceFresh = false,
      dedupeKey = '',
      staleWhileRevalidate = false,
      onRevalidate = null,
      baseCandidates = null,
      ...fetchOptions
    } = options || {};
    const method = String(fetchOptions.method || 'GET').toUpperCase();
    const headers = {
      Accept: 'application/json',
      ...(fetchOptions.headers || {}),
    };
    if (options.body !== undefined && !(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    if (method === 'GET' && !forceFresh) {
      const cached = getCachedApiResponse(cacheKey, Number(cacheTtlMs || 0), persistCache);
      if (cached != null) {
        if (staleWhileRevalidate && cacheKey) {
          window.setTimeout(() => {
            apiJson(url, {
              ...options,
              forceFresh: true,
              staleWhileRevalidate: false,
              requestKey: '',
              dedupeKey: `swr:${cacheKey}`,
            })
              .then((fresh) => {
                if (typeof onRevalidate === 'function') onRevalidate(fresh);
              })
              .catch(() => {});
          }, 0);
        }
        return cached;
      }
    }

    const effectiveDedupeKey = method === 'GET' ? String(dedupeKey || '').trim() : '';
    if (effectiveDedupeKey && !forceFresh && inflightRequests.has(effectiveDedupeKey)) {
      return inflightRequests.get(effectiveDedupeKey);
    }

    const requestPromise = apiJsonNetwork(url, {
      timeoutMs,
      requestKey,
      cacheKey,
      cacheTtlMs,
      persistCache,
      baseCandidates,
      fetchOptions,
      headers,
      method,
    });

    if (effectiveDedupeKey) {
      inflightRequests.set(effectiveDedupeKey, requestPromise);
      requestPromise.finally(() => {
        if (inflightRequests.get(effectiveDedupeKey) === requestPromise) {
          inflightRequests.delete(effectiveDedupeKey);
        }
      }).catch(() => {});
    }

    return requestPromise;
  }

  async function apiJsonNetwork(url, options = {}) {
    const {
      timeoutMs = 8000,
      requestKey = '',
      cacheKey = '',
      cacheTtlMs = 0,
      persistCache = false,
      baseCandidates = null,
      fetchOptions = {},
      headers = {},
      method = 'GET',
    } = options || {};

    if (requestKey) {
      try { inflightControllers.get(requestKey)?.abort(); } catch (_) {}
    }

    let lastError = null;
    let requestCancelled = false;
    const requestHandle = {
      abort() {
        requestCancelled = true;
        try { this.controller?.abort(); } catch (_) {}
      },
      controller: null,
    };

    if (requestKey) inflightControllers.set(requestKey, requestHandle);

    try {
      const candidates = Array.isArray(baseCandidates) && baseCandidates.length
        ? unique(baseCandidates)
        : getApiCandidates();

      for (const base of candidates) {
        if (requestCancelled) break;
        const candidateUrl = withFallbackApiBase(url, base);
        const controller = new AbortController();
        requestHandle.controller = controller;
        let timedOut = false;
        const timer = window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, Math.max(1000, Number(timeoutMs || 8000)));

        try {
          const response = await fetch(candidateUrl, {
            cache: 'no-store',
            ...fetchOptions,
            headers,
            signal: controller.signal,
          });
          window.clearTimeout(timer);

          if (response.status === 204) return null;

          const text = await response.text();
          let payload = null;
          try {
            payload = text ? JSON.parse(text) : null;
          } catch (_) {
            payload = null;
          }

          const contentType = response.headers.get('content-type') || '';
          if (response.ok && isApiRequest(url) && payload == null && !contentType.includes('application/json')) {
            throw new Error(`Non-JSON API response from ${candidateUrl}`);
          }

          if (!response.ok) {
            const detailText = normalizeApiErrorDetail(payload?.detail || payload?.message || text || response.statusText || 'API error');
            const httpError = new Error(`HTTP ${response.status} ${response.statusText}${detailText ? ' - ' + detailText : ''}`);
            if (payload != null || contentType.includes('application/json')) {
              httpError.stopFallback = true;
            }
            throw httpError;
          }

          if (method === 'GET') {
            setCachedApiResponse(cacheKey, Number(cacheTtlMs || 0), payload, persistCache);
          }
          return payload;
        } catch (error) {
          window.clearTimeout(timer);
          if (error?.stopFallback) throw error;
          if (error?.name === 'AbortError' && !timedOut) {
            const abortError = new Error('__REQUEST_ABORTED__');
            abortError.name = 'AbortError';
            lastError = abortError;
            break;
          }
          lastError = timedOut
            ? new Error('Сервер отвечает слишком долго. Нажмите "Повторить" через несколько секунд.')
            : error;
        } finally {
          window.clearTimeout(timer);
          if (requestHandle.controller === controller) requestHandle.controller = null;
        }
      }
    } finally {
      if (requestKey && inflightControllers.get(requestKey) === requestHandle) {
        inflightControllers.delete(requestKey);
      }
    }

    throw lastError || new Error('API недоступен');
  }

  async function apiPostJson(url, payload, options = {}) {
    const hasPayload = payload !== undefined;
    return apiJson(url, {
      ...options,
      method: options.method || 'POST',
      headers: {
        ...(hasPayload ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
      body: hasPayload ? JSON.stringify(payload || {}) : undefined,
    });
  }

  function buildQuery(params = {}) {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      qs.set(key, String(value));
    });
    return qs.toString();
  }

  function endpoint(path) {
    return path.startsWith('/') ? path : `/${path}`;
  }

  const endpoints = {
    auth: {
      apiCredentials: endpoint('/api/payme/auth/api-credentials'),
      phone: endpoint('/api/payme/auth/phone'),
      code: endpoint('/api/payme/auth/code'),
      password: endpoint('/api/payme/auth/password'),
      reauthorize: endpoint('/api/payme/auth/reauthorize'),
      logout: endpoint('/api/payme/auth/logout'),
    },
    dashboard: {
      summary: endpoint('/api/payme/dashboard/summary'),
      runtimeStatus: endpoint('/api/payme/runtime-status'),
      serverStatus: endpoint('/api/payme/server-status'),
      systemMetrics: endpoint('/api/payme/system-metrics'),
    },
    leads: {
      list: endpoint('/api/payme/leads'),
      reloadSource: endpoint('/api/payme/source/reload'),
      addSource: endpoint('/api/payme/source/add'),
      removeSource: endpoint('/api/payme/source/remove'),
      activate: endpoint('/api/payme/leads/activate'),
      deactivate: endpoint('/api/payme/leads/deactivate'),
      delete: endpoint('/api/payme/leads/delete'),
      group: endpoint('/api/payme/leads/group'),
    },
    contacts: {
      list: endpoint('/api/payme/contacts'),
      chats: endpoint('/api/payme/contacts/chats'),
      status: endpoint('/api/payme/contacts/status'),
      refresh: endpoint('/api/payme/contacts/refresh'),
      config: endpoint('/api/payme/contacts/config'),
      qualificationPrompts: endpoint('/api/payme/contacts/qualification-prompts'),
    },
    crm: {
      contacts: endpoint('/api/payme/crm/contacts'),
      status: endpoint('/api/payme/crm/status'),
      refresh: endpoint('/api/payme/crm/refresh'),
      config: endpoint('/api/payme/crm/config'),
    },
    import: {
      dialogs: endpoint('/api/payme/telegram/dialogs'),
      dialogsImport: endpoint('/api/payme/telegram/dialogs/import'),
      dialogsSettings: endpoint('/api/payme/telegram/dialogs/settings'),
      removeAdded: endpoint('/api/payme/telegram/dialogs/remove-added'),
      syncStatus: endpoint('/api/payme/import-sync/status'),
      syncEnable: endpoint('/api/payme/import-sync/enable'),
      syncDisable: endpoint('/api/payme/import-sync/disable'),
    },
    media: {
      config: endpoint('/api/payme/media/config'),
      status: endpoint('/api/payme/media/status'),
      add: endpoint('/api/payme/media/add'),
      addMany: endpoint('/api/payme/media/add-many'),
      remove: endpoint('/api/payme/media/remove'),
      clear: endpoint('/api/payme/media/clear'),
      clearAll: endpoint('/api/payme/media/clear-all'),
      images: endpoint('/api/payme/images'),
      imageText: endpoint('/api/payme/images/text'),
      ocrPending: endpoint('/api/payme/images/ocr-pending'),
    },
    outreach: {
      items: endpoint('/api/payme/outreach/items'),
      sequences: endpoint('/api/payme/outreach/sequences'),
    },
    events: {
      keywords: endpoint('/api/payme/event-keywords'),
      messages: endpoint('/api/payme/event-messages'),
      messagesDelete: endpoint('/api/payme/event-messages/delete'),
      status: endpoint('/api/payme/events/status'),
      refresh: endpoint('/api/payme/events/refresh'),
      config: endpoint('/api/payme/events/config'),
    },
    jurEntities: {
      list: endpoint('/api/payme/jur-entities'),
      sync: endpoint('/api/payme/jur-entities/sync'),
      parserAdd: endpoint('/api/payme/jur-entities/parser-add'),
      parserRemove: endpoint('/api/payme/jur-entities/parser-remove'),
    },
    settings: endpoint('/api/payme/settings'),
    realtimeStream: endpoint('/api/payme/stream/realtime'),
    monitorStream: endpoint('/api/payme/monitor/stream'),
    allLeadsStream: endpoint('/api/payme/stream/leads'),
    runtimeLogs: endpoint('/api/payme/runtime-logs'),
    license: {
      status: endpoint('/api/payme/license/status'),
      menus: endpoint('/api/payme/license/menus'),
      activate: endpoint('/api/payme/license/activate'),
      emailImport: endpoint('/api/payme/license/email/import'),
    },
  };

  const candidates = getApiCandidates();
  window.API_BASE = window.API_BASE || candidates[0] || '';
  window.API_BASE_CANDIDATES = window.API_BASE_CANDIDATES || candidates;
  window.BackfrontApi = {
    endpoints,
    get base() {
      return getApiCandidates()[0] || '';
    },
    get candidates() {
      return getApiCandidates();
    },
    getApiCandidates,
    withFallbackApiBase,
    apiJson,
    apiPostJson,
    buildQuery,
    normalizeApiErrorDetail,
  };
})();
