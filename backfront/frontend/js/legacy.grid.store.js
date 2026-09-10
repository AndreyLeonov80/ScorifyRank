/* Legacy grid store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.grid.store.js");
    return;
  }
  with (ctx) {
  const GRID_UI_STATE_KEY = 'grid.groups-default.v1';
  window.gridApp = function gridApp() {
    return {
      ui: createPersistedUiState(GRID_UI_STATE_KEY, {
        leadFilter: '',
        page: 1,
        pageSize: 5,
        showChannels: false,
        showGroups: true,
        showPrivate: false,
        scanFilter: 'scanning',
        statusFilter: 'all',
        groupFilter: 'all',
      }, ['leadFilter', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'scanFilter', 'statusFilter', 'groupFilter']),
      loading: false,
      error: null,
      leads: [],
      _globalEs: null,
      _leadTimer: null,
      _leadEventsBatcher: null,
      _suspendLeadSort: false,
      streamState: 'connecting',
      lastUpdatedAt: null,
      lastRealtimeAt: null,
      totalLeads: 0,
      totalLeadPages: 1,
      leadActionBusyName: null,
      leadActionBusyType: '',
      bulkUnlimitedBusy: false,
      bulkLimitDialog: {
        visible: false,
        mode: 'unlimited',
        unlimited: true,
        import_history_months: 1,
        import_message_limit: 1000,
      },
      bulkLimitOverride: null,
      personalLimitDialog: {
        visible: false,
        leadName: '',
        selector: '',
        title: '',
        import_history_months: 1,
        import_message_limit: 1000,
      },
      telegramSyncJob: null,
      telegramSyncControl: { paused: false },
      telegramSyncPauseBusy: false,
      activeTelegramSources: [],
      settings: {
        telegram_scan_groups: [],
      },
      ...createOutreachToggleState(),

      sortLeadsInPlace() {
        this.leads = (this.leads || []).slice().sort((a, b) => {
          const sourceDelta = Number(!!b?.in_source) - Number(!!a?.in_source);
          if (sourceDelta !== 0) return sourceDelta;

          const activeDelta = Number(!!(b?.telegram_active || b?.read_now)) - Number(!!(a?.telegram_active || a?.read_now));
          if (activeDelta !== 0) return activeDelta;

          const statusRank = { active: 0, pending: 1, archived: 2 };
          const statusDelta = (statusRank[a?.sync_status] ?? 9) - (statusRank[b?.sync_status] ?? 9);
          if (statusDelta !== 0) return statusDelta;

          const da = a?.last_date_utc || '';
          const db = b?.last_date_utc || '';
          if (da !== db) return db.localeCompare(da);

          const countDelta = Number(b?.count || 0) - Number(a?.count || 0);
          if (countDelta !== 0) return countDelta;

          return String(a?.name || '').localeCompare(String(b?.name || ''), 'ru');
        });
      },

      ensurePageBounds() {
        const total = this.totalPages();
        if (this.ui.page < 1) this.ui.page = 1;
        if (this.ui.page > total) this.ui.page = total;
      },

      updateLeadMeta(leadName, patch = {}) {
        if (!leadName) return;

        const found = this.leads.find(lead => lead?.name === leadName);
        if (!found) {
          this.leads.push({
            name: leadName,
            file: `${leadName}.jsonl`,
            count: 0,
            last_date_utc: null,
            last_text_preview: '',
            in_source: true,
            has_jsonl: false,
            sync_status: 'pending',
            source_selector: leadName,
            scan_group: 'C',
            scan_group_label: 'C — фоновые',
            scan_group_frequency: '1–4 раза в день',
            scan_group_interval_minutes: 360,
            bump_delta: 0,
            bump_until: 0,
            ...patch,
          });
        } else {
          Object.assign(found, patch);
        }

        if (!this._suspendLeadSort) {
          this.sortLeadsInPlace();
          this.ensurePageBounds();
        }
      },

      bumpLeadActivity(leadName, delta = 1) {
        if (!leadName || delta <= 0) return;
        const currentDelta = Number(this.leads.find(x => x?.name === leadName)?.bump_delta || 0);
        this.updateLeadMeta(leadName, {
          bump_delta: currentDelta + delta,
          bump_until: Date.now(),
        });
      },

      mergeLeadsData(data, { trackFresh = false } = {}) {
        const leadItems = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : []);
        const prevByName = new Map((this.leads || []).map(lead => [lead.name, lead]));
        const nextLeads = leadItems.map((lead) => {
          const prev = prevByName.get(lead.name);
          const nextLead = {
            ...lead,
            scan_group: lead.scan_group || prev?.scan_group || 'C',
            scan_group_label: lead.scan_group_label || prev?.scan_group_label || '',
            scan_group_frequency: lead.scan_group_frequency || prev?.scan_group_frequency || '',
            scan_group_interval_minutes: lead.scan_group_interval_minutes || prev?.scan_group_interval_minutes || null,
            bump_delta: Number(prev?.bump_delta || 0),
            bump_until: Number(prev?.bump_until || 0),
          };

          if (trackFresh && prev) {
            const prevCount = Number(prev.count || 0);
            const nextCount = Number(lead.count || 0);
            if (nextCount > prevCount) {
              nextLead.bump_delta = Number(nextLead.bump_delta || 0) + (nextCount - prevCount);
              nextLead.bump_until = Date.now();
            }
          }

          return this.applyBulkLimitOverrideToLead(nextLead);
        });

        this.leads = reconcileKeyedCollection(this.leads, nextLeads, (lead) => lead?.name || '');
        this.lastUpdatedAt = Date.now();
        this.sortLeadsInPlace();
        this.ensurePageBounds();
      },

      sourceRuntimeToLead(item) {
        const selector = String(item?.selector || '').trim();
        const title = String(item?.title || selector || '').trim();
        const safeName = title || selector;
        return {
          name: safeName,
          file: `${safeName}.jsonl`,
          count: Number(item?.duckdb_rows || 0),
          last_date_utc: item?.last_message_at || null,
          last_text_preview: item?.status_reason || '',
          in_source: !!item?.is_selected,
          has_jsonl: !!item?.has_jsonl,
          sync_status: item?.status === 'archived' ? 'archived' : (item?.status === 'pending' || item?.status === 'empty' ? 'pending' : 'active'),
          source_selector: selector || safeName,
          chat_type: item?.chat_type || 'group',
          scan_group: item?.scan_group || 'C',
          scan_group_label: item?.scan_group_label || '',
          scan_group_frequency: item?.scan_group_label || '',
          telegram_active: !!item?.read_now,
          telegram_active_stage: item?.read_stage || '',
          live_connected: !!item?.live_connected,
          backfill_running: !!item?.backfill_running,
          setup_running: !!item?.setup_running,
          paused: !!item?.paused,
          cooldown: !!item?.cooldown,
          waiting_schedule: !!item?.waiting_schedule,
          last_live_update_at: item?.last_live_update_at || null,
          read_messages_count: Number(item?.read_done || 0),
          total_messages_estimate: Number(item?.read_total || item?.duckdb_rows || 0),
          remaining_messages_estimate: Number(item?.remaining || 0),
          read_progress_percent: Number(item?.progress_percent || 0),
          import_history_months: Number(item?.limit_months ?? 1),
          import_message_limit: Number(item?.limit_messages ?? 1000),
          telegram_status: item?.status || '',
          source_policy_mode: item?.source_policy_mode || '',
          source_scan_allowed: item?.source_scan_allowed !== false,
        };
      },

      applyBulkLimitOverrideToLead(lead) {
        if (!lead || !this.bulkLimitOverride || !lead.in_source) return lead;
        return {
          ...lead,
          import_history_months: this.bulkLimitOverride.import_history_months,
          import_message_limit: this.bulkLimitOverride.import_message_limit,
          import_max_history_months: this.bulkLimitOverride.import_history_months,
          import_max_message_limit: this.bulkLimitOverride.import_message_limit,
        };
      },

      applyGlobalLeadEvent(rec) {
        const leadName = String(rec?.chat?.username || rec?.chat?.title || rec?.lead || '').trim();
        if (!leadName) return;

        const msg = rec?.message || {};
        const previewText = (msg.text || '').trim() || (msg.has_media ? '[media]' : '');
        const previousLead = this.leads.find(x => x?.name === leadName) || null;
        const nextCount = Number(previousLead?.count || 0) + 1;

        this.bumpLeadActivity(leadName, 1);
        this.updateLeadMeta(leadName, {
          file: previousLead?.file || `${leadName}.jsonl`,
          count: nextCount,
          last_date_utc: msg.date_utc || previousLead?.last_date_utc || null,
          last_text_preview: previewText || previousLead?.last_text_preview || '',
          in_source: previousLead?.in_source ?? true,
          has_jsonl: true,
          sync_status: 'active',
          source_selector: previousLead?.source_selector || leadName,
          chat_type: previousLead?.chat_type || 'channel',
          is_archived: Boolean(previousLead?.is_archived),
        });

        this.lastRealtimeAt = Date.now();
        this.lastUpdatedAt = Date.now();
      },

      applyGlobalLeadEventsBatch(batch) {
        if (!Array.isArray(batch) || !batch.length) return;
        this._suspendLeadSort = true;
        try {
          for (const rec of batch) {
            this.applyGlobalLeadEvent(rec);
          }
        } finally {
          this._suspendLeadSort = false;
        }
        this.sortLeadsInPlace();
        this.ensurePageBounds();
        this.lastRealtimeAt = Date.now();
        this.lastUpdatedAt = Date.now();
      },

      typeVisible(lead) {
        if (!lead) return false;
        if (lead.chat_type === 'group') return !!this.ui.showGroups;
        if (lead.chat_type === 'private') return !!this.ui.showPrivate;
        if (lead.chat_type === 'bot') return false;
        return !!this.ui.showChannels;
      },

      filteredLeads() {
        return this.leads || [];
      },

      totalPages() {
        return Math.max(1, Number(this.totalLeadPages || 1));
      },

      pagedLeads() {
        return this.filteredLeads();
      },

      pageWindow() {
        const total = this.totalPages();
        const current = Math.min(Math.max(1, this.ui.page), total);
        let start = Math.max(1, current - 2);
        let end = Math.min(total, start + 4);
        start = Math.max(1, end - 4);

        const pages = [];
        for (let page = start; page <= end; page += 1) {
          pages.push(page);
        }
        return pages;
      },

      visibleRangeText() {
        const items = this.filteredLeads();
        const total = Math.max(0, Number(this.totalLeads || 0));
        if (!items.length || !total) return '0 из 0';
        const size = Math.max(1, Number(this.ui.pageSize || 1));
        const start = (this.ui.page - 1) * size;
        const from = start + 1;
        const to = Math.min(total, start + items.length);
        return `${from}-${to} из ${total}`;
      },

      resetPage() {
        this.ui.page = 1;
        this.persistUi();
        this.loadLeads();
      },

      setScanFilter(value) {
        this.ui.scanFilter = String(value || 'scanning');
        this.resetPage();
      },

      setStatusFilter(value) {
        this.ui.statusFilter = String(value || 'all');
        this.resetPage();
      },

      setGroupFilter(value) {
        this.ui.groupFilter = String(value || 'all');
        this.resetPage();
      },

      scanGroups() {
        const groups = Array.isArray(this.settings?.telegram_scan_groups)
          ? this.settings.telegram_scan_groups
          : [];
        return groups.length ? groups : [
          { id: 'A', label: 'A — критичные продажи/лиды', frequency: 'каждые 1–5 минут' },
          { id: 'B', label: 'B — важные отраслевые', frequency: 'каждые 10–30 минут' },
          { id: 'C', label: 'C — фоновые', frequency: '1–4 раза в день' },
          { id: 'D', label: 'D — архив/редко', frequency: 'раз в сутки/неделю' },
        ];
      },

      groupLabel(lead) {
        const groupId = String(lead?.scan_group || 'C');
        const found = this.scanGroups().find(group => String(group?.id || '') === groupId);
        return found?.label || lead?.scan_group_label || groupId;
      },

      groupFrequency(lead) {
        const groupId = String(lead?.scan_group || 'C');
        const found = this.scanGroups().find(group => String(group?.id || '') === groupId);
        return found?.frequency || lead?.scan_group_frequency || '';
      },

      goToPage(page) {
        this.ui.page = Number(page || 1);
        this.ensurePageBounds();
        this.persistUi();
        this.loadLeads({ silent: true });
      },

      prevPage() {
        this.goToPage(this.ui.page - 1);
      },

      nextPage() {
        this.goToPage(this.ui.page + 1);
      },

      previewText(text, maxLen = 110) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },

      leadPreview(lead) {
        if (!lead) return '';
        const telegramStatus = String(lead.telegram_status || '').trim();
        if (lead.last_error && ['risk_blocked', 'blocked_privacy', 'risk_rate_limited', 'cooldown'].includes(telegramStatus)) {
          return `Telegram: ${lead.last_error}`;
        }
        if (lead.retry_after && ['risk_rate_limited', 'cooldown'].includes(telegramStatus)) {
          return `Telegram cooldown до ${fmtDate(lead.retry_after, true)}`;
        }
        if (lead.last_text_preview) return this.previewText(lead.last_text_preview, 110);
        if (!lead.in_source) {
          return lead.has_jsonl ? 'Не сканируется, история сохранена в базе' : 'Не сканируется';
        }
        if (lead.sync_status === 'pending') return 'Сканируется: ждём первую выгрузку из Telegram';
        if (lead.sync_status === 'archived') return 'Не сканируется, история сохранена';
        return '';
      },

      leadStatusText(lead) {
        if (!lead) return '';
        if (lead.telegram_active) return `читает Telegram${lead.telegram_active_stage ? ` · ${lead.telegram_active_stage}` : ''}`;
        const telegramStatus = String(lead.telegram_status || '').trim();
        if (telegramStatus === 'blocked_privacy') return 'privacy blocked';
        if (telegramStatus === 'risk_blocked') return 'risk · blocked';
        if (telegramStatus === 'risk_rate_limited') {
          return lead.retry_after ? `risk · cooldown до ${fmtDate(lead.retry_after, true)}` : 'risk · cooldown';
        }
        if (telegramStatus === 'cooldown') {
          return lead.retry_after ? `cooldown до ${fmtDate(lead.retry_after, true)}` : 'cooldown';
        }
        if (lead.in_source) {
          if (lead.sync_status === 'pending' || Number(lead.count || 0) <= 0) return 'ждёт первую выгрузку';
          return 'ожидает расписания';
        }
        return lead.has_jsonl ? 'не сканируется · есть в базе' : 'не сканируется';
      },

      leadStatusClass(lead) {
        if (!lead) return 'badge-archived';
        if (lead.telegram_active) return 'badge-active';
        const telegramStatus = String(lead.telegram_status || '').trim();
        if (telegramStatus === 'risk_blocked' || telegramStatus === 'blocked_privacy') return 'badge-error';
        if (telegramStatus === 'risk_rate_limited' || telegramStatus === 'cooldown') return 'badge-pending';
        if (!lead.in_source) return 'badge-archived';
        if (lead.sync_status === 'active') return 'badge-active';
        if (lead.sync_status === 'pending') return 'badge-pending';
        return 'badge-archived';
      },

      leadDeltaText(lead) {
        const delta = Number(lead?.bump_delta || 0);
        return delta > 0 ? `+${delta}` : '';
      },

      leadHasFreshActivity(lead) {
        return Number(lead?.bump_delta || 0) > 0;
      },

      canDeactivateLead(lead) {
        return !!lead?.source_selector && !!lead?.in_source;
      },

      canActivateLead(lead) {
        return !!lead?.source_selector && !lead?.in_source;
      },

      canDeleteLead(lead) {
        return !!lead?.name;
      },

      isLeadActionBusy(lead, action) {
        return this.leadActionBusyName === lead?.name && this.leadActionBusyType === action;
      },

      realtimeLabel() {
        if (this.streamState === 'connected') return 'Realtime подключен';
        if (this.streamState === 'error') return 'Realtime переподключается';
        return 'Realtime подключается';
      },

      realtimeClass() {
        if (this.streamState === 'connected') return 'badge-active';
        if (this.streamState === 'error') return 'badge-pending';
        return 'badge-archived';
      },

      async init() {
        this._leadEventsBatcher = createBatchedQueueProcessor({
          delayMs: 250,
          maxBatchSize: 100,
          onFlush: (batch) => this.applyGlobalLeadEventsBatch(batch),
        });
        await this.loadSettings();
        await this.loadTelegramSyncJob();
        await this.loadTelegramSyncControl();
        await this.loadLeads();
        this.startLeadPolling();
        this.startGlobalLeadStream();
      },

      normalizeActiveTelegramSources(job) {
        const result = job?.result && typeof job.result === 'object' ? job.result : {};
        const rows = Array.isArray(result.active_sources) ? result.active_sources : [];
        return rows
          .filter(item => item && String(item.selector || item.title || '').trim())
          .slice(0, 8);
      },

      telegramSyncProgressLabel() {
        const job = this.telegramSyncJob || {};
        const result = job?.result && typeof job.result === 'object' ? job.result : {};
        const syncTotal = Math.max(0, Number(this.totalLeads || 0));
        const workerTotal = Math.max(0, Number(result.selected_sources_count || job.chunks_total || 0));
        const enabled = Math.max(0, Number(result.enabled_sources_count || job.chunks_done || 0));
        const active = Math.max(0, Number(result.active_sources_count || this.activeTelegramSources.length || 0));
        const total = workerTotal || syncTotal;
        const pending = Math.max(0, total - Math.max(enabled, active));
        if (total > 0) {
          return `Telegram live-sync: выбрано ${total}; подключено ${Math.min(enabled, total)}; активных сейчас ${active}; ожидают ${pending}`;
        }
        return job.progress_label || 'Статус worker-а появится после запуска Telegram sync.';
      },

      telegramSyncHumanLabel() {
        const job = this.telegramSyncJob || {};
        const result = job?.result && typeof job.result === 'object' ? job.result : {};
        const control = this.telegramSyncControl || result.sync_control || {};
        if (control.paused) {
          return `Telegram sync на паузе: ${control.reason || 'ручная пауза'}. Запросы в Telegram не выполняются.`;
        }
        const total = Math.max(0, Number(result.selected_sources_count || job.chunks_total || this.totalLeads || 0));
        const connected = Math.max(0, Number(result.enabled_sources_count || job.chunks_done || 0));
        const active = Math.max(0, Number(result.active_sources_count || this.activeTelegramSources.length || 0));
        const pending = Math.max(0, total - Math.max(connected, active));
        const heartbeat = result.heartbeat_age_seconds != null
          ? ` · heartbeat ${Math.round(Number(result.heartbeat_age_seconds || 0))}с назад`
          : '';
        if (!total) return 'Telegram sync: ждём данных worker-а.';
        if (active > 0) return `Telegram sync: сейчас читает ${active}, подключено ${connected}/${total}${heartbeat}.`;
        return `Telegram sync: подключено ${connected}/${total}, ${pending} ждут очереди, активного чтения сейчас нет${heartbeat}.`;
      },

      async loadTelegramSyncJob() {
        try {
          const job = await apiGetTelegramSyncJob({ timeoutMs: 5000, cacheTtlMs: 0, forceFresh: true });
          this.telegramSyncJob = job;
          this.activeTelegramSources = this.normalizeActiveTelegramSources(job);
          const control = job?.result?.sync_control;
          if (control && typeof control === 'object') this.telegramSyncControl = control;
        } catch (e) {
          console.warn('Grid telegram sync job failed:', e);
        }
      },

      async loadTelegramSyncControl() {
        try {
          this.telegramSyncControl = await apiGetTelegramSyncControl({ timeoutMs: 5000, cacheTtlMs: 0, forceFresh: true });
        } catch (e) {
          console.warn('Grid telegram sync control failed:', e);
        }
      },

      telegramSyncPaused() {
        return !!this.telegramSyncControl?.paused;
      },

      async toggleTelegramSyncPause() {
        if (this.telegramSyncPauseBusy) return;
        this.telegramSyncPauseBusy = true;
        this.error = null;
        try {
          const paused = this.telegramSyncPaused();
          const result = paused
            ? await apiResumeTelegramSync('manual-sync-page', { timeoutMs: 20000 })
            : await apiPauseTelegramSync('manual-sync-page', { timeoutMs: 20000 });
          this.telegramSyncControl = result?.status || { paused: !paused };
          await this.loadTelegramSyncJob();
          await this.loadLeads({ silent: true, forceFresh: true });
          toast(paused ? 'Telegram sync продолжен' : 'Telegram sync поставлен на паузу. Запросы в Telegram остановлены.', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.telegramSyncPauseBusy = false;
        }
      },

      async loadSettings() {
        try {
          const data = await apiGetAppSettings({ cacheKey: 'grid:settings', cacheTtlMs: 30000, timeoutMs: 5000 });
          this.settings = {
            ...this.settings,
            ...data,
            telegram_scan_groups: Array.isArray(data?.telegram_scan_groups) ? data.telegram_scan_groups : this.scanGroups(),
          };
        } catch (e) {
          console.warn('Grid settings failed:', e);
        }
      },

      async loadLeads(options = {}) {
        const { silent = false, trackFresh = false, forceFresh = false } = options;
        if (!silent) this.loading = true;
        this.error = null;
        try {
          const params = {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.leadFilter || '').trim(),
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            scan_filter: this.ui.scanFilter,
            status_filter: this.ui.statusFilter,
            group_filter: this.ui.groupFilter,
            sort_mode: 'status',
          };
          const qs = buildQuery(params);
          const data = await apiJson(`${API_BASE}/api/payme/sources/runtime-status${qs ? `?${qs}` : ''}`, buildPagedRequestOptions('grid:runtime-status', params, {
            requestKey: 'grid:leads',
            cacheTtlMs: 0,
            persistCache: false,
            forceFresh: !!forceFresh,
            timeoutMs: 5000,
          }));
          this.totalLeads = Number(data?.total || 0);
          this.totalLeadPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
          this.persistUi();
          this.mergeLeadsData((data?.items || []).map((item) => this.sourceRuntimeToLead(item)), { trackFresh });
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          if (!silent) toast(this.error, 'error');
        } finally {
          if (!silent) this.loading = false;
        }
      },

      persistUi() {
        persistUiState(GRID_UI_STATE_KEY, this.ui, ['leadFilter', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'scanFilter', 'statusFilter', 'groupFilter']);
      },

      async deactivateLead(lead) {
        if (!lead?.name) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!selector) return;
        if (!window.confirm(`Отключить синхронизацию для "${selector}"?`)) return;

        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'deactivate';
        this.error = null;
        try {
          const result = await apiDeactivateLead({ lead: lead.name, selector });
          await this.loadLeads();
          toast(result.message || 'Синхронизация отключена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async activateLead(lead) {
        if (!lead?.name) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!selector) return;

        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'activate';
        this.error = null;
        try {
          const result = await apiActivateLead({ lead: lead.name, selector });
          await this.loadLeads();
          toast(result.message || 'Синхронизация включена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async deleteLead(lead) {
        if (!lead?.name) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();

        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'delete';
        this.error = null;
        try {
          const result = await apiDeleteLead({ lead: lead.name, selector });
          await this.loadLeads();
          toast(result.message || 'Лид удалён', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async setLeadGroup(lead, scanGroup) {
        if (!lead?.name || !scanGroup) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'group';
        this.error = null;
        try {
          const result = await apiSetLeadGroup({
            lead: lead.name,
            selector,
            scan_group: scanGroup,
          });
          if (typeof invalidateTelegramSourceCaches === 'function') invalidateTelegramSourceCaches();
          const nextGroup = result.scan_group || scanGroup;
          const nextLabel = result.scan_group_label || lead.scan_group_label || '';
          const nextFrequency = result.scan_group_frequency || lead.scan_group_frequency || '';
          const nextInterval = result.scan_group_interval_minutes ?? lead.scan_group_interval_minutes ?? null;
          const applySavedGroup = () => {
            this.leads = (this.leads || []).map((item) => {
              if (item?.name !== lead.name && item?.source_selector !== selector) return item;
              return {
                ...item,
                scan_group: nextGroup,
                scan_group_label: nextLabel,
                scan_group_frequency: nextFrequency,
                scan_group_interval_minutes: nextInterval,
              };
            });
          };
          applySavedGroup();
          await this.loadLeads({ forceFresh: true, silent: true });
          applySavedGroup();
          toast(result.message || 'Группа обновлена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      openLeadChat(lead) {
        const name = String(lead?.name || '').trim();
        if (!name) return;
        try {
          window.localStorage.setItem('xfiles.index.lastOpenChat.v1', name);
        } catch (_) {}
        window.location.href = 'index.html';
      },

      openBulkLimitDialog(mode = 'unlimited') {
        const unlimited = mode !== 'limited';
        this.bulkLimitDialog = {
          visible: true,
          mode: unlimited ? 'unlimited' : 'limited',
          unlimited,
          import_history_months: unlimited ? 1 : Number(this.settings?.import_default_history_months || 1),
          import_message_limit: unlimited ? 1000 : Number(this.settings?.import_default_message_limit || 1000),
        };
      },

      closeBulkLimitDialog() {
        this.bulkLimitDialog = {
          ...(this.bulkLimitDialog || {}),
          visible: false,
        };
      },

      openPersonalLimitDialog(lead) {
        if (!lead) return;
        this.personalLimitDialog = {
          visible: true,
          leadName: lead.name || '',
          selector: lead.source_selector || lead.name || '',
          title: lead.name || lead.source_selector || 'Источник',
          import_history_months: Number(lead.import_history_months ?? this.settings?.import_default_history_months ?? 1),
          import_message_limit: Number(lead.import_message_limit ?? this.settings?.import_default_message_limit ?? 1000),
        };
      },

      closePersonalLimitDialog() {
        this.personalLimitDialog = {
          ...(this.personalLimitDialog || {}),
          visible: false,
        };
      },

      async applyPersonalImportLimits() {
        const dialog = this.personalLimitDialog || {};
        const selector = String(dialog.selector || '').trim();
        if (!selector || this.bulkUnlimitedBusy) return;
        this.bulkUnlimitedBusy = true;
        this.error = null;
        try {
          const historyMonths = Math.max(0, Number(dialog.import_history_months || 0));
          const messageLimit = Math.max(0, Number(dialog.import_message_limit || 0));
          const result = await apiSaveTelegramDialogSettings({
            selector,
            import_history_months: historyMonths,
            import_message_limit: messageLimit,
          }, { timeoutMs: 15000, forceFresh: true });
          if (typeof invalidateTelegramSourceCaches === 'function') invalidateTelegramSourceCaches();
          const nextHistory = Number(result?.import_history_months ?? historyMonths);
          const nextMessages = Number(result?.import_message_limit ?? messageLimit);
          const applySavedLimits = () => {
            this.leads = (this.leads || []).map((lead) => {
            if (lead?.name !== dialog.leadName && lead?.source_selector !== selector) return lead;
            return {
              ...lead,
              import_history_months: nextHistory,
              import_message_limit: nextMessages,
              import_max_history_months: Number(result?.import_max_history_months ?? nextHistory),
              import_max_message_limit: Number(result?.import_max_message_limit ?? nextMessages),
            };
            });
          };
          applySavedLimits();
          await this.loadLeads({ forceFresh: true });
          applySavedLimits();
          this.closePersonalLimitDialog();
          toast(result?.message || 'Персональный лимит источника сохранён', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.bulkUnlimitedBusy = false;
        }
      },

      async applyBulkImportLimits() {
        if (this.bulkUnlimitedBusy) return;
        this.bulkUnlimitedBusy = true;
        this.error = null;
        try {
          const dialog = this.bulkLimitDialog || {};
          const unlimited = !!dialog.unlimited;
          const result = await apiPostJson(`${API_BASE}/api/payme/settings/import/limits-all`, {
            unlimited,
            import_history_months: Math.max(1, Number(dialog.import_history_months || 1)),
            import_message_limit: Math.max(1, Number(dialog.import_message_limit || 1000)),
          }, { timeoutMs: 20000 });
          if (typeof invalidateTelegramSourceCaches === 'function') invalidateTelegramSourceCaches();
          if (result?.settings) {
            this.settings = {
              ...this.settings,
              ...result.settings,
              telegram_scan_groups: Array.isArray(result.settings?.telegram_scan_groups)
                ? result.settings.telegram_scan_groups
                : this.scanGroups(),
            };
          } else {
            await this.loadSettings();
          }
          const nextHistory = unlimited ? 0 : Math.max(1, Number(dialog.import_history_months || 1));
          const nextMessages = unlimited ? 0 : Math.max(1, Number(dialog.import_message_limit || 1000));
          this.bulkLimitOverride = {
            import_history_months: nextHistory,
            import_message_limit: nextMessages,
          };
          this.leads = (this.leads || []).map((lead) => ({
            ...lead,
            import_history_months: nextHistory,
            import_message_limit: nextMessages,
            import_max_history_months: unlimited ? 0 : nextHistory,
            import_max_message_limit: unlimited ? 0 : nextMessages,
          }));
          await this.loadLeads({ forceFresh: true, trackFresh: false });
          this.leads = (this.leads || []).map((lead) => ({
            ...lead,
            import_history_months: nextHistory,
            import_message_limit: nextMessages,
            import_max_history_months: unlimited ? 0 : nextHistory,
            import_max_message_limit: unlimited ? 0 : nextMessages,
          }));
          await this.loadTelegramSyncJob();
          this.closeBulkLimitDialog();
          toast(result.message || 'Лимиты сканирования применены ко всем источникам', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.bulkUnlimitedBusy = false;
        }
      },

      startLeadPolling() {
        this.stopLeadPolling();
        this._leadTimer = setInterval(() => {
          if (document.hidden || this.loading) return;
          this.loadLeads({ silent: true, trackFresh: true });
          this.loadTelegramSyncJob();
          this.loadTelegramSyncControl();
        }, 10000);
      },

      stopLeadPolling() {
        if (this._leadTimer) {
          clearInterval(this._leadTimer);
          this._leadTimer = null;
        }
      },

      startGlobalLeadStream() {
        this.stopGlobalLeadStream();
        this.streamState = 'connecting';
        try {
          const client = window.BackfrontRealtime;
          if (!client?.startTypedRealtimeStreamConsumer) throw new Error('typed realtime client unavailable');
          this._globalEs = client.startTypedRealtimeStreamConsumer({
            baseUrl: URL_REALTIME_STREAM,
            baseCandidates: API_BASE_CANDIDATES_UNIQUE,
            types: ['lead'],
            onState: ({ state }) => {
              this.streamState = state === 'error' ? 'error' : (state === 'connected' ? 'connected' : 'connecting');
            },
            onEnvelope: (envelope) => {
              if (envelope?.type === 'lead_event' && envelope?.payload) {
                this.streamState = 'connected';
                this._leadEventsBatcher?.push(envelope.payload);
              }
            },
            onError: (error) => {
              this.streamState = 'error';
              console.warn('Grid typed SSE stream error:', error);
            },
          });
          if (!this._globalEs) throw new Error('typed realtime stream init failed');
        } catch (e) {
          this.streamState = 'error';
          console.warn('Grid SSE init failed:', e);
          return;
        }
      },

      stopGlobalLeadStream() {
        this._leadEventsBatcher?.flush();
        if (this._globalEs) {
          try { this._globalEs.close(); } catch {}
          this._globalEs = null;
        }
      },
    };
  };
  }
})();
