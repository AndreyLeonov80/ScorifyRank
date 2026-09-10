import type { ApiRequestOptions, BackendErrorPayload } from '../types/api';

const DEFAULT_BACKEND_PORT = '8009';
const LEGACY_BACKEND_PORT = '8001';

declare global {
  interface Window {
    BackfrontApi?: {
      getApiCandidates?: () => string[];
      apiJson?: <T>(path: string, options?: ApiRequestOptions) => Promise<T>;
    };
    XFILES_API_BASE?: string;
    PUBLIC_BASE_URL?: string;
    XFILES_PUBLIC_BASE_URL?: string;
    XFILES_BACKEND_PORT?: string | number;
    XFILES_LEGACY_BACKEND_PORT?: string | number;
  }
}

function normalizeBaseUrl(value: unknown): string {
  if (!value) return '';
  return String(value).replace(/\/+$/, '');
}

function toQuery(params?: URLSearchParams | Record<string, unknown> | string): string {
  if (!params) return '';
  if (typeof params === 'string') return params.startsWith('?') || !params ? params : `?${params}`;
  if (params instanceof URLSearchParams) {
    const value = params.toString();
    return value ? `?${value}` : '';
  }
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    query.set(key, String(value));
  }
  const value = query.toString();
  return value ? `?${value}` : '';
}

function extractError(payload: BackendErrorPayload | string | null | undefined, fallback: string): string {
  if (!payload) return fallback;
  if (typeof payload === 'string') return payload;
  const value = payload.detail ?? payload.error ?? payload.message;
  if (!value) return fallback;
  return typeof value === 'string' ? value : JSON.stringify(value);
}

export function getApiCandidates(): string[] {
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

export async function apiJson<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  if (window.BackfrontApi?.apiJson) {
    return window.BackfrontApi.apiJson<T>(path, options);
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  let lastError: unknown;

  for (const base of getApiCandidates()) {
    const controller = options.timeoutMs ? new AbortController() : null;
    const timeout = controller
      ? window.setTimeout(() => controller.abort(), Math.max(1, Number(options.timeoutMs)))
      : null;
    try {
      const response = await fetch(`${base}${normalizedPath}`, {
        ...options,
        signal: options.signal || controller?.signal,
        headers: { Accept: 'application/json', ...(options.headers || {}) },
      });

      if (!response.ok) {
        let payload: BackendErrorPayload | string | null = null;
        try {
          payload = await response.json();
        } catch {
          payload = await response.text();
        }
        lastError = new Error(`HTTP ${response.status}: ${extractError(payload, response.statusText)}`);
        continue;
      }

      return await response.json() as T;
    } catch (error) {
      lastError = error;
    } finally {
      if (timeout) window.clearTimeout(timeout);
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Backend unavailable');
}

export async function apiText(path: string, options: ApiRequestOptions = {}): Promise<string> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  let lastError: unknown;

  for (const base of getApiCandidates()) {
    const controller = options.timeoutMs ? new AbortController() : null;
    const timeout = controller
      ? window.setTimeout(() => controller.abort(), Math.max(1, Number(options.timeoutMs)))
      : null;
    try {
      const response = await fetch(`${base}${normalizedPath}`, {
        ...options,
        signal: options.signal || controller?.signal,
        headers: { Accept: 'text/html, text/plain, */*', ...(options.headers || {}) },
      });
      if (!response.ok) {
        lastError = new Error(`HTTP ${response.status}: ${response.statusText}`);
        continue;
      }
      return await response.text();
    } catch (error) {
      lastError = error;
    } finally {
      if (timeout) window.clearTimeout(timeout);
    }
  }

  throw lastError instanceof Error ? lastError : new Error('Backend unavailable');
}

export function apiPath(path: string, params?: URLSearchParams | Record<string, unknown> | string): string {
  return `${path.startsWith('/') ? path : `/${path}`}${toQuery(params)}`;
}
