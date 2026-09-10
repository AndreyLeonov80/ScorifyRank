import type { ChatUser } from './types';

export type LeadStoreUsersState = {
  users: ChatUser[];
  loading: boolean;
  page: number;
  pageSize: number;
};

export function createLeadStoreUsersState(): LeadStoreUsersState {
  return {
    users: [],
    loading: false,
    page: 1,
    pageSize: 2,
  };
}
