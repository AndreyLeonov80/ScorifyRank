import type { PromptTemplate } from '../../api/promptsApi';

export type PromptSettingsProps = {
  prompts: PromptTemplate[];
  page: number;
  totalPages: number;
  onSave: (prompt: PromptTemplate) => void;
  onDelete: (id: string) => void;
  onPrev: () => void;
  onNext: () => void;
};

export function PromptSettings({ prompts, page, totalPages, onSave, onDelete, onPrev, onNext }: PromptSettingsProps) {
  return (
    <section className="prompt-settings">
      {prompts.map((prompt) => (
        <article className="prompt-card" key={prompt.id}>
          <input value={prompt.title} onChange={() => undefined} />
          <textarea value={prompt.body} onChange={() => undefined} />
          <div className="row">
            <button className="btn" type="button" onClick={() => onSave(prompt)}>Сохранить</button>
            <button className="btn btn-danger" type="button" onClick={() => onDelete(prompt.id)}>Удалить</button>
          </div>
        </article>
      ))}
      <div className="modal-actions">
        <button className="btn btn-ghost" type="button" onClick={onPrev} disabled={page <= 1}>Назад</button>
        <span>{page}/{Math.max(1, totalPages)}</span>
        <button className="btn btn-ghost" type="button" onClick={onNext} disabled={page >= totalPages}>Далее</button>
      </div>
    </section>
  );
}
