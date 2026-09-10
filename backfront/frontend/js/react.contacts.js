/* React contacts page powered by legacy contactsApp store */
'use strict';

(function mountReactContactsPage() {
  if (!window.BackfrontReact || !window.BackfrontReactShared || !window.contactsApp) {
    console.error('[React] contactsApp runtime is unavailable');
    return;
  }

  const { React, ReactDOM, html, useLegacyStore, useDebouncedCallback } = window.BackfrontReact;
  const { HtmlBlock, StatusPanel, ErrorBox, PageHeader, TablePaginationFooter, OutreachToggle, LoadingNotice, DealActionButton, cleanDealText, firstNonEmpty } = window.BackfrontReactShared;

  function cleanResultText(value) {
    return String(value || '')
      .replace(/\r\n/g, '\n')
      .replace(/\*\*/g, '')
      .trim();
  }

  function splitTableCells(line) {
    return String(line || '')
      .trim()
      .replace(/^\|/, '')
      .replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.trim().replace(/<br\s*\/?>/gi, '\n'));
  }

  function isMarkdownSeparator(line) {
    return /^[\s|:-]+$/.test(String(line || '').trim()) && String(line || '').includes('-');
  }

  function QualificationResultContent({ text }) {
    const source = cleanResultText(text);
    if (!source) return html`<div className="contact-result-text">Пустой ответ</div>`;
    const lines = source.split('\n');
    const blocks = [];
    let currentTable = [];
    let currentText = [];
    const flushText = () => {
      const body = currentText.join('\n').replace(/<br\s*\/?>/gi, '\n').trim();
      if (body) blocks.push({ type: 'text', body });
      currentText = [];
    };
    const flushTable = () => {
      const rows = currentTable.filter((line) => !isMarkdownSeparator(line)).map(splitTableCells).filter((row) => row.length);
      if (rows.length) blocks.push({ type: 'table', rows });
      currentTable = [];
    };
    lines.forEach((line) => {
      const trimmed = String(line || '').trim();
      if (trimmed.startsWith('|') && trimmed.includes('|')) {
        flushText();
        currentTable.push(trimmed);
      } else {
        if (currentTable.length) flushTable();
        currentText.push(line);
      }
    });
    flushText();
    flushTable();

    return html`
      <div className="contact-result-content">
        ${blocks.map((block, index) => {
          if (block.type === 'table') {
            const [head, ...body] = block.rows;
            return html`
              <div className="qualification-table-wrap" key=${`table-${index}`}>
                <table className="qualification-result-table">
                  <thead>
                    <tr>${(head || []).map((cell, cellIndex) => html`<th key=${cellIndex}>${cell}</th>`)}</tr>
                  </thead>
                  <tbody>
                    ${body.map((row, rowIndex) => html`
                      <tr key=${rowIndex}>${row.map((cell, cellIndex) => html`<td key=${cellIndex}>${cell}</td>`)}</tr>
                    `)}
                  </tbody>
                </table>
              </div>
            `;
          }
          return html`
            <div className="contact-result-text" key=${`text-${index}`}>
              ${block.body.split('\n\n').map((part, partIndex) => html`<p key=${partIndex}>${part}</p>`)}
            </div>
          `;
        })}
      </div>
    `;
  }

  function QualificationProgress({ progress }) {
    if (!progress) return null;
    const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    const entries = Array.isArray(progress.log) ? progress.log : [];
    return html`
      <div className=${`qualification-progress ${progress.waiting ? 'qualification-progress-waiting' : ''}`}>
        <div className="qualification-progress-head">
          <div>
            <div className="font-semibold">${progress.label || 'Анализ выполняется'}</div>
            <div className="subtle">${progress.waiting ? 'Ожидаем ответ ...' : 'Выполняется запрос и обработка результата'}</div>
          </div>
          <span className="badge badge-pending">${percent.toFixed(0)}%</span>
        </div>
        <div className="qualification-progress-bar"><span style=${{ width: `${percent}%` }} /></div>
        <div className="qualification-progress-log">
          ${entries.length ? entries.map((entry) => html`
            <div key=${entry.id} className=${`qualification-progress-log-row qualification-progress-log-${entry.tone || 'info'}`}>
              <span>${window.fmtDate ? window.fmtDate(entry.ts, true) : ''}</span>
              <span>${entry.message}</span>
            </div>
          `) : html`<div className="subtle">Лог появится сразу после запуска.</div>`}
        </div>
      </div>
    `;
  }

  function ContactRow({ store, row }) {
    const rowSelected = store.selectedContact?.contact_key === row?.contact_key;
    const latestText = String(row.latest_message_text || row.latest_message_preview || '').trim();
    const firstMessageSuggestion = String(row.first_message_suggestion || '').trim();
    const productOfferSuggestion = String(row.product_offer_suggestion || '').trim();
    const payload = {
      field_type: 'telegram_contact',
      field_label: 'Контакт',
      value: String(row.display_name || row.contact_key || '').trim(),
      contact_key: row.contact_key || '',
      lead: row.latest_lead || '',
      source_selector: Array.isArray(row.source_selectors) ? (row.source_selectors[0] || '') : '',
      sender_name: row.display_name,
      sender_username: Array.isArray(row.usernames) ? (row.usernames[0] || '') : '',
      date_utc: row.last_message_at,
      text: latestText,
    };
    const latestMessagePayload = {
      field_type: 'message',
      field_label: 'Сообщение',
      value: latestText,
      contact_key: row.contact_key || '',
      lead: row.latest_lead || '',
      source_selector: Array.isArray(row.source_selectors) ? (row.source_selectors[0] || '') : '',
      sender_name: row.display_name,
      sender_username: Array.isArray(row.usernames) ? (row.usernames[0] || '') : '',
      date_utc: row.last_message_at,
      text: latestText,
    };
    const dealPayload = {
      title: firstNonEmpty([
        row.display_name ? `Контакт: ${row.display_name}` : '',
        row.contact_key ? `Контакт: ${row.contact_key}` : '',
        row.latest_lead ? `Контакт из ${row.latest_lead}` : '',
      ]),
      stage: 'lead',
      score: Number(row.deal_score || 0) || (Number(row.qualification_count || 0) > 0 ? 50 : 25),
      probability: Number(row.deal_score || 0) >= 70 ? 0.45 : Number(row.deal_score || 0) >= 45 ? 0.3 : 0.2,
      contact_key: row.contact_key || '',
      contact_name: firstNonEmpty([row.display_name, row.sender_name, row.sender_username]),
      source: 'contacts',
      source_chat: row.latest_lead || '',
      source_message_id: firstNonEmpty([row.latest_message_id, row.last_message_at, row.contact_key]),
      need: cleanDealText(latestText || '', 4000),
      product_match: productOfferSuggestion || row.best_product_hint || (Array.isArray(row.leads) ? `Чаты: ${row.leads.slice(0, 8).join(', ')}` : ''),
      next_action: row.why_now || 'Открыть историю контакта, квалифицировать потребность и подготовить первое сообщение',
      notes: [
        `Создано из Контактов. Сообщений: ${row.total_messages || 0}. Квалификаций: ${row.qualification_count || 0}.`,
        `Температура: ${row.lead_temperature_label || '—'}.`,
        `Score: ${row.score_explanation || row.deal_score || 0}.`,
        productOfferSuggestion ? `Что предложить: ${productOfferSuggestion}` : '',
        firstMessageSuggestion ? `Первое сообщение: ${firstMessageSuggestion}` : '',
        `Не хватает: ${row.missing_qualification || '—'}.`,
      ].filter(Boolean).join('\n'),
    };
    return html`
      <tr
        className=${rowSelected ? 'contacts-row-selected' : ''}
        onClick=${() => store.selectContact(row)}
      >
        <td>
          <div className="font-semibold">${row.display_name || '—'}</div>
          <div className="subtle cell-text">${row.contact_key}</div>
        </td>
        <td className="cell-text">${store.senderMetaLabel(row)}</td>
        <td><div className="font-semibold">${row.total_messages || 0}</div></td>
        <td>
          <span className=${`score-pill ${Number(row.deal_score || 0) >= 70 ? 'score-hot' : Number(row.deal_score || 0) >= 45 ? 'score-warm' : 'score-cold'}`}>
            ${row.lead_temperature_label || 'Нужно больше данных'}
          </span>
          <div className="subtle">score ${row.deal_score || 0}/100</div>
          <div className="subtle">fit ${row.fit_score || 0} · intent ${row.intent_score || 0}</div>
          ${Array.isArray(row.signal_tags) && row.signal_tags.length ? html`
            <div className="contact-signal-tags">
              ${row.signal_tags.map((tag) => html`<span className="badge badge-muted" key=${tag}>${tag}</span>`)}
            </div>
          ` : null}
        </td>
        <td><div className="cell-text">${store.listLabel(row.leads)}</div></td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
            ${row.do_not_contact
              ? html`<span className="badge badge-warn" title="Контакт исключён из ручного outreach">не писать</span>`
              : html`<${OutreachToggle} store=${store} payload=${latestMessagePayload} title="Добавить последнее сообщение в enReach" />`}
            <div className="cell-text">${row.latest_message_preview || '—'}</div>
          </div>
          <div className="subtle">${row.latest_lead || '—'}</div>
          ${firstMessageSuggestion ? html`
            <div className="first-message-suggestion">
              <div className="first-message-suggestion-label">Первое сообщение</div>
              <div className="cell-text">${firstMessageSuggestion}</div>
              <div className="subtle">
                ${row.first_message_model ? html`модель: ${row.first_message_model}` : null}
                ${row.first_message_updated_at ? html`${row.first_message_model ? ' · ' : ''}${window.fmtDate ? window.fmtDate(row.first_message_updated_at, true) : row.first_message_updated_at}` : null}
              </div>
            </div>
          ` : null}
          ${productOfferSuggestion ? html`
            <div className="product-offer-suggestion">
              <div className="first-message-suggestion-label">Что предложить</div>
              <div className="cell-text">${productOfferSuggestion}</div>
              <div className="subtle">
                ${row.product_offer_model ? html`модель: ${row.product_offer_model}` : null}
                ${row.product_offer_updated_at ? html`${row.product_offer_model ? ' · ' : ''}${window.fmtDate ? window.fmtDate(row.product_offer_updated_at, true) : row.product_offer_updated_at}` : null}
              </div>
            </div>
          ` : null}
        </td>
        <td>
          <div className="subtle">С: <span>${window.fmtDate ? window.fmtDate(row.first_message_at, true) : (row.first_message_at || '—')}</span></div>
          <div className="subtle">По: <span>${window.fmtDate ? window.fmtDate(row.last_message_at, true) : (row.last_message_at || '—')}</span></div>
        </td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
            ${row.do_not_contact
              ? html`<span className="badge badge-warn" title=${row.do_not_contact_reason || 'Контакт исключён из ручного outreach'}>do_not_contact</span>`
              : html`<${OutreachToggle} store=${store} payload=${payload} title="Добавить контакт в enReach" />`}
            ${Number(row.qualification_count || 0) > 0 ? html`
              <span className="badge badge-active">${row.qualification_count} анализ</span>
            ` : null}
            <${DealActionButton}
              payload=${dealPayload}
              label="Создать сделку"
              title="Создать сделку из контакта"
            />
            <button className="btn" onClick=${(e) => { e.stopPropagation(); store.openQualificationDialog(row); }}>Квалифицировать</button>
            <button className="btn" onClick=${(e) => { e.stopPropagation(); store.nextMessagePlaceholder(row); }}>
              ${firstMessageSuggestion ? 'Показать сообщение' : 'Следующее сообщение'}
            </button>
            <button
              className=${`btn ${row.do_not_contact ? 'btn-active' : ''}`}
              disabled=${store.contactDoNotContactBusyKey === row.contact_key}
              title=${row.do_not_contact ? 'Вернуть контакт в ручные очереди enReach' : 'Исключить контакт и удалить его из enReach-очередей'}
              onClick=${(e) => {
                e.stopPropagation();
                store.toggleContactDoNotContact(row);
              }}
            >
              ${store.contactDoNotContactBusyKey === row.contact_key ? 'Сохраняю…' : (row.do_not_contact ? 'Можно писать' : 'Не писать')}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  function QualificationDialog({ store }) {
    if (!store.qualificationDialogOpen || !store.qualificationContact) return null;
    const contact = store.qualificationContact;
    return html`
      <div className="contact-modal-backdrop" role="presentation" onClick=${() => store.closeQualificationDialog()}>
        <div className="contact-modal" role="dialog" aria-modal="true" aria-label="Квалификация контакта" onClick=${(event) => event.stopPropagation()}>
          <div className="contact-modal-head">
            <div>
              <div className="contact-modal-title">Квалификация: ${contact.display_name || contact.contact_key}</div>
              <div className="subtle">${store.senderMetaLabel(contact)} · сообщений: ${contact.total_messages || 0}</div>
            </div>
            <button className="btn" onClick=${() => store.closeQualificationDialog()}>Закрыть</button>
          </div>
          <div className="contact-modal-body">
            ${store.qualificationError ? html`<div className="contact-modal-error">${store.qualificationError}</div>` : null}
            <div className="contact-template-list">
              ${(store.qualificationPrompts || []).map((prompt) => {
                const result = store.qualificationResultByTemplate(prompt.id);
                const busy = store.isQualificationBusyFor(prompt.id);
                const progress = String(store.qualificationProgress?.template_id || '') === String(prompt.id || '') ? store.qualificationProgress : null;
                const canRetry = !!progress?.waiting;
                return html`
                  <div className="contact-template-card" key=${prompt.id}>
                    <div className="contact-template-head">
                      <div>
                        <div className="font-semibold">${prompt.title || prompt.id}</div>
                        <div className="subtle contact-prompt-text">${prompt.prompt}</div>
                      </div>
                      <button
                        className="btn btn-active"
                        disabled=${!canRetry && (!!store.qualificationBusyTemplate || !!store.qualificationProgress)}
                        onClick=${() => {
                          if (canRetry) store.stopQualificationProgress();
                          window.setTimeout(() => store.qualifyContactWithTemplate(prompt), 0);
                        }}
                      >
                        ${canRetry ? 'Повторить' : (busy ? 'Ожидаем…' : (result ? 'Пересчитать' : 'Запустить'))}
                      </button>
                    </div>
                    <${QualificationProgress} progress=${progress} />
                    ${result ? html`
                      <div className=${`contact-result ${result.status === 'error' ? 'contact-result-error' : ''}`}>
                        <div className="subtle">
	                          ${result.status === 'error' ? 'Ошибка' : 'Готово'} ·
	                          ${result.updated_at ? (window.fmtDate ? window.fmtDate(result.updated_at, true) : result.updated_at) : '—'} ·
	                          ${result.model || 'model'} · сообщений: ${result.messages_count || 0}
	                          ${result.cache_hit ? ' · из кеша' : ''}
	                        </div>
                        <${QualificationResultContent} text=${result.status === 'error' ? (result.error || 'Ошибка анализа') : (result.result_text || 'Пустой ответ')} />
                      </div>
                    ` : null}
                  </div>
                `;
              })}
              ${!(store.qualificationPrompts || []).length ? html`<div className="empty">Шаблоны не настроены. Добавьте их в Настройках.</div>` : null}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  function ContactMessageRow({ store, row }) {
    const text = String(row.text || '').trim() || (row.has_media ? '[media без текста]' : '');
    const payload = {
      field_type: 'message',
      field_label: 'Сообщение',
      value: text,
      contact_key: store.selectedContact?.contact_key || '',
      lead: row.lead,
      source_selector: row.source_selector,
      sender_name: row.sender_name,
      sender_username: row.sender_username,
      message_id: row.message_id,
      date_utc: row.date_utc,
      text,
    };
    return html`
      <tr>
        <td>
          <div>${window.fmtDate ? window.fmtDate(row.date_utc, true) : (row.date_utc || '—')}</div>
          <div className="subtle">#${row.message_id}</div>
        </td>
        <td>
          <div className="font-semibold">${row.lead}</div>
          <div className="subtle cell-text">${row.source_selector || '—'}</div>
        </td>
        <td>
          <div style=${{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
            <${OutreachToggle} store=${store} payload=${payload} title="Добавить сообщение в enReach" />
            <div className="cell-text">${row.text || '—'}</div>
          </div>
        </td>
        <td>
          <span className=${`badge ${row.has_media ? 'badge-active' : 'badge-archived'}`}>
            ${row.has_media ? 'есть media' : 'без media'}
          </span>
        </td>
      </tr>
    `;
  }

  function BulkQualificationPanel({ store }) {
    const state = store.bulkQualification;
    if (!state) return null;
    const percent = store.bulkQualificationPercent ? store.bulkQualificationPercent() : 0;
    return html`
      <section className="panel" style=${{ borderColor: state.running ? '#bfdbfe' : '#bbf7d0', background: state.running ? 'rgba(239,246,255,.78)' : 'rgba(240,253,244,.78)' }}>
        <div style=${{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <div className="section-title">Массовая квалификация</div>
            <div className="subtle">
              ${state.running ? 'Идёт анализ видимых контактов' : 'Массовая квалификация завершена'} ·
              шаблон: <strong>${state.title || state.template_id}</strong>
            </div>
            <div className="subtle">
              Выполнено: <strong>${state.done || 0}/${state.total || 0}</strong> ·
              из кеша: <strong>${state.cached || 0}</strong> ·
              новых OpenRouter: <strong>${state.refreshed || 0}</strong> ·
              ошибок: <strong>${state.errors || 0}</strong>
              ${state.current ? html` · текущий: <strong>${state.current}</strong>` : null}
            </div>
          </div>
          <span className=${`badge ${state.running ? 'badge-warn' : 'badge-active'}`}>${state.running ? 'анализ' : 'готово'}</span>
        </div>
        <div className="qualification-progress-bar" style=${{ marginTop: '12px' }}><span style=${{ width: `${percent}%` }} /></div>
        <div className="subtle" style=${{ marginTop: '6px' }}>${percent}% · OpenRouter вызывается только если кеш устарел по fingerprint сообщений.</div>
        <div className="qualification-progress-log" style=${{ marginTop: '10px' }}>
          ${(state.log || []).map((entry) => html`
            <div key=${entry.id} className=${`qualification-progress-log-row qualification-progress-log-${entry.tone || 'info'}`}>
              <span>${window.fmtDate ? window.fmtDate(entry.ts, true) : ''}</span>
              <span>${entry.message}</span>
            </div>
          `)}
        </div>
      </section>
    `;
  }

  function ContactsPage() {
    const store = useLegacyStore(window.contactsApp);
    const [booted, setBooted] = React.useState(false);
    const debounceRowsReload = useDebouncedCallback(() => store.resetPage(), 300);
    const debounceMessagesReload = useDebouncedCallback(() => store.resetMessagesPage(), 300);

    React.useEffect(() => {
      let cancelled = false;
      Promise.resolve(store.init?.())
        .catch((error) => {
          console.error('[React] Contacts init failed:', error);
          store.error = String(error?.message || error);
        })
        .finally(() => {
          if (!cancelled) setBooted(true);
        });
      return () => {
        cancelled = true;
      };
    }, [store]);

    return html`
      <div className="page">
        <${PageHeader}
          title="Контакты"
          subtitle="Авторы сообщений из Telegram с кешированием на backend и историей связанных сообщений."
          active="contacts"
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '280px' }}
              type="text"
              placeholder="Поиск по имени, username, чату, тексту…"
              value=${store.ui.query}
              onChange=${(e) => {
                store.ui.query = e.target.value;
                debounceRowsReload();
              }}
            />
            <select
              className="select"
              style=${{ minWidth: '280px' }}
              value=${store.ui.leadFilter}
              onChange=${(e) => {
                store.ui.leadFilter = e.target.value;
                debounceRowsReload();
              }}
            >
              <option value="">Все чаты</option>
              ${(store.chatOptions || []).map((option) => html`
                <option key=${option.value} value=${option.value}>
                  ${store.chatOptionLabel(option)}
                </option>
              `)}
            </select>
            <select
              className="select"
              style=${{ minWidth: '240px' }}
              value=${store.ui.leadTemperatureFilter || 'all'}
              onChange=${(e) => {
                store.ui.leadTemperatureFilter = e.target.value;
                store.resetPage();
              }}
            >
              <option value="all">Все по температуре</option>
              <option value="hot">Горячие</option>
              <option value="warm">Тёплые</option>
              <option value="cold">Холодные</option>
              <option value="not_fit">Не подходит</option>
              <option value="needs_data">Нужно больше данных</option>
            </select>
            <select
              className="select"
              style=${{ minWidth: '240px' }}
              value=${store.ui.qualificationFilter || 'all'}
              onChange=${(e) => {
                store.ui.qualificationFilter = e.target.value;
                store.resetPage();
              }}
            >
              <option value="all">Все квалификации</option>
              <option value="qualified">Квалифицированные</option>
              ${(store.qualificationPrompts || []).map((prompt) => html`
                <option key=${prompt.id} value=${prompt.id}>
                  ${store.qualificationFilterLabel(prompt)}
                </option>
              `)}
            </select>
            <div className="toolbar-group contact-signal-filters" style=${{ gap: '6px' }}>
              ${store.signalFilterOptions().map((option) => html`
                <label className="chip" key=${option.value}>
                  <input
                    type="checkbox"
                    checked=${Array.isArray(store.ui.signalFilters) && store.ui.signalFilters.includes(option.value)}
                    onChange=${() => store.toggleSignalFilter(option.value)}
                  />
                  ${option.label}
                </label>
              `)}
            </div>
            <select
              className="select"
              style=${{ minWidth: '260px' }}
              value=${store.ui.bulkQualificationTemplate || ''}
              onChange=${(e) => { store.ui.bulkQualificationTemplate = e.target.value; }}
            >
              <option value="">Шаблон для массовой квалификации</option>
              ${(store.qualificationPrompts || []).map((prompt) => html`
                <option key=${prompt.id} value=${prompt.id}>
                  ${store.qualificationFilterLabel(prompt)}
                </option>
              `)}
            </select>
            <button
              className="btn btn-active"
              disabled=${store.bulkQualification?.running || !(store.rows || []).length}
              onClick=${() => store.qualifyVisibleContactsWithTemplate()}
            >
              ${store.bulkQualification?.running ? 'Квалифицирую…' : 'Квалифицировать видимые'}
            </button>
            <select
              className="select"
              value=${String(store.ui.pageSize)}
              onChange=${(e) => {
                store.ui.pageSize = Number(e.target.value);
                store.resetPage();
              }}
            >
              <option value="5">5 строк</option>
              <option value="10">10 строк</option>
              <option value="20">20 строк</option>
              <option value="50">50 строк</option>
              <option value="100">100 строк</option>
            </select>
            <button className="btn" onClick=${() => store.triggerRefresh()} disabled=${store.refreshing}>
              ${store.refreshing ? 'Запуск…' : 'Обновить контакты'}
            </button>
          </div>
          <div className="toolbar-group">
            <label className="chip"><input type="checkbox" checked=${store.ui.autoRefreshEnabled} onChange=${(e) => { store.ui.autoRefreshEnabled = e.target.checked; store.saveAutoRefreshConfig(); }} /> Автообновление</label>
            <select
              className="select"
              value=${String(store.ui.autoRefreshIntervalSec)}
              onChange=${(e) => {
                store.ui.autoRefreshIntervalSec = Number(e.target.value);
                store.saveAutoRefreshConfig();
              }}
            >
              <option value="30">30 сек</option>
              <option value="60">1 мин</option>
              <option value="300">5 мин</option>
              <option value="900">15 мин</option>
              <option value="1800">30 мин</option>
            </select>
            <span className="subtle">В кеше: <strong>${store.cacheStatus?.total_rows ?? store.totalRows}</strong></span>
          </div>
        </section>

        <${ErrorBox} error=${store.error} tag="section" />
        <${BulkQualificationPanel} store=${store} />

        <section className="panel">
          <div className="section-title">Телеграм-контакты</div>
          <div className="section-subtitle subtle">Каждый контакт — это автор сообщений. Ниже можно открыть связанные с ним сообщения из разных чатов.</div>

          <div className="table-wrap contacts-table-wrap">
            ${store.loading && store.rows.length === 0 ? html`<${LoadingNotice} message="Собираю и группирую авторов сообщений…" details="Контакты строятся из сохранённого архива сообщений; новые Telegram-запросы идут только через фоновые очереди." />` : null}
            ${!store.loading && store.isBootstrapping() ? html`<div className="empty">Идёт первичная сборка кеша контактов по архиву сообщений. Контакты появятся автоматически, как только backend обработает первые чанки.</div>` : null}
            ${!store.loading && store.rows.length === 0 && !store.isBootstrapping() ? html`<div className="empty">Под текущие фильтры контакты не нашлись.</div>` : null}

            ${store.rows.length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Контакт</th>
                    <th>Username / id</th>
                    <th>Сообщений</th>
                    <th>Температура</th>
                    <th>Чаты</th>
                    <th>Последнее сообщение</th>
                    <th>Даты</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.rows.map((row) => html`<${ContactRow} key=${row.contact_key} store=${store} row=${row} />`)}
                </tbody>
              </table>
            ` : null}
          </div>

          <${TablePaginationFooter}
            rangeText=${store.visibleRangeText()}
            page=${store.ui.page}
            totalPages=${store.totalRowPages}
            pageWindow=${store.pageWindow()}
            onPrev=${() => store.prevPage()}
            onNext=${() => store.nextPage()}
            onGo=${(page) => store.goToPage(page)}
          />
        </section>

        <section className="toolbar" style=${{ paddingTop: 0 }}>
          <div className="toolbar-group">
            <div className="section-title" style=${{ padding: 0 }}>${store.selectedTitle()}</div>
          </div>
          <div className="toolbar-group">
            <input
              className="input"
              style=${{ minWidth: '260px' }}
              type="text"
              placeholder="Фильтр по связанным сообщениям…"
              value=${store.ui.messagesQuery}
              onChange=${(e) => {
                store.ui.messagesQuery = e.target.value;
                debounceMessagesReload();
              }}
            />
            <input
              className="input"
              style=${{ minWidth: '220px' }}
              type="text"
              placeholder="Фильтр по чату…"
              value=${store.ui.messagesLeadFilter}
              onChange=${(e) => {
                store.ui.messagesLeadFilter = e.target.value;
                debounceMessagesReload();
              }}
            />
          </div>
        </section>

        <${ErrorBox} error=${store.messagesError} tag="section" />

        <section className="panel">
          <div className="section-title">Связанные сообщения контакта</div>
          <div className="section-subtitle subtle">Показываются сохранённые сообщения выбранного автора. Данные читаются из backend-кеша.</div>

          <div className="table-wrap messages-table-wrap">
            ${store.messagesLoading && store.messageRows.length === 0 ? html`<${LoadingNotice} message="Загружаю связанные сообщения…" details="Связанные сообщения читаются из backend-кеша контакта." />` : null}
            ${!store.messagesLoading && store.messageRows.length === 0 ? html`<div className="empty">Для выбранного контакта сообщений под текущие фильтры не нашлось.</div>` : null}

            ${store.messageRows.length > 0 ? html`
              <table>
                <thead>
                  <tr>
                    <th>Дата</th>
                    <th>Чат</th>
                    <th>Сообщение</th>
                    <th>Media</th>
                  </tr>
                </thead>
                <tbody>
                  ${store.messageRows.map((row) => html`<${ContactMessageRow} key=${`${row.lead}:${row.message_id}`} store=${store} row=${row} />`)}
                </tbody>
              </table>
            ` : null}
          </div>

          <div className="footer">
            <div className="subtle">Показано <strong>${store.messagesVisibleRangeText()}</strong></div>
            <div className="pagination">
              <button className="btn" onClick=${() => store.prevMessagesPage()} disabled=${store.ui.messagesPage <= 1}>Назад</button>
              ${store.messagesPageWindow().map((page) => html`
                <button
                  key=${page}
                  className=${`btn ${page === store.ui.messagesPage ? 'btn-active' : ''}`}
                  onClick=${() => store.goToMessagesPage(page)}
                >${page}</button>
              `)}
              <button className="btn" onClick=${() => store.nextMessagesPage()} disabled=${store.ui.messagesPage >= store.messagesTotalPages}>Вперёд</button>
            </div>
          </div>
        </section>

        <section className="panel contacts-status-panel">
          <${StatusPanel} config=${store.statusPanelConfig()} />
        </section>

        ${!booted && !store.error ? html`<div className="subtle" style=${{ padding: '0 20px 16px' }}>Инициализация React UI…</div>` : null}
        <${QualificationDialog} store=${store} />
      </div>
    `;
  }

  const root = document.getElementById('react-root');
  if (!root) {
    console.error('[React] Root container #react-root was not found');
    return;
  }

  ReactDOM.createRoot(root).render(html`<${ContactsPage} />`);
})();
