export type DashboardSummaryItem = {
  label: string;
  value: string | number;
  note?: string;
};

export function DashboardSummary({ items }: { items: DashboardSummaryItem[] }) {
  return (
    <section className="panel">
      <div className="section-title">Состояние сейчас</div>
      <div className="stats">
        {items.map((item) => (
          <div className="stat" key={item.label}>
            {item.label}
            <strong>{item.value}</strong>
            <small>{item.note || ''}</small>
          </div>
        ))}
      </div>
    </section>
  );
}
