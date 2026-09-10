<style>
  .llm-modern {
    --llm-border: #dbe5ef;
    --llm-soft: #f8fbff;
    --llm-ink: #0f172a;
    --llm-muted: #64748b;
    --llm-blue: #2563eb;
    --llm-green: #16a34a;
    color: var(--llm-ink);
    display: grid;
    gap: 14px;
    font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .llm-modern * { box-sizing: border-box; }
  .llm-hero {
    border: 1px solid var(--llm-border);
    border-radius: 18px;
    padding: 16px;
    background:
      radial-gradient(circle at 0 0, rgba(59, 130, 246, .10), transparent 18rem),
      linear-gradient(135deg, #ffffff, #f8fbff);
  }
  .llm-eyebrow {
    color: var(--llm-muted);
    font-size: 11px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
  }
  .llm-title {
    margin-top: 6px;
    font-size: 18px;
    line-height: 1.2;
    font-weight: 850;
    letter-spacing: -.02em;
  }
  .llm-token-card {
    margin-top: 14px;
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    border: 1px solid #bfdbfe;
    border-radius: 999px;
    padding: 8px 12px;
    background: #eff6ff;
    color: #1d4ed8;
    font-weight: 800;
  }
  .llm-token-card strong { font-size: 20px; color: #0f172a; }
  .llm-section {
    border: 1px solid var(--llm-border);
    border-radius: 18px;
    padding: 14px;
    background: rgba(255,255,255,.86);
  }
  .llm-section-title {
    font-size: 14px;
    font-weight: 850;
    margin-bottom: 10px;
  }
  .llm-filter-grid {
    display: grid;
    gap: 8px;
  }
  .llm-filter {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 1px solid #e5eef7;
    border-radius: 14px;
    padding: 9px 10px;
    background: var(--llm-soft);
  }
  .llm-filter span:first-child {
    color: var(--llm-muted);
    font-size: 12px;
    font-weight: 750;
  }
  .llm-filter span:last-child {
    color: #0f172a;
    font-size: 12px;
    font-weight: 850;
  }
  .llm-actions {
    display: grid;
    gap: 10px;
  }
  .llm-run,
  .llm-ag1,
  .llm-ag2,
  .llm-btn {
    width: 100%;
    border: 0;
    border-radius: 14px;
    cursor: pointer;
    text-align: left;
    font: inherit;
    transition: transform .14s ease, box-shadow .14s ease, background .14s ease;
  }
  .llm-run {
    padding: 13px 14px;
    background: linear-gradient(135deg, #16a34a, #22c55e);
    color: #fff;
    font-weight: 850;
    box-shadow: 0 14px 28px rgba(22, 163, 74, .18);
  }
  .llm-ag1,
  .llm-ag2 {
    padding: 11px 12px;
    border: 1px solid #bbf7d0;
    background: #f0fdf4;
    color: #166534;
    font-weight: 800;
  }
  .llm-btn {
    display: grid;
    gap: 8px;
    padding: 13px 14px;
    border: 1px solid #bfdbfe;
    background: #eff6ff;
    color: #172554;
    line-height: 1.45;
  }
  .llm-btn::before {
    content: "Рекомендованный ответ";
    color: #2563eb;
    font-size: 11px;
    font-weight: 850;
    letter-spacing: .06em;
    text-transform: uppercase;
  }
  .llm-actions .llm-btn::before { content: none; }
  .llm-run:hover,
  .llm-ag1:hover,
  .llm-ag2:hover,
  .llm-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 16px 34px rgba(15, 23, 42, .10);
  }
  .llm-answer-list {
    display: grid;
    gap: 10px;
  }
  .llm-empty-note {
    color: var(--llm-muted);
    font-size: 12px;
    line-height: 1.5;
  }
</style>

<div class="llm-modern">
  <section class="llm-hero">
    <div class="llm-eyebrow">AI NPC business assistant</div>
    <div class="llm-title">Структуры сделки и рекомендованные ответы</div>
    <div class="llm-token-card"><strong>{tokens}</strong><span>токенов в источнике</span></div>
  </section>

  <section class="llm-section">
    <div class="llm-section-title">Фильтры анализа</div>
    <div class="llm-filter-grid">
      <div class="llm-filter"><span>Токены</span><span>Все</span></div>
      <div class="llm-filter"><span>Период</span><span>Все</span></div>
      <div class="llm-filter"><span>Смыслы</span><span>Все</span></div>
      <div class="llm-filter"><span>Кластеры</span><span>Все</span></div>
    </div>
  </section>

  <section class="llm-section">
    <div class="llm-section-title">Действия</div>
    <div class="llm-actions">
      <button type="button" class="llm-run">Посчитать LLM-рекомендованные ответы</button>
      <button type="button" class="llm-ag1 llm-btn" data-text="АГЕНТ-1 SYSTEM PROMPT 1 + config">Агент-1 · system prompt + config</button>
      <button type="button" class="llm-ag2 llm-btn" data-text="АГЕНТ-2 SYSTEM PROMPT 2 + config">Агент-2 · system prompt + config</button>
    </div>
  </section>

  <section class="llm-section">
    <div class="llm-section-title">Готовые ответы</div>
    <div class="llm-answer-list">
      {button}
    </div>
  </section>
</div>
