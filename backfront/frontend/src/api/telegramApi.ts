import { apiJson, apiPath } from './http';
import type { ApiRequestOptions } from '../types/api';
import type { TelegramDialogPage, TelegramDialogQuery, TelegramImportResult } from '../types/telegram';

export function getTelegramDialogs(
  query: TelegramDialogQuery = {},
  options: ApiRequestOptions = {},
): Promise<TelegramDialogPage> {
  return apiJson<TelegramDialogPage>(apiPath('/api/payme/import/dialogs', query), options);
}

export function importTelegramDialogs(
  selectors: string[],
  options: ApiRequestOptions = {},
): Promise<TelegramImportResult> {
  return apiJson<TelegramImportResult>('/api/payme/import/dialogs/import', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify({ selectors }),
  });
}

export function removeTelegramDialogsFromScan(
  selectors: string[],
  options: ApiRequestOptions = {},
): Promise<TelegramImportResult> {
  return apiJson<TelegramImportResult>('/api/payme/import/dialogs/remove', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify({ selectors }),
  });
}
