import type { JobProgress } from '../../api/jobsApi';

export type ChatAnalysisProps = {
  progress?: JobProgress | null;
  onRun: () => void;
};

export function ChatAnalysis({ progress, onRun }: ChatAnalysisProps) {
  const percent = Math.max(0, Math.min(100, Number(progress?.progress_percent || 0)));
  return (
    <section className="analysis-panel">
      <div className="analysis-toolbar">
        <button className="btn" type="button" onClick={onRun}>Анализ чата</button>
        <span className="subtle">{progress?.progress_label || progress?.status || 'Ожидание'}</span>
      </div>
      <div className="progress-track">
        <div className="progress-bar" style={{ width: `${percent}%` }} />
      </div>
    </section>
  );
}
