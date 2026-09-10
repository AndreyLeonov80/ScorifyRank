/* Lazy loader for per-page React bundles */
'use strict';

(function initBackfrontPageLoader() {
  if (window.BackfrontPageLoader?.load) return;

  function getPageRoot() {
    return document.querySelector('[data-page-script]');
  }

  function normalizeScriptSrc(value) {
    return String(value || '').trim();
  }

  function hasScript(src) {
    const normalized = normalizeScriptSrc(src);
    return Array.from(document.scripts).some((script) => normalizeScriptSrc(script.getAttribute('src')) === normalized);
  }

  function loadScript(src) {
    const normalized = normalizeScriptSrc(src);
    if (!normalized) {
      console.error('[React] data-page-script is empty');
      return Promise.reject(new Error('data-page-script is empty'));
    }
    if (hasScript(normalized)) return Promise.resolve();

    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = normalized;
      script.async = false;
      script.onload = () => resolve();
      script.onerror = () => {
        const error = new Error(`Failed to load page script: ${normalized}`);
        console.error('[React]', error.message);
        reject(error);
      };
      document.body.appendChild(script);
    });
  }

  function scheduleLoad(callback) {
    if (typeof window.requestIdleCallback === 'function') {
      window.requestIdleCallback(callback, { timeout: 1000 });
      return;
    }
    window.setTimeout(callback, 0);
  }

  function boot() {
    const root = getPageRoot();
    const src = root?.getAttribute('data-page-script') || '';
    scheduleLoad(() => {
      loadScript(src).catch(() => {});
    });
  }

  function shouldAutoBoot() {
    return document.body?.dataset.pageLoader !== 'manual';
  }

  function maybeBoot() {
    if (shouldAutoBoot()) boot();
  }

  window.BackfrontPageLoader = { load: loadScript };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybeBoot, { once: true });
  } else {
    maybeBoot();
  }
})();
