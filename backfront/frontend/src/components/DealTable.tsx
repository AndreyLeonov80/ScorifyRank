import type { Deal } from '../types/deal';

export type DealTableProps = {
  deals: Deal[];
  onOpen?: (deal: Deal) => void;
};

export function DealTable({ deals, onOpen }: DealTableProps) {
  return (
    <table className="deal-table">
      <thead>
        <tr>
          <th>Сделка</th>
          <th>Стадия</th>
          <th>Сумма</th>
          <th>Обновлено</th>
        </tr>
      </thead>
      <tbody>
        {deals.map((deal) => (
          <tr key={String(deal.id)} onClick={() => onOpen?.(deal)}>
            <td>{deal.title}</td>
            <td>{deal.stage || ''}</td>
            <td>{deal.amount == null ? '' : `${deal.amount} ${deal.currency || ''}`.trim()}</td>
            <td>{deal.updated_at || deal.created_at || ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
