export type ProgressDialogState = {
  visible: boolean;
  running: boolean;
  percent: number;
  etaSec?: number;
  title: string;
  status: string;
  detail?: string;
};

export function formatEta(seconds?: number): string {
  const value = Math.max(0, Math.round(Number(seconds || 0)));
  if (!value) return 'ETA: почти готово';
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  if (!minutes) return `ETA: ${rest} сек`;
  return `ETA: ${minutes} мин ${String(rest).padStart(2, '0')} сек`;
}

export function ProgressDialog({ progress }: { progress: ProgressDialogState }) {
  if (!progress.visible) return null;
  const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
  return (
    <div className="import-progress-backdrop" role="presentation">
      <section className="import-progress-popup" role="dialog" aria-modal="true" aria-live="polite">
        <div className="import-progress-head">
          <div>
            <div className="import-progress-title">{progress.title}</div>
            <div className="subtle">{progress.running ? 'Операция выполняется' : 'Операция завершена'}</div>
          </div>
          <span className={`badge ${progress.running ? 'badge-warn' : 'badge-active'}`}>
            {progress.running ? 'выполняется' : 'готово'}
          </span>
        </div>
        <div className="import-progress-status">{progress.status}</div>
        {progress.detail ? <div className="import-progress-detail">{progress.detail}</div> : null}
        <div className="import-progress-meta">
          <strong>{Math.round(percent)}%</strong>
          <span>{formatEta(progress.etaSec)}</span>
        </div>
        <div className="import-progress-track">
          <div className="import-progress-bar" style={{ width: `${Math.max(2, percent)}%` }} />
        </div>
      </section>
    </div>
  );
}
