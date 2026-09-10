export type ImportDialogRow = {
  selector: string;
  title: string;
  type?: string;
  username?: string;
  is_already_added?: boolean;
};

export type ImportTableProps = {
  rows: ImportDialogRow[];
  selected: Set<string>;
  onToggle: (selector: string) => void;
  onAdd: (row: ImportDialogRow) => void;
  onRemove: (row: ImportDialogRow) => void;
};

export function ImportTable({ rows, selected, onToggle, onAdd, onRemove }: ImportTableProps) {
  return (
    <table className="import-table">
      <thead>
        <tr>
          <th>Выбор</th>
          <th>Диалог</th>
          <th>Тип</th>
          <th>Статус</th>
          <th>Действие</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.selector}>
            <td><input type="checkbox" checked={selected.has(row.selector)} onChange={() => onToggle(row.selector)} /></td>
            <td><strong>{row.title || row.selector}</strong><small>{row.username || row.selector}</small></td>
            <td>{row.type || 'telegram'}</td>
            <td>{row.is_already_added ? 'Добавлен' : 'Не добавлен'}</td>
            <td>
              {row.is_already_added
                ? <button type="button" onClick={() => onRemove(row)}>Удалить</button>
                : <button type="button" onClick={() => onAdd(row)}>Добавить</button>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
