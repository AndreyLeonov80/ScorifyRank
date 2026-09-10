import { apiJson } from './http';
import type { ApiRequestOptions } from '../types/api';

export type PromptTemplate = {
  id: string;
  title: string;
  body: string;
  scope: 'chat_reply' | 'chat_analysis' | 'contact_qualification' | string;
  is_default?: boolean;
  updated_at?: string | null;
};

export function getPrompts(options: ApiRequestOptions = {}): Promise<PromptTemplate[]> {
  return apiJson<PromptTemplate[]>('/api/payme/prompts', options);
}

export function savePrompt(prompt: PromptTemplate, options: ApiRequestOptions = {}): Promise<PromptTemplate> {
  return apiJson<PromptTemplate>('/api/payme/prompts', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(prompt),
  });
}

export function deletePrompt(id: string, options: ApiRequestOptions = {}): Promise<{ ok: boolean }> {
  return apiJson<{ ok: boolean }>(`/api/payme/prompts/${encodeURIComponent(id)}`, {
    ...options,
    method: 'DELETE',
  });
}
