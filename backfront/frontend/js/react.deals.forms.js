/* React X-Files deals forms */
'use strict';

(function initBackfrontDealsForms() {
  if (!window.BackfrontReact || !window.BackfrontDealsUtils) {
    console.error('[React] Runtime libraries are not loaded for deals forms');
    return;
  }

  const { html } = window.BackfrontReact;
  const { STAGES } = window.BackfrontDealsUtils();

  function DealCreateForm({ form, setForm, createDeal, savingId }) {
    return html`
        <section className="panel">
          <div className="section-title">Создать сделку</div>
          <form className="deal-form" onSubmit=${createDeal}>
            <input className="input wide" placeholder="Название сделки" value=${form.title} onChange=${(e) => setForm({ ...form, title: e.target.value })} />
            <select className="select" value=${form.stage} onChange=${(e) => setForm({ ...form, stage: e.target.value })}>
              ${STAGES.map(([value, label]) => html`<option key=${value} value=${value}>${label}</option>`)}
            </select>
            <input className="input" type="number" min="0" max="100" placeholder="Скоринг" value=${form.score} onChange=${(e) => setForm({ ...form, score: Number(e.target.value || 0) })} />
            <input className="input" type="number" min="0" placeholder="Сумма" value=${form.expected_value} onChange=${(e) => setForm({ ...form, expected_value: Number(e.target.value || 0) })} />
            <input className="input" type="number" min="0" max="1" step="0.05" placeholder="Вероятность" value=${form.probability} onChange=${(e) => setForm({ ...form, probability: Number(e.target.value || 0) })} />
            <input className="input" type="number" min="0" max="1" step="0.05" placeholder="Маржа 0–1" value=${form.margin} onChange=${(e) => setForm({ ...form, margin: Number(e.target.value || 0) })} />
            <input className="input" placeholder="Контакт" value=${form.contact_name} onChange=${(e) => setForm({ ...form, contact_name: e.target.value })} />
            <input className="input" placeholder="Компания" value=${form.company} onChange=${(e) => setForm({ ...form, company: e.target.value })} />
            <textarea className="input wide" rows="3" placeholder="Потребность / боль клиента" value=${form.need} onChange=${(e) => setForm({ ...form, need: e.target.value })}></textarea>
            <textarea className="input wide" rows="3" placeholder="Подходящий продукт / оффер" value=${form.product_match} onChange=${(e) => setForm({ ...form, product_match: e.target.value })}></textarea>
            <input className="input wide" placeholder="Следующее действие" value=${form.next_action} onChange=${(e) => setForm({ ...form, next_action: e.target.value })} />
            <button className="btn btn-active" type="submit" disabled=${savingId === 'new' || !form.title.trim()}>
              ${savingId === 'new' ? 'Создаю…' : 'Создать сделку'}
            </button>
          </form>
        </section>

    `;

  }

  window.BackfrontDealsForms = function BackfrontDealsForms() {
    return { DealCreateForm };
  };
})();
