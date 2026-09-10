/* Shared status panel renderer for legacy stores and React pages */
'use strict';

(function initBackfrontStatusPanel() {
  if (window.BackfrontStatusPanel) return;

  function escapeHtmlText(value) {
    return String(value == null ? '' : value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function statusBadgeClassByTone(tone) {
    if (tone === 'success') return 'badge-active';
    if (tone === 'error') return 'badge-pending';
    if (tone === 'loading') return 'badge-warn';
    return 'badge-archived';
  }

  function statusBadgeTextByTone(tone) {
    if (tone === 'success') return 'готово';
    if (tone === 'error') return 'ошибка';
    if (tone === 'loading') return 'анализ';
    return 'ожидание';
  }

  function statusProgressPercent(status) {
    return Math.max(0, Math.min(100, Number(status?.progress_percent || 0)));
  }

  function statusProgressLabel(status, fallbackRunning = 'Идёт обработка', fallbackIdle = 'Ожидание') {
    return status?.progress_label || (status?.running ? fallbackRunning : fallbackIdle);
  }

  function statusProgressCounterLabel(status, suffix = 'элементов') {
    const current = Number(status?.progress_current || 0);
    const total = Number(status?.progress_total || 0);
    if (total > 0) return `${current} из ${total} ${suffix}`;
    return status?.running ? 'Подсчитываю объём обработки…' : '—';
  }

  function statusProgressLogEntries(status) {
    return Array.isArray(status?.progress_log) ? status.progress_log : [];
  }

  function formatLogEntry(entry) {
    if (typeof entry === 'string') return entry;
    const ts = entry?.ts && window.fmtDate ? `${window.fmtDate(entry.ts, true)} ` : '';
    return `${ts}${entry?.message || ''}`;
  }

  function renderUnifiedStatusPanel(config = {}) {
    const compact = !!config.compact;
    const badgeClass = escapeHtmlText(config.badgeClass || 'badge-archived');
    const badgeText = escapeHtmlText(config.badgeText || 'ожидание');
    const statusMessage = escapeHtmlText(config.statusMessage || '');
    const nextRefreshLabel = escapeHtmlText(config.nextRefreshLabel || '—');
    const progressLabel = escapeHtmlText(config.progressLabel || 'Ожидание');
    const progressCounter = escapeHtmlText(config.progressCounter || '—');
    const progressPercent = Math.max(0, Math.min(100, Number(config.progressPercent || 0)));
    const currentItemLabel = escapeHtmlText(config.currentItemLabel || 'Текущий элемент');
    const currentItemValue = String(config.currentItemValue || '').trim();
    const progressLog = Array.isArray(config.progressLog) ? config.progressLog : [];
    const statusLog = Array.isArray(config.statusLog) ? config.statusLog : [];
    const progressLogTitle = escapeHtmlText(config.progressLogTitle || (compact ? 'Лог обработки' : ''));
    const logMaxHeight = escapeHtmlText(config.logMaxHeight || (compact ? '170px' : '240px'));
    const logRows = [...progressLog, ...statusLog.map(formatLogEntry)]
      .filter((entry) => String(entry || '').trim());

    const logRowsHtml = logRows.length
      ? logRows.map((entry) => `
          <div style="padding:4px 0; border-bottom:1px solid rgba(226,232,240,.8); line-height:1.45;">
            <span class="subtle">${escapeHtmlText(entry)}</span>
          </div>
        `).join('')
      : '<div class="subtle">Лог пока пуст.</div>';

    return `
      <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:${compact ? '10px' : '14px'}; flex-wrap:wrap;">
        <div>
          <div class="section-title" style="margin:0; padding:0;">Статус анализа</div>
          <div class="subtle">${statusMessage}</div>
          <div class="subtle">Следующее автообновление: <strong>${nextRefreshLabel}</strong></div>
          ${currentItemValue ? `<div class="subtle">${currentItemLabel}: <strong>${escapeHtmlText(currentItemValue)}</strong></div>` : ''}
        </div>
        <span class="badge ${badgeClass}">${badgeText}</span>
      </div>
      <div style="display:grid; gap:${compact ? '6px' : '8px'}; margin-top:${compact ? '10px' : '14px'};">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
          <strong>${progressLabel}</strong>
          <span class="subtle">${progressCounter}</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" style="width:${progressPercent}%;"></div>
        </div>
        <div class="subtle"><strong>${progressPercent.toFixed(1)}</strong>%</div>
      </div>
      <div style="display:grid; gap:6px; margin-top:${compact ? '10px' : '12px'};">
        ${progressLogTitle ? `<div class="subtle" style="font-weight:700; text-transform:uppercase; letter-spacing:.04em;">${progressLogTitle}</div>` : ''}
        <div style="max-height:${logMaxHeight}; overflow:auto; padding-right:6px;">
          ${logRowsHtml}
        </div>
      </div>
    `;
  }

  window.BackfrontStatusPanel = {
    escapeHtmlText,
    statusBadgeClassByTone,
    statusBadgeTextByTone,
    statusProgressPercent,
    statusProgressLabel,
    statusProgressCounterLabel,
    statusProgressLogEntries,
    renderUnifiedStatusPanel,
  };
})();
