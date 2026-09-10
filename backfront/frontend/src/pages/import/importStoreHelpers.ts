import type { TelegramDialogPage, TelegramDialogQuery } from '../../types/telegram';

export type ImportProgress = {
  visible: boolean;
  running: boolean;
  percent: number;
  etaSec: number;
  status: string;
  detail: string;
  kind: string;
  startedAt: number;
  timeoutSec: number;
};

export function createImportProgress(kind = 'initial'): ImportProgress {
  return {
    visible: true,
    running: true,
    percent: 5,
    etaSec: 15,
    status: 'Готовлю импорт Telegram...',
    detail: 'Проверяю настройки, кэш и авторизацию Telegram.',
    kind,
    startedAt: Date.now(),
    timeoutSec: 15,
  };
}

export function buildDialogQuery(params: TelegramDialogQuery): URLSearchParams {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    query.set(key, String(value));
  }
  return query;
}

export function pageSummary(page: TelegramDialogPage): string {
  return `Показано строк: ${Number(page.items?.length || 0)}, всего: ${Number(page.total || 0)}.`;
}
