import type { ApiResponse } from '../types/api';

export function isApiResponse<T>(value: unknown): value is ApiResponse<T> {
  return Boolean(value && typeof value === 'object' && 'ok' in value);
}

export function normalizeApiResponse<T>(value: T | ApiResponse<T>): ApiResponse<T> {
  if (isApiResponse<T>(value)) return value;
  return { ok: true, data: value };
}

export function unwrapApiResponse<T>(value: T | ApiResponse<T>, fallbackError = 'Backend returned an error'): T {
  const response = normalizeApiResponse(value);
  if (response.ok) return response.data;
  throw new Error(response.error || fallbackError);
}
