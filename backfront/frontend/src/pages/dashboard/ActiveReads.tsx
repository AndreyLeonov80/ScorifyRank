export type ActiveReadSource = {
  selector: string;
  title: string;
  status: string;
  progress_percent?: number;
  read_done?: number;
  read_total?: number;
  remaining?: number;
  last_live_update_at?: string;
};

export function ActiveReads({ sources }: { sources: ActiveReadSource[] }) {
  if (!sources.length) {
    return <p className="subtle">Активного чтения Telegram сейчас нет.</p>;
  }

  return (
    <section className="panel">
      <div className="section-title">Сейчас читаются</div>
      <table>
        <thead>
          <tr>
            <th>Источник</th>
            <th>Статус</th>
            <th>Прочитано</th>
            <th>Осталось</th>
            <th>Последний live</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.selector} className="row-active-sync">
              <td><strong>{source.title || source.selector}</strong><small>{source.selector}</small></td>
              <td>{source.status}</td>
              <td>{source.read_done || 0} / {source.read_total || 0} · {Math.round(source.progress_percent || 0)}%</td>
              <td>{source.remaining || 0}</td>
              <td>{source.last_live_update_at || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
