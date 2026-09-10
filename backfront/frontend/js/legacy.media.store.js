/* Legacy media store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.media.store.js");
    return;
  }
  with (ctx) {
  window.mediaApp = function mediaApp() {
    return {
      loading: false,
      ocrLoading: false,
      configLoading: false,
      mediaBulkAdding: false,
      actionBusyLead: null,
      actionBusyType: '',
      error: null,
      statusMessage: 'Готов к обработке media.',
      statusTone: 'idle',
      statusLog: [],
      cacheStatus: null,
      _lastRefreshAt: null,
      _statusSeq: 0,
      rows: [],
      leads: [],
      mediaConfig: null,
      ocrStatus: null,
      ocrTextCacheByPath: {},
      ocrTextExpandedByPath: {},
      ocrTextLoadingByPath: {},
      ocrTextErrorByPath: {},
      mediaOutreachBusyPath: '',
      mediaOutreachSelectedByPath: {},
      ui: {
        query: '',
        leadFilter: '',
        leadMembershipFilter: 'all',
        showChannels: true,
        showGroups: true,
        showPrivate: true,
        page: 1,
        pageSize: 5,
        showRecognizedOnly: false,
        showPendingOnly: false,
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
          this.loadRows(),
          this.loadLeads(),
          this.loadMediaConfig(),
        ]);
        this.runPendingOcr(false);
        this.startPolling();
        this.startStatusStream();
      },

      startPolling() {
        this.stopPolling();
        this._timer = setInterval(() => {
          if (this._streamState !== 'connected') this.loadStatus(true);
          this.loadRows(true);
          this.loadMediaConfig(true);
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
        const status = snapshot?.media;
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

      nextRefreshLabel() {
        return this.cacheStatus?.next_refresh_at ? fmtDate(this.cacheStatus.next_refresh_at, true) : '—';
      },

      progressPercent() {
        return statusProgressPercent(this.cacheStatus);
      },

      progressLabel() {
        return statusProgressLabel(this.cacheStatus, 'Идёт OCR-обработка изображений', 'Ожидание');
      },

      progressCounterLabel() {
        return statusProgressCounterLabel(this.cacheStatus, 'изображений');
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
          currentItemLabel: 'Текущее изображение / чат',
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
        if (status.running) {
          this.pushStatus('Media-обработка сейчас выполняется. Показываю уже сохранённые изображения и OCR-результаты.', 'loading');
        } else if (status.last_error) {
          this.pushStatus(`Ошибка media/OCR: ${status.last_error}`, 'error');
        } else if (status.stale_reason) {
          this.pushStatus(status.stale_reason, 'loading');
        } else if (status.last_refresh_at) {
          this.pushStatus(`Media-кеш готов. Последнее обновление: ${fmtDate(status.last_refresh_at, true)}.`, 'success');
        } else {
          this.pushStatus('Media-кеш пока пуст. Включите media для нужных чатов или дождитесь новых изображений.', 'idle');
        }

        const currentRefresh = status.last_refresh_at || null;
        if (currentRefresh && currentRefresh !== previousRefresh) {
          this._lastRefreshAt = currentRefresh;
          await this.loadRows(true);
        }
      },

      async loadStatus(silent = false) {
        try {
          const status = await apiGetMediaStatus({
            requestKey: 'media:status',
            cacheKey: 'media:status',
            cacheTtlMs: 2500,
            forceFresh: !!silent,
          });
          await this.applyStatusSnapshot(status, silent);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            this.error = humanizeApiError(e, 'Не удалось загрузить статус media');
            this.pushStatus(this.error, 'error');
          }
        }
      },

      async loadRows(silent = false) {
        if (!silent) this.loading = true;
        this.error = null;
        try {
          this.ui.pageSize = Math.min(100, Math.max(1, Number(this.ui.pageSize || 5)));
          const data = await apiGetImages({
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: 2000,
            query: (this.ui.query || '').trim(),
            lead_filter: (this.ui.leadFilter || '').trim(),
            recognized_only: this.ui.showRecognizedOnly,
            pending_only: this.ui.showPendingOnly,
          }, buildPagedRequestOptions('media:images', {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: 2000,
            query: (this.ui.query || '').trim(),
            lead_filter: (this.ui.leadFilter || '').trim(),
            recognized_only: this.ui.showRecognizedOnly,
            pending_only: this.ui.showPendingOnly,
          }, {
            requestKey: 'media:images',
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => row?.media_path || '');
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить изображения media');
          if (!silent) toast(this.error, 'error');
        } finally {
          if (!silent) this.loading = false;
        }
      },

      async loadLeads(silent = false) {
        if (!silent) this.loading = true;
        try {
          const data = await apiGetLeads({
            page: 1,
            page_size: 5,
            query: (this.ui.leadFilter || '').trim(),
            sort_mode: 'status',
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: false,
            show_archived: false,
          }, buildPagedRequestOptions('media:leads', {
            page: 1,
            page_size: 5,
            query: (this.ui.leadFilter || '').trim(),
            sort_mode: 'status',
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: false,
            show_archived: false,
          }, {
            requestKey: 'media:leads',
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.leads = reconcileKeyedCollection(this.leads, data?.items || [], (lead) => lead?.name || '');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить чаты для media');
          if (!silent) toast(this.error, 'error');
        } finally {
          if (!silent) this.loading = false;
        }
      },

      async loadMediaConfig(silent = false) {
        if (!silent) this.configLoading = true;
        try {
          this.mediaConfig = await apiGetMediaConfig({
            requestKey: 'media:config',
            cacheKey: 'media:config',
            cacheTtlMs: 2500,
            forceFresh: !!silent,
          });
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить настройки media');
          if (!silent) toast(this.error, 'error');
        } finally {
          if (!silent) this.configLoading = false;
        }
      },

      async runPendingOcr(showToast = true) {
        if (this.ocrLoading) return;
        this.ocrLoading = true;
        try {
          this.ocrStatus = await apiRunPendingImageOcr();
          await this.loadStatus(true);
          if (showToast) toast(this.ocrStatus?.message || 'OCR запущен', 'log');
          await this.loadRows(true);
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось запустить OCR изображений');
          if (showToast) toast(this.error, 'error');
        } finally {
          this.ocrLoading = false;
        }
      },

      imageTextCache(row) {
        return this.ocrTextCacheByPath[String(row?.media_path || '')] || null;
      },

      imageTextExpanded(row) {
        return !!this.ocrTextExpandedByPath[String(row?.media_path || '')];
      },

      imageTextLoading(row) {
        return !!this.ocrTextLoadingByPath[String(row?.media_path || '')];
      },

      imageTextError(row) {
        return this.ocrTextErrorByPath[String(row?.media_path || '')] || '';
      },

      imageTextPreview(row) {
        const cached = this.imageTextCache(row);
        if (cached?.preview) return cached.preview;
        if (row?.ocr_preview) return row.ocr_preview;
        if (row?.recognized) return '';
        return 'Текст пока не распознан';
      },

      mediaImagesSizeLabel() {
        return this.formatBytes(this.cacheStatus?.images_bytes || 0);
      },

      ocrIsEnabled() {
        return !!this.cacheStatus?.ocr_enabled;
      },

      ocrIsAvailable() {
        if (this.cacheStatus && Object.prototype.hasOwnProperty.call(this.cacheStatus, 'ocr_available')) {
          return !!this.cacheStatus.ocr_available;
        }
        if (this.ocrStatus && Object.prototype.hasOwnProperty.call(this.ocrStatus, 'available')) {
          return !!this.ocrStatus.available;
        }
        return false;
      },

      ocrIsRunning() {
        return !!(this.ocrStatus?.running || (this.cacheStatus?.running && String(this.cacheStatus?.progress_label || '').toLowerCase().includes('ocr')));
      },

      ocrBadgeClass() {
        if (!this.ocrIsEnabled() || !this.ocrIsAvailable()) return 'badge-archived';
        if (this.ocrIsRunning()) return 'badge-pending';
        return 'badge-active';
      },

      ocrBadgeText() {
        if (!this.ocrIsEnabled()) return 'OCR выключен';
        if (!this.ocrIsAvailable()) return 'OCR недоступен';
        if (this.ocrIsRunning()) return 'OCR в работе';
        return 'OCR готов';
      },

      ocrPendingCount() {
        const value = this.ocrStatus?.pending_count ?? this.cacheStatus?.pending_count;
        return Number.isFinite(Number(value)) ? Number(value) : '—';
      },

      mediaOcrCategoryLabel(row) {
        const cached = this.imageTextCache(row);
        const categories = Array.isArray(cached?.crm_categories) ? cached.crm_categories : [];
        if (categories.length) return categories.join(', ');
        const fields = Array.isArray(cached?.crm_fields) ? cached.crm_fields : [];
        const labels = [...new Set(fields.map((item) => String(item?.field_label || '').trim()).filter(Boolean))];
        return labels.length ? labels.join(', ') : 'Сообщение';
      },

      mediaOcrOutreachLabel(row) {
        const label = this.mediaOcrCategoryLabel(row);
        return label === 'Сообщение' ? 'OCR: Сообщение' : `OCR: ${label}`;
      },

      mediaOcrOutreachPayload(row, data = null) {
        const cached = data || this.imageTextCache(row) || {};
        const text = String(cached?.text || '').trim();
        return {
          field_type: 'media',
          field_label: this.mediaOcrOutreachLabel(row),
          value: text,
          lead: row?.lead,
          source_selector: row?.lead,
          date_utc: row?.modified_at,
          text,
        };
      },

      mediaOcrOutreachItemId(row) {
        const mediaPath = String(row?.media_path || '');
        if (this.mediaOutreachSelectedByPath[mediaPath]) {
          return this.mediaOutreachSelectedByPath[mediaPath];
        }
        const cached = this.imageTextCache(row);
        if (!cached?.text) return '';
        return this.outreachSelectedByKey[this.outreachPayloadKey(this.mediaOcrOutreachPayload(row, cached))] || '';
      },

      async ensureImageTextLoaded(row) {
        const mediaPath = String(row?.media_path || '');
        if (!mediaPath || !row?.recognized) return null;
        const cached = this.imageTextCache(row);
        if (cached?.text) return cached;
        if (this.imageTextLoading(row)) return cached || null;

        this.ocrTextLoadingByPath = { ...this.ocrTextLoadingByPath, [mediaPath]: true };
        this.ocrTextErrorByPath = { ...this.ocrTextErrorByPath, [mediaPath]: '' };
        try {
          const data = await apiGetImageText(mediaPath, {
            requestKey: `media:text:${mediaPath}`,
            cacheKey: `media:text:${mediaPath}`,
            cacheTtlMs: 30000,
          });
          const nextValue = {
            text: String(data?.text || ''),
            preview: String(data?.preview || ''),
            text_path: data?.text_path || null,
            crm_fields: Array.isArray(data?.crm_fields) ? data.crm_fields : [],
            crm_categories: Array.isArray(data?.crm_categories) ? data.crm_categories : [],
          };
          this.ocrTextCacheByPath = {
            ...this.ocrTextCacheByPath,
            [mediaPath]: nextValue,
          };
          return nextValue;
        } catch (e) {
          const message = String(e?.message || e);
          this.ocrTextErrorByPath = {
            ...this.ocrTextErrorByPath,
            [mediaPath]: message,
          };
          throw e;
        } finally {
          this.ocrTextLoadingByPath = { ...this.ocrTextLoadingByPath, [mediaPath]: false };
        }
      },

      imageToggleTextLabel(row) {
        if (this.imageTextLoading(row)) return 'Загрузка OCR…';
        if (this.imageTextExpanded(row)) return 'Скрыть OCR';
        return 'Показать OCR';
      },

      async toggleImageText(row) {
        const mediaPath = String(row?.media_path || '');
        if (!mediaPath || !row?.recognized) return;
        if (this.imageTextLoading(row)) return;

        if (this.imageTextExpanded(row)) {
          this.ocrTextExpandedByPath = { ...this.ocrTextExpandedByPath, [mediaPath]: false };
          return;
        }

        if (!this.imageTextCache(row)) {
          try {
            await this.ensureImageTextLoaded(row);
          } catch (e) {
            toast(`Не удалось загрузить OCR для ${row?.file_name || mediaPath}`, 'error');
            return;
          }
        }

        this.ocrTextExpandedByPath = { ...this.ocrTextExpandedByPath, [mediaPath]: true };
      },

      isMediaOutreachBusy(row) {
        return this.mediaOutreachBusyPath === String(row?.media_path || '');
      },

      isMediaOutreachSelected(row) {
        return !!this.mediaOcrOutreachItemId(row);
      },

      async toggleMediaOutreach(row) {
        const mediaPath = String(row?.media_path || '');
        if (!mediaPath || !row?.recognized || this.isMediaOutreachBusy(row)) return;

        if (this.isMediaOutreachSelected(row)) {
          let itemId = this.mediaOcrOutreachItemId(row);
          this.mediaOutreachBusyPath = mediaPath;
          try {
            if (!itemId || itemId === true) {
              await this.loadOutreachSelections(false);
              itemId = this.mediaOcrOutreachItemId(row);
            }
            if (!itemId || itemId === true) {
              toast('Не удалось найти OCR-текст enReach для удаления. Обновите Media и попробуйте ещё раз.', 'error');
              return;
            }
            await apiDeleteOutreachItem(itemId);
            const next = { ...this.mediaOutreachSelectedByPath };
            delete next[mediaPath];
            this.mediaOutreachSelectedByPath = next;
            toast('OCR-текст удалён из enReach', 'log');
          } catch (e) {
            toast(humanizeApiError(e, 'Не удалось удалить OCR-текст из enReach'), 'error');
          } finally {
            this.mediaOutreachBusyPath = '';
          }
          return;
        }

        this.mediaOutreachBusyPath = mediaPath;
        try {
          const data = await this.ensureImageTextLoaded(row);
          const text = String(data?.text || '').trim();
          if (!text) {
            toast('OCR-текст пока пустой, добавлять нечего', 'error');
            return;
          }
          const payload = this.mediaOcrOutreachPayload(row, data);
          const result = await apiAddOutreachItem(normalizeOutreachPayload(payload));
          this.mediaOutreachSelectedByPath = {
            ...this.mediaOutreachSelectedByPath,
            [mediaPath]: result?.item?.id || true,
          };
          toast(result?.message || 'OCR-текст добавлен в enReach', 'log');
        } catch (e) {
          toast(humanizeApiError(e, 'Не удалось добавить OCR-текст в enReach'), 'error');
        } finally {
          this.mediaOutreachBusyPath = '';
        }
      },

      selectedMediaLeads() {
        return new Set((this.mediaConfig?.selected_leads || []).map(item => String(item || '').toLowerCase()));
      },

      isMediaEnabled(lead) {
        const name = String(lead?.name || '').toLowerCase();
        return this.selectedMediaLeads().has(name);
      },

      mediaLeadStatus(lead) {
        const name = String(lead?.name || '').trim().toLowerCase();
        if (!name) return null;
        const rows = Array.isArray(this.cacheStatus?.media_backfill_leads) ? this.cacheStatus.media_backfill_leads : [];
        return rows.find((row) => String(row?.lead || '').trim().toLowerCase() === name) || null;
      },

      mediaLeadStatusClass(lead) {
        const status = this.mediaLeadStatus(lead);
        if (!this.isMediaEnabled(lead)) return 'badge-archived';
        if (status?.running) return 'badge-pending';
        if (status?.waiting) return 'badge-warn';
        if (status?.done) return 'badge-active';
        if (Number(status?.checked || 0) > 0 || Number(status?.downloaded || 0) > 0) return 'badge-warn';
        return 'badge-pending';
      },

      mediaLeadStatusLabel(lead) {
        const status = this.mediaLeadStatus(lead);
        if (!this.isMediaEnabled(lead)) return 'Media выключено';
        return String(status?.status_label || 'Ожидает проверки');
      },

      mediaLeadStatusDetails(lead) {
        const status = this.mediaLeadStatus(lead);
        if (!this.isMediaEnabled(lead)) return '';
        const checked = Number(status?.checked || 0);
        const downloaded = Number(status?.downloaded || 0);
        const parts = [`проверено ${checked}`, `скачано ${downloaded}`];
        if (status?.completed_at) parts.push(`готово ${fmtDate(status.completed_at, true)}`);
        if (status?.updated_at && !status?.completed_at) parts.push(`обновлено ${fmtDate(status.updated_at, true)}`);
        return parts.join(' · ');
      },

      isMediaActionBusy(lead, action) {
        return this.actionBusyLead === lead?.name && this.actionBusyType === action;
      },

      async enableMediaLead(lead) {
        if (!lead?.name) return;
        this.actionBusyLead = lead.name;
        this.actionBusyType = 'enable';
        try {
          this.mediaConfig = await apiAddMediaLead(lead.name);
          this.pushStatus(`Media включено для ${lead.name}. Ждём новые изображения или уже сохранённые файлы для OCR.`, 'loading');
          await Promise.all([this.loadMediaConfig(true), this.loadStatus(true), this.loadRows(true)]);
          if (this.cacheStatus?.pending_count > 0) this.runPendingOcr(false);
          toast(`Media включено для ${lead.name}`, 'log');
        } catch (e) {
          this.error = humanizeApiError(e, `Не удалось включить media для ${lead.name}`);
          toast(this.error, 'error');
        } finally {
          this.actionBusyLead = null;
          this.actionBusyType = '';
        }
      },

      async disableMediaLead(lead) {
        if (!lead?.name) return;
        this.actionBusyLead = lead.name;
        this.actionBusyType = 'disable';
        try {
          this.mediaConfig = await apiRemoveMediaLead(lead.name);
          this.pushStatus(`Media выключено для ${lead.name}.`, 'idle');
          await Promise.all([this.loadMediaConfig(true), this.loadStatus(true)]);
          toast(`Media выключено для ${lead.name}`, 'log');
        } catch (e) {
          this.error = humanizeApiError(e, `Не удалось выключить media для ${lead.name}`);
          toast(this.error, 'error');
        } finally {
          this.actionBusyLead = null;
          this.actionBusyType = '';
        }
      },

      async clearMediaLead(lead) {
        if (!lead?.name) return;
        if (!window.confirm(`Удалить все сохранённые изображения для "${lead.name}"?`)) return;
        this.actionBusyLead = lead.name;
        this.actionBusyType = 'clear';
        try {
          const result = await apiClearMediaLead(lead.name);
          this.mediaConfig = {
            ...(this.mediaConfig || {}),
            selected_leads: result.selected_leads || [],
          };
          this.ocrTextCacheByPath = {};
          this.ocrTextExpandedByPath = {};
          this.ocrTextLoadingByPath = {};
          this.ocrTextErrorByPath = {};
          await this.loadRows(true);
          toast(result.message || 'Media очищено', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.actionBusyLead = null;
          this.actionBusyType = '';
        }
      },

      async clearAllMedia() {
        if (!window.confirm('Удалить все сохранённые изображения по всем чатам?')) return;
        this.ocrLoading = true;
        try {
          const result = await apiClearAllMedia();
          this.mediaConfig = {
            ...(this.mediaConfig || {}),
            selected_leads: result.selected_leads || [],
          };
          this.ocrTextCacheByPath = {};
          this.ocrTextExpandedByPath = {};
          this.ocrTextLoadingByPath = {};
          this.ocrTextErrorByPath = {};
          await this.loadRows(true);
          toast(result.message || 'Все изображения удалены', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.ocrLoading = false;
        }
      },

      filteredLeadRows() {
        const q = String(this.ui.leadFilter || '').trim().toLowerCase();
        const membership = String(this.ui.leadMembershipFilter || 'all');
        const rowsByName = new Map();
        (this.leads || []).forEach((lead) => {
          const name = String(lead?.name || '').trim();
          if (name) rowsByName.set(name.toLowerCase(), lead);
        });
        this.selectedMediaLeads().forEach((name) => {
          const key = String(name || '').trim().toLowerCase();
          if (!key || rowsByName.has(key)) return;
          rowsByName.set(key, {
            name: key,
            source_selector: key,
            sync_status: 'media включено',
          });
        });
        const filtered = Array.from(rowsByName.values()).filter((lead) => {
          const enabled = this.isMediaEnabled(lead);
          if (membership === 'added' && !enabled) return false;
          if (membership === 'not_added' && enabled) return false;
          if (!q) return true;
          return (
            String(lead?.name || '').toLowerCase().includes(q) ||
            String(lead?.source_selector || '').toLowerCase().includes(q)
          );
        });
        return filtered.slice(0, Math.max(1, Number(this.ui.pageSize || 5)));
      },

      setLeadMembershipFilter(filterName) {
        this.ui.leadMembershipFilter = String(filterName || 'all');
      },

      leadMembershipLabel() {
        const membership = String(this.ui.leadMembershipFilter || 'all');
        if (membership === 'added') return 'Добавленные';
        if (membership === 'not_added') return 'Не добавленные';
        return 'Все';
      },

      reloadLeadFilters() {
        this.loadLeads(true);
      },

      visibleMediaNotAddedCount() {
        return this.filteredLeadRows().filter((lead) => !this.isMediaEnabled(lead)).length;
      },

      async collectAllMediaNotAddedLeads() {
        if (String(this.ui.leadMembershipFilter || 'all') === 'added') return [];
        const selected = this.selectedMediaLeads();
        const leads = [];
        const seen = new Set();
        const pageSize = 100;
        let page = 1;
        let totalPages = 1;

        do {
          const data = await apiGetLeads({
            page,
            page_size: pageSize,
            query: (this.ui.leadFilter || '').trim(),
            sort_mode: 'status',
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: false,
            show_archived: false,
          }, {
            requestKey: `media:add-all:${page}`,
            cacheTtlMs: 0,
            forceFresh: true,
            timeoutMs: 10000,
          });

          for (const lead of data?.items || []) {
            const name = String(lead?.name || '').trim();
            const key = name.toLowerCase();
            if (!name || selected.has(key) || seen.has(key)) continue;
            seen.add(key);
            leads.push(name);
          }

          totalPages = Math.max(1, Number(data?.total_pages || totalPages || 1));
          page += 1;
        } while (page <= totalPages);

        return leads;
      },

      async enableAllMediaLeads() {
        if (this.mediaBulkAdding) return;
        this.mediaBulkAdding = true;
        this.error = null;
        try {
          const leads = await this.collectAllMediaNotAddedLeads();
          if (!leads.length) {
            toast('Нет не добавленных чатов под текущими фильтрами', 'log');
            return;
          }
          this.mediaConfig = await apiAddManyMediaLeads(leads, { timeoutMs: 30000 });
          this.pushStatus(`Media включено для ${leads.length} чатов. Фоновая обработка пойдёт по очереди.`, 'loading');
          await Promise.all([this.loadMediaConfig(true), this.loadStatus(true), this.loadLeads(true)]);
          toast(`Media включено для чатов: ${leads.length}`, 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось массово включить media');
          toast(this.error, 'error');
        } finally {
          this.mediaBulkAdding = false;
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

      imageStatusLabel(row) {
        return row?.recognized ? 'OCR готов' : 'Ждёт OCR';
      },

      imageStatusClass(row) {
        return row?.recognized ? 'badge-active' : 'badge-pending';
      },

      previewText(text, maxLen = 160) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },

      formatBytes(bytes) {
        const size = Number(bytes || 0);
        if (!size) return '0 B';
        if (size < 1024) return `${size} B`;
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
        if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(2)} MB`;
        return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`;
      },
    };
  };

  window.imagesApp = window.mediaApp;
  }
})();
