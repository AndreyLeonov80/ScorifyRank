import { apiJson, apiPath } from './http';
import type { ApiRequestOptions, PageResponse } from '../types/api';

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'idle' | string;

export type JobProgress = {
  job_id: string;
  type?: string;
  queue_name?: string;
  status: JobStatus;
  progress_percent: number;
  progress_label?: string;
  queue_started_at?: string | null;
  chunks_done?: number;
  chunks_total?: number;
  last_chunk_at?: string | null;
  eta_seconds?: number | null;
  error?: string | null;
  result?: Record<string, unknown>;
  payload?: Record<string, unknown>;
};

export type JobEvent = {
  id: number;
  job_id: string;
  level: string;
  message: string;
  payload?: Record<string, unknown>;
  created_at?: string | null;
};

export type JobCreatePayload = {
  type?: string;
  queue_name?: string;
  payload?: Record<string, unknown>;
};

export type JobCreateResponse = {
  ok: boolean;
  job_id: string;
  status: JobStatus;
  queue_name: string;
  message: string;
  job: JobProgress;
};

export function getRuntimeStatus(options: ApiRequestOptions = {}): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>('/api/payme/runtime-status', options);
}

export function getDashboardSummary(limit = 10, options: ApiRequestOptions = {}): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>(apiPath('/api/payme/dashboard/summary', { limit }), options);
}

export function getJobs(options: ApiRequestOptions = {}): Promise<PageResponse<JobProgress> | JobProgress[]> {
  return apiJson<PageResponse<JobProgress> | JobProgress[]>('/api/payme/jobs', options);
}

export function createJob(payload: JobCreatePayload, options: ApiRequestOptions = {}): Promise<JobCreateResponse> {
  return apiJson<JobCreateResponse>('/api/payme/jobs', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}

export function runAnalysisJob(payload: JobCreatePayload, options: ApiRequestOptions = {}): Promise<JobCreateResponse> {
  return apiJson<JobCreateResponse>('/api/payme/analysis/run', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify({ type: 'llm_analysis', ...payload }),
  });
}

export function getJob(jobId: string, options: ApiRequestOptions = {}): Promise<JobProgress> {
  return apiJson<JobProgress>(`/api/payme/jobs/${encodeURIComponent(jobId)}`, options);
}

export function getJobEvents(jobId: string, options: ApiRequestOptions = {}): Promise<PageResponse<JobEvent>> {
  return apiJson<PageResponse<JobEvent>>(`/api/payme/jobs/${encodeURIComponent(jobId)}/events`, options);
}

export function cancelJob(jobId: string, options: ApiRequestOptions = {}): Promise<{ ok: boolean; job_id: string; status: JobStatus; message: string }> {
  return apiJson(`/api/payme/jobs/${encodeURIComponent(jobId)}/cancel`, { ...options, method: 'POST' });
}
