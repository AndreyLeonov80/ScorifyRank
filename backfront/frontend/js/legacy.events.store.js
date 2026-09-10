/* Legacy events store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.events.store.js");
    return;
  }
  with (ctx) {
  window.eventsApp = function eventsApp() {
    return {
      loading: false,
      saving: false,
      refreshing: false,
      deletingKey: '',
      error: null,
      statusMessage: 'Готов к поиску сообщений по мероприятиям.',
      statusTone: 'idle',
      statusLog: [],
      cacheStatus: null,
      _lastRefreshAt: null,
      _lastEventDateProcessed: null,
      _lastEventDateFound: null,
      _statusSeq: 0,
      keywordsText: '',
      keywords: [],
      rows: [],
      ui: {
        limit: 300,
        page: 1,
        pageSize: 5,
        autoRefreshEnabled: true,
        autoRefreshIntervalSec: 300,
        filter: '',
        leadFilter: '',
        senderFilter: '',
        keywordFilter: '',
        dateFrom: '',
        dateTo: '',
      },
      totalRows: 0,
      totalRowPages: 1,
      _timer: null,
      _statusStream: null,
      _streamState: 'idle',
      ...createOutreachToggleState(),

      async init() {
        await this.loadKeywords();
        await this.loadRows();
        await this.loadStatus(true);
        this.startPolling();
        this.startStatusStream();
      },

      startPolling() {
        this.stopPolling();
        this._timer = setInterval(() => {
          if (this._streamState !== 'connected') this.loadStatus(true);
        }, 5000);
      },

      stopPolling() {
        if (this._timer) {
          clearInterval(this._timer);
          this._timer = null;
        }
      },

      startStatusStream() {
        this.stopStatusStream();
        this._statusStream = startMonitorStreamConsumer({
          onSnapshot: (snapshot) => this.handleMonitorSnapshot(snapshot),
          onState: ({ state }) => { this._streamState = state; },
        });
      },

      stopStatusStream() {
        if (this._statusStream) {
          try { this._statusStream.close(); } catch (_) {}
          this._statusStream = null;
        }
      },

      async handleMonitorSnapshot(snapshot) {
        const status = snapshot?.events;
        if (!status) return;
        await this.applyStatusSnapshot(status, true);
      },

      pushStatus(message, tone = 'info') {
        this.statusMessage = String(message || '');
        this.statusTone = tone;
        this.statusLog = [
          {
            id: `${Date.now()}-${++this._statusSeq}`,
            ts: Date.now(),
            message: String(message || ''),
            tone,
          },
          ...(this.statusLog || []),
        ].slice(0, 6);
      },

      statusBadgeClass() {
        return statusBadgeClassByTone(this.statusTone);
      },

      statusBadgeText() {
        return statusBadgeTextByTone(this.statusTone);
      },

      analysisIntervalLabel() {
        const sec = Number(this.ui.autoRefreshIntervalSec || 0);
        if (sec < 60) return `${sec} сек`;
        if (sec % 3600 === 0) return `${sec / 3600} ч`;
        if (sec % 60 === 0) return `${sec / 60} мин`;
        return `${sec} сек`;
      },

      nextRefreshLabel() {
        return this.cacheStatus?.next_refresh_at ? fmtDate(this.cacheStatus.next_refresh_at, true) : '—';
      },

      progressPercent() {
        return statusProgressPercent(this.cacheStatus);
      },

      progressLabel() {
        return statusProgressLabel(this.cacheStatus, 'Идёт обновление кеша мероприятий', 'Ожидание');
      },

      progressCounterLabel() {
        return statusProgressCounterLabel(this.cacheStatus, 'файлов');
      },

      progressLogEntries() {
        return statusProgressLogEntries(this.cacheStatus);
      },

      statusPanelConfig() {
        return {
          badgeClass: this.statusBadgeClass(),
          badgeText: this.statusBadgeText(),
          statusMessage: this.statusMessage,
          nextRefreshLabel: this.nextRefreshLabel(),
          currentItemLabel: 'Текущий чат',
          currentItemValue: this.cacheStatus?.current_item || '',
          progressLabel: this.progressLabel(),
          progressCounter: this.progressCounterLabel(),
          progressPercent: this.progressPercent(),
          progressLog: this.progressLogEntries(),
          statusLog: this.statusLog,
        };
      },

      renderStatusPanel() {
        return renderUnifiedStatusPanel(this.statusPanelConfig()) + this.renderEventDateStatusPanel();
      },

      renderEventDateStatusPanel() {
        const status = this.cacheStatus || {};
        const total = Number(status.event_date_total || 0);
        const processed = Number(status.event_date_processed || 0);
        const found = Number(status.event_date_found || 0);
        const pending = Number(status.event_date_pending || 0);
        const percent = Math.max(0, Math.min(100, Number(status.event_date_percent || 0)));
        const rate = Number(status.event_date_rate_per_min || 0);
        const running = !!status.event_date_running;
        const lastError = String(status.event_date_last_error || '').trim();
        const escapedError = lastError.replace(/[&<>"']/g, (ch) => ({
          '&': '&amp;',
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
        }[ch]));
        const label = running
          ? 'OpenRouter сейчас извлекает даты'
          : (pending > 0 ? 'OpenRouter ждёт следующую пачку' : 'OpenRouter даты обработаны');
        const toneClass = lastError ? 'badge-pending' : (running ? 'badge-warn' : 'badge-active');
        return `
          <div style="margin-top:14px; padding-top:12px; border-top:1px solid rgba(226,232,240,.9);">
            <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap;">
              <div>
                <div class="section-title" style="margin:0; padding:0;">OpenRouter даты мероприятий</div>
                <div class="subtle">${label}</div>
              </div>
              <span class="badge ${toneClass}">${running ? 'LLM работает' : (lastError ? 'ошибка' : 'готово')}</span>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-top:12px;">
              <div><div class="subtle">Всего для анализа</div><strong>${total}</strong></div>
              <div><div class="subtle">Обработано</div><strong>${processed}</strong></div>
              <div><div class="subtle">Дат нашлось</div><strong>${found}</strong></div>
              <div><div class="subtle">Осталось</div><strong>${pending}</strong></div>
              <div><div class="subtle">Скорость</div><strong>${rate.toFixed(1)} / мин</strong></div>
            </div>
            <div style="display:grid; gap:6px; margin-top:10px;">
              <div class="progress-track"><div class="progress-bar" style="width:${percent}%;"></div></div>
              <div class="subtle"><strong>${percent.toFixed(1)}</strong>% LLM-разбора дат</div>
              ${lastError ? `<div class="subtle" style="color:#b91c1c;">Последняя ошибка: ${escapedError}</div>` : ''}
            </div>
          </div>
        `;
      },

      parseKeywordsText() {
        return String(this.keywordsText || '')
          .split(/[\n,;]+/)
          .map((item) => item.trim())
          .filter(Boolean);
      },

      async loadKeywords() {
        try {
          const data = await apiGetEventKeywords({
            requestKey: 'events:keywords',
            cacheKey: 'events:keywords',
            cacheTtlMs: 4000,
          });
          this.keywords = data?.keywords || [];
          this.keywordsText = this.keywords.join('\n');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить ключевые слова');
        }
      },

      async saveKeywords() {
        if (this.saving) return;
        this.saving = true;
        this.error = null;
        try {
          const data = await apiSetEventKeywords(this.parseKeywordsText());
          this.keywords = data?.keywords || [];
          this.keywordsText = this.keywords.join('\n');
          toast(data?.message || 'Ключевые слова сохранены', 'log');
          this.pushStatus('Ключевые слова сохранены. Для новых правил запустите обновление мероприятий.', 'loading');
          await this.loadStatus(true);
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось сохранить ключевые слова');
          toast(this.error, 'error');
        } finally {
          this.saving = false;
        }
      },

      async applyStatusSnapshot(status, silent = false) {
        const previousRefresh = this.cacheStatus?.last_refresh_at || this._lastRefreshAt || null;
        const previousEventDateProcessed = this._lastEventDateProcessed;
        const previousEventDateFound = this._lastEventDateFound;
        this.cacheStatus = status;
        this.ui.autoRefreshEnabled = !!status.enabled;
        this.ui.autoRefreshIntervalSec = Number(status.interval_sec || 300);
        this._lastEventDateProcessed = Number(status.event_date_processed || 0);
        this._lastEventDateFound = Number(status.event_date_found || 0);

        if (status.running) {
          this.pushStatus('Кеш мероприятий сейчас догружается. Показываю уже сохранённые совпадения.', 'loading');
        } else if (status.last_error) {
          this.pushStatus(`Ошибка обновления кеша мероприятий: ${status.last_error}`, 'error');
        } else if (status.stale_reason) {
          this.pushStatus(status.stale_reason, 'loading');
        } else if (status.last_refresh_at) {
          this.pushStatus(`Кеш мероприятий готов. Последнее обновление: ${fmtDate(status.last_refresh_at, true)}.`, 'success');
        } else {
          this.pushStatus('Кеш мероприятий пока пуст. Нажмите "Обновить таблицу" или дождитесь автообновления.', 'idle');
        }

        const currentRefresh = status.last_refresh_at || null;
        if (currentRefresh && currentRefresh !== previousRefresh) {
          this._lastRefreshAt = currentRefresh;
          await this.loadRows(true);
        } else if (
          previousEventDateProcessed !== null
          && (
            Number(status.event_date_processed || 0) !== Number(previousEventDateProcessed || 0)
            || Number(status.event_date_found || 0) !== Number(previousEventDateFound || 0)
          )
        ) {
          await this.loadRows(true);
        }
      },

      async loadStatus(silent = false) {
        try {
          const status = await apiGetEventsStatus({
            requestKey: 'events:status',
            cacheKey: 'events:status',
            cacheTtlMs: 1000,
            forceFresh: !!silent,
          });
          await this.applyStatusSnapshot(status, silent);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            this.error = humanizeApiError(e, 'Не удалось загрузить статус мероприятий');
            this.pushStatus(this.error, 'error');
          }
        }
      },

      async triggerRefresh(options = {}) {
        const shouldConfirm = options?.confirm !== false;
        if (shouldConfirm && !confirmLongRebuild(
          'Обновление мероприятий',
          'Backend пересоберёт кеш сообщений с мероприятиями и может поставить LLM-разбор дат в очередь.'
        )) {
          this.pushStatus('Обновление мероприятий отменено пользователем', 'idle');
          return;
        }
        this.refreshing = true;
        this.error = null;
        try {
          const result = await apiRefreshEvents();
          this.cacheStatus = result?.status || this.cacheStatus;
          this.pushStatus(result?.message || 'Обновление кеша мероприятий запущено', 'loading');
          toast(result?.message || 'Обновление кеша мероприятий запущено', 'log');
          await this.loadRows(true);
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось запустить обновление мероприятий');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        } finally {
          this.refreshing = false;
        }
      },

      async saveAutoRefreshConfig() {
        try {
          const result = await apiSetEventsConfig({
            enabled: !!this.ui.autoRefreshEnabled,
            interval_sec: Number(this.ui.autoRefreshIntervalSec || 300),
          });
          this.cacheStatus = result?.status || this.cacheStatus;
          this.pushStatus(result?.message || 'Настройки мероприятий сохранены', 'success');
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось сохранить настройки мероприятий');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        }
      },

      async loadRows(silent = false) {
        if (!silent) this.loading = true;
        if (!silent) this.error = null;
        try {
          const params = {
            limit: this.ui.limit,
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.filter || '').trim(),
            lead_filter: (this.ui.leadFilter || '').trim(),
            sender_filter: (this.ui.senderFilter || '').trim(),
            keyword_filter: (this.ui.keywordFilter || '').trim(),
            date_from: this.ui.dateFrom,
            date_to: this.ui.dateTo,
          };
          const data = await apiGetEventMessages(
            params,
            buildPagedRequestOptions('event-messages', params, {
              requestKey: 'events:rows',
              cacheTtlMs: silent ? 2500 : 0,
              forceFresh: !silent,
              timeoutMs: 20000,
            }),
          );
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => `${row?.lead || ''}:${row?.message_id || ''}`);
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить мероприятия');
          if (!silent) {
            this.pushStatus(this.error, 'error');
            toast(this.error, 'error');
          } else {
            this.pushStatus(`Фоновое обновление мероприятий не удалось: ${this.error}`, 'error');
          }
        } finally {
          if (!silent) this.loading = false;
        }
      },

      eventRowKey(row) {
        return [
          row?.lead || '',
          row?.source_selector || '',
          row?.message_id || '',
          String(row?.text || '').slice(0, 120),
        ].join(':');
      },

      async deleteEvent(row) {
        if (!row || this.deletingKey) return;
        const source = row.lead || row.source_selector || '';
        const text = String(row.text || '').trim();
        if (!source || !text) {
          toast('Не хватает источника или текста мероприятия для удаления', 'error');
          return;
        }
        if (!window.confirm('Удалить это мероприятие? Если у этого источника есть одинаковые сообщения, они тоже будут скрыты/удалены.')) return;
        const key = this.eventRowKey(row);
        this.deletingKey = key;
        this.error = null;
        try {
          const result = await apiDeleteEventMessage({
            lead: row.lead || '',
            source_selector: row.source_selector || '',
            message_id: row.message_id || null,
            text,
          }, { timeoutMs: 30000 });
          this.pushStatus(result?.message || 'Мероприятие удалено', 'success');
          toast(result?.message || 'Мероприятие удалено', 'log');
          this.rows = (this.rows || []).filter((item) => this.eventRowKey(item) !== key);
          await this.loadRows(false);
          await this.loadStatus(true);
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось удалить мероприятие');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        } finally {
          this.deletingKey = '';
        }
      },

      filteredRows() {
        return this.rows || [];
      },

      totalPages() {
        return Math.max(1, Number(this.totalRowPages || 1));
      },

      pagedRows() {
        return this.filteredRows();
      },

      pageWindow() {
        const total = this.totalPages();
        const current = Math.min(Math.max(1, this.ui.page), total);
        let start = Math.max(1, current - 2);
        let end = Math.min(total, start + 4);
        start = Math.max(1, end - 4);
        const pages = [];
        for (let page = start; page <= end; page += 1) pages.push(page);
        return pages;
      },

      resetPage() {
        this.ui.page = 1;
        this.loadRows();
      },

      goToPage(page) {
        const total = this.totalPages();
        this.ui.page = Math.min(Math.max(1, Number(page || 1)), total);
        this.loadRows(true);
      },

      prevPage() {
        this.goToPage(this.ui.page - 1);
      },

      nextPage() {
        this.goToPage(this.ui.page + 1);
      },

      visibleRangeText() {
        const items = this.filteredRows();
        const total = Math.max(0, Number(this.totalRows || 0));
        if (!items.length || !total) return '0 из 0';
        const size = Math.max(1, Number(this.ui.pageSize || 1));
        const start = (this.ui.page - 1) * size;
        const from = start + 1;
        const to = Math.min(total, start + items.length);
        return `${from}-${to} из ${total}`;
      },

      keywordsLabel(row) {
        return (row?.matched_keywords || []).join(', ');
      },

      previewText(text, maxLen = 220) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },
    };
  };
  }
})();
