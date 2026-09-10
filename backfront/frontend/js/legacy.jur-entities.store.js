/* Legacy jur-entities store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.jur-entities.store.js");
    return;
  }
  with (ctx) {
  window.jurEntitiesApp = function jurEntitiesApp() {
    return {
      loading: false,
      syncing: false,
      error: null,
      rows: [],
      totalRows: 0,
      totalRowPages: 1,
      lastSyncAt: null,
      syncError: null,
      channel: 'baza_directorov',
      rowBusyKey: null,
      rowBusyAction: '',
      ui: {
        query: '',
        page: 1,
        pageSize: 5,
        parserFilter: 'all',
      },
      ...createOutreachToggleState(),

      async init() {
        await this.loadRows();
      },

      async loadRows(options = {}) {
        const { forceFresh = false, sync = false } = options || {};
        this.loading = true;
        this.error = null;
        try {
          const params = {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.query || '').trim(),
            parser_filter: this.ui.parserFilter,
            sync: sync ? 1 : '',
          };
          const data = await apiGetJurEntities(
            params,
            buildPagedRequestOptions('jur-entities', params, {
              requestKey: 'jur-entities:rows',
              cacheTtlMs: 4000,
              forceFresh,
              timeoutMs: sync ? 180000 : 20000,
            }),
          );
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => row?.file_key || '');
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
          this.channel = String(data?.channel || this.channel || 'baza_directorov');
          this.lastSyncAt = data?.last_sync_at || null;
          this.syncError = data?.sync_error || null;
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить XLSX-файлы');
          toast(this.error, 'error');
        } finally {
          this.loading = false;
        }
      },

      async syncFiles() {
        if (this.syncing) return;
        this.syncing = true;
        this.error = null;
        try {
          const result = await apiSyncJurEntities({
            requestKey: 'jur-entities:sync',
            timeoutMs: 180000,
          });
          this.lastSyncAt = result?.last_sync_at || this.lastSyncAt;
          this.syncError = result?.sync_error || null;
          await this.loadRows({ forceFresh: true, sync: false });
          toast('XLSX синхронизированы', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось синхронизировать XLSX-файлы');
          toast(this.error, 'error');
        } finally {
          this.syncing = false;
        }
      },

      ensurePageBounds() {
        const total = this.totalPages();
        if (this.ui.page < 1) this.ui.page = 1;
        if (this.ui.page > total) this.ui.page = total;
      },

      totalPages() {
        return Math.max(1, Number(this.totalRowPages || 1));
      },

      pagedRows() {
        return this.rows || [];
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
        const items = this.pagedRows();
        const total = Math.max(0, Number(this.totalRows || 0));
        if (!items.length || !total) return '0 из 0';
        const size = Math.max(1, Number(this.ui.pageSize || 1));
        const start = (this.ui.page - 1) * size;
        const from = start + 1;
        const to = Math.min(total, start + items.length);
        return `${from}-${to} из ${total}`;
      },

      resetPage() {
        this.ui.page = 1;
        this.loadRows({ forceFresh: true });
      },

      setParserFilter(value) {
        this.ui.parserFilter = String(value || 'all');
        this.resetPage();
      },

      goToPage(page) {
        this.ui.page = Number(page || 1);
        this.ensurePageBounds();
        this.loadRows({ forceFresh: true });
      },

      prevPage() {
        this.goToPage(this.ui.page - 1);
      },

      nextPage() {
        this.goToPage(this.ui.page + 1);
      },

      previewText(text, maxLen = 120) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },

      structureBadgeClass(row) {
        return row?.structure_common ? 'badge-active' : 'badge-error';
      },

      structureBadgeText(row) {
        return row?.structure_label || (row?.structure_common ? 'Одинаковая' : 'Разная');
      },

      syncLabel() {
        return this.lastSyncAt ? fmtDate(this.lastSyncAt, true) : 'ещё не запускалась';
      },

      parserBadgeClass(row) {
        return row?.parser_enabled ? 'badge-active' : 'badge-archived';
      },

      parserBadgeText(row) {
        return row?.parser_enabled ? 'в парсере' : 'не в парсере';
      },

      formatBytes(bytes) {
        const size = Number(bytes || 0);
        if (!size) return '0 B';
        if (size < 1024) return `${size} B`;
        if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
        return `${(size / (1024 * 1024)).toFixed(2)} MB`;
      },

      isRowBusy(row, action = '') {
        const rowKey = String(row?.file_key || '');
        return rowKey && this.rowBusyKey === rowKey && (!action || this.rowBusyAction === action);
      },

      async addToParser(row) {
        const fileKey = String(row?.file_key || '').trim();
        if (!fileKey || this.rowBusyKey) return;
        this.rowBusyKey = fileKey;
        this.rowBusyAction = 'add';
        try {
          const result = await apiAddJurEntityToParser(fileKey);
          const selected = new Set(result?.parser_selected || []);
          this.rows = (this.rows || []).map((item) => (
            String(item?.file_key || '') === fileKey
              ? { ...item, parser_enabled: true }
              : { ...item, parser_enabled: selected.has(String(item?.file_key || '')) }
          ));
          toast(result?.message || 'Файл добавлен в парсер', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось добавить файл в парсер');
          toast(this.error, 'error');
        } finally {
          this.rowBusyKey = null;
          this.rowBusyAction = '';
        }
      },

      async removeFromParser(row) {
        const fileKey = String(row?.file_key || '').trim();
        if (!fileKey || this.rowBusyKey) return;
        this.rowBusyKey = fileKey;
        this.rowBusyAction = 'remove';
        try {
          const result = await apiRemoveJurEntityFromParser(fileKey);
          const selected = new Set(result?.parser_selected || []);
          this.rows = (this.rows || []).map((item) => (
            String(item?.file_key || '') === fileKey
              ? { ...item, parser_enabled: false }
              : { ...item, parser_enabled: selected.has(String(item?.file_key || '')) }
          ));
          toast(result?.message || 'Файл удалён из парсера', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось удалить файл из парсера');
          toast(this.error, 'error');
        } finally {
          this.rowBusyKey = null;
          this.rowBusyAction = '';
        }
      },
    };
  };
  }
})();
