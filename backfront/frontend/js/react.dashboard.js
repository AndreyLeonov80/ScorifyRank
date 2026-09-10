/* React dashboard page: lightweight operations view */
'use strict';

(function mountReactDashboardPage() {
  if (!window.React || !window.ReactDOM || !window.htm || !window.BackfrontReactShared || !window.BackfrontDashboardUtils) {
    console.error('[React] Runtime libraries are not loaded for Dashboard');
    return;
  }

  const React = window.React;
  const ReactDOM = window.ReactDOM;
  const html = window.htm.bind(React.createElement);
  const { PageHeader } = window.BackfrontReactShared;

  const {
    API_BASE,
    fmtTs,
    fmtNum,
    fmtBytes,
    fmtAge,
    badgeClass,
    apiJson,
    loadFallbackDashboardSummary,
  } = window.BackfrontDashboardUtils();

  function toneForRunning(running, error) {
    if (error) return 'red';
    return running ? 'yellow' : 'green';
  }

  function statusText(value, fallback = 'ожидание') {
    return String(value || fallback);
  }

  function DashboardLightPage() {
    const [summary, setSummary] = React.useState(null);
    const [loading, setLoading] = React.useState(false);
    const [status, setStatus] = React.useState({ tone: 'yellow', text: 'Загружаю состояние...' });
    const summaryInflightRef = React.useRef(false);

    const loadSummary = React.useCallback(async () => {
      if (summaryInflightRef.current) return summary;
      summaryInflightRef.current = true;
      setLoading(true);
      try {
        const data = await apiJson(`${API_BASE}/api/payme/dashboard/summary-lite`, {
          timeoutMs: 6000,
          dedupeKey: 'dashboard:summary-lite',
          cacheKey: 'dashboard:summary-lite:v1',
          cacheTtlMs: 2500,
          staleWhileRevalidate: true,
          onRevalidate: (fresh) => setSummary(fresh),
        });
        let nextSummary = data;
        try {
          const sourceRuntime = await apiJson(`${API_BASE}/api/payme/sources/runtime-status?page=1&page_size=500&sort_mode=status`, {
            timeoutMs: 5000,
            dedupeKey: 'dashboard:sources-runtime',
            cacheKey: 'dashboard:sources-runtime:v1',
            cacheTtlMs: 2500,
            staleWhileRevalidate: true,
          });
          const sourceItems = Array.isArray(sourceRuntime?.items) ? sourceRuntime.items : [];
          const totals = sourceRuntime?.summary || {};
          nextSummary = {
            ...data,
            scanned_sources: {
              items: sourceItems.map((source) => ({
                selector: source.selector,
                source: source.selector,
                title: source.title,
                source_type: 'telegram',
                chat_type: source.chat_type,
                status: source.status,
                status_label: source.status_reason || source.status,
                tone: source.status === 'reading' ? 'green' : source.status === 'error' ? 'red' : 'yellow',
                messages_count: source.duckdb_rows,
                read_messages_count: source.read_done,
                total_messages_estimate: source.read_total,
                remaining_messages_estimate: source.remaining,
                read_progress_percent: source.progress_percent,
                last_message_at: source.last_message_at,
                last_live_update_at: source.last_live_update_at,
                last_sync_at: source.last_worker_heartbeat_at,
                scan_group: source.scan_group,
                scan_group_label: source.scan_group_label,
                scan_group_frequency: source.scan_group_label,
                has_jsonl: source.has_jsonl,
              })),
              total: sourceRuntime?.total || sourceItems.length,
              totals: {
                selected_sources: totals.selected_sources || data?.counts?.selected_sources || 0,
                imported_sources: totals.imported_sources || data?.counts?.imported_sources || 0,
                active_sources: totals.active_sources || 0,
                pending_sources: totals.pending_sources || 0,
                waiting_sources: totals.waiting_sources || 0,
                error_sources: totals.error_sources || 0,
                empty_sources: totals.empty_sources || 0,
                messages_count: totals.messages_total || data?.counts?.messages || 0,
              },
              message: `Выбрано источников: ${totals.selected_sources || 0}; активных ${totals.active_sources || 0}; ожидают ${totals.pending_sources || 0}; сообщений ${totals.messages_total || 0}`,
            },
          };
        } catch (sourceError) {
          console.warn('Dashboard source runtime failed:', sourceError);
        }
        setSummary(nextSummary);
        setStatus({ tone: 'green', text: 'Dashboard обновлён' });
        return nextSummary;
      } catch (error) {
        const fallback = await loadFallbackDashboardSummary(50);
        setSummary(fallback);
        setStatus({ tone: 'yellow', text: `Показан быстрый fallback: ${error.message}` });
        return fallback;
      } finally {
        summaryInflightRef.current = false;
        setLoading(false);
      }
    }, [summary]);

    React.useEffect(() => {
      let cancelled = false;
      let timer = null;
      loadSummary().catch((error) => {
        if (!cancelled) setStatus({ tone: 'red', text: `Не удалось загрузить dashboard: ${error.message}` });
      });
      timer = window.setInterval(() => {
        if (document.hidden || summaryInflightRef.current) return;
        loadSummary().catch((error) => {
          console.warn('Dashboard background refresh failed:', error);
        });
      }, 30000);
      return () => {
        cancelled = true;
        if (timer) window.clearInterval(timer);
      };
    }, [loadSummary]);

    const runtime = summary?.runtime || {};
    const server = summary?.server || {};
    const counts = summary?.counts || {};
    const storage = summary?.storage || {};
    const telegram = summary?.telegram || {};
    const importSync = summary?.import_sync || {};
    const duckdbSync = summary?.duckdb_sync || summary?.duckdb || {};
    const telegramSyncJob = summary?.telegram_sync_job || summary?.telegram?.job || {};
    const scannedSources = summary?.scanned_sources || {};
    const scannedSourceTotals = scannedSources.totals || {};

    const progress = Math.max(0, Math.min(100, Number(duckdbSync.progress_percent || 0)));
    const transferredPercent = Math.round(progress);
    const remainingPercent = Math.max(0, 100 - transferredPercent);
    const etaText = duckdbSync.running && progress > 0 ? 'ETA считается по скорости текущего прохода' : 'ETA появится после старта очереди';
    const duckdbFilesTotal = Math.max(0, Number(duckdbSync.source_files_total || duckdbSync.progress_total || 0));
    const duckdbFilesDone = Math.max(0, Number(duckdbSync.source_files_indexed || duckdbSync.progress_current || 0));
    const duckdbFilesLeft = Math.max(0, duckdbFilesTotal - duckdbFilesDone);
    const duckdbBytesTotal = Math.max(0, Number(duckdbSync.bytes_total || 0));
    const duckdbBytesDone = Math.max(0, Number(duckdbSync.bytes_processed || 0));
    const duckdbBytesLeft = Math.max(0, duckdbBytesTotal - duckdbBytesDone);
    const selectedSourcesCount = Number(scannedSourceTotals.selected_sources || scannedSources.total || 0);
    const telegramJobStatus = String(telegramSyncJob.status || '').toLowerCase();
    const telegramJobRunning = ['running', 'queued', 'pending'].includes(telegramJobStatus);
    const telegramJobFailed = ['failed', 'error'].includes(String(telegramSyncJob.status || '').toLowerCase());
    const telegramWorkerDone = Number(telegramSyncJob.chunks_done || 0);
    const telegramWorkerRawTotal = Number(telegramSyncJob.chunks_total || selectedSourcesCount || 0);
    const telegramWorkerTotal = selectedSourcesCount > 0 && telegramWorkerRawTotal > selectedSourcesCount
      ? selectedSourcesCount
      : telegramWorkerRawTotal;
    const activeSourcesCount = Math.max(Number(scannedSourceTotals.active_sources || 0), telegramJobRunning ? telegramWorkerDone : 0);
    const pendingSourcesCount = telegramJobRunning && telegramWorkerTotal > 0
      ? Math.max(0, telegramWorkerTotal - Math.max(telegramWorkerDone, activeSourcesCount))
      : Number(scannedSourceTotals.pending_sources || 0);
    const scheduleWaitHint = selectedSourcesCount > 0 && activeSourcesCount === 0 && !telegramJobRunning
      ? telegramJobFailed
        ? `Telegram sync остановился с ошибкой: ${telegramSyncJob.error || telegramSyncJob.progress_label || 'unknown'}.`
        : 'Источники выбраны, но активного чтения прямо сейчас нет. Когда worker возьмет источник в работу, статус изменится на “читает”.'
      : '';
    const importSyncWaitHint = Number(importSync.pending_dialogs || 0) > 0 && Number(importSync.active_dialogs || 0) === 0 && !telegramJobRunning
      ? `В очереди ${fmtNum(importSync.pending_dialogs || 0, 0)} источников, активных сейчас ${fmtNum(importSync.active_dialogs || 0, 0)}.`
      : '';
    const telegramJobSummary = telegramJobRunning
      ? (telegramSyncJob.progress_label || `Telegram worker читает источники: ${fmtNum(telegramSyncJob.chunks_done || 0, 0)} / ${fmtNum(telegramSyncJob.chunks_total || selectedSourcesCount || 0, 0)}`)
      : '';
    const telegramWorkerActivity = telegramJobRunning
      ? `${telegramJobSummary} · heartbeat ${fmtAge(telegramSyncJob.updated_at)}`
      : telegramJobFailed
        ? `Telegram worker остановился: ${telegramSyncJob.error || telegramSyncJob.progress_label || 'ошибка'}`
        : '';
    const headerSyncStatus = telegramWorkerActivity || (
      selectedSourcesCount
        ? `Telegram sync: выбрано ${fmtNum(selectedSourcesCount, 0)}, активных ${fmtNum(activeSourcesCount, 0)}, ожидают ${fmtNum(pendingSourcesCount, 0)}.`
        : 'Telegram sync: источники не выбраны.'
    );
    const noActiveTelegramSourcesMessage = runtime.connected === false
      ? `Telegram сейчас не подключён: ${runtime.auth_message || runtime.auth_status || runtime.auth_step || 'нужна авторизация/переподключение'}. Пока соединения нет, worker не может читать источники.`
      : telegramJobRunning
        ? 'Worker запущен, но сейчас не отдал активный setup/backfill источник. Обновляю статус по heartbeat.'
        : 'Сейчас нет активного чтения Telegram. Если включён безлимит, источники попадут сюда после запуска worker и подключения Telegram.';

    return html`
      <div className="page">
        <${PageHeader}
          title="X-Files Dashboard"
          subtitle="Короткая оперативная панель: что сканируется, что сейчас выполняется и где есть ошибки."
          active="dashboard"
          statusSlot=${headerSyncStatus}
        />

        <section className="toolbar">
          <div className="toolbar-group">
            <span className=${badgeClass(status.tone)}>${status.text}</span>
            <span className="subtle">Snapshot: <strong>${fmtTs(summary?.ts)}</strong></span>
          </div>
        </section>

        <section className="panel">
          <div className="section-title">Состояние сейчас</div>
          <div className="stats">
            <div className="stat">Backend<strong>${server.ok === false ? 'ошибка' : 'работает'}</strong><small>${runtime.auth_status || runtime.auth_step || 'runtime ok'}</small></div>
            <div className="stat">Telegram / Import<strong>${telegramJobFailed ? 'worker ошибка' : telegramJobRunning ? 'читает' : statusText(importSync.status || telegram.sync_control?.status)}</strong><small>${telegramJobFailed ? (telegramSyncJob.error || telegramSyncJob.progress_label || 'последняя задача упала') : telegramJobSummary || (telegram.flood_wait?.active ? 'FloodWait активен' : 'без FloodWait')}</small></div>
            <div className="stat">DuckDB / база<strong>${duckdbSync.running ? 'sync идёт' : (duckdbSync.message_rows ? 'готова' : 'ожидание')}</strong><small>${fmtNum(duckdbSync.message_rows || 0, 0)} сообщений</small></div>
            <div className="stat">Чаты<strong>${fmtNum(counts.leads || scannedSourceTotals.selected_sources || 0, 0)}</strong><small>источники и лиды</small></div>
            <div className="stat">JSONL<strong>${fmtBytes(storage.jsonl_bytes || 0)}</strong><small>локальные первичные данные</small></div>
            <div className="stat">DuckDB файл<strong>${fmtBytes(storage.duckdb_bytes || 0)}</strong><small>${storage.duckdb_path || duckdbSync.db_path || 'путь не получен'}</small></div>
            <div className="stat">JSONL → DuckDB<strong>${fmtNum(duckdbFilesDone, 0)} / ${fmtNum(duckdbFilesTotal, 0)}</strong><small>осталось файлов: ${fmtNum(duckdbFilesLeft, 0)}</small></div>
            <div className="stat">Перекачано<strong>${transferredPercent}%</strong><small>осталось ${remainingPercent}% · ${duckdbBytesTotal ? `${fmtBytes(duckdbBytesDone)} / ${fmtBytes(duckdbBytesTotal)}` : `${fmtNum(duckdbSync.message_rows || 0, 0)} сообщений в DuckDB`}</small></div>
          </div>
          <div style=${{ padding: '0 16px 16px' }}>
            <div className="subtle">progress ${Math.round(progress)}% · ETA: ${etaText}</div>
            <div className="progress-track"><div className="progress-bar" style=${{ width: `${Math.max(2, progress)}%` }}></div></div>
          </div>
          ${scheduleWaitHint ? html`
            <div className="subtle" style=${{ padding: '0 16px 16px', color: '#92400e' }}>
              ${scheduleWaitHint}${importSyncWaitHint ? ` ${importSyncWaitHint}` : ''}
            </div>
          ` : null}
        </section>

        <div className="footer-note">Dashboard оставлен лёгким: состояние, краткий Sync-статус, progress/ETA и статистика JSONL → DuckDB. Таблица источников находится на Sync.</div>
      </div>
    `;
  }

  function mount() {
    const rootNode = document.getElementById('app');
    if (!rootNode) {
      console.error('[React] #app root was not found for Dashboard page');
      return;
    }
    const root = ReactDOM.createRoot(rootNode);
    root.render(html`<${DashboardLightPage} />`);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
