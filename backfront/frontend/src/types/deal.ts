import type { ApiResponse, PageResponse } from './api';

export type DealStage = 'new' | 'active' | 'won' | 'lost' | string;

export type Deal = {
  id: string | number;
  title: string;
  lead_id?: string | number | null;
  source_selector?: string | null;
  stage?: DealStage;
  amount?: number | null;
  currency?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DealListData = PageResponse<Deal> | Deal[];
export type DealListResponse = ApiResponse<DealListData>;
