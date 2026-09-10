/* Legacy import store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.import.store.js");
    return;
  }
  with (ctx) {
  const IMPORT_UI_STATE_KEY = 'import.groups-default.v1';
  const IMPORT_INITIAL_PROGRESS_DONE_KEY = 'gramlead.import.initial-progress.done.v1';
  window.telegramImportApp = function telegramImportApp() {
    return {
      loading: false,
      importing: false,
      removingAll: false,
      syncingImport: false,
      importProgress: {
        visible: false,
        running: false,
        percent: 0,
        etaSec: 0,
        status: '',
        detail: '',
        kind: '',
        startedAt: 0,
        timeoutSec: 15,
      },
      _importProgressTimer: null,
      rowBusySelector: null,
      rowBusyAction: '',
      error: null,
      cacheWarning: null,
      dialogs: [],
      selected: {},
      authStatus: null,
      settings: {
        import_default_add_limit: 50,
        import_default_history_months: 1,
        import_default_message_limit: 1000,
        import_max_history_months: 1,
        import_max_message_limit: 1000,
      },
      ui: createPersistedUiState(IMPORT_UI_STATE_KEY, {
        query: '',
        page: 1,
        pageSize: 5,
        showChannels: false,
        showGroups: true,
        showPrivate: false,
        membershipFilter: 'all',
        sortBy: 'last_date_desc',
      }, ['query', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'membershipFilter', 'sortBy']),
      totalDialogs: 0,
      totalDialogPages: 1,
      ...createOutreachToggleState(),

      async init() {
        await this.loadSettings();
        await this.refreshAuthStatus();
        const hadCachedDialogs = this.hydrateDialogsFromLocalCache();
        const showInitialProgress = this.shouldShowInitialImportProgress(hadCachedDialogs);
        if (showInitialProgress) {
          this.startImportProgress({
            kind: 'initial',
            status: 'Загружаю источники Telegram для импорта...',
            detail: 'Первый вход после авторизации: жду список диалогов и статусы добавления.',
            timeoutSec: 18,
          });
          this.updateImportProgress({
            percent: 18,
            status: 'Настройки Import загружены',
            detail: 'Проверяю локальный кэш диалогов.',
          });
        }
        await this.loadDialogs({
          forceFresh: false,
          progress: false,
          progressStatus: hadCachedDialogs ? 'Показываю сохранённый список Import...' : 'Загружаю список диалогов Telegram...',
        });
        if (this.error) {
          if (showInitialProgress) {
            this.finishImportProgress({
              ok: false,
              status: 'Import не загрузился',
              detail: this.error,
            });
          }
          return;
        }
        if (showInitialProgress) {
          this.updateImportProgress({
            percent: 82,
            status: 'Диалоги Telegram получены',
            detail: 'Фиксирую первый успешный импорт, дальше popup будет только для явных действий.',
          });
          this.markInitialImportProgressDone();
          this.finishImportProgress({
            ok: true,
            status: 'Import готов',
            detail: `Загружено строк: ${Number(this.totalDialogs || this.dialogs.length || 0)}.`,
          });
        }
      },

      initialProgressFingerprint() {
        const status = this.authStatus || {};
        return [
          status.pending_phone,
          status.telegram_api_id,
          status.auth_status || status.auth_step,
        ].map((item) => String(item || '').trim()).filter(Boolean).join(':') || 'default';
      },

      initialProgressDoneStorageKey() {
        return `${IMPORT_INITIAL_PROGRESS_DONE_KEY}:${this.initialProgressFingerprint()}`;
      },

      isTelegramAuthorizedForInitialProgress() {
        const status = this.authStatus || {};
        return status.auth_status === 'authorized' || status.auth_step === 'done' || status.connected === true;
      },

      shouldShowInitialImportProgress(hadCachedDialogs = false) {
        if (hadCachedDialogs || !this.isTelegramAuthorizedForInitialProgress()) return false;
        try {
          return window.localStorage?.getItem(this.initialProgressDoneStorageKey()) !== '1';
        } catch (_) {
          return true;
        }
      },

      markInitialImportProgressDone() {
        try {
          window.localStorage?.setItem(this.initialProgressDoneStorageKey(), '1');
        } catch (_) {}
      },

      invalidateSourceCaches() {
        try {
          if (typeof invalidateTelegramSourceCaches === 'function') invalidateTelegramSourceCaches();
        } catch (_) {}
      },

      _emitImportProgress() {
        if (typeof this.emit === 'function') this.emit();
      },

      updateImportProgress(patch = {}) {
        this.importProgress = {
          ...(this.importProgress || {}),
          ...patch,
        };
        this._emitImportProgress();
      },

      startImportProgress(options = {}) {
        if (this._importProgressTimer) {
          window.clearInterval(this._importProgressTimer);
          this._importProgressTimer = null;
        }
        const startedAt = Date.now();
        const timeoutSec = Math.max(5, Math.min(120, Number(options.timeoutSec || 15)));
        this.importProgress = {
          visible: true,
          running: true,
          percent: Math.max(2, Math.min(35, Number(options.percent || 5))),
          etaSec: timeoutSec,
          status: String(options.status || 'Подключаюсь к Telegram...'),
          detail: String(options.detail || 'Backend читает локальный кэш и при необходимости обновляет данные Telegram.'),
          kind: String(options.kind || 'load'),
          startedAt,
          timeoutSec,
        };
        this._emitImportProgress();
        this._importProgressTimer = window.setInterval(() => {
          const elapsed = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
          const base = Number(this.importProgress?.percent || 5);
          const estimated = Math.min(92, Math.max(base, Math.round((elapsed / timeoutSec) * 86)));
          const nextStatus = elapsed < 4
            ? this.importProgress.status
            : elapsed < 10
              ? 'Telegram отвечает, обновляю таблицу...'
              : 'Операция ещё выполняется, ожидаю backend...';
          this.importProgress = {
            ...(this.importProgress || {}),
            percent: estimated,
            etaSec: Math.max(1, timeoutSec - elapsed),
            status: nextStatus,
          };
          this._emitImportProgress();
        }, 1000);
      },

      finishImportProgress(options = {}) {
        if (this._importProgressTimer) {
          window.clearInterval(this._importProgressTimer);
          this._importProgressTimer = null;
        }
        const ok = options.ok !== false;
        this.importProgress = {
          ...(this.importProgress || {}),
          visible: true,
          running: false,
          percent: ok ? 100 : Math.max(1, Number(this.importProgress?.percent || 0)),
          etaSec: 0,
          status: String(options.status || (ok ? 'Готово' : 'Не удалось завершить импорт')),
          detail: String(options.detail || ''),
        };
        this._emitImportProgress();
        const hideDelayMs = Math.max(400, Number(options.hideDelayMs || (ok ? 1200 : 3000)));
        window.setTimeout(() => {
          if (this.importProgress?.running) return;
          this.importProgress = {
            ...(this.importProgress || {}),
            visible: false,
          };
          this._emitImportProgress();
        }, hideDelayMs);
      },

      defaultAddLimit() {
        const value = Number(this.settings?.import_default_add_limit || 50);
        if (!Number.isFinite(value)) return 50;
        return Math.min(1000000, Math.max(1, Math.trunc(value)));
      },

      importLimitValue(value, fallback) {
        const parsed = Number(value);
        if (Number.isFinite(parsed) && parsed === 0) return 0;
        if (!Number.isFinite(parsed)) return fallback;
        return Math.max(1, Math.trunc(parsed));
      },

      importMaxHistoryMonths() {
        const value = Number(this.settings?.import_max_history_months);
        if (Number.isFinite(value) && value === 0) return 0;
        return Math.max(1, Math.trunc(Number.isFinite(value) ? value : 1));
      },

      importMaxMessageLimit() {
        const value = Number(this.settings?.import_max_message_limit);
        if (Number.isFinite(value) && value === 0) return 0;
        return Math.max(1, Math.trunc(Number.isFinite(value) ? value : 1000));
      },

      clampImportHistoryMonths(value) {
        const max = this.importMaxHistoryMonths();
        const parsed = Number(value || 0);
        if (max === 0 || parsed === 0) return 0;
        return Math.min(this.importMaxHistoryMonths(), Math.max(1, Math.trunc(Number.isFinite(parsed) ? parsed : 1)));
      },

      clampImportMessageLimit(value) {
        const max = this.importMaxMessageLimit();
        const parsed = Number(value || 0);
        if (max === 0 || parsed === 0) return 0;
        return Math.min(this.importMaxMessageLimit(), Math.max(1, Math.trunc(Number.isFinite(parsed) ? parsed : 1000)));
      },

      async loadSettings() {
        try {
          const data = await apiGetAppSettings({ cacheKey: 'app:settings', cacheTtlMs: 30000, timeoutMs: 5000 });
          this.settings.import_default_add_limit = Math.min(
            1000000,
            Math.max(1, Number(data?.import_default_add_limit || 50)),
          );
          this.settings.import_max_history_months = this.importLimitValue(data?.import_max_history_months, 1);
          this.settings.import_max_message_limit = this.importLimitValue(data?.import_max_message_limit, 1000);
          this.settings.import_default_history_months = this.clampImportHistoryMonths(data?.import_default_history_months ?? 1);
          this.settings.import_default_message_limit = this.clampImportMessageLimit(data?.import_default_message_limit ?? 1000);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          console.warn('Import settings failed:', e);
        }
      },

      async refreshAuthStatus() {
        try {
          this.authStatus = await apiGetRuntimeStatus();
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          console.warn('Import auth status failed:', e);
        }
      },

      dialogRequestParams(options = {}) {
        const membershipFilter = String(this.ui.membershipFilter || 'all');
        return {
          page: this.ui.page,
          page_size: this.ui.pageSize,
          query: (this.ui.query || '').trim(),
          show_channels: this.ui.showChannels,
          show_groups: this.ui.showGroups,
          show_private: this.ui.showPrivate,
          show_bots: true,
          show_archived: true,
          membership_filter: membershipFilter,
          sort_by: this.ui.sortBy,
          force_refresh: !!options.forceRefresh,
        };
      },

      applyDialogsData(data) {
        const membership = String(this.ui.membershipFilter || 'all');
        const rawItems = Array.isArray(data?.items) ? data.items : [];
        const visibleItems = rawItems.filter((dialog) => {
          if (membership === 'added') return !!dialog?.is_already_added;
          if (membership === 'not_added') return !dialog?.is_already_added;
          return true;
        });
        this.dialogs = reconcileKeyedCollection([], visibleItems, (dialog) => dialog?.id ?? dialog?.selector ?? '');
        const filteredOut = rawItems.length - visibleItems.length;
        this.totalDialogs = filteredOut > 0 ? visibleItems.length : Number(data?.total || visibleItems.length || 0);
        this.totalDialogPages = filteredOut > 0 ? 1 : Number(data?.total_pages || 1);
        this.ui.page = Number(data?.page || this.ui.page || 1);
        this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
        this.persistUi();
        this.pruneSelection();
      },

      hydrateDialogsFromLocalCache() {
        const params = this.dialogRequestParams();
        const cached = getImportDialogsCachedResponse(params);
        if (!cached) return false;
        this.applyDialogsData(cached);
        const cachedAt = cached.__cached_at ? fmtDate(cached.__cached_at, true) : 'ранее';
        const exact = cached.__cache_exact_match ? 'для текущих фильтров' : 'последний доступный';
        this.cacheWarning = `Сразу показываю ${exact} кэш Import от ${cachedAt}. Для живого обновления нажмите “Синхронизировать”.`;
        return true;
      },

      async loadDialogs(options = {}) {
        const {
          forceFresh = false,
          progress = false,
          progressStatus = 'Загружаю список диалогов Telegram...',
          progressDetail = '',
          progressKind = 'load-dialogs',
          timeoutSec = null,
          timeoutMs = 20000,
          _retriedNetwork = false,
        } = options || {};
        this.loading = true;
        this.error = null;
        this.cacheWarning = null;
        const params = this.dialogRequestParams({ forceRefresh: !!forceFresh });
        const hasWarmRows = Array.isArray(this.dialogs) && this.dialogs.length > 0;
        const hasExactLocalCache = !!getImportDialogsCachedResponse(params);
        const shouldShowProgress = !!progress || !!params.force_refresh || (!hasWarmRows && !hasExactLocalCache);
        if (shouldShowProgress) {
          this.startImportProgress({
            kind: progressKind,
            status: progressStatus,
            detail: progressDetail || (params.force_refresh
              ? 'Обращаюсь к Telegram за свежим списком диалогов; это может занять до полутора минут.'
              : 'Жду список диалогов от backend и готовлю фильтры.'),
            timeoutSec: timeoutSec || (params.force_refresh ? 95 : 18),
          });
        } else {
          this.updateImportProgress({ status: progressStatus, detail: 'Жду ответ backend по Telegram dialogs.' });
        }
        try {
          const data = await apiGetTelegramDialogs(params, buildPagedRequestOptions('import:dialogs:v4', params, {
            requestKey: `import:dialogs:v4:${params.membership_filter}:${params.page}:${params.page_size}:${params.query}:${params.show_channels}:${params.show_groups}:${params.show_private}:${params.show_bots}:${params.show_archived}:${params.sort_by}:${params.force_refresh}`,
            cacheTtlMs: 5000,
            forceFresh,
            timeoutMs: params.force_refresh ? Math.max(timeoutMs, 95000) : timeoutMs,
          }));
          rememberImportDialogsResponse(params, data);
          this.applyDialogsData(data);
          if (shouldShowProgress) {
            this.finishImportProgress({
              ok: true,
              status: 'Список Telegram обновлён',
              detail: `Показано строк: ${Number(data?.items?.length || 0)}, всего: ${Number(data?.total || 0)}.`,
            });
          }
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          const rawError = String(e?.message || e);
          if (!_retriedNetwork && rawError.includes('Failed to fetch')) {
            await new Promise(resolve => setTimeout(resolve, 900));
            return await this.loadDialogs({
              ...options,
              _retriedNetwork: true,
              progress: false,
              timeoutMs: Math.max(timeoutMs, 30000),
            });
          }
          const cached = getImportDialogsCachedResponse(params);
          if (cached) {
            this.applyDialogsData(cached);
            const cachedAt = cached.__cached_at ? fmtDate(cached.__cached_at, true) : 'ранее';
            const exact = cached.__cache_exact_match ? 'для текущих фильтров' : 'последний доступный';
            const reason = isTelegramCooldownError(e)
              ? describeTelegramCooldownError(e)
              : `Не удалось быстро обновить Import: ${rawError}`;
            this.cacheWarning = `${reason}. Показываю ${exact} кэш Import от ${cachedAt}.`;
            toast(this.cacheWarning, 'log');
            if (shouldShowProgress) {
              this.finishImportProgress({
                ok: true,
                status: 'Показан кэш Import',
                detail: this.cacheWarning,
              });
            }
            return;
          }
          this.error = rawError;
          if (shouldShowProgress) {
            this.finishImportProgress({
              ok: false,
              status: 'Не удалось обновить Import',
              detail: this.error,
            });
          }
          toast(this.error, 'error');
        } finally {
          this.loading = false;
        }
      },

      async syncTelegramImportData() {
        if (this.syncingImport || this.loading || this.importing) return;
        this.syncingImport = true;
        this.error = null;
        this.cacheWarning = null;
        this.startImportProgress({
          kind: 'sync-import',
          status: 'Синхронизирую источники Telegram...',
          detail: 'Включаю import-sync, обновляю source reload и читаю свежий список диалогов.',
          timeoutSec: 45,
        });
        try {
          this.updateImportProgress({
            percent: 18,
            status: 'Включаю автоматическую догрузку Import...',
            detail: 'Backend будет добавлять новые данные по импортированным источникам.',
          });
          await apiPostJson(URL_IMPORT_SYNC_ENABLE, {}, { timeoutMs: 20000 });
          this.updateImportProgress({
            percent: 36,
            status: 'Перезагружаю список источников...',
            detail: 'Снимаю stale-кэши Sync/Import и прошу backend перечитать selectors.',
          });
          await apiPostJson(URL_RELOAD_SOURCE, {}, { timeoutMs: 30000 });
          try {
            const syncJob = typeof apiGetTelegramSyncJob === 'function'
              ? await apiGetTelegramSyncJob({ timeoutMs: 5000, cacheTtlMs: 0, forceFresh: true })
              : null;
            if (syncJob?.job_id) {
              this.updateImportProgress({
                percent: Math.max(42, Number(syncJob.progress_percent || 42)),
                status: 'Telegram sync передан в worker...',
                detail: `${syncJob.progress_label || syncJob.status || 'Worker обновляет источники'} · job ${syncJob.job_id}`,
              });
            }
          } catch (_) {}
          this.invalidateSourceCaches();
          clearImportDialogsLocalCache();
          this.updateImportProgress({
            percent: 58,
            status: 'Получаю свежие данные Telegram...',
            detail: 'Если Telegram вернёт пустой список, старые строки будут убраны из Import.',
          });
          await this.loadDialogs({
            forceFresh: true,
            progress: false,
            progressStatus: 'Синхронизация Import: обновляю таблицу...',
            timeoutMs: 95000,
          });
          if (!Number(this.totalDialogs || 0)) {
            this.dialogs = [];
            this.selected = {};
            this.totalDialogPages = 1;
            clearImportDialogsLocalCache();
            this.invalidateSourceCaches();
            this.finishImportProgress({
              ok: true,
              status: 'Данных нет',
              detail: 'Telegram не вернул источники под текущими фильтрами. Старый кэш Import очищен.',
            });
            toast('Данных нет: старый кэш Import очищен', 'log');
            return;
          }
          this.finishImportProgress({
            ok: true,
            status: 'Синхронизация завершена',
            detail: `Новые данные добавлены/обновлены. Источников в таблице: ${Number(this.totalDialogs || this.dialogs.length || 0)}.`,
          });
          toast('Синхронизация Import завершена', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          const rawError = String(e?.message || e);
          this.error = rawError.includes('Failed to fetch')
            ? 'Backend не ответил на синхронизацию Import. Проверьте контейнер backend и повторите через несколько секунд.'
            : rawError;
          this.finishImportProgress({
            ok: false,
            status: 'Синхронизация не завершена',
            detail: this.error,
          });
          toast(this.error, 'error');
        } finally {
          this.syncingImport = false;
        }
      },

      pruneSelection() {
        for (const key of Object.keys(this.selected)) {
          if (!String(key || '').trim()) delete this.selected[key];
        }
      },

      resetPage(options = {}) {
        this.ui.page = 1;
        this.persistUi();
        this.loadDialogs(options);
      },

      setMembershipFilter(filterName) {
        const nextFilter = String(filterName || 'not_added');
        if (String(this.ui.membershipFilter || 'all') === nextFilter && this.loading) return;
        this.ui.membershipFilter = nextFilter;
        this.dialogs = [];
        this.selected = {};
        this.totalDialogs = 0;
        this.totalDialogPages = 1;
        this.cacheWarning = null;
        this.error = null;
        this.loading = true;
        this.resetPage({
          progress: true,
          progressStatus: 'Применяю фильтр Import...',
          progressKind: 'filter',
          progressDetail: 'Жду backend-кэш и пересчитываю список по статусу добавления.',
          timeoutSec: 8,
        });
      },

      typeVisible(dialog) {
        if (!dialog) return false;
        if (dialog.chat_type === 'channel') return !!this.ui.showChannels;
        if (dialog.chat_type === 'group') return !!this.ui.showGroups;
        if (dialog.chat_type === 'private') return !!this.ui.showPrivate;
        if (dialog.chat_type === 'bot') return false;
        return true;
      },

      filteredDialogs() {
        return this.dialogs || [];
      },

      ensurePageBounds() {
        const total = this.totalPages();
        if (this.ui.page < 1) this.ui.page = 1;
        if (this.ui.page > total) this.ui.page = total;
      },

      totalPages() {
        return Math.max(1, Number(this.totalDialogPages || 1));
      },

      pagedDialogs() {
        return this.filteredDialogs();
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

      visibleRangeText() {
        const items = this.filteredDialogs();
        const total = Math.max(0, Number(this.totalDialogs || 0));
        if (!items.length || !total) return '0 из 0';
        const size = Math.max(1, Number(this.ui.pageSize || 1));
        const start = (this.ui.page - 1) * size;
        const from = start + 1;
        const to = Math.min(total, start + items.length);
        return `${from}-${to} из ${total}`;
      },

      goToPage(page, options = {}) {
        this.ui.page = Number(page || 1);
        this.ensurePageBounds();
        this.persistUi();
        this.loadDialogs(options);
      },

      persistUi() {
        persistUiState(IMPORT_UI_STATE_KEY, this.ui, ['query', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'membershipFilter', 'sortBy']);
      },

      prevPage() {
        this.goToPage(this.ui.page - 1);
      },

      nextPage() {
        this.goToPage(this.ui.page + 1);
      },

      isSelected(selector) {
        return !!this.selected[String(selector)];
      },

      toggleSelected(selector) {
        const key = String(selector);
        this.selected[key] = !this.selected[key];
      },

      clearSelection() {
        this.selected = {};
      },

      selectVisibleNotAdded() {
        const next = { ...this.selected };
        for (const dialog of this.filteredDialogs()) {
          if (!dialog.is_already_added) next[String(dialog.selector)] = true;
        }
        this.selected = next;
      },

      visibleNotAddedCount() {
        return this.filteredDialogs().filter(dialog => !dialog.is_already_added).length;
      },

      allNotAddedCountLabel() {
        if (this.ui.membershipFilter === 'not_added') return Number(this.totalDialogs || 0);
        if (this.ui.membershipFilter === 'added') return 0;
        return null;
      },

      selectedCount() {
        return Object.values(this.selected).filter(Boolean).length;
      },

      selectedSelectors() {
        return Object.entries(this.selected)
          .filter(([, checked]) => !!checked)
          .map(([selector]) => selector);
      },

      chatTypeLabel(dialog) {
        const kind = dialog?.chat_type;
        if (kind === 'channel') return 'channel';
        if (kind === 'group') return 'group';
        if (kind === 'private') return 'private';
        if (kind === 'bot') return 'bot';
        return 'unknown';
      },

      chatTypeClass(dialog) {
        const kind = dialog?.chat_type;
        if (kind === 'channel') return 'badge-active';
        if (kind === 'group') return 'badge-pending';
        if (kind === 'private') return 'badge-archived';
        if (kind === 'bot') return 'badge-bot';
        return 'badge-archived';
      },

      previewText(text, maxLen = 120) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },

      rowClass(dialog) {
        return dialog?.is_already_added ? 'row-added' : '';
      },

      isRowBusy(dialog) {
        return String(this.rowBusySelector || '') === String(dialog?.selector || '');
      },

      normalizeSelectorKey(selector) {
        return String(selector || '').trim().replace(/^@/, '').toLowerCase();
      },

      markImportedSelectors(selectors) {
        const added = new Set((selectors || []).map(selector => this.normalizeSelectorKey(selector)).filter(Boolean));
        if (!added.size) return;
        this.dialogs = (this.dialogs || []).map((dialog) => {
          const selectorKey = this.normalizeSelectorKey(dialog?.selector);
          if (!selectorKey || !added.has(selectorKey)) return dialog;
          return { ...dialog, is_already_added: true };
        });
        this.pruneSelection();
      },

      async updateDialogMembership(dialog, action, options = {}) {
        const selector = String(dialog?.selector || '').trim();
        if (!selector) return;

        this.rowBusySelector = selector;
        this.rowBusyAction = action;
        this.error = null;
        const showProgress = action === 'remove' && options.progress !== false;
        if (showProgress) {
          this.startImportProgress({
            kind: 'delete-source',
            status: `Удаляю источник ${selector}...`,
            detail: 'Backend удаляет источник из Import, Sync, кэшей, локальных файлов и DuckDB-связанных данных.',
            timeoutSec: 90,
          });
        }

        try {
          const url = action === 'remove' ? URL_REMOVE_SOURCE : URL_ADD_SOURCE;
          const requestOptions = action === 'remove'
            ? { timeoutMs: 120000, requestKey: `import-source-remove:${selector}`, forceFresh: true }
            : { timeoutMs: 30000, requestKey: `import-source-add:${selector}`, forceFresh: true };
          const result = await apiPostJson(url, { selector }, requestOptions);
          this.invalidateSourceCaches();
          this.dialogs = (this.dialogs || []).map((item) => {
            if (String(item?.selector || '') !== selector) return item;
            return {
              ...item,
              is_already_added: action === 'add',
            };
          });
          this.pruneSelection();
          this.ensurePageBounds();
          const purge = result?.purge && typeof result.purge === 'object' ? result.purge : null;
          const purgeTotal = Number(purge?.total || 0);
          const defaultMessage = action === 'remove' ? 'Источник удалён из Import, Sync, кэшей и локальных данных' : 'Канал добавлен';
          const details = action === 'remove' && purgeTotal > 0 ? ` Очищено объектов: ${purgeTotal}.` : '';
          toast(`${result.message || defaultMessage}${details}`, 'log');
          if (showProgress) {
            this.finishImportProgress({
              ok: true,
              status: 'Источник удалён',
              detail: `${selector}: удалён из Import, Sync и локальных данных.${details}`,
            });
          }
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          if (showProgress) {
            this.finishImportProgress({
              ok: false,
              status: 'Удаление не завершено',
              detail: this.error,
            });
          }
          toast(this.error, 'error');
        } finally {
          this.rowBusySelector = null;
          this.rowBusyAction = '';
        }
      },

      async saveDialogImportSettings(dialog, nextValues = {}) {
        const selector = String(dialog?.selector || '').trim();
        if (!selector) return;
        this.rowBusySelector = selector;
        this.rowBusyAction = 'settings';
        this.error = null;
        const importHistoryMonths = this.clampImportHistoryMonths(
          nextValues.import_history_months ?? dialog.import_history_months ?? this.settings.import_default_history_months,
        );
        const importMessageLimit = this.clampImportMessageLimit(
          nextValues.import_message_limit ?? dialog.import_message_limit ?? this.settings.import_default_message_limit,
        );
        try {
          const result = await apiSaveTelegramDialogSettings({
            selector,
            import_history_months: importHistoryMonths,
            import_message_limit: importMessageLimit,
          }, { timeoutMs: 10000 });
          this.dialogs = (this.dialogs || []).map((item) => {
            if (String(item?.selector || '') !== selector) return item;
            return {
              ...item,
              import_history_months: result.import_history_months,
              import_message_limit: result.import_message_limit,
              import_max_history_months: result.import_max_history_months,
              import_max_message_limit: result.import_max_message_limit,
            };
          });
          toast(result.message || 'Лимиты импорта сохранены', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.rowBusySelector = null;
          this.rowBusyAction = '';
        }
      },

      async saveImportDefaults(nextValues = {}) {
        this.error = null;
        const importHistoryMonths = this.clampImportHistoryMonths(
          nextValues.import_default_history_months ?? this.settings.import_default_history_months,
        );
        const importMessageLimit = this.clampImportMessageLimit(
          nextValues.import_default_message_limit ?? this.settings.import_default_message_limit,
        );
        try {
          const current = await apiGetAppSettings({ timeoutMs: 7000 });
          const saved = await apiSaveAppSettings({
            ...(current || {}),
            import_default_history_months: importHistoryMonths,
            import_default_message_limit: importMessageLimit,
          }, { timeoutMs: 10000 });
          this.settings.import_default_history_months = this.clampImportHistoryMonths(saved.import_default_history_months);
          this.settings.import_default_message_limit = this.clampImportMessageLimit(saved.import_default_message_limit);
          this.settings.import_max_history_months = Math.max(1, Number(saved.import_max_history_months || this.settings.import_max_history_months || 1));
          this.settings.import_max_message_limit = Math.max(1, Number(saved.import_max_message_limit || this.settings.import_max_message_limit || 1000));
          toast('Настройки Import сохранены', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        }
      },

      async addDialog(dialog) {
        await this.updateDialogMembership(dialog, 'add');
      },

      async removeDialog(dialog) {
        const selector = String(dialog?.selector || '').trim();
        if (!selector) return;
        if (!window.confirm(`Удалить "${selector}" из чатов?`)) return;
        await this.updateDialogMembership(dialog, 'remove');
      },

      async deleteSelectedDialogs() {
        const selectors = this.selectedSelectors();
        if (!selectors.length || this.removingAll) return;
        if (!window.confirm(`Удалить выбранные источники везде: ${selectors.length}?`)) return;

        this.removingAll = true;
        this.error = null;
        const startedAt = Date.now();
        let removed = 0;
        let failed = 0;
        this.startImportProgress({
          kind: 'delete-selected',
          status: 'Удаляю выбранные источники...',
          detail: `К удалению: ${selectors.length}. Удаление идёт из Import, Sync, кэшей, локальных файлов и DuckDB-связанных данных.`,
          timeoutSec: Math.min(240, Math.max(45, selectors.length * 10)),
        });
        try {
          for (let index = 0; index < selectors.length; index += 1) {
            const selector = String(selectors[index] || '').trim();
            if (!selector) continue;
            const elapsedSec = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
            const avgSec = removed + failed > 0 ? elapsedSec / (removed + failed) : 4;
            this.rowBusySelector = selector;
            this.rowBusyAction = 'remove';
            this.updateImportProgress({
              percent: Math.max(3, Math.min(96, Math.round((index / selectors.length) * 100))),
              etaSec: Math.max(1, Math.round((selectors.length - index) * avgSec)),
              status: `Удаляю ${index + 1} из ${selectors.length}`,
              detail: selector,
            });
            try {
              await apiPostJson(URL_REMOVE_SOURCE, { selector }, {
                timeoutMs: 120000,
                requestKey: `import-source-remove:${selector}`,
                forceFresh: true,
              });
              removed += 1;
              delete this.selected[selector];
            } catch (e) {
              failed += 1;
              console.warn('Import selected delete failed:', selector, e);
            }
          }
          this.invalidateSourceCaches();
          if (typeof clearImportDialogsLocalCache === 'function') clearImportDialogsLocalCache();
          await this.loadDialogs({
            forceFresh: true,
            progress: false,
            progressStatus: 'Обновляю Import после массового удаления...',
            timeoutMs: 95000,
          });
          this.finishImportProgress({
            ok: failed === 0,
            status: failed ? 'Удаление завершено с ошибками' : 'Выбранные источники удалены',
            detail: `Удалено: ${removed}. Ошибок: ${failed}.`,
          });
          toast(`Удалено выбранных источников: ${removed}${failed ? `, ошибок: ${failed}` : ''}`, failed ? 'error' : 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          this.finishImportProgress({
            ok: false,
            status: 'Массовое удаление не завершено',
            detail: this.error,
          });
          toast(this.error, 'error');
        } finally {
          this.rowBusySelector = null;
          this.rowBusyAction = '';
          this.removingAll = false;
        }
      },

      async importSelectors(selectors) {
        const cleaned = (selectors || []).map(v => String(v || '').trim()).filter(Boolean);
        if (!cleaned.length || this.importing) return;

        this.importing = true;
        this.error = null;
        this.startImportProgress({
          kind: 'import-selectors',
          status: 'Добавляю выбранные источники Telegram...',
          detail: `Источников к добавлению: ${cleaned.length}.`,
          timeoutSec: cleaned.length > 10 ? 60 : 30,
        });
        try {
          const result = await apiImportTelegramDialogs(cleaned, { timeoutMs: 30000 });
          this.invalidateSourceCaches();
          this.markImportedSelectors(result.added_selectors || cleaned);
          toast(result.message || 'Диалоги добавлены', 'log');
          this.clearSelection();
          await this.loadDialogs({
            forceFresh: true,
            progress: false,
            progressStatus: 'Обновляю таблицу после добавления...',
          });
          this.finishImportProgress({
            ok: true,
            status: 'Источники добавлены',
            detail: result.message || `Добавлено источников: ${cleaned.length}.`,
          });
        } catch (e) {
          this.error = String(e?.message || e);
          this.finishImportProgress({
            ok: false,
            status: 'Не удалось добавить источники',
            detail: this.error,
          });
          toast(this.error, 'error');
        } finally {
          this.importing = false;
        }
      },

      async importSelected() {
        await this.importSelectors(this.selectedSelectors());
      },

      async importVisible() {
        const visible = this.filteredDialogs()
          .filter(dialog => !dialog.is_already_added)
          .map(dialog => dialog.selector);
        await this.importSelectors(visible);
      },

      async selectAllNotAddedUpToLimit() {
        if (this.importing || this.loading) return;
        this.error = null;
        try {
          const limit = this.defaultAddLimit();
          const selectors = await this.collectAllNotAddedSelectors({ limit });
          const next = { ...this.selected };
          for (const selector of selectors) {
            next[String(selector)] = true;
          }
          this.selected = next;
          toast(selectors.length ? `Выбрано источников: ${selectors.length}` : 'Нет не добавленных диалогов под текущими фильтрами', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        }
      },

      async collectDialogsByMembership(membershipFilter, options = {}) {
        const { limit = 0, onlyNotAdded = false, onlyAdded = false } = options || {};
        const selectors = [];
        const seen = new Set();
        const pageSize = 100;
        let page = 1;
        let totalPages = 1;
        const maxItems = Math.max(0, Number(limit || 0));

        do {
          const data = await apiGetTelegramDialogs({
            page,
            page_size: pageSize,
            query: (this.ui.query || '').trim(),
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: true,
            show_archived: true,
            membership_filter: membershipFilter || this.ui.membershipFilter,
            sort_by: this.ui.sortBy,
            force_refresh: false,
          }, {
            requestKey: `import:v4:${membershipFilter || this.ui.membershipFilter}:all:${page}`,
            cacheTtlMs: 5000,
            forceFresh: false,
            timeoutMs: 30000,
          });

          for (const dialog of data?.items || []) {
            const selector = String(dialog?.selector || '').trim();
            if (!selector || seen.has(selector)) continue;
            if (onlyNotAdded && dialog?.is_already_added) continue;
            if (onlyAdded && !dialog?.is_already_added) continue;
            seen.add(selector);
            selectors.push(selector);
            if (maxItems && selectors.length >= maxItems) return selectors.slice(0, maxItems);
          }

          totalPages = Math.max(1, Number(data?.total_pages || totalPages || 1));
          page += 1;
        } while (page <= totalPages);

        return selectors;
      },

      async collectAllNotAddedSelectors(options = {}) {
        return this.collectDialogsByMembership('not_added', {
          limit: options?.limit || this.defaultAddLimit(),
          onlyNotAdded: true,
        });
      },

      async collectAllAddedSelectors() {
        return this.collectDialogsByMembership('added', {
          onlyAdded: true,
        });
      },

      async importAll() {
        if (this.importing) return;
        await this.selectAllNotAddedUpToLimit();
      },

      async removeAllAddedFromScan() {
        if (this.removingAll) return;
        if (!window.confirm('Снять все добавленные под текущими фильтрами со сканирования Telegram? История в базе и JSONL останется.')) return;

        this.removingAll = true;
        this.error = null;
        try {
          const selectors = await this.collectAllAddedSelectors();
          if (!selectors.length) {
            toast('Нет добавленных диалогов под текущими фильтрами', 'log');
            return;
          }
          const result = await apiRemoveTelegramDialogsFromScan(selectors, { timeoutMs: 60000 });
          this.invalidateSourceCaches();
          toast(result.message || `Снято со сканирования: ${selectors.length}`, 'log');
          this.clearSelection();
          await this.loadDialogs({ forceFresh: true });
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.removingAll = false;
        }
      },
    };
  };
  }
})();
