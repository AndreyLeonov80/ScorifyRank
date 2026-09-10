'use strict';

(function initBackfrontRealtimeClient(global) {
  function withFallbackApiBase(url, base) {
    try {
      const original = new URL(url, global.location ? global.location.href : 'http://localhost/');
      const fallbackBase = new URL(base);
      original.protocol = fallbackBase.protocol;
      original.hostname = fallbackBase.hostname;
      original.port = fallbackBase.port;
      return original.toString();
    } catch (_) {
      return url;
    }
  }

  function openEventSourceWithFallback(url, baseCandidates, handlers = {}) {
    const {
      onOpen = () => {},
      onMessage = () => {},
      onError = () => {},
    } = handlers;
    const candidates = Array.isArray(baseCandidates) ? baseCandidates : [];
    let es = null;
    for (const base of candidates) {
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

  function buildTypedRealtimeUrl(baseUrl, options = {}) {
    const {
      types = [],
      lead = '',
      minutes = null,
      historyPoints = null,
      extraParams = {},
    } = options;
    const params = new URLSearchParams();
    const typeList = Array.isArray(types) ? types.filter(Boolean) : [];
    if (typeList.length) params.set('types', typeList.join(','));
    if (lead) params.set('lead', String(lead).trim());
    if (minutes != null) params.set('minutes', String(minutes));
    if (historyPoints != null) params.set('history_points', String(historyPoints));
    for (const [key, value] of Object.entries(extraParams || {})) {
      if (value == null || value === '') continue;
      params.set(key, String(value));
    }
    const qs = params.toString();
    return qs ? `${baseUrl}?${qs}` : baseUrl;
  }

  function startTypedRealtimeStreamConsumer(config = {}) {
    const {
      baseUrl,
      baseCandidates = [],
      types = [],
      lead = '',
      minutes = null,
      historyPoints = null,
      extraParams = {},
      onEnvelope = () => {},
      onError = () => {},
      onState = () => {},
    } = config;

    const streamUrl = buildTypedRealtimeUrl(baseUrl, {
      types,
      lead,
      minutes,
      historyPoints,
      extraParams,
    });

    const es = openEventSourceWithFallback(streamUrl, baseCandidates, {
      onOpen: (_event, resolvedUrl) => {
        onState({ state: 'connected', url: resolvedUrl });
      },
      onMessage: (event, resolvedUrl) => {
        try {
          const envelope = JSON.parse(event.data);
          onEnvelope(envelope, resolvedUrl);
        } catch (error) {
          onError(error, resolvedUrl);
        }
      },
      onError: (_event, resolvedUrl, source) => {
        onState({ state: 'error', url: resolvedUrl });
        try { source?.close(); } catch (_) {}
        onError(new Error('typed realtime stream error'), resolvedUrl);
      },
    });

    if (!es) {
      onState({ state: 'error', url: '' });
      onError(new Error('typed realtime stream init failed'), '');
      return null;
    }

    onState({ state: 'connecting', url: es._resolvedUrl || '' });
    return es;
  }

  global.BackfrontRealtime = {
    withFallbackApiBase,
    openEventSourceWithFallback,
    buildTypedRealtimeUrl,
    startTypedRealtimeStreamConsumer,
  };
})(window);
