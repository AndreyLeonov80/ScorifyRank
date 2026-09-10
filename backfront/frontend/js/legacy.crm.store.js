/* Legacy crm store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.crm.store.js");
    return;
  }
  with (ctx) {
  window.crmApp = function crmApp() {
    return {
      loading: false,
      refreshing: false,
      error: null,
      statusMessage: 'Готов к анализу CRM-сообщений.',
      statusTone: 'idle',
      statusLog: [],
      cacheStatus: null,
      _lastRefreshAt: null,
      _statusSeq: 0,
      rows: [],
      leads: [],
      outreachBusyKey: null,
      outreachSelectedByKey: {},
      ui: {
        query: '',
        leadFilter: '',
        page: 1,
        pageSize: 5,
        limit: 1500,
        autoRefreshEnabled: true,
        autoRefreshIntervalSec: 300,
        onlyName: false,
        onlyPhone: false,
        onlyEmail: false,
        onlyCompany: false,
        onlyCity: false,
        onlyTitle: false,
      },
      totalRows: 0,
      totalRowPages: 1,
      _timer: null,
      _statusStream: null,
      _streamState: 'idle',
      ...createOutreachToggleState(),

      async init() {
        await Promise.all([
          this.loadStatus(),
          this.loadOutreachSelections(true),
        ]);
        await this.loadRows();
        this.startPolling();
        this.startStatusStream();
      },

      startPolling() {
        this.stopPolling();
        this._timer = setInterval(() => {
          if (this._streamState !== 'connected') this.loadStatus(true);
        }, 15000);
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
        const status = snapshot?.crm;
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
        return statusProgressLabel(this.cacheStatus, 'Идёт обновление CRM-кеша', 'Ожидание');
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
        return renderUnifiedStatusPanel(this.statusPanelConfig());
      },

      async applyStatusSnapshot(status, silent = false) {
        const previousRefresh = this.cacheStatus?.last_refresh_at || this._lastRefreshAt || null;
        this.cacheStatus = status;
        this.ui.autoRefreshEnabled = !!status.enabled;
        this.ui.autoRefreshIntervalSec = Number(status.interval_sec || 300);

        if (status.running) {
          this.pushStatus('CRM-кеш сейчас догружается. Показываю уже сохранённые данные.', 'loading');
        } else if (status.last_error) {
          this.pushStatus(`Ошибка обновления CRM-кеша: ${status.last_error}`, 'error');
        } else if (status.last_refresh_at) {
          this.pushStatus(`CRM-кеш готов. Последнее обновление: ${fmtDate(status.last_refresh_at, true)}.`, 'success');
        } else {
          this.pushStatus('CRM-кеш пока пуст. Нажмите "Обновить CRM" или дождитесь автообновления.', 'idle');
        }

        const currentRefresh = status.last_refresh_at || null;
        if (currentRefresh && currentRefresh !== previousRefresh) {
          this._lastRefreshAt = currentRefresh;
          await this.loadRows(true);
        }
      },

      async loadStatus(silent = false) {
        try {
          const status = await apiGetCrmStatus({
            requestKey: 'crm:status',
            cacheKey: 'crm:status',
            cacheTtlMs: 2500,
            forceFresh: !!silent,
          });
          await this.applyStatusSnapshot(status, silent);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            this.error = humanizeApiError(e, 'Не удалось загрузить статус CRM');
            this.pushStatus(this.error, 'error');
          }
        }
      },

      async triggerRefresh(options = {}) {
        const shouldConfirm = options?.confirm !== false;
        if (shouldConfirm && !confirmLongRebuild(
          'Обновление CRM',
          'Backend догрузит и пересоберёт CRM-кеш по сообщениям. Если данных много, процесс продолжится в фоне с progress/log.'
        )) {
          this.pushStatus('Обновление CRM отменено пользователем', 'idle');
          return;
        }
        this.refreshing = true;
        this.error = null;
        try {
          const result = await apiRefreshCrm();
          this.cacheStatus = result?.status || this.cacheStatus;
          this.pushStatus(result?.message || 'Обновление CRM-кеша запущено', 'loading');
          toast(result?.message || 'Обновление CRM-кеша запущено', 'log');
          await this.loadRows(true);
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось запустить обновление CRM');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        } finally {
          this.refreshing = false;
        }
      },

      async saveAutoRefreshConfig() {
        try {
          const result = await apiSetCrmConfig({
            enabled: !!this.ui.autoRefreshEnabled,
            interval_sec: Number(this.ui.autoRefreshIntervalSec || 300),
          });
          this.cacheStatus = result?.status || this.cacheStatus;
          this.pushStatus(result?.message || 'Настройки CRM сохранены', 'success');
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось сохранить настройки CRM');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        }
      },

      async loadRows(silent = false) {
        if (!silent) this.loading = true;
        this.error = null;
        try {
          const data = await apiGetCrmContacts({
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: this.ui.limit,
            lead: (this.ui.leadFilter || '').trim(),
            query: (this.ui.query || '').trim(),
            only_name: this.ui.onlyName,
            only_phone: this.ui.onlyPhone,
            only_email: this.ui.onlyEmail,
            only_company: this.ui.onlyCompany,
            only_city: this.ui.onlyCity,
            only_title: this.ui.onlyTitle,
          }, buildPagedRequestOptions('crm', {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: this.ui.limit,
            lead: (this.ui.leadFilter || '').trim(),
            query: (this.ui.query || '').trim(),
            only_name: this.ui.onlyName,
            only_phone: this.ui.onlyPhone,
            only_email: this.ui.onlyEmail,
            only_company: this.ui.onlyCompany,
            only_city: this.ui.onlyCity,
            only_title: this.ui.onlyTitle,
          }, {
            requestKey: 'crm:rows',
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => `${row?.lead || ''}:${row?.message_id || ''}`);
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить CRM');
          if (!silent) {
            this.pushStatus(this.error, 'error');
            toast(this.error, 'error');
          } else {
            this.pushStatus(`Фоновое обновление CRM не удалось: ${this.error}`, 'error');
          }
        } finally {
          if (!silent) this.loading = false;
        }
      },

      resetPage() {
        this.ui.page = 1;
        this.loadRows();
      },

      filteredRows() {
        return this.rows || [];
      },

      totalPages() {
        return Math.max(1, Number(this.totalRowPages || 1));
      },

      ensurePageBounds() {
        const total = this.totalPages();
        if (this.ui.page < 1) this.ui.page = 1;
        if (this.ui.page > total) this.ui.page = total;
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

      goToPage(page) {
        this.ui.page = Number(page || 1);
        this.ensurePageBounds();
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

      leadLabel(row) {
        return row?.source_selector || row?.lead || '—';
      },

      outreachSelectionKey(row, fieldType, value) {
        if (
          ['message', 'event_message'].includes(fieldType || '')
          && row?.lead
          && (row?.message_id || row?.date_utc)
        ) {
          return [
            fieldType || '',
            row?.lead || '',
            row?.message_id || '',
            row?.date_utc || '',
          ].join('::');
        }
        return [
          fieldType || '',
          String(value || '').replace(/\s+/g, ' ').trim(),
          row?.lead || '',
          row?.message_id || '',
          row?.date_utc || '',
        ].join('::');
      },

      outreachFieldLabel(fieldType) {
        return outreachFieldLabel(fieldType, '') || 'CRM-поле';
      },

      outreachFieldValues(row, fieldType) {
        if (!row) return [];
        if (fieldType === 'fio') {
          return row.full_name ? [row.full_name] : [];
        }
        if (fieldType === 'job_title') {
          return row.job_title ? [row.job_title] : [];
        }
        if (fieldType === 'company') {
          return Array.isArray(row.companies) ? row.companies.filter(Boolean) : [];
        }
        if (fieldType === 'contact') {
          return [
            ...(Array.isArray(row.phones) ? row.phones : []),
            ...(Array.isArray(row.emails) ? row.emails : []),
          ].filter(Boolean);
        }
        if (fieldType === 'city') {
          return row.city ? [row.city] : [];
        }
        if (fieldType === 'message') {
          return row.text ? [row.text] : [];
        }
        return [];
      },

      outreachButtonKey(row, fieldType, value) {
        return `${row?.lead || ''}:${row?.message_id || ''}:${fieldType}:${value}`;
      },

      isOutreachSelected(row, fieldType, value) {
        return !!this.outreachSelectedByKey[this.outreachSelectionKey(row, fieldType, value)];
      },

      async loadOutreachSelections(silent = false) {
        try {
          const selected = {};
          let page = 1;
          let totalPages = 1;
          do {
            const data = await apiGetOutreachItems({
              page,
              page_size: 100,
              limit: 20000,
            }, {
              requestKey: `crm:outreach-selections:${page}`,
              cacheKey: `crm:outreach-selections:${page}`,
              cacheTtlMs: silent ? 5000 : 0,
              forceFresh: !silent,
            });
            for (const item of (data?.items || [])) {
              const key = ['message', 'event_message'].includes(item?.field_type || '') && item?.lead && (item?.message_id || item?.date_utc)
                ? [
                    item?.field_type || '',
                    item?.lead || '',
                    item?.message_id || '',
                    item?.date_utc || '',
                  ].join('::')
                : [
                    item?.field_type || '',
                    String(item?.value || '').replace(/\s+/g, ' ').trim(),
                    item?.lead || '',
                    item?.message_id || '',
                    item?.date_utc || '',
                  ].join('::');
              if (key) selected[key] = item?.id || true;
            }
            totalPages = Math.max(1, Number(data?.total_pages || 1));
            page += 1;
          } while (page <= totalPages && page <= 50);
          this.outreachSelectedByKey = selected;
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            toast(humanizeApiError(e, 'Не удалось сверить выбранные enReach-поля'), 'error');
          }
        }
      },

      async addOutreachField(row, fieldType, value) {
        const cleanValue = fieldType === 'message'
          ? String(value || '').trim()
          : String(value || '').replace(/\s+/g, ' ').trim();
        if (!cleanValue) return;
        const busyKey = this.outreachButtonKey(row, fieldType, cleanValue);
        this.outreachBusyKey = busyKey;
        try {
          const result = await apiAddOutreachItem({
            field_type: fieldType,
            field_label: this.outreachFieldLabel(fieldType),
            value: cleanValue,
            lead: row?.lead || null,
            source_selector: row?.source_selector || null,
            message_id: row?.message_id || null,
            date_utc: row?.date_utc || null,
            text: row?.text || null,
            sender_username: row?.sender_username || null,
            sender_name: row?.sender_name || null,
          });
          const selectionKey = this.outreachSelectionKey(row, fieldType, cleanValue);
          this.outreachSelectedByKey = {
            ...this.outreachSelectedByKey,
            [selectionKey]: result?.item?.id || true,
          };
          toast(result?.message || `${this.outreachFieldLabel(fieldType)} добавлено в enReach`, 'log');
        } catch (e) {
          const message = humanizeApiError(e, `Не удалось добавить ${this.outreachFieldLabel(fieldType)} в enReach`);
          toast(message, 'error');
        } finally {
          this.outreachBusyKey = null;
        }
      },

      async removeOutreachField(row, fieldType, value) {
        const cleanValue = fieldType === 'message'
          ? String(value || '').trim()
          : String(value || '').replace(/\s+/g, ' ').trim();
        if (!cleanValue) return;
        const selectionKey = this.outreachSelectionKey(row, fieldType, cleanValue);
        const itemId = this.outreachSelectedByKey[selectionKey];
        if (!itemId || itemId === true) {
          await this.loadOutreachSelections(false);
          const refreshedItemId = this.outreachSelectedByKey[selectionKey];
          if (!refreshedItemId || refreshedItemId === true) {
            toast('Не удалось найти элемент enReach для удаления. Обновите enReach и попробуйте ещё раз.', 'error');
            return;
          }
          return this.removeOutreachField(row, fieldType, cleanValue);
        }
        const busyKey = this.outreachButtonKey(row, fieldType, cleanValue);
        this.outreachBusyKey = busyKey;
        try {
          const result = await apiDeleteOutreachItem(itemId);
          const next = { ...this.outreachSelectedByKey };
          delete next[selectionKey];
          this.outreachSelectedByKey = next;
          toast(result?.message || `${this.outreachFieldLabel(fieldType)} удалено из enReach`, 'log');
        } catch (e) {
          const message = humanizeApiError(e, `Не удалось удалить ${this.outreachFieldLabel(fieldType)} из enReach`);
          toast(message, 'error');
        } finally {
          this.outreachBusyKey = null;
        }
      },

      toggleOutreachField(row, fieldType, value) {
        return this.isOutreachSelected(row, fieldType, value)
          ? this.removeOutreachField(row, fieldType, value)
          : this.addOutreachField(row, fieldType, value);
      },

      senderLabel(row) {
        const sender = row?.sender_name || row?.sender_username || '—';
        if (row?.sender_username && row?.sender_name) {
          return `${row.sender_name} · @${row.sender_username}`;
        }
        if (row?.sender_username && !row?.sender_name) {
          return `@${row.sender_username}`;
        }
        return sender;
      },

      fullNameLabel(row) {
        if (!row?.full_name) return '—';
        const parts = Number(row?.name_components_count || 0);
        return parts > 0 ? `${row.full_name} (${parts})` : row.full_name;
      },

      listLabel(items) {
        const list = Array.isArray(items) ? items.filter(Boolean) : [];
        return list.length ? list.join(', ') : '—';
      },

      contactLabel(row) {
        const chunks = [];
        if ((row?.phones || []).length) chunks.push((row.phones || []).join(', '));
        if ((row?.emails || []).length) chunks.push((row.emails || []).join(', '));
        return chunks.length ? chunks.join(' / ') : '—';
      },

      matchSourcesLabel(row) {
        const items = Array.isArray(row?.match_sources) ? row.match_sources : [];
        return items.length ? items.join(', ') : '—';
      },

      fieldProvenanceLabel(row) {
        const raw = row?.field_provenance;
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return '';
        const labels = {
          fio: 'ФИО',
          job_title: 'должность',
          company: 'компания',
          phone: 'телефон',
          email: 'email',
          city: 'город',
        };
        const chunks = Object.entries(raw)
          .map(([field, sources]) => {
            const list = Array.isArray(sources) ? sources : [];
            const compact = list
              .map((item) => String(item || '').replace(/^[^:]+:/, '').replace(/^telegram\./, 'tg.'))
              .filter(Boolean)
              .slice(0, 3);
            return compact.length ? `${labels[field] || field}: ${compact.join(', ')}` : '';
          })
          .filter(Boolean);
        return chunks.join(' · ');
      },

      previewText(text, maxLen = 180) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },
    };
  };
  }
})();
