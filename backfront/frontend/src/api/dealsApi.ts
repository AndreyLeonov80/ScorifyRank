import { apiJson, apiPath } from './http';
import type { ApiRequestOptions } from '../types/api';
import type { DealListData } from '../types/deal';

export type DealQuery = {
  page?: number;
  page_size?: number;
  query?: string;
  stage?: string;
  source_selector?: string;
};

export function getDeals(query: DealQuery = {}, options: ApiRequestOptions = {}): Promise<DealListData> {
  return apiJson<DealListData>(apiPath('/api/payme/deals', query), options);
}
