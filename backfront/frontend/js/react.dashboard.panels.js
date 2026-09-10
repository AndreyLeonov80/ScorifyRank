/* React dashboard reusable panels */
'use strict';

(function initBackfrontDashboardPanels() {
  if (!window.React || !window.htm || !window.BackfrontDashboardUtils) {
    console.error('[React] Runtime libraries are not loaded for Dashboard panels');
    return;
  }

  const React = window.React;
  const html = window.htm.bind(React.createElement);
  const {
    fmtTs,
    fmtNum,
    fmtFutureDuration,
    toneClass,
    badgeClass,
  } = window.BackfrontDashboardUtils();

  function Card({ card }) {
    return html`
      <div className=${`card ${toneClass(card.tone)}`}>
        <div className="card-label">${card.title}</div>
        <div className="card-value">${card.value}</div>
        <div className="card-sub">${card.sub}</div>
      </div>
    `;
  }

  function LogList({ rows, emptyText }) {
    return html`
      <div className="stack">
        ${rows.length
          ? rows.map((row, idx) => html`<div key=${`row-${idx}`} className="subtle" style=${{ padding: '8px 0', borderBottom: idx < rows.length - 1 ? '1px solid #eef2f7' : 'none', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>${row}</div>`)
          : html`<div className="subtle">${emptyText}</div>`}
      </div>
    `;
  }

  function TaskRow({ task }) {
    const tone = task.status === 'error' ? 'red' : ((task.status === 'running' || task.status === 'stale') ? 'yellow' : 'green');
    const progress = Math.max(0, Math.min(100, Number(task.progress_percent || 0)));
    return html`
      <div className=${`task-row ${toneClass(tone)}`}>
        <div className="task-top">
          <div>
            <div className="task-name">${task.label || task.kind || 'Задача'}</div>
            <div className="task-summary">${task.summary || '—'}</div>
          </div>
          <div className=${badgeClass(tone)}>${task.status || 'idle'}</div>
        </div>
        <div className="progress-track"><div className="progress-bar" style=${{ width: `${progress}%` }}></div></div>
        <div className="task-meta">
          ${task.progress_total > 0 ? `Прогресс: ${task.progress_current} / ${task.progress_total}` : `Строк кеша: ${task.total_rows || 0}`}
          ${task.current_item ? ` · Текущий: ${task.current_item}` : ''}
          ${task.last_refresh_at ? ` · Последнее обновление: ${fmtTs(task.last_refresh_at)}` : ''}
        </div>
      </div>
    `;
  }

  function TelegramCollectionPanel({
    summary,
    runtime,
    importSync,
    telegramFloodWait,
    telegramRateLimits,
    telegramSyncControl,
  }) {
    const cooldowns = Object.values(telegramRateLimits?.operation_cooldowns || {})
      .filter((item) => item && (item.active || item.status === 'cooldown' || item.status === 'risk_rate_limited'))
      .sort((a, b) => Number(b.remaining_sec || 0) - Number(a.remaining_sec || 0));
    const cooldown = cooldowns[0] || null;
    const floodActive = Boolean(telegramFloodWait?.active);
    const syncPaused = Boolean(telegramSyncControl?.paused);
    const connected = Boolean(runtime?.connected);
    const authStatus = String(runtime?.auth_status || '');
    const selectedSourceCount = Number(
      importSync?.selected_sources
        || importSync?.source_count
        || importSync?.configured_sources
        || summary?.telegram?.selected_sources
        || summary?.telegram?.source_count
        || summary?.counts?.selected_sources
        || summary?.counts?.sources
        || 0
    );
    const rawTotalDialogs = Number(importSync?.total_dialogs || importSync?.total_sources || 0);
    const totalDialogs = selectedSourceCount > 0 && rawTotalDialogs > selectedSourceCount
      ? selectedSourceCount
      : Math.max(rawTotalDialogs, selectedSourceCount);
    const completedDialogs = Number(importSync?.completed_dialogs || 0);
    const activeDialogs = Number(importSync?.active_dialogs || 0);
    const pendingDialogs = Number(importSync?.pending_dialogs || Math.max(0, totalDialogs - completedDialogs));
    const processedUnits = Number(importSync?.processed_units || 0);
    const totalUnits = Number(importSync?.total_units || 0);
    const directProgress = Number(importSync?.progress_percent);
    const progress = Number.isFinite(directProgress) && directProgress > 0
      ? directProgress
      : (totalDialogs > 0 ? (completedDialogs / Math.max(1, totalDialogs)) * 100 : 0);
    const lastTelegramLog = (summary?.previews?.telegram_logs || [])[0] || null;

    let tone = 'yellow';
    let status = 'Ожидаем';
    let reason = 'Ожидаем первый snapshot backend.';
    let eta = 'ETA появится после начала чтения Telegram.';

    if (!summary) {
      reason = 'Dashboard ещё получает данные от backend.';
    } else if (authStatus === 'needs_api_credentials') {
      tone = 'red';
      status = 'Нужны настройки';
      reason = 'Не заполнены Telegram api_id/api_hash. Откройте Настройки или setup_wizard.';
      eta = 'До заполнения Telegram API credentials.';
    } else if (authStatus === 'needs_auth') {
      tone = 'red';
      status = 'Нужна авторизация';
      reason = runtime?.auth_message || 'Telegram просит телефон, код или 2FA пароль.';
      eta = 'До завершения авторизации Telegram.';
    } else if (floodActive) {
      tone = 'red';
      status = 'Telegram FloodWait';
      reason = telegramFloodWait?.reason || 'Telegram временно ограничил получение сообщений.';
      eta = `Можно продолжить после ${fmtTs(telegramFloodWait?.can_fetch_after || telegramFloodWait?.until)} · ${fmtFutureDuration(telegramFloodWait?.remaining_sec || 0)}`;
    } else if (cooldown) {
      tone = String(cooldown.status || '').includes('risk') ? 'red' : 'yellow';
      status = 'Telegram cooldown';
      reason = `${cooldown.operation || 'Telegram API'} · ${cooldown.context || cooldown.reason || 'backoff активен'}`;
      eta = `Повтор после ${fmtTs(cooldown.can_fetch_after || cooldown.retry_after)} · ${fmtFutureDuration(cooldown.remaining_sec || 0)}`;
    } else if (syncPaused) {
      tone = 'yellow';
      status = 'Сканирование на паузе';
      reason = telegramSyncControl?.reason || 'Telegram sync приостановлен вручную.';
      eta = 'До ручного возобновления.';
    } else if (connected && activeDialogs > 0) {
      tone = 'green';
      status = 'Получаем сообщения';
      reason = `Активных источников сейчас: ${activeDialogs}. Данные попадают в JSONL/DuckDB и кеши страниц.`;
      eta = importSync?.eta_seconds ? fmtFutureDuration(importSync.eta_seconds) : 'Оценка появится после нескольких чанков.';
    } else if (connected && pendingDialogs > 0) {
      tone = 'yellow';
      status = 'Ждём очереди';
      reason = `Источники выбраны, осталось в очереди: ${pendingDialogs}.`;
      eta = importSync?.eta_seconds ? fmtFutureDuration(importSync.eta_seconds) : 'Оценка появится после старта очереди.';
    } else if (connected && totalDialogs > 0) {
      tone = 'green';
      status = 'Готово / idle';
      reason = 'Telegram подключён, выбранные источники сейчас не читаются или уже обработаны.';
      eta = 'Следующая проверка по расписанию групп сканирования.';
    } else if (connected && selectedSourceCount > 0) {
      tone = 'green';
      status = 'Источники выбраны';
      reason = `Выбрано источников: ${selectedSourceCount}. Сейчас нет активного чтения, но Docker будет продолжать фоновые задачи по расписанию.`;
      eta = 'Следующая проверка по расписанию групп сканирования.';
    } else if (connected) {
      tone = 'yellow';
      status = 'Нет источников';
      reason = 'Telegram подключён, но источники для сканирования не выбраны в Импорте/Сетке.';
      eta = 'Добавьте источники на странице Импорт.';
    } else {
      tone = 'red';
      status = 'Нет подключения';
      reason = runtime?.auth_message || 'Telegram не подключён. Проверьте VPN, api_id/api_hash и авторизацию.';
      eta = 'До восстановления подключения.';
    }

    const progressLabel = totalUnits > 0
      ? `${processedUnits.toLocaleString('ru-RU')} / ${totalUnits.toLocaleString('ru-RU')} сообщений`
      : (totalDialogs > 0
        ? `${completedDialogs.toLocaleString('ru-RU')} / ${totalDialogs.toLocaleString('ru-RU')} источников`
        : 'объём сообщений пока неизвестен');

    return html`
      <section className=${`panel ${toneClass(tone)}`} style=${{ marginTop: '12px', borderWidth: '1px' }}>
        <div className="task-top" style=${{ padding: '16px 16px 8px' }}>
          <div>
            <div className="section-title">Получение сообщений из Telegram</div>
            <div className="section-subtitle">${reason}</div>
          </div>
          <span className=${badgeClass(tone)}>${status}</span>
        </div>
        <div style=${{ padding: '0 16px 16px' }}>
          <div className="stats" style=${{ padding: 0 }}>
            <div className="stat">Прогресс<strong>${fmtNum(progress, 1)}%</strong><small>${progressLabel}</small></div>
            <div className="stat">ETA<strong>${eta}</strong><small>${importSync?.updated_at ? `обновлено ${fmtTs(importSync.updated_at)}` : 'ожидаем новые чанки'}</small></div>
            <div className="stat">Источники<strong>${totalDialogs || 0}</strong><small>активно ${activeDialogs || 0} · осталось ${pendingDialogs || 0}</small></div>
            <div className="stat">Последний лог<strong>${lastTelegramLog ? fmtTs(lastTelegramLog.ts) : '—'}</strong><small>${lastTelegramLog?.message || 'Telegram-логов пока нет'}</small></div>
          </div>
          <div className="progress-track" style=${{ marginTop: '12px' }}>
            <div className="progress-bar" style=${{ width: `${Math.max(0, Math.min(100, progress))}%` }}></div>
          </div>
        </div>
      </section>
    `;
  }

  function PreviewPanel({ title, total, rows, columns, limit }) {
    const safeRows = Array.isArray(rows) ? rows.slice(0, limit) : [];
    return html`
      <section className="panel">
        <div className="section-title">${title}</div>
        <div className="section-subtitle">В кеше: ${String(total || 0)} · preview: до ${limit} строк</div>
        <div className="mini-wrap">
          <table className="mini-table">
            <tbody>
              ${safeRows.length
                ? safeRows.map((row, idx) => html`<tr key=${`${title}-${idx}`}>${columns.map((col, colIdx) => html`<td key=${`${title}-${idx}-${colIdx}`}>${col(row)}</td>`)}</tr>`)
                : html`<tr><td colSpan=${columns.length} className="subtle">Данных пока нет.</td></tr>`}
            </tbody>
          </table>
        </div>
      </section>
    `;
  }


  window.BackfrontDashboardPanels = function BackfrontDashboardPanels() {
    return {
      Card,
      LogList,
      TaskRow,
      TelegramCollectionPanel,
      PreviewPanel,
    };
  };
})();
