import { apiJson, apiPath, apiText } from './http';
import type { ApiRequestOptions } from '../types/api';
import type { ChatMessage } from '../pages/index/types';

export type SendMessagePayload = {
  chat_id: string;
  message: string;
};

export type SendMessageResponse = {
  ok?: boolean;
  message?: string;
  [key: string]: unknown;
};

export type LlmDraftPayload = {
  chat_id: string;
  filename: string;
  prompt_id?: string | null;
};

export function getChatMessages(
  lead: string,
  query: { offset?: number; limit?: number } = {},
  options: ApiRequestOptions = {},
): Promise<ChatMessage[]> {
  return apiJson<ChatMessage[]>(apiPath(`/api/payme/leads/${encodeURIComponent(lead)}/messages`, query), options);
}

export function getLeadLlmHtml(lead: string, options: ApiRequestOptions = {}): Promise<string> {
  return apiText(`/api/payme/leads/${encodeURIComponent(lead)}/llm`, options);
}

export function sendChatMessage(payload: SendMessagePayload, options: ApiRequestOptions = {}): Promise<SendMessageResponse> {
  return apiJson<SendMessageResponse>('/api/payme/send', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}

export function runLlmDraft(payload: LlmDraftPayload, options: ApiRequestOptions = {}): Promise<Record<string, unknown>> {
  return apiJson<Record<string, unknown>>('/api/payme/llm-run', {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}
