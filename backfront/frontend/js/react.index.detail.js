/* Shared detail/log components for React index page */
'use strict';

(function initReactIndexDetail() {
  window.BackfrontIndexDetail = function BackfrontIndexDetail({ React, html, normalizeAnalysisText, formatEta }) {
  function AnalysisFormattedText({ text }) {
    const clean = normalizeAnalysisText(text);
    if (!clean) return null;
    const blocks = clean.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
    return html`
      <div className="analysis-formatted">
        ${blocks.map((block, index) => {
          const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
          const tableLines = lines.filter((line) => line.includes('|'));
          if (tableLines.length >= 2) {
            const rows = tableLines
              .map((line) => line.split('|').map((cell) => cell.trim()).filter((cell) => cell && !/^-+$/.test(cell)))
              .filter((row) => row.length >= 2);
            if (rows.length >= 2) {
              const [head, ...body] = rows;
              return html`
                <table key=${`table-${index}`}>
                  <thead><tr>${head.map((cell, i) => html`<th key=${i}>${cell}</th>`)}</tr></thead>
                  <tbody>
                    ${body.map((row, r) => html`<tr key=${r}>${row.map((cell, c) => html`<td key=${c}>${cell}</td>`)}</tr>`)}
                  </tbody>
                </table>
              `;
            }
          }
          if (lines.length > 1 && lines.every((line) => /^(-|\*|•|\d+\.)\s+/.test(line))) {
            return html`
              <ul key=${`list-${index}`}>
                ${lines.map((line, i) => html`<li key=${i}>${line.replace(/^(-|\*|•|\d+\.)\s+/, '')}</li>`)}
              </ul>
            `;
          }
          return html`<p key=${`p-${index}`}>${lines.join(' ')}</p>`;
        })}
      </div>
    `;
  }

  function formatDetailValue(value) {
    if (value === null || typeof value === 'undefined') return '';
    if (typeof value === 'string') return value;
    try {
      return JSON.stringify(value, null, 2);
    } catch (_) {
      return String(value);
    }
  }

  function DetailPopup({ open, title, subtitle, body, onClose, size = 'wide' }) {
    if (!open) return null;
    const sizeClass = size === 'full' ? 'detail-popup-full' : 'detail-popup-wide';
    return html`
      <div className="detail-popup-backdrop chat-analysis-detail-popup" role="presentation" onClick=${onClose}>
        <div
          className=${`detail-popup ${sizeClass}`}
          role="dialog"
          aria-modal="true"
          aria-label=${title}
          onClick=${(event) => event.stopPropagation()}
        >
          <div className="detail-popup-head">
            <div>
              <div className="detail-popup-title">${title}</div>
              ${subtitle ? html`<div className="detail-popup-subtitle">${subtitle}</div>` : null}
            </div>
            <button className="btn" type="button" onClick=${onClose}>Закрыть</button>
          </div>
          <div className="detail-popup-body">${body}</div>
        </div>
      </div>
    `;
  }

  function LlmLogRows({ rows, emptyText = 'Лог появится здесь во время анализа.' }) {
    const items = Array.isArray(rows) ? rows : [];
    if (!items.length) return html`<div className="chat-analysis-empty">${emptyText}</div>`;
    return html`
      <div className="detail-log-list">
        ${items.map((line, index) => {
          const detailText = formatDetailValue(line.details);
          return html`
            <article className="detail-log-row" key=${`${line.ts}-${index}`}>
              <div className="detail-log-meta">
                <span className="muted">${line.ts}</span>
                <span className=${`badge ${line.kind === 'error' ? 'badge-error' : line.kind === 'response' ? 'badge-green' : line.kind === 'request' ? 'badge-blue' : 'badge-pending'}`}>
                  ${line.kind || 'status'}
                </span>
              </div>
              <div className="detail-log-message">${line.message}</div>
              ${detailText ? html`<pre className="detail-log-pre">${detailText}</pre>` : null}
            </article>
          `;
        })}
      </div>
    `;
  }

  function compactText(value, max = 1800) {
    const text = String(value || '');
    return text.length > max ? `${text.slice(0, max)}\n\n…лог обрезан, откройте полный файл.` : text;
  }

  function logFileHref(line, index = 0, scope = 'llm') {
    const payload = {
      scope,
      index,
      exported_at: new Date().toISOString(),
      ts: line?.ts || '',
      kind: line?.kind || 'status',
      message: line?.message || '',
      details: line?.details ?? null,
    };
    return `data:text/plain;charset=utf-8,${encodeURIComponent(JSON.stringify(payload, null, 2))}`;
  }

  function LlmLogNavigator({ state, rows, scope = 'llm' }) {
    const items = Array.isArray(rows) ? rows : [];
    const [index, setIndex] = React.useState(0);
    const [fullLog, setFullLog] = React.useState(null);
    React.useEffect(() => {
      setIndex(0);
    }, [items.length, state?.running, state?.refreshing]);
    if (!items.length) return html`<div className="chat-analysis-empty">Лог появится здесь во время анализа.</div>`;
    const safeIndex = Math.min(Math.max(0, index), items.length - 1);
    const line = items[safeIndex];
    const detailText = formatDetailValue(line?.details);
    const fullText = [
      `${line?.ts || ''} ${line?.kind || 'status'}`,
      line?.message || '',
      detailText,
    ].filter(Boolean).join('\n\n');
    const running = !!(state?.running || state?.refreshing);
    const percent = running ? Math.max(8, Math.min(99, Number(state?.progressPercent || 35))) : Number(state?.progressPercent || 0);
    return html`
      <div className="detail-popup-stack">
        ${running ? html`
          <div className="analysis-progress">
            <div className="row">
              <strong>${state?.refreshing ? 'Обновление анализа выполняется' : 'LLM анализ выполняется'}</strong>
              <span className="muted">${Math.round(percent)}% · ETA ${formatEta(state?.progressEtaSec || 300)}</span>
            </div>
            <div className="muted" style=${{ marginTop: '6px' }}>${state?.progressStatus || 'Ожидаем следующий статус…'}</div>
            <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${percent}%` }}></div></div>
          </div>
        ` : null}
        <div className="row" style=${{ justifyContent: 'flex-start', flexWrap: 'wrap' }}>
          <button className="btn" type="button" disabled=${safeIndex >= items.length - 1} onClick=${() => setIndex((value) => Math.min(items.length - 1, value + 1))}>
            Предыдущий лог
          </button>
          <span className="chip">${safeIndex + 1} / ${items.length}</span>
          <button className="btn" type="button" disabled=${safeIndex <= 0} onClick=${() => setIndex((value) => Math.max(0, value - 1))}>
            Следующий лог
          </button>
          <a className="btn" href=${logFileHref(line, safeIndex, scope)} download=${`${scope}-${safeIndex + 1}.log`} target="_blank" rel="noreferrer">
            Log файл
          </a>
        </div>
        <article className="detail-log-row">
          <div className="detail-log-meta">
            <span className="muted">${line?.ts || ''}</span>
            <span className=${`badge ${line?.kind === 'error' ? 'badge-error' : line?.kind === 'response' ? 'badge-green' : line?.kind === 'request' ? 'badge-blue' : 'badge-pending'}`}>
              ${line?.kind || 'status'}
            </span>
          </div>
          <div className="detail-log-message">${line?.message || ''}</div>
          ${detailText ? html`<pre className="detail-log-pre">${compactText(detailText)}</pre>` : null}
          ${fullText.length > 1800 ? html`
            <button className="btn" type="button" style=${{ marginTop: '10px' }} onClick=${() => setFullLog({ line, text: fullText, index: safeIndex })}>
              Открыть полный лог
            </button>
          ` : null}
        </article>
        <${DetailPopup}
          open=${!!fullLog}
          title="Полный лог"
          subtitle=${fullLog ? `Запись ${fullLog.index + 1} из ${items.length}` : ''}
          onClose=${() => setFullLog(null)}
          body=${fullLog ? html`
            <div className="detail-popup-stack">
              <a className="btn" href=${logFileHref(fullLog.line, fullLog.index, scope)} download=${`${scope}-${fullLog.index + 1}.log`} target="_blank" rel="noreferrer">Открыть log файл</a>
              <pre className="detail-log-pre">${fullLog.text}</pre>
            </div>
          ` : null}
        />
      </div>
    `;
  }

  function LlmLogPopupBody({ state, rows }) {
    const running = !!(state?.running || state?.refreshing);
    const percent = running ? Math.max(8, Math.min(99, Number(state?.progressPercent || 35))) : 0;
    const eta = running ? formatEta(state?.progressEtaSec || state?.timeout_sec || 300) : '';
    return html`
      <div className="detail-popup-stack">
        ${running ? html`
          <div className="analysis-progress">
            <div className="row">
              <strong>${state?.refreshing ? 'Обновление анализа выполняется' : 'LLM анализ выполняется'}</strong>
              <span className="muted">${Math.round(percent)}% · ETA ${eta}</span>
            </div>
            <div className="muted" style=${{ marginTop: '6px' }}>${state?.progressStatus || 'Ожидаем следующий статус…'}</div>
            <div className="analysis-progress-track"><div className="analysis-progress-bar" style=${{ width: `${percent}%` }}></div></div>
          </div>
        ` : null}
        <${LlmLogRows} rows=${rows} />
      </div>
    `;
  }


    return {
      AnalysisFormattedText,
      DetailPopup,
      LlmLogRows,
      LlmLogNavigator,
      LlmLogPopupBody,
      logFileHref,
    };
  };
})();
