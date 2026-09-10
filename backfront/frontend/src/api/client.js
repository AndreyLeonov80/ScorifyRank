const DEFAULT_BACKEND_PORT = '8009';
const LEGACY_BACKEND_PORT = '8001';

function normalizeBaseUrl(value) {
  if (!value) return '';
  return String(value).replace(/\/+$/, '');
}

export function getApiCandidates() {
  if (window.BackfrontApi?.getApiCandidates) {
    return window.BackfrontApi.getApiCandidates();
  }

  const origin = window.location.origin;
  const host = window.location.hostname || '127.0.0.1';
  const protocol = window.location.protocol || 'http:';
  const backendPort = String(window.XFILES_BACKEND_PORT || DEFAULT_BACKEND_PORT).trim();
  const legacyPort = String(window.XFILES_LEGACY_BACKEND_PORT || LEGACY_BACKEND_PORT).trim();
  const explicit = normalizeBaseUrl(window.XFILES_API_BASE || window.PUBLIC_BASE_URL || window.XFILES_PUBLIC_BASE_URL);

  return [
    explicit,
    origin,
    `${protocol}//${host}:${backendPort}`,
    `http://127.0.0.1:${backendPort}`,
    `http://localhost:${backendPort}`,
    `${protocol}//${host}:${legacyPort}`,
    `http://127.0.0.1:${legacyPort}`,
    `http://localhost:${legacyPort}`,
  ].filter(Boolean);
}

export async function apiJson(path, options = {}) {
  if (window.BackfrontApi?.apiJson) {
    return window.BackfrontApi.apiJson(path, options);
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  let lastError;

  for (const base of getApiCandidates()) {
    try {
      const response = await fetch(`${base}${normalizedPath}`, {
        headers: { Accept: 'application/json', ...(options.headers || {}) },
        ...options,
      });

      if (!response.ok) {
        lastError = new Error(`HTTP ${response.status}`);
        continue;
      }

      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('Backend unavailable');
}
