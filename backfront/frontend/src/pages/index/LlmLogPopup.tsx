export type LlmLogPopupProps = {
  open: boolean;
  text: string;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
};

export function LlmLogPopup({ open, text, onClose, onPrev, onNext }: LlmLogPopupProps) {
  if (!open) return null;
  return (
    <div className="modal-backdrop">
      <section className="modal modal-80" role="dialog" aria-modal="true">
        <div className="modal-head">
          <h2>Лог LLM</h2>
          <button className="btn btn-ghost" type="button" onClick={onClose}>Закрыть</button>
        </div>
        <pre className="llm-log-body">{text}</pre>
        <div className="modal-actions">
          <button className="btn btn-ghost" type="button" onClick={onPrev}>Предыдущий лог</button>
          <button className="btn btn-ghost" type="button" onClick={onNext}>Следующий лог</button>
        </div>
      </section>
    </div>
  );
}
