export type SourceRow = {
  selector: string;
  title: string;
  status: string;
  status_reason?: string;
  scan_group?: string;
  scan_group_label?: string;
  duckdb_rows?: number;
  progress_percent?: number;
  limit_months?: number;
  limit_messages?: number;
  last_message_at?: string;
  jsonl_url?: string;
  read_now?: boolean;
};

export type SourceTableProps = {
  rows: SourceRow[];
  onOpenChat: (row: SourceRow) => void;
  onEditLimit: (row: SourceRow) => void;
  onChangeGroup: (row: SourceRow, group: string) => void;
};

export function SourceTable({ rows, onOpenChat, onEditLimit, onChangeGroup }: SourceTableProps) {
  return (
    <table className="grid-source-table">
      <thead>
        <tr>
          <th>Канал</th>
          <th>Статус</th>
          <th>Группа</th>
          <th>Сообщения</th>
          <th>Прогресс чтения</th>
          <th>Лимит времени</th>
          <th>Лимит сообщений</th>
          <th>Последнее сообщение</th>
          <th>Действия</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.selector} className={row.read_now ? 'row-active-sync' : ''}>
            <td>
              {row.jsonl_url ? <a href={row.jsonl_url}>{row.title || row.selector}</a> : <strong>{row.title || row.selector}</strong>}
              <small>{row.selector}</small>
            </td>
            <td><strong>{row.status}</strong><small>{row.status_reason || ''}</small></td>
            <td>
              <select value={row.scan_group || 'C'} onChange={(event: { currentTarget: HTMLSelectElement }) => onChangeGroup(row, event.currentTarget.value)}>
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
                <option value="D">D</option>
              </select>
              <small>{row.scan_group_label || ''}</small>
            </td>
            <td>{row.duckdb_rows || 0}</td>
            <td>{Math.round(row.progress_percent || 0)}%</td>
            <td>{row.limit_months === 0 ? 'безлимит' : row.limit_months || 1}</td>
            <td>{row.limit_messages === 0 ? 'безлимит' : row.limit_messages || 1000}</td>
            <td>{row.last_message_at || '-'}</td>
            <td>
              <button type="button" onClick={() => onOpenChat(row)}>Открыть чат</button>
              <button type="button" onClick={() => onEditLimit(row)}>Лимит</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
