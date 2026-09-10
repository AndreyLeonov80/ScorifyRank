/* Single HTML entrypoint router for the React frontend */
'use strict';

(function initBackfrontEntrypoint() {
  const MANIFEST_URL = 'app.manifest.json';
  const MOUNT_ID = 'backfront-app-root';
  const SETUP_REQUIRED_STATUSES = new Set(['needs_api_credentials', 'needs_auth']);
  const SESSION_RECONNECTING_STATUSES = new Set(['session_present', 'unknown']);

  function normalizePathname(pathname) {
    const file = String(pathname || '')
      .split('/')
      .filter(Boolean)
      .pop();
    return file && file.endsWith('.html') ? file : 'index.html';
  }

  function isSetupAllowedPage(pageName) {
    return pageName === 'setup_wizard.html' || pageName === 'tariffs.html';
  }

  function redirectToSetupWizard(reason) {
    const next = encodeURIComponent(window.location.pathname + (window.location.search || ''));
    const safeReason = encodeURIComponent(reason || 'needs_api_credentials');
    window.location.replace(`/setup_wizard.html?next=${next}&reason=${safeReason}`);
    return next;
  }

  async function redirectToSetupWizardIfNeeded(pageName) {
    if (isSetupAllowedPage(pageName)) return false;
    if (!window.BackfrontApi?.apiJson) return false;

    try {
      const runtime = await window.BackfrontApi.apiJson('/api/payme/runtime-status', {
        timeoutMs: 1000,
      });
      const authStatus = String(runtime?.auth_status || '');
      if (authStatus === 'authorized' || SESSION_RECONNECTING_STATUSES.has(authStatus)) {
        return false;
      }
      if (SETUP_REQUIRED_STATUSES.has(authStatus)) {
        redirectToSetupWizard(authStatus || 'needs_auth');
        return true;
      }
    } catch (_) {
      return false;
    }

    return false;
  }

  function isExternalAsset(src) {
    return /^https?:\/\//i.test(src);
  }

  function normalizeLocalAsset(src) {
    return String(src || '').split(/[?#]/)[0];
  }

  function hasScript(src) {
    const expected = normalizeLocalAsset(src);
    return Array.from(document.scripts).some((script) => {
      const current = script.getAttribute('src') || '';
      if (isExternalAsset(src)) return current === src;
      return normalizeLocalAsset(current) === expected;
    });
  }

  function loadScript(src) {
    if (!src || hasScript(src)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = src;
      script.async = false;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Failed to load dependency: ${src}`));
      document.head.appendChild(script);
    });
  }

  function loadStyle(href) {
    if (!href) return;
    const expected = normalizeLocalAsset(href);
    const exists = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).some((link) => {
      const current = link.getAttribute('href') || '';
      return normalizeLocalAsset(current) === expected;
    });
    if (exists) return;

    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.pageStyle = 'true';
    document.head.appendChild(link);
  }

  function mountRoot(page) {
    const container = document.getElementById(MOUNT_ID);
    if (!container) throw new Error(`Missing ${MOUNT_ID}`);
    container.innerHTML = '';

    const root = document.createElement('div');
    root.id = page.rootId || 'app';
    root.setAttribute('data-page-script', page.script);
    container.appendChild(root);
    return root;
  }

  async function loadManifest() {
    const response = await fetch(MANIFEST_URL, { cache: 'no-store' });
    if (!response.ok) throw new Error(`Failed to load ${MANIFEST_URL}: HTTP ${response.status}`);
    return response.json();
  }

  async function boot() {
    const pageName = normalizePathname(window.location.pathname);
    if (await redirectToSetupWizardIfNeeded(pageName)) return;

    const manifest = await loadManifest();
    const page = manifest.pages?.[pageName] || manifest.pages?.[manifest.defaultPage];
    if (!page) throw new Error(`No page manifest entry for ${pageName}`);

    document.title = page.title || 'X-Files';
    loadStyle(page.style);
    mountRoot(page);

    for (const dependency of page.dependencies || []) {
      await loadScript(dependency);
    }

    await window.BackfrontPageLoader.load(page.script);
  }

  boot().catch((error) => {
    console.error('[Entrypoint]', error);
    const container = document.getElementById(MOUNT_ID);
    if (container) {
      container.innerHTML = '<div class="error-box">Не удалось загрузить страницу приложения.</div>';
    }
  });
})();
