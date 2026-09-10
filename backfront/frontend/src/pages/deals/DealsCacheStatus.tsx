export type DealsCacheStatusState = {
  postgresql_waiting?: boolean;
  postgresql_available?: boolean;
  cache_ready?: boolean;
  message?: string;
  last_error?: string | null;
};

export function isDealsPostgresWaiting(status: DealsCacheStatusState | null | undefined): boolean {
  return Boolean(status?.postgresql_waiting && !status?.postgresql_available);
}

export function DealsCacheStatus({ status }: { status: DealsCacheStatusState | null | undefined }) {
  const waiting = isDealsPostgresWaiting(status);
  if (!waiting && !status?.last_error) return null;
  return (
    <section className={waiting ? 'deals-cache-status deals-cache-status-waiting' : 'deals-cache-status deals-cache-status-error'}>
      <h3>{waiting ? 'PostgreSQL подключается' : 'Ошибка кеша сделок'}</h3>
      <p>
        {status?.message || (waiting
          ? 'Показываем локальный кеш state.json, пока PostgreSQL становится доступен.'
          : status?.last_error || 'Не удалось обновить статус сделок.')}
      </p>
    </section>
  );
}
