import type { ApiResponse, PageResponse } from './api';

export type LeadStatus = 'new' | 'in_work' | 'qualified' | 'archived' | string;

export type Lead = {
  id: string | number;
  source_selector?: string | null;
  sender_name?: string | null;
  sender_username?: string | null;
  text?: string | null;
  response?: string | null;
  recommendation?: string | null;
  status?: LeadStatus;
  created_at?: string | null;
  updated_at?: string | null;
};

export type LeadListData = PageResponse<Lead> | Lead[];
export type LeadListResponse = ApiResponse<LeadListData>;
