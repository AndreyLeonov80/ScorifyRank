export type ApiOk<T> = {
  ok: true;
  data: T;
  error?: never;
  meta?: Record<string, unknown>;
};

export type ApiFail = {
  ok: false;
  data?: never;
  error: string;
  meta?: Record<string, unknown>;
};

export type ApiResponse<T> = ApiOk<T> | ApiFail;

export type PageResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type ApiRequestOptions = RequestInit & {
  timeoutMs?: number;
  requestKey?: string;
  forceFresh?: boolean;
  cacheTtlMs?: number;
};

export type BackendErrorPayload = {
  detail?: unknown;
  error?: unknown;
  message?: unknown;
};
