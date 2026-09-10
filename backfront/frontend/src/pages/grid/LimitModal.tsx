export type LimitModalValue = {
  unlimited: boolean;
  months: number;
  messages: number;
};

export type LimitModalProps = {
  value: LimitModalValue;
  title: string;
  onChange: (value: LimitModalValue) => void;
  onApply: () => void;
  onClose: () => void;
};

export function LimitModal({ value, title, onChange, onApply, onClose }: LimitModalProps) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal-card" onClick={(event: { stopPropagation: () => void }) => event.stopPropagation()}>
        <header>
          <h2>{title}</h2>
          <button type="button" onClick={onClose}>Закрыть</button>
        </header>
        <label>
          <input
            type="checkbox"
            checked={value.unlimited}
            onChange={(event: { currentTarget: HTMLInputElement }) => onChange({ ...value, unlimited: event.currentTarget.checked })}
          />
          Безлимит
        </label>
        <label>
          Месяцев истории
          <input
            type="number"
            disabled={value.unlimited}
            value={value.months}
            onChange={(event: { currentTarget: HTMLInputElement }) => onChange({ ...value, months: Number(event.currentTarget.value || 0) })}
          />
        </label>
        <label>
          Сообщений на источник
          <input
            type="number"
            disabled={value.unlimited}
            value={value.messages}
            onChange={(event: { currentTarget: HTMLInputElement }) => onChange({ ...value, messages: Number(event.currentTarget.value || 0) })}
          />
        </label>
        <button type="button" onClick={onApply}>Применить</button>
      </section>
    </div>
  );
}
