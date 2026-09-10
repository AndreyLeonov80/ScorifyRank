import { ProgressDialog, type ProgressDialogState } from '../../components/ProgressDialog';

export type ImportProgressState = ProgressDialogState & {
  kind?: 'initial' | 'load-dialogs' | 'import-selectors' | 'import-all' | string;
};

export function ImportProgressDialog({ progress }: { progress: ImportProgressState }) {
  return (
    <ProgressDialog
      progress={{
        ...progress,
        title: progress.title || 'Импорт Telegram',
        detail: progress.detail || 'Backend обновляет данные и готовит таблицу.',
      }}
    />
  );
}
