'use strict';

function initApp() {
  const browserHost = window.location.hostname || '127.0.0.1';
  const isLocalBrowserHost = ['localhost', '127.0.0.1', '::1', '[::1]'].includes(browserHost);
  const apiProtocol = (window.location.protocol === 'http:' || window.location.protocol === 'https:')
    ? window.location.protocol
    : 'http:';
  const explicitApiBase = String(window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL || '').trim().replace(/\/$/, '');
  const pageOrigin = explicitApiBase || ((window.location.origin && window.location.origin !== 'null')
    ? window.location.origin
    : `${apiProtocol}//${browserHost}${window.location.port ? ':' + window.location.port : ''}`);
  const API_BASE = pageOrigin;
  const API_BASE_CANDIDATES = [
    API_BASE,
  ];
  if (isLocalBrowserHost || window.location.protocol === 'file:') {
    const splitBackendPort = String(window.XFILES_BACKEND_PORT || '8009').trim();
    const legacyBackendPort = String(window.XFILES_LEGACY_BACKEND_PORT || '8001').trim();
    if (splitBackendPort) {
      API_BASE_CANDIDATES.push(
        `${apiProtocol}//${browserHost}:${splitBackendPort}`,
        `${apiProtocol}//127.0.0.1:${splitBackendPort}`,
        `${apiProtocol}//localhost:${splitBackendPort}`,
      );
    }
    API_BASE_CANDIDATES.push(
      `${apiProtocol}//${browserHost}:${legacyBackendPort}`,
      `${apiProtocol}//127.0.0.1:${legacyBackendPort}`,
      `${apiProtocol}//localhost:${legacyBackendPort}`,
    );
  }
  const API_BASE_CANDIDATES_UNIQUE = Array.from(new Set(API_BASE_CANDIDATES));
  const PAYME_API = `${API_BASE}/api/payme`;
  const U = path => `${PAYME_API}${path}`;
  const URL_LIST_LEADS = U('/leads');
  const URL_SOURCE_STATS = U('/source-stats');
  const URL_RELOAD_SOURCE = U('/source/reload');
  const URL_ADD_SOURCE = U('/source/add');
  const URL_REMOVE_SOURCE = U('/source/remove');
  const URL_ACTIVATE_LEAD = U('/leads/activate');
  const URL_DEACTIVATE_LEAD = U('/leads/deactivate');
  const URL_DELETE_LEAD = U('/leads/delete');
  const URL_LEAD_GROUP = U('/leads/group');
  const URL_RUNTIME_STATUS = U('/runtime-status');
  const URL_MONITOR_STREAM = U('/monitor/stream');
  const URL_ALL_LEADS_STREAM = U('/stream/leads');
  const URL_REALTIME_STREAM = U('/stream/realtime');
  const URL_TELEGRAM_DIALOGS = U('/telegram/dialogs');
  const URL_TELEGRAM_DIALOGS_IMPORT = U('/telegram/dialogs/import');
  const URL_TELEGRAM_DIALOGS_SETTINGS = U('/telegram/dialogs/settings');
  const URL_TELEGRAM_DIALOGS_REMOVE_ADDED = U('/telegram/dialogs/remove-added');
  const URL_SETTINGS = U('/settings');
  const URL_IMAGES = U('/images');
  const URL_IMAGE_TEXT = U('/images/text');
  const URL_IMAGES_OCR_PENDING = U('/images/ocr-pending');
  const URL_MEDIA_CONFIG = U('/media/config');
  const URL_MEDIA_STATUS = U('/media/status');
  const URL_MEDIA_ADD = U('/media/add');
  const URL_MEDIA_ADD_MANY = U('/media/add-many');
  const URL_MEDIA_REMOVE = U('/media/remove');
  const URL_MEDIA_CLEAR = U('/media/clear');
  const URL_MEDIA_CLEAR_ALL = U('/media/clear-all');
  const URL_JUR_ENTITIES = U('/jur-entities');
  const URL_JUR_ENTITIES_SYNC = U('/jur-entities/sync');
  const URL_JUR_ENTITIES_PARSER_ADD = U('/jur-entities/parser-add');
  const URL_JUR_ENTITIES_PARSER_REMOVE = U('/jur-entities/parser-remove');
  const URL_CONTACTS = U('/contacts');
  const URL_CONTACTS_CHATS = U('/contacts/chats');
  const URL_CONTACTS_STATUS = U('/contacts/status');
  const URL_CONTACTS_REFRESH = U('/contacts/refresh');
  const URL_CONTACTS_CONFIG = U('/contacts/config');
  const URL_CONTACTS_QUALIFICATION_PROMPTS = U('/contacts/qualification-prompts');
  const URL_CRM_CONTACTS = U('/crm/contacts');
  const URL_CRM_STATUS = U('/crm/status');
  const URL_CRM_REFRESH = U('/crm/refresh');
  const URL_CRM_CONFIG = U('/crm/config');
  const URL_OUTREACH_ITEMS = U('/outreach/items');
  const URL_OUTREACH_SEQUENCES = U('/outreach/sequences');
  const URL_EVENT_KEYWORDS = U('/event-keywords');
  const URL_EVENT_MESSAGES = U('/event-messages');
  const URL_EVENT_MESSAGES_DELETE = U('/event-messages/delete');
  const URL_EVENTS_STATUS = U('/events/status');
  const URL_EVENTS_REFRESH = U('/events/refresh');
  const URL_EVENTS_CONFIG = U('/events/config');
  const URL_IMPORT_SYNC_STATUS = U('/import-sync/status');
  const URL_IMPORT_SYNC_ENABLE = U('/import-sync/enable');
  const URL_IMPORT_SYNC_DISABLE = U('/import-sync/disable');
  const URL_TELEGRAM_SYNC_JOB = U('/telegram-sync/job');
  const URL_TELEGRAM_SYNC_RUN = U('/telegram-sync/run');
  const URL_TELEGRAM_SYNC_CONTROL = U('/telegram-sync/control');
  const URL_TELEGRAM_SYNC_PAUSE = U('/telegram-sync/pause');
  const URL_TELEGRAM_SYNC_RESUME = U('/telegram-sync/resume');
  const URL_AUTH_API_CREDENTIALS = U('/auth/api-credentials');
  const URL_AUTH_PHONE = U('/auth/phone');
  const URL_AUTH_CODE = U('/auth/code');
  const URL_AUTH_PASSWORD = U('/auth/password');
  const URL_AUTH_REAUTHORIZE = U('/auth/reauthorize');
  const URL_AUTH_LOGOUT = U('/auth/logout');
  const _apiInflightControllers = new Map();
  const _apiResponseCache = new Map();

  function fmtDate(input, withSeconds = false) {
    if (input == null || input === '') return '';
    let d = null;
    if (typeof input === 'number') {
      d = new Date(input < 1e12 ? input * 1000 : input);
    } else {
      d = new Date(input);
    }
    if (isNaN(d)) return String(input);

    const pad = n => String(n).padStart(2, '0');
    const yyyy = d.getFullYear();
    const MM   = pad(d.getMonth() + 1);
    const dd   = pad(d.getDate());
    const HH   = pad(d.getHours());
    const mm   = pad(d.getMinutes());
    const ss   = pad(d.getSeconds());

    return withSeconds
      ? `${yyyy}-${MM}-${dd} ${HH}:${mm}:${ss}`
      : `${yyyy}-${MM}-${dd} ${HH}:${mm}`;
  }

  window.fmtDate = fmtDate;

  function confirmLongRebuild(title, details) {
    const header = String(title || 'Тяжёлая операция').trim();
    const body = String(details || 'Операция может запустить долгий фоновой пересчёт и нагрузить backend.').trim();
    const message = `${header}\n\n${body}\n\nПродолжить?`;
    if (typeof window.confirm !== 'function') return true;
    return window.confirm(message);
  }

  window.confirmLongRebuild = confirmLongRebuild;

  const statusPanel = window.BackfrontStatusPanel || {};
  const escapeHtmlText = statusPanel.escapeHtmlText || ((value) => String(value == null ? '' : value));
  const statusBadgeClassByTone = statusPanel.statusBadgeClassByTone || (() => 'badge-archived');
  const statusBadgeTextByTone = statusPanel.statusBadgeTextByTone || (() => 'ожидание');
  const statusProgressPercent = statusPanel.statusProgressPercent || ((status) => Math.max(0, Math.min(100, Number(status?.progress_percent || 0))));
  const statusProgressLabel = statusPanel.statusProgressLabel || ((status, fallbackRunning = 'Идёт обработка', fallbackIdle = 'Ожидание') => status?.progress_label || (status?.running ? fallbackRunning : fallbackIdle));
  const statusProgressCounterLabel = statusPanel.statusProgressCounterLabel || (() => '—');
  const statusProgressLogEntries = statusPanel.statusProgressLogEntries || ((status) => Array.isArray(status?.progress_log) ? status.progress_log : []);
  const renderUnifiedStatusPanel = statusPanel.renderUnifiedStatusPanel || (() => '');

  function withFallbackApiBase(url, base) {
    try {
      const original = new URL(url, window.location.href);
      const fallbackBase = new URL(base);
      original.protocol = fallbackBase.protocol;
      original.hostname = fallbackBase.hostname;
      original.port = fallbackBase.port;
      return original.toString();
    } catch {
      return url;
    }
  }

  function cloneJsonSafe(value) {
    if (typeof window.structuredClone === 'function') {
      return window.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  const PAGE_UI_STATE_KEY_PREFIX = 'xfiles.page-ui.';

  function persistedUiStorageKey(key) {
    return `${PAGE_UI_STATE_KEY_PREFIX}${String(key || 'page')}`;
  }

  function coercePersistedUiValue(value, fallback) {
    if (typeof fallback === 'boolean') return Boolean(value);
    if (typeof fallback === 'number') {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : fallback;
    }
    if (typeof fallback === 'string') return String(value ?? fallback);
    return value ?? fallback;
  }

  function isSafePersistedUiField(field) {
    return !/^(leads|dialogs|messages|items|rows|cache|history)$/i.test(String(field || '').trim());
  }

  function createPersistedUiState(key, defaults = {}, fields = []) {
    const base = { ...(defaults || {}) };
    try {
      const raw = window.localStorage?.getItem(persistedUiStorageKey(key));
      const parsed = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return base;
      for (const field of fields || []) {
        if (!isSafePersistedUiField(field)) continue;
        if (!Object.prototype.hasOwnProperty.call(base, field)) continue;
        if (!Object.prototype.hasOwnProperty.call(parsed, field)) continue;
        base[field] = coercePersistedUiValue(parsed[field], base[field]);
      }
    } catch (_) {}
    return base;
  }

  function persistUiState(key, ui = {}, fields = []) {
    try {
      const payload = {};
      for (const field of fields || []) {
        if (!isSafePersistedUiField(field)) continue;
        if (Object.prototype.hasOwnProperty.call(ui || {}, field)) {
          payload[field] = ui[field];
        }
      }
      window.localStorage?.setItem(persistedUiStorageKey(key), JSON.stringify(payload));
    } catch (_) {}
  }

  function makeRequestCacheKey(scope, params = {}) {
    return `${String(scope || 'request')}:${buildQuery(params || {})}`;
  }

  const PAGED_API_LOCAL_CACHE_KEY = 'xfiles.paged-api-cache.v1';

  function readPagedApiCacheStore() {
    try {
      const raw = window.localStorage?.getItem(PAGED_API_LOCAL_CACHE_KEY);
      if (!raw) return {};
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    } catch (_) {
      return {};
    }
  }

  function writePagedApiCacheStore(store) {
    try {
      window.localStorage?.setItem(PAGED_API_LOCAL_CACHE_KEY, JSON.stringify(store || {}));
    } catch (_) {}
  }

  function getPersistentApiResponse(cacheKey) {
    if (!cacheKey) return null;
    const store = readPagedApiCacheStore();
    const entry = store[cacheKey];
    if (!entry?.value) return null;
    try {
      const value = cloneJsonSafe(entry.value);
      if (value && typeof value === 'object') {
        value.__from_persistent_cache = true;
        value.__cached_at = entry.cachedAt || '';
      }
      return value;
    } catch (_) {
      delete store[cacheKey];
      writePagedApiCacheStore(store);
      return null;
    }
  }

  function setPersistentApiResponse(cacheKey, value, maxEntries = 90) {
    if (!cacheKey || !value || typeof value !== 'object') return;
    const store = readPagedApiCacheStore();
    store[cacheKey] = {
      cachedAt: new Date().toISOString(),
      value: cloneJsonSafe(value),
    };
    const sorted = Object.entries(store)
      .sort((a, b) => String(b[1]?.cachedAt || '').localeCompare(String(a[1]?.cachedAt || '')))
      .slice(0, Math.max(10, Number(maxEntries || 90)));
    writePagedApiCacheStore(Object.fromEntries(sorted));
  }

  function getCachedApiResponse(cacheKey, cacheTtlMs, persistCache = false) {
    if (!cacheKey || !(cacheTtlMs > 0)) return null;
    const cached = _apiResponseCache.get(cacheKey);
    if (!cached) return persistCache ? getPersistentApiResponse(cacheKey) : null;
    if (Date.now() > Number(cached.expiresAt || 0)) {
      _apiResponseCache.delete(cacheKey);
      return persistCache ? getPersistentApiResponse(cacheKey) : null;
    }
    try {
      return cloneJsonSafe(cached.value);
    } catch (_) {
      _apiResponseCache.delete(cacheKey);
      return null;
    }
  }

  function setCachedApiResponse(cacheKey, cacheTtlMs, value, persistCache = false) {
    if (!cacheKey || !(cacheTtlMs > 0)) return;
    _apiResponseCache.set(cacheKey, {
      expiresAt: Date.now() + Number(cacheTtlMs || 0),
      value: cloneJsonSafe(value),
    });
    if (persistCache) setPersistentApiResponse(cacheKey, value);
  }

  function clearCachedApiResponse(cacheKey) {
    if (cacheKey) _apiResponseCache.delete(cacheKey);
  }

  function clearPagedApiResponsesByPrefixes(prefixes = []) {
    const normalized = (Array.isArray(prefixes) ? prefixes : [prefixes])
      .map((item) => String(item || '').trim())
      .filter(Boolean);
    if (!normalized.length) return;
    try {
      for (const key of Array.from(_apiResponseCache.keys())) {
        if (normalized.some((prefix) => String(key).startsWith(prefix))) {
          _apiResponseCache.delete(key);
        }
      }
    } catch (_) {}
    try {
      const store = readPagedApiCacheStore();
      let changed = false;
      for (const key of Object.keys(store || {})) {
        if (normalized.some((prefix) => String(key).startsWith(prefix))) {
          delete store[key];
          changed = true;
        }
      }
      if (changed) writePagedApiCacheStore(store);
    } catch (_) {}
  }

  const IMPORT_DIALOGS_LOCAL_CACHE_KEY = 'gramlead.import.dialogs.cache.v3';
  const IMPORT_DIALOGS_LEGACY_CACHE_KEYS = ['gramlead.import.dialogs.cache.v1'];

  function importDialogsCacheParams(params = {}) {
    return {
      page: Number(params.page || 1),
      page_size: Number(params.page_size || 5),
      query: String(params.query || '').trim(),
      show_channels: params.show_channels !== false,
      show_groups: params.show_groups !== false,
      show_private: params.show_private !== false,
      show_bots: params.show_bots !== false,
      show_archived: !!params.show_archived,
      membership_filter: String(params.membership_filter || 'all'),
      sort_by: String(params.sort_by || 'last_date_desc'),
      force_refresh: !!params.force_refresh,
    };
  }

  function importDialogsCacheKey(params = {}) {
    return makeRequestCacheKey('import:dialogs:local', importDialogsCacheParams(params));
  }

  function readImportDialogsCacheStore() {
    try {
      const raw = window.localStorage?.getItem(IMPORT_DIALOGS_LOCAL_CACHE_KEY);
      if (!raw) return { entries: {}, lastKey: '' };
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return { entries: {}, lastKey: '' };
      return {
        entries: parsed.entries && typeof parsed.entries === 'object' ? parsed.entries : {},
        lastKey: String(parsed.lastKey || ''),
      };
    } catch (_) {
      return { entries: {}, lastKey: '' };
    }
  }

  function writeImportDialogsCacheStore(store) {
    try {
      window.localStorage?.setItem(IMPORT_DIALOGS_LOCAL_CACHE_KEY, JSON.stringify(store));
    } catch (_) {}
  }

  function clearImportDialogsLocalCache() {
    writeImportDialogsCacheStore({ entries: {}, lastKey: '' });
    try {
      for (const key of IMPORT_DIALOGS_LEGACY_CACHE_KEYS) {
        window.localStorage?.removeItem(key);
      }
    } catch (_) {}
  }

  function invalidateTelegramSourceCaches() {
    clearPagedApiResponsesByPrefixes(['chat:leads:', 'grid:leads:', 'import:dialogs:']);
    clearImportDialogsLocalCache();
  }

  function rememberImportDialogsResponse(params = {}, payload = null) {
    if (!payload || typeof payload !== 'object') return;
    const key = importDialogsCacheKey(params);
    const store = readImportDialogsCacheStore();
    const entries = store.entries || {};
    entries[key] = {
      cachedAt: new Date().toISOString(),
      params: importDialogsCacheParams(params),
      payload: cloneJsonSafe(payload),
    };

    const sorted = Object.entries(entries)
      .sort((a, b) => String(b[1]?.cachedAt || '').localeCompare(String(a[1]?.cachedAt || '')))
      .slice(0, 40);

    writeImportDialogsCacheStore({
      lastKey: key,
      entries: Object.fromEntries(sorted),
    });
  }

  function getImportDialogsCachedResponse(params = {}) {
    const store = readImportDialogsCacheStore();
    const key = importDialogsCacheKey(params);
    const exactEntry = store.entries?.[key] || null;
    if (!exactEntry) return null;
    const entry = exactEntry;
    if (!entry?.payload) return null;
    const payload = cloneJsonSafe(entry.payload);
    payload.__from_import_local_cache = true;
    payload.__cached_at = entry.cachedAt || '';
    payload.__cache_exact_match = Boolean(exactEntry);
    return payload;
  }

  function isTelegramCooldownError(error) {
    const raw = String(error?.message || error || '');
    return raw.includes('HTTP 429') || raw.includes('Telegram cooldown активен') || raw.includes('FLOOD_WAIT');
  }

  function describeTelegramCooldownError(error) {
    const raw = String(error?.message || error || '');
    const isoMatch = raw.match(/до\s+([0-9T:\-+.]+(?:Z|[+-][0-9:]+)?)/i);
    if (isoMatch?.[1]) {
      return `Telegram cooldown активен до ${isoMatch[1]}`;
    }
    return 'Telegram временно ограничил обновление списка диалогов';
  }

  function isObjectRecord(value) {
    return !!value && typeof value === 'object' && !Array.isArray(value);
  }

  function syncObjectInPlace(target, source) {
    if (!isObjectRecord(target) || !isObjectRecord(source)) return source;
    for (const key of Object.keys(target)) {
      if (!(key in source)) delete target[key];
    }
    for (const [key, value] of Object.entries(source)) {
      target[key] = value;
    }
    return target;
  }

  function reconcileKeyedCollection(previousItems, nextItems, getKey) {
    const prevList = Array.isArray(previousItems) ? previousItems : [];
    const nextList = Array.isArray(nextItems) ? nextItems : [];
    const keyFn = typeof getKey === 'function' ? getKey : (item) => item?.id;
    const prevByKey = new Map();

    for (const item of prevList) {
      const key = keyFn(item);
      if (key == null || key === '') continue;
      if (!prevByKey.has(key)) prevByKey.set(key, item);
    }

    return nextList.map((item) => {
      const key = keyFn(item);
      if (key == null || key === '') return item;
      const previous = prevByKey.get(key);
      if (!previous || previous === item) return item;
      if (!isObjectRecord(previous) || !isObjectRecord(item)) return item;
      return syncObjectInPlace(previous, item);
    });
  }

  function createBatchedQueueProcessor(config = {}) {
    const {
      delayMs = 250,
      maxBatchSize = 100,
      onFlush = () => {},
    } = config;

    let queue = [];
    let timer = null;

    const flush = () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (!queue.length) return;
      const batch = queue;
      queue = [];
      onFlush(batch);
    };

    const schedule = () => {
      if (timer) return;
      timer = setTimeout(flush, delayMs);
    };

    return {
      push(item) {
        queue.push(item);
        if (queue.length >= maxBatchSize) {
          flush();
          return;
        }
        schedule();
      },
      flush,
      clear() {
        queue = [];
        if (timer) {
          clearTimeout(timer);
          timer = null;
        }
      },
    };
  }

  function isAbortedRequestError(error) {
    return error?.name === 'AbortError' || String(error?.message || '') === '__REQUEST_ABORTED__';
  }

  function openEventSourceWithFallback(url, handlers = {}) {
    const {
      onOpen = () => {},
      onMessage = () => {},
      onError = () => {},
    } = handlers;
    let es = null;
    for (const base of API_BASE_CANDIDATES_UNIQUE) {
      try {
        const candidateUrl = withFallbackApiBase(url, base);
        es = new EventSource(candidateUrl);
        es.onopen = (event) => onOpen(event, candidateUrl, es);
        es.onmessage = (event) => onMessage(event, candidateUrl, es);
        es.onerror = (event) => onError(event, candidateUrl, es);
        es._resolvedUrl = candidateUrl;
        return es;
      } catch (_) {}
    }
    return null;
  }

  function startMonitorStreamConsumer(config = {}) {
    const {
      historyPoints = 60,
      onSnapshot = () => {},
      onError = () => {},
      onState = () => {},
    } = config;
    const client = window.BackfrontRealtime;
    if (!client?.startTypedRealtimeStreamConsumer) {
      onState({ state: 'error', url: '' });
      onError(new Error('typed realtime client unavailable'), '');
      return null;
    }
    return client.startTypedRealtimeStreamConsumer({
      baseUrl: URL_REALTIME_STREAM,
      baseCandidates: API_BASE_CANDIDATES_UNIQUE,
      types: ['monitor'],
      historyPoints,
      onState,
      onError,
      onEnvelope: (envelope, resolvedUrl) => {
        if (envelope?.type === 'monitor_snapshot' && envelope?.payload) {
          onSnapshot(envelope.payload, resolvedUrl);
        } else if (envelope?.type === 'stream_error' && envelope?.payload?.error) {
          onError(new Error(envelope.payload.error), resolvedUrl);
        }
      },
    });
  }

  function buildLeadLiveStreamUrl(leadName = '') {
    const client = window.BackfrontRealtime;
    if (client?.buildTypedRealtimeUrl) {
      return client.buildTypedRealtimeUrl(URL_REALTIME_STREAM, {
        types: ['lead'],
        lead: String(leadName || '').trim(),
      });
    }
    const name = String(leadName || '').trim();
    const params = new URLSearchParams({ types: 'lead' });
    if (name) params.set('lead', name);
    return `${URL_REALTIME_STREAM}?${params.toString()}`;
  }

  async function apiJson(url, options = {}) {
    if (window.BackfrontApi?.apiJson) {
      return window.BackfrontApi.apiJson(url, options);
    }

    const {
      timeoutMs = 8000,
      requestKey = '',
      cacheKey = '',
      cacheTtlMs = 0,
      persistCache = false,
      forceFresh = false,
      ...fetchOptions
    } = options;
    const headers = {
      'Accept': 'application/json',
      ...(fetchOptions.headers || {}),
    };
    const method = String(fetchOptions.method || 'GET').toUpperCase();

    if (method === 'GET' && !forceFresh) {
      const cached = getCachedApiResponse(cacheKey, cacheTtlMs, persistCache);
      if (cached != null) return cached;
    }

    if (requestKey) {
      const previous = _apiInflightControllers.get(requestKey);
      if (previous) {
        try { previous.abort(); } catch (_) {}
      }
    }

    let lastError = null;
    let activeController = null;
    let requestCancelled = false;
    const requestHandle = {
      abort() {
        requestCancelled = true;
        if (activeController) {
          try { activeController.abort(); } catch (_) {}
        }
      },
    };
    if (requestKey) {
      _apiInflightControllers.set(requestKey, requestHandle);
    }
    try {
      for (const base of API_BASE_CANDIDATES_UNIQUE) {
        if (requestCancelled) break;
        const candidateUrl = withFallbackApiBase(url, base);
        let timedOut = false;
        const controller = new AbortController();
        activeController = controller;
        const timer = window.setTimeout(() => {
          timedOut = true;
          controller.abort();
        }, Math.max(1000, Number(timeoutMs || 8000)));
        try {
          const r = await fetch(candidateUrl, {
            ...fetchOptions,
            headers,
            signal: controller.signal,
          });
          window.clearTimeout(timer);
          const ct = r.headers.get('content-type') || '';
          if (!r.ok) {
            let txt = ''; try { txt = await r.text(); } catch {}
            let detail = txt;
            try {
              const payload = txt ? JSON.parse(txt) : null;
              detail = payload?.detail || payload?.message || txt;
            } catch {}
            const httpError = new Error(`HTTP ${r.status} ${r.statusText}${detail ? ' — ' + detail : ''}`);
            if (ct.includes('application/json')) httpError.stopFallback = true;
            throw httpError;
          }
          if (!ct.includes('application/json')) {
            if (r.status === 204) return null;
            throw new Error(`Ожидалась JSON, получено: ${ct || 'unknown'}`);
          }
          const payload = await r.json();
          if (method === 'GET') {
            setCachedApiResponse(cacheKey, cacheTtlMs, payload, persistCache);
          }
          return payload;
        } catch (error) {
          window.clearTimeout(timer);
          if (error?.stopFallback) throw error;
          if (error && error.name === 'AbortError') {
            if (timedOut) {
              lastError = new Error('Сервер отвечает слишком долго. Нажмите “Повторить” через несколько секунд.');
            } else {
              const abortError = new Error('__REQUEST_ABORTED__');
              abortError.name = 'AbortError';
              lastError = abortError;
              break;
            }
          } else {
            lastError = error;
          }
        } finally {
          window.clearTimeout(timer);
          if (activeController === controller) activeController = null;
        }
      }
    } finally {
      if (requestKey && _apiInflightControllers.get(requestKey) === requestHandle) {
        _apiInflightControllers.delete(requestKey);
      }
    }

    throw lastError || new Error('API недоступен');
  }

  function humanizeApiError(error, fallback = 'Не удалось загрузить данные') {
    const raw = String(error?.message || error || '').trim();
    if (!raw) return fallback;

    if (
      raw.includes('Failed to fetch') ||
      raw.includes('Load failed') ||
      raw.includes('NetworkError')
    ) {
      return `${fallback}: backend недоступен по адресу текущей страницы ${API_BASE}. Проверьте, что контейнер запущен, backend-порт опубликован и firewall не блокирует доступ.`;
    }

    if (raw.includes('HTTP 504')) {
      return `${fallback}: анализ занял слишком много времени. Попробуйте повторить запрос ещё раз через несколько секунд.`;
    }

    if (raw.includes('HTTP 502') || raw.includes('HTTP 503')) {
      return `${fallback}: LLM-провайдер временно не ответил или перегружен. Система уже делает повторные попытки; если ошибка осталась, нажмите «Повторить» через несколько секунд.`;
    }

    return raw;
  }

  function buildQuery(params = {}) {
    const qs = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      qs.set(key, String(value));
    });
    return qs.toString();
  }

  function buildPagedRequestOptions(scope, params = {}, options = {}) {
    return {
      requestKey: String(options.requestKey || `${scope}:rows`),
      cacheKey: makeRequestCacheKey(scope, params),
      cacheTtlMs: Number(options.cacheTtlMs || 4000),
      persistCache: options.persistCache !== false,
      forceFresh: !!options.forceFresh,
      timeoutMs: Number(options.timeoutMs || 8000),
    };
  }

  async function apiGetLeads(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_LIST_LEADS}?${qs}` : URL_LIST_LEADS, options);
  }

  async function apiGetSourceStats(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_SOURCE_STATS}?${qs}` : URL_SOURCE_STATS, options);
  }

  async function apiReloadSource() {
    return apiJson(URL_RELOAD_SOURCE, {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
    });
  }

  async function apiGetRuntimeStatus() {
    return apiJson(URL_RUNTIME_STATUS);
  }

  async function apiGetTelegramDialogs(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_TELEGRAM_DIALOGS}?${qs}` : URL_TELEGRAM_DIALOGS, { timeoutMs: 20000, ...options });
  }

  async function apiImportTelegramDialogs(selectors, options = {}) {
    return apiPostJson(URL_TELEGRAM_DIALOGS_IMPORT, { selectors }, options);
  }

  async function apiSaveTelegramDialogSettings(payload, options = {}) {
    return apiPostJson(URL_TELEGRAM_DIALOGS_SETTINGS, payload, options);
  }

  async function apiRemoveTelegramDialogsFromScan(selectors, options = {}) {
    return apiPostJson(URL_TELEGRAM_DIALOGS_REMOVE_ADDED, { selectors }, options);
  }

  async function apiGetAppSettings(options = {}) {
    return apiJson(URL_SETTINGS, options);
  }

  async function apiSaveAppSettings(payload, options = {}) {
    return apiPostJson(URL_SETTINGS, payload, options);
  }

  async function apiGetImages(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_IMAGES}?${qs}` : URL_IMAGES, options);
  }

  async function apiGetImageText(mediaPath, options = {}) {
    const qs = buildQuery({ media_path: mediaPath });
    return apiJson(qs ? `${URL_IMAGE_TEXT}?${qs}` : URL_IMAGE_TEXT, options);
  }

  async function apiRunPendingImageOcr() {
    return apiPostJson(URL_IMAGES_OCR_PENDING, {});
  }

  async function apiGetMediaConfig(options = {}) {
    return apiJson(URL_MEDIA_CONFIG, options);
  }

  async function apiGetMediaStatus(options = {}) {
    return apiJson(URL_MEDIA_STATUS, options);
  }

  async function apiAddMediaLead(lead) {
    return apiPostJson(URL_MEDIA_ADD, { lead });
  }

  async function apiAddManyMediaLeads(leads, options = {}) {
    return apiPostJson(URL_MEDIA_ADD_MANY, { leads }, options);
  }

  async function apiRemoveMediaLead(lead) {
    return apiPostJson(URL_MEDIA_REMOVE, { lead });
  }

  async function apiClearMediaLead(lead) {
    return apiPostJson(URL_MEDIA_CLEAR, { lead });
  }

  async function apiClearAllMedia() {
    return apiPostJson(URL_MEDIA_CLEAR_ALL, {});
  }

  async function apiGetJurEntities(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_JUR_ENTITIES}?${qs}` : URL_JUR_ENTITIES, options);
  }

  async function apiSyncJurEntities(options = {}) {
    return apiPostJson(URL_JUR_ENTITIES_SYNC, {}, options);
  }

  async function apiAddJurEntityToParser(fileKey) {
    return apiPostJson(URL_JUR_ENTITIES_PARSER_ADD, { file_key: fileKey });
  }

  async function apiRemoveJurEntityFromParser(fileKey) {
    return apiPostJson(URL_JUR_ENTITIES_PARSER_REMOVE, { file_key: fileKey });
  }

  async function apiGetTelegramContacts(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_CONTACTS}?${qs}` : URL_CONTACTS, options);
  }

  async function apiGetContactChatFilters(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_CONTACTS_CHATS}?${qs}` : URL_CONTACTS_CHATS, options);
  }

  async function apiGetTelegramContactMessages(contactKey, params = {}, options = {}) {
    const qs = buildQuery(params);
    const url = `${URL_CONTACTS}/${encodeURIComponent(contactKey)}/messages`;
    return apiJson(qs ? `${url}?${qs}` : url, options);
  }

  async function apiGetContactQualificationPrompts(options = {}) {
    return apiJson(URL_CONTACTS_QUALIFICATION_PROMPTS, options);
  }

  async function apiGetContactQualifications(contactKey, options = {}) {
    return apiJson(`${URL_CONTACTS}/${encodeURIComponent(contactKey)}/qualifications`, options);
  }

  async function apiQualifyContact(contactKey, templateId, options = {}) {
    const { force = false, ...requestOptions } = options || {};
    return apiPostJson(`${URL_CONTACTS}/${encodeURIComponent(contactKey)}/qualify`, {
      template_id: templateId,
      force: !!force,
    }, requestOptions);
  }

  async function apiSetContactDoNotContact(contactKey, payload = {}) {
    return apiPostJson(`${URL_CONTACTS}/${encodeURIComponent(contactKey)}/do-not-contact`, {
      enabled: !!payload.enabled,
      reason: String(payload.reason || '').trim(),
    });
  }

  async function apiGetContactsStatus(options = {}) {
    return apiJson(URL_CONTACTS_STATUS, options);
  }

  async function apiRefreshContacts() {
    return apiPostJson(URL_CONTACTS_REFRESH, {});
  }

  async function apiSetContactsConfig(payload) {
    return apiPostJson(URL_CONTACTS_CONFIG, payload);
  }

  async function apiGetCrmContacts(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_CRM_CONTACTS}?${qs}` : URL_CRM_CONTACTS, options);
  }

  async function apiGetCrmStatus(options = {}) {
    return apiJson(URL_CRM_STATUS, options);
  }

  async function apiRefreshCrm() {
    return apiPostJson(URL_CRM_REFRESH, {});
  }

  async function apiSetCrmConfig(payload) {
    return apiPostJson(URL_CRM_CONFIG, payload);
  }

  async function apiGetOutreachItems(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_OUTREACH_ITEMS}?${qs}` : URL_OUTREACH_ITEMS, options);
  }

  async function apiAddOutreachItem(payload) {
    return apiPostJson(URL_OUTREACH_ITEMS, payload);
  }

  async function apiDeleteOutreachItem(itemId) {
    return apiJson(`${URL_OUTREACH_ITEMS}/${encodeURIComponent(itemId)}`, {
      method: 'DELETE',
      headers: { 'Accept': 'application/json' },
    });
  }

  async function apiCreateOutreachSequenceFromEnreach(itemId) {
    return apiPostJson(`${URL_OUTREACH_SEQUENCES}/from-enreach/${encodeURIComponent(itemId)}`, {});
  }

  const outreachShared = window.BackfrontOutreach || {};
  const OUTREACH_FIELD_LABELS = outreachShared.OUTREACH_FIELD_LABELS || {};
  const normalizeOutreachFieldType = outreachShared.normalizeOutreachFieldType || (() => 'message');
  const outreachFieldLabel = outreachShared.outreachFieldLabel || (() => 'Сообщение');
  const normalizeOutreachPayload = outreachShared.normalizeOutreachPayload || ((payload = {}) => payload);
  const outreachPayloadKey = outreachShared.outreachPayloadKey || ((payload = {}) => JSON.stringify(payload));
  function createOutreachToggleState() {
    return outreachShared.createOutreachToggleState({
      apiGetOutreachItems,
      apiAddOutreachItem,
      apiDeleteOutreachItem,
      isAbortedRequestError,
      humanizeApiError,
      toast,
    });
  }

  async function apiDeactivateLead(payload) {
    return apiPostJson(URL_DEACTIVATE_LEAD, payload);
  }

  async function apiActivateLead(payload) {
    return apiPostJson(URL_ACTIVATE_LEAD, payload);
  }

  async function apiDeleteLead(payload) {
    return apiPostJson(URL_DELETE_LEAD, payload);
  }

  async function apiSetLeadGroup(payload) {
    return apiPostJson(URL_LEAD_GROUP, payload);
  }

  async function apiGetEventKeywords(options = {}) {
    return apiJson(URL_EVENT_KEYWORDS, options);
  }

  async function apiSetEventKeywords(keywords) {
    return apiPostJson(URL_EVENT_KEYWORDS, { keywords });
  }

  async function apiGetEventMessages(params = {}, options = {}) {
    const qs = buildQuery(params);
    return apiJson(qs ? `${URL_EVENT_MESSAGES}?${qs}` : URL_EVENT_MESSAGES, options);
  }

  async function apiDeleteEventMessage(payload, options = {}) {
    return apiPostJson(URL_EVENT_MESSAGES_DELETE, payload, options);
  }

  async function apiGetEventsStatus(options = {}) {
    return apiJson(URL_EVENTS_STATUS, options);
  }

  async function apiRefreshEvents() {
    return apiPostJson(URL_EVENTS_REFRESH, {});
  }

  async function apiSetEventsConfig(payload) {
    return apiPostJson(URL_EVENTS_CONFIG, payload);
  }

  async function apiGetImportSyncStatus(options = {}) {
    return apiJson(URL_IMPORT_SYNC_STATUS, options);
  }

  async function apiEnableImportSync() {
    return apiPostJson(URL_IMPORT_SYNC_ENABLE, {});
  }

  async function apiDisableImportSync() {
    return apiPostJson(URL_IMPORT_SYNC_DISABLE, {});
  }

  async function apiGetTelegramSyncJob(options = {}) {
    return apiJson(URL_TELEGRAM_SYNC_JOB, options);
  }

  async function apiGetTelegramSyncControl(options = {}) {
    return apiJson(URL_TELEGRAM_SYNC_CONTROL, options);
  }

  async function apiPauseTelegramSync(reason = 'manual-sync-page', options = {}) {
    const qs = buildQuery({ reason });
    return apiPostJson(`${URL_TELEGRAM_SYNC_PAUSE}?${qs}`, {}, options);
  }

  async function apiResumeTelegramSync(reason = 'manual-sync-page', options = {}) {
    const qs = buildQuery({ reason });
    return apiPostJson(`${URL_TELEGRAM_SYNC_RESUME}?${qs}`, {}, options);
  }

  async function apiRunTelegramSync(reason = 'manual', options = {}) {
    const qs = buildQuery({ reason });
    return apiPostJson(qs ? `${URL_TELEGRAM_SYNC_RUN}?${qs}` : URL_TELEGRAM_SYNC_RUN, {}, options);
  }

  async function apiPostJson(url, payload, options = {}) {
    return apiJson(url, {
      ...options,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      body: JSON.stringify(payload),
    });
  }

  window.BackfrontActions = window.BackfrontActions || {};

  function clearFrontendRuntimeState() {
    try {
      const exactKeys = new Set([
        'xfiles.currentLead',
        'leadApp.currentLead',
        'leadApp.lastLead',
        'xfiles.chat.current',
      ]);
      const prefixes = [
        'leadApp.',
        'gridApp.',
        'importApp.',
        'chatAnalysis.',
        PAGE_UI_STATE_KEY_PREFIX,
        'xfiles.chat',
        'xfiles.leads',
      ];
      [window.localStorage, window.sessionStorage].forEach((storage) => {
        if (!storage) return;
        Object.keys(storage).forEach((key) => {
          if (exactKeys.has(key) || prefixes.some((prefix) => key.startsWith(prefix))) {
            storage.removeItem(key);
          }
        });
      });
    } catch (_) {
      // Best-effort cleanup: backend reset remains authoritative.
    }
  }

  window.BackfrontClearRuntimeState = clearFrontendRuntimeState;

  window.BackfrontActions.reauthorizeTelegram = async function reauthorizeTelegramFromMenu() {
    if (!window.confirm('Сбросить текущую Telegram-сессию и пройти авторизацию заново?')) return;
    try {
      const result = await apiPostJson(URL_AUTH_REAUTHORIZE, {}, { timeoutMs: 30000 });
      clearFrontendRuntimeState();
      toast(result?.message || 'Telegram-сессия сброшена. Открою мастер настройки.', 'log');
      window.location.href = '/setup_wizard.html';
    } catch (e) {
      toast(humanizeApiError(e, 'Не удалось запустить переавторизацию Telegram'), 'error');
    }
  };

  window.BackfrontActions.logoutTelegram = async function logoutTelegramFromMenu() {
    if (!window.confirm('Выйти из Telegram и удалить сохранённую авторизацию?')) return;
    try {
      const result = await apiPostJson(URL_AUTH_LOGOUT, {}, { timeoutMs: 30000 });
      clearFrontendRuntimeState();
      toast(result?.message || 'Telegram-сессия удалена. Открою мастер настройки.', 'log');
      window.location.href = '/setup_wizard.html';
    } catch (e) {
      toast(humanizeApiError(e, 'Не удалось выйти из Telegram'), 'error');
    }
  };

  async function apiGetMessages(lead, offset = 0, limit = 0) {
    const qs = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    const url = `${PAYME_API}/leads/${encodeURIComponent(lead)}/messages?${qs}`;
    return apiJson(url);
  }

  async function apiGetChatAnalysisStats(lead) {
    const url = `${PAYME_API}/leads/${encodeURIComponent(lead)}/analysis/stats`;
    return apiJson(url, { timeoutMs: 15000, requestKey: `chat-analysis-stats:${lead}`, forceFresh: true });
  }

  async function apiGetChatAnalysisHistory(lead) {
    const url = `${PAYME_API}/leads/${encodeURIComponent(lead)}/analysis/history`;
    return apiJson(url, { timeoutMs: 15000, requestKey: `chat-analysis-history:${lead}`, forceFresh: true });
  }

  async function apiRunChatAnalysis(lead, payload) {
    const url = `${PAYME_API}/leads/${encodeURIComponent(lead)}/analysis/run`;
    return apiPostJson(url, payload, { timeoutMs: 305000, requestKey: `chat-analysis-run:${lead}`, forceFresh: true });
  }

  function toast(msg, kind = 'error') {
    console[kind === 'error' ? 'error' : 'log'](msg);
    let el = document.createElement('div');
    el.textContent = msg;
    Object.assign(el.style, {
      position: 'fixed',
      zIndex: 9999,
      left: '50%',
      top: '24px',
      transform: 'translateX(-50%)',
      padding: '10px 14px',
      borderRadius: '10px',
      boxShadow: '0 6px 18px rgba(0,0,0,.15)',
      background: kind === 'error' ? '#fee2e2' : '#e0f2fe',
      color: '#111827',
      fontSize: '14px',
      maxWidth: '80vw',
      whiteSpace: 'pre-wrap',
    });
    document.body.appendChild(el);
    setTimeout(() => { el.style.transition = 'opacity .25s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 250); }, 2000);
  }

  function scrollToBottomNow(el) { if (el) el.scrollTop = el.scrollHeight; }

  function scrollToBottomSmooth(el) {
    if (!el) return;
    let ticks = 4;
    function step(){ scrollToBottomNow(el); if(--ticks>0) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }

  window.BackfrontLegacy = {
    API_BASE,
    API_BASE_CANDIDATES,
    API_BASE_CANDIDATES_UNIQUE,
    URL_LIST_LEADS,
    URL_RELOAD_SOURCE,
    URL_ADD_SOURCE,
    URL_REMOVE_SOURCE,
    URL_ACTIVATE_LEAD,
    URL_DEACTIVATE_LEAD,
    URL_DELETE_LEAD,
    URL_LEAD_GROUP,
    URL_RUNTIME_STATUS,
    URL_MONITOR_STREAM,
    URL_ALL_LEADS_STREAM,
    URL_REALTIME_STREAM,
    URL_TELEGRAM_DIALOGS,
    URL_TELEGRAM_DIALOGS_IMPORT,
    URL_TELEGRAM_DIALOGS_SETTINGS,
    URL_TELEGRAM_DIALOGS_REMOVE_ADDED,
    URL_SETTINGS,
    URL_IMAGES,
    URL_IMAGE_TEXT,
    URL_IMAGES_OCR_PENDING,
    URL_MEDIA_CONFIG,
    URL_MEDIA_STATUS,
    URL_MEDIA_ADD,
    URL_MEDIA_ADD_MANY,
    URL_MEDIA_REMOVE,
    URL_MEDIA_CLEAR,
    URL_MEDIA_CLEAR_ALL,
    URL_JUR_ENTITIES,
    URL_JUR_ENTITIES_SYNC,
    URL_JUR_ENTITIES_PARSER_ADD,
    URL_JUR_ENTITIES_PARSER_REMOVE,
    URL_CONTACTS,
    URL_CONTACTS_CHATS,
    URL_CONTACTS_STATUS,
    URL_CONTACTS_REFRESH,
    URL_CONTACTS_CONFIG,
    URL_CONTACTS_QUALIFICATION_PROMPTS,
    URL_CRM_CONTACTS,
    URL_CRM_STATUS,
    URL_CRM_REFRESH,
    URL_CRM_CONFIG,
    URL_OUTREACH_ITEMS,
    URL_OUTREACH_SEQUENCES,
    URL_EVENT_KEYWORDS,
    URL_EVENT_MESSAGES,
    URL_EVENT_MESSAGES_DELETE,
    URL_EVENTS_STATUS,
    URL_EVENTS_REFRESH,
    URL_EVENTS_CONFIG,
    URL_IMPORT_SYNC_STATUS,
    URL_IMPORT_SYNC_ENABLE,
    URL_IMPORT_SYNC_DISABLE,
    URL_TELEGRAM_SYNC_JOB,
    URL_TELEGRAM_SYNC_RUN,
    URL_TELEGRAM_SYNC_CONTROL,
    URL_TELEGRAM_SYNC_PAUSE,
    URL_TELEGRAM_SYNC_RESUME,
    URL_AUTH_API_CREDENTIALS,
    URL_AUTH_PHONE,
    URL_AUTH_CODE,
    URL_AUTH_PASSWORD,
    URL_AUTH_REAUTHORIZE,
    URL_AUTH_LOGOUT,
    _apiInflightControllers,
    _apiResponseCache,
    fmtDate,
    confirmLongRebuild,
    escapeHtmlText,
    statusBadgeClassByTone,
    statusBadgeTextByTone,
    statusProgressPercent,
    statusProgressLabel,
    statusProgressCounterLabel,
    statusProgressLogEntries,
    renderUnifiedStatusPanel,
    withFallbackApiBase,
    cloneJsonSafe,
    createPersistedUiState,
    persistUiState,
    makeRequestCacheKey,
    PAGED_API_LOCAL_CACHE_KEY,
    readPagedApiCacheStore,
    writePagedApiCacheStore,
    getPersistentApiResponse,
    setPersistentApiResponse,
    getCachedApiResponse,
    setCachedApiResponse,
    clearCachedApiResponse,
    clearPagedApiResponsesByPrefixes,
    IMPORT_DIALOGS_LOCAL_CACHE_KEY,
    importDialogsCacheParams,
    importDialogsCacheKey,
    readImportDialogsCacheStore,
    writeImportDialogsCacheStore,
    clearImportDialogsLocalCache,
    invalidateTelegramSourceCaches,
    rememberImportDialogsResponse,
    getImportDialogsCachedResponse,
    isTelegramCooldownError,
    describeTelegramCooldownError,
    isObjectRecord,
    syncObjectInPlace,
    reconcileKeyedCollection,
    createBatchedQueueProcessor,
    isAbortedRequestError,
    openEventSourceWithFallback,
    startMonitorStreamConsumer,
    buildLeadLiveStreamUrl,
    apiJson,
    humanizeApiError,
    buildQuery,
    buildPagedRequestOptions,
    apiGetLeads,
    apiGetSourceStats,
    apiReloadSource,
    apiGetRuntimeStatus,
    apiGetTelegramDialogs,
    apiImportTelegramDialogs,
    apiSaveTelegramDialogSettings,
    apiRemoveTelegramDialogsFromScan,
    apiGetAppSettings,
    apiSaveAppSettings,
    apiGetImages,
    apiGetImageText,
    apiRunPendingImageOcr,
    apiGetMediaConfig,
    apiGetMediaStatus,
    apiAddMediaLead,
    apiAddManyMediaLeads,
    apiRemoveMediaLead,
    apiClearMediaLead,
    apiClearAllMedia,
    apiGetJurEntities,
    apiSyncJurEntities,
    apiAddJurEntityToParser,
    apiRemoveJurEntityFromParser,
    apiGetTelegramContacts,
    apiGetContactChatFilters,
    apiGetTelegramContactMessages,
    apiGetContactQualificationPrompts,
    apiGetContactQualifications,
    apiQualifyContact,
    apiSetContactDoNotContact,
    apiGetContactsStatus,
    apiRefreshContacts,
    apiSetContactsConfig,
    apiGetCrmContacts,
    apiGetCrmStatus,
    apiRefreshCrm,
    apiSetCrmConfig,
    apiGetOutreachItems,
    apiAddOutreachItem,
    apiDeleteOutreachItem,
    apiCreateOutreachSequenceFromEnreach,
    OUTREACH_FIELD_LABELS,
    normalizeOutreachFieldType,
    outreachFieldLabel,
    normalizeOutreachPayload,
    outreachPayloadKey,
    createOutreachToggleState,
    apiDeactivateLead,
    apiActivateLead,
    apiDeleteLead,
    apiSetLeadGroup,
    apiGetEventKeywords,
    apiSetEventKeywords,
    apiGetEventMessages,
    apiDeleteEventMessage,
    apiGetEventsStatus,
    apiRefreshEvents,
    apiSetEventsConfig,
    apiGetImportSyncStatus,
    apiEnableImportSync,
    apiDisableImportSync,
    apiGetTelegramSyncJob,
    apiGetTelegramSyncControl,
    apiPauseTelegramSync,
    apiResumeTelegramSync,
    apiRunTelegramSync,
    apiPostJson,
    clearFrontendRuntimeState,
    apiGetMessages,
    apiGetChatAnalysisStats,
    apiGetChatAnalysisHistory,
    apiRunChatAnalysis,
    toast,
    scrollToBottomNow,
    scrollToBottomSmooth,
  };

  window.addLlmButton = function(label, optDataText) {
    const llmBox = document.getElementById('llmBox');
    if (!llmBox) return null;

    const b = document.createElement('button');
    b.className = 'llm-btn';
    b.type = 'button';
    b.textContent = label;
    if (optDataText !== undefined) b.dataset.text = optDataText;
    llmBox.appendChild(b);
    return b;
  };
}

initApp();
