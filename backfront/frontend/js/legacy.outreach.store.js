/* Legacy outreach store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.outreach.store.js");
    return;
  }
  with (ctx) {
  window.outreachApp = function outreachApp() {
    return {
      loading: false,
      deletingId: null,
      creatingSequenceId: null,
      error: null,
      rows: [],
      totalRows: 0,
      totalRowPages: 1,
      ui: {
        query: '',
        fieldType: 'all',
        page: 1,
        pageSize: 5,
      },

      async init() {
        await this.loadRows();
      },

      async loadRows(silent = false) {
        if (!silent) this.loading = true;
        this.error = null;
        try {
          const data = await apiGetOutreachItems({
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.query || '').trim(),
            field_type: this.ui.fieldType === 'all' ? '' : this.ui.fieldType,
          }, buildPagedRequestOptions('outreach', {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.query || '').trim(),
            field_type: this.ui.fieldType,
          }, {
            requestKey: 'outreach:rows',
            cacheTtlMs: 2500,
            forceFresh: !!silent,
          }));
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => row?.id || '');
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить enReach');
          toast(this.error, 'error');
        } finally {
          if (!silent) this.loading = false;
        }
      },

      async deleteItem(item) {
        const id = String(item?.id || '');
        if (!id) return;
        this.deletingId = id;
        try {
          const result = await apiDeleteOutreachItem(id);
          this.rows = (this.rows || []).filter((row) => row.id !== id);
          this.totalRows = Math.max(0, Number(this.totalRows || 0) - 1);
          toast(result?.message || 'Элемент удалён из enReach', 'log');
          await this.loadRows(true);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось удалить элемент enReach');
          toast(this.error, 'error');
        } finally {
          this.deletingId = null;
        }
      },

      async createOutreachSequence(item) {
        const id = String(item?.id || '');
        if (!id) return;
        this.creatingSequenceId = id;
        try {
          const result = await apiCreateOutreachSequenceFromEnreach(id);
          toast(result?.message || 'outReach sequence создана', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось создать outReach sequence');
          toast(this.error, 'error');
        } finally {
          this.creatingSequenceId = null;
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
        return `${start + 1}-${Math.min(total, start + items.length)} из ${total}`;
      },

      fieldTypeLabel(value) {
        return outreachFieldLabel(value, '') || value || '—';
      },

      senderLabel(row) {
        if (row?.sender_username && row?.sender_name) return `${row.sender_name} · @${row.sender_username}`;
        if (row?.sender_username) return `@${row.sender_username}`;
        return row?.sender_name || '—';
      },

      previewText(text, maxLen = 220) {
        const value = String(text || '').replace(/\s+/g, ' ').trim();
        if (!value) return '—';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },
    };
  };
  }
})();
