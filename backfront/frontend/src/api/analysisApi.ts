import { apiJson } from './http';
import type { ApiRequestOptions } from '../types/api';

export type ChatAnalysisMode = 'all' | 'last_messages' | 'token_budget' | 'selected';
export type ChatAnalysisProvider = 'openrouter' | 'local';

export type ChatTokenSender = {
  sender_key: string;
  sender_name?: string;
  sender_username?: string;
  messages_count?: number;
  tokens_estimate?: number;
};

export type ChatTokenStats = {
  ok: boolean;
  lead: string;
  total_messages: number;
  total_tokens: number;
  max_messages: number;
  by_sender: ChatTokenSender[];
  updated_at: string;
};

export type ChatAnalysisPayload = {
  mode: ChatAnalysisMode;
  message_limit?: number;
  token_budget?: number;
  selected_message_ids?: number[];
  prompt?: string;
  provider?: ChatAnalysisProvider;
  model?: string;
  sender_key?: string;
};

export type ChatAnalysisHistory = {
  ok: boolean;
  lead: string;
  items: Array<Record<string, unknown>>;
};

export type ChatAnalysisRunResult = {
  ok: boolean;
  lead: string;
  item: Record<string, unknown>;
  history: Array<Record<string, unknown>>;
  message: string;
};

export function getChatAnalysisStats(lead: string, options: ApiRequestOptions = {}): Promise<ChatTokenStats> {
  return apiJson<ChatTokenStats>(`/api/payme/leads/${encodeURIComponent(lead)}/analysis/stats`, options);
}

export function getChatAnalysisHistory(lead: string, options: ApiRequestOptions = {}): Promise<ChatAnalysisHistory> {
  return apiJson<ChatAnalysisHistory>(`/api/payme/leads/${encodeURIComponent(lead)}/analysis/history`, options);
}

export function runChatAnalysis(
  lead: string,
  payload: ChatAnalysisPayload,
  options: ApiRequestOptions = {},
): Promise<ChatAnalysisRunResult> {
  return apiJson<ChatAnalysisRunResult>(`/api/payme/leads/${encodeURIComponent(lead)}/analysis/run`, {
    ...options,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: JSON.stringify(payload),
  });
}
