import type { Lead } from '../../types/lead';

export type ChatMessage = {
  id: string | number;
  date_utc?: string | null;
  sender_name?: string | null;
  sender_username?: string | null;
  role?: string | null;
  text?: string | null;
  has_media?: boolean;
};

export type ChatUser = {
  id: string | number;
  title: string;
  username?: string | null;
  message_count?: number;
  token_count?: number;
};

export type ChatAppState = {
  current: Lead | null;
  messages: ChatMessage[];
  users: ChatUser[];
  loading: boolean;
};
