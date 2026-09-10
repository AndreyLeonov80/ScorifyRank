import { getJobs, type JobProgress } from '../../api/jobsApi';
import { formatEta } from '../index/utils';

export type JobsPanelState = {
  loading: boolean;
  error: string;
  items: JobProgress[];
  updatedAt: string;
};

export const initialJobsPanelState: JobsPanelState = {
  loading: false,
  error: '',
  items: [],
  updatedAt: '',
};

export async function loadJobsPanelState(): Promise<JobsPanelState> {
  const response = await getJobs({ timeoutMs: 12000 });
  const items = Array.isArray(response) ? response : response.items;
  return {
    loading: false,
    error: '',
    items: Array.isArray(items) ? items : [],
    updatedAt: new Date().toISOString(),
  };
}

export function JobsPanel({ state, onRefresh }: { state: JobsPanelState; onRefresh: () => void }) {
  const rows = Array.isArray(state.items) ? state.items.slice(0, 8) : [];
  return (
    <section className="jobs-panel">
      <div className="jobs-panel-head">
        <div>
          <div className="section-title">Фоновые задачи</div>
          <div className="subtle">{state.updatedAt ? `Обновлено ${state.updatedAt}` : 'Status/progress обновляется отдельно от dashboard.'}</div>
        </div>
        <button className="btn" type="button" disabled={state.loading} onClick={onRefresh}>
          {state.loading ? 'Обновляем...' : 'Обновить'}
        </button>
      </div>
      {state.error ? <div className="analysis-error">{state.error}</div> : null}
      <div className="jobs-panel-list">
        {rows.length ? rows.map((job) => {
          const percent = Math.max(0, Math.min(100, Number(job.progress_percent || 0)));
          return (
            <article className="jobs-panel-row" key={job.job_id}>
              <div className="row">
                <strong>{job.type || job.queue_name || job.job_id}</strong>
                <span className="muted">{job.status}</span>
              </div>
              <div className="subtle">{job.progress_label || 'Ожидаем обновление статуса'} · ETA {formatEta(job.eta_seconds || 0)}</div>
              <div className="progress-track">
                <div className="progress-bar" style={{ width: `${percent}%` }} />
              </div>
            </article>
          );
        }) : <div className="empty">Активных задач пока нет.</div>}
      </div>
    </section>
  );
}
