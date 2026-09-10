import { apiJson, apiPath } from './http';
import type { ApiRequestOptions } from '../types/api';
import type { LeadListData } from '../types/lead';

export type LeadQuery = {
  page?: number;
  page_size?: number;
  query?: string;
  source_selector?: string;
  status?: string;
};

export function getLeads(query: LeadQuery = {}, options: ApiRequestOptions = {}): Promise<LeadListData> {
  return apiJson<LeadListData>(apiPath('/api/payme/leads', query), options);
}
