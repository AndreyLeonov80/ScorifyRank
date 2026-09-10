import { apiJson } from './http';
import type { ApiRequestOptions } from '../types/api';

export type AppSettings = Record<string, unknown>;

export function getSettings(options: ApiRequestOptions = {}): Promise<AppSettings> {
  return apiJson<AppSettings>('/api/payme/settings', options);
}

export function saveSettings(payload: AppSettings, options: ApiRequestOptions = {}): Promise<AppSettings> {
  return apiJson<AppSettings>('/api/payme/settings', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}

export function updateLicense(payload: AppSettings, options: ApiRequestOptions = {}): Promise<AppSettings> {
  return apiJson<AppSettings>('/api/payme/license/update', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}
