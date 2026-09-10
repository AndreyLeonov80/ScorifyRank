import type { PageResponse } from './api';
import type { ChannelKind } from './channel';

export type TelegramDialog = {
  id: string | number;
  title: string;
  username?: string | null;
  selector: string;
  chat_type: ChannelKind | string;
  is_archived: boolean;
  is_already_added: boolean;
  unread_count?: number;
  last_date_utc?: string | null;
  last_text_preview?: string | null;
  last_text_full?: string | null;
  import_history_months?: number;
  import_message_limit?: number;
  import_max_history_months?: number;
  import_max_message_limit?: number;
};

export type TelegramDialogPage = PageResponse<TelegramDialog>;

export type TelegramImportResult = {
  ok?: boolean;
  message?: string;
  added_selectors?: string[];
  removed_selectors?: string[];
};

export type TelegramDialogQuery = {
  page?: number;
  page_size?: number;
  query?: string;
  show_channels?: boolean;
  show_groups?: boolean;
  show_private?: boolean;
  membership_filter?: 'all' | 'added' | 'not_added' | string;
  sort_by?: string;
};
