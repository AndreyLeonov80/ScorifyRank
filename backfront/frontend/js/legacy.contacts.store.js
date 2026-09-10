/* Legacy contacts store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.contacts.store.js");
    return;
  }
  with (ctx) {
  window.contactsApp = function contactsApp() {
    return {
      loading: false,
      refreshing: false,
      messagesLoading: false,
      error: null,
      messagesError: null,
      statusMessage: 'Готов к загрузке контактов.',
      statusTone: 'idle',
      statusLog: [],
      cacheStatus: null,
      _lastRefreshAt: null,
      _statusSeq: 0,
      rows: [],
      chatOptions: [],
      chatOptionsLoading: false,
      qualificationPrompts: [],
      qualificationResults: [],
      qualificationDialogOpen: false,
      qualificationContact: null,
      qualificationBusyTemplate: '',
      qualificationError: '',
      qualificationProgress: null,
      bulkQualification: null,
      contactDoNotContactBusyKey: '',
      _qualificationProgressTimer: null,
      _qualificationPollTimer: null,
      _qualificationProgressSeq: 0,
      _bulkQualificationSeq: 0,
      selectedContact: null,
      messageRows: [],
      totalRows: 0,
      totalRowPages: 1,
      messagesTotalRows: 0,
      messagesTotalPages: 1,
      _timer: null,
      _statusStream: null,
      _streamState: 'idle',
      ui: {
        query: '',
        leadFilter: '',
        qualificationFilter: 'all',
        leadTemperatureFilter: 'all',
        signalFilters: [],
        bulkQualificationTemplate: '',
        page: 1,
        pageSize: 5,
        limit: 5000,
        autoRefreshEnabled: true,
        autoRefreshIntervalSec: 300,
        messagesQuery: '',
        messagesLeadFilter: '',
        messagesPage: 1,
        messagesPageSize: 5,
      },
      ...createOutreachToggleState(),

      async init() {
        await this.loadStatus();
        if (this.cacheStatus && !this.cacheStatus.cache_ready && !this.cacheStatus.running && !this.refreshing) {
          await this.triggerRefresh({ confirm: false });
          await this.loadStatus(true);
        }
        await Promise.all([
          this.loadChatOptions(true),
          this.loadQualificationPrompts(true),
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
        const status = snapshot?.contacts;
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

      isBootstrapping() {
        return !this.rows.length && (!!this.cacheStatus?.running || !this.cacheStatus?.cache_ready);
      },

      progressPercent() {
        return statusProgressPercent(this.cacheStatus);
      },

      progressLabel() {
        return statusProgressLabel(this.cacheStatus, 'Идёт обработка контактов', 'Ожидание');
      },

      progressCounterLabel() {
        return statusProgressCounterLabel(this.cacheStatus, 'файлов');
      },

      progressLogEntries() {
        return statusProgressLogEntries(this.cacheStatus);
      },

      statusPanelConfig() {
        return {
          compact: true,
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
          progressLogTitle: 'Лог обработки',
          logMaxHeight: '180px',
        };
      },

      renderStatusPanel() {
        return renderUnifiedStatusPanel(this.statusPanelConfig());
      },

      selectedTitle() {
        if (!this.selectedContact) return 'Выберите контакт в таблице выше';
        return this.selectedContact.display_name || this.selectedContact.sender_name || this.selectedContact.sender_username || this.selectedContact.contact_key;
      },

      senderMetaLabel(row) {
        const parts = [];
        if (row?.sender_username) parts.push(`@${String(row.sender_username).replace(/^@+/, '')}`);
        if (row?.sender_id != null) parts.push(`id:${row.sender_id}`);
        return parts.join(' · ') || '—';
      },

      listLabel(values) {
        return Array.isArray(values) && values.length ? values.join(', ') : '—';
      },

      chatOptionLabel(option) {
        const label = String(option?.label || option?.value || '').trim();
        const selector = String(option?.selector || '').trim();
        const count = Number(option?.total_contacts || 0);
        const selectorPart = selector && selector !== label ? ` · ${selector}` : '';
        const countPart = count ? ` · ${count} контактов` : '';
        return `${label || 'Без названия'}${selectorPart}${countPart}`;
      },

      qualificationFilterLabel(prompt) {
        const title = String(prompt?.title || prompt?.id || '').trim();
        return title || 'Шаблон';
      },

      signalFilterOptions() {
        return [
          { value: 'contact', label: 'Есть телефон/email' },
          { value: 'need', label: 'Есть потребность' },
          { value: 'event', label: 'Есть событие' },
          { value: 'company', label: 'Есть компания' },
          { value: 'city', label: 'Есть город' },
        ];
      },

      signalFilterValue() {
        return Array.isArray(this.ui.signalFilters) ? this.ui.signalFilters.join(',') : '';
      },

      toggleSignalFilter(value) {
        const target = String(value || '').trim();
        if (!target) return;
        const current = new Set(Array.isArray(this.ui.signalFilters) ? this.ui.signalFilters : []);
        if (current.has(target)) current.delete(target);
        else current.add(target);
        this.ui.signalFilters = [...current];
        this.resetPage();
      },

      async applyStatusSnapshot(status, silent = false) {
        const previousRefresh = this.cacheStatus?.last_refresh_at || this._lastRefreshAt || null;
        this.cacheStatus = status;
        this.ui.autoRefreshEnabled = !!status.enabled;
        this.ui.autoRefreshIntervalSec = Number(status.interval_sec || 300);

        if (status.running) {
          this.pushStatus('Идёт первичная или фоновая сборка кеша контактов. Данные будут появляться по мере обработки архива.', 'loading');
        } else if (status.last_error) {
          this.pushStatus(`Ошибка обновления кеша контактов: ${status.last_error}`, 'error');
        } else if (status.last_refresh_at) {
          this.pushStatus(`Кеш контактов готов. Последнее обновление: ${fmtDate(status.last_refresh_at, true)}.`, 'success');
          if (!silent) this.error = null;
        } else {
          this.pushStatus('Кеш контактов ещё не собран. Сейчас запустим первичную индексацию авторов сообщений.', 'idle');
        }

        const currentRefresh = status.last_refresh_at || null;
        if (currentRefresh && currentRefresh !== previousRefresh) {
          this._lastRefreshAt = currentRefresh;
          await this.loadRows(true);
          if (this.selectedContact?.contact_key) {
            await this.loadMessages(true);
          }
        }
      },

      async loadStatus(silent = false) {
        try {
          const status = await apiGetContactsStatus({
            requestKey: 'contacts:status',
            cacheKey: 'contacts:status',
            cacheTtlMs: 2500,
            forceFresh: !!silent,
          });
          await this.applyStatusSnapshot(status, silent);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            this.error = humanizeApiError(e, 'Не удалось загрузить статус контактов');
            this.pushStatus(this.error, 'error');
          }
        }
      },

      async loadChatOptions(silent = false) {
        this.chatOptionsLoading = true;
        try {
          const data = await apiGetContactChatFilters({ limit: this.ui.limit }, {
            requestKey: 'contacts:chat-options',
            cacheKey: 'contacts:chat-options',
            cacheTtlMs: 30000,
            forceFresh: !silent,
          });
          this.chatOptions = Array.isArray(data?.items) ? data.items : [];
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) {
            toast(humanizeApiError(e, 'Не удалось загрузить список чатов для фильтра'), 'error');
          }
        } finally {
          this.chatOptionsLoading = false;
        }
      },

      async loadQualificationPrompts(silent = false) {
        try {
          const data = await apiGetContactQualificationPrompts({
            requestKey: 'contacts:qualification-prompts',
            cacheKey: 'contacts:qualification-prompts',
            cacheTtlMs: 30000,
            forceFresh: !silent,
          });
          this.qualificationPrompts = Array.isArray(data?.items) ? data.items : [];
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (!silent) toast(humanizeApiError(e, 'Не удалось загрузить шаблоны квалификации'), 'error');
        }
      },

      async triggerRefresh(options = {}) {
        const shouldConfirm = options?.confirm !== false;
        if (shouldConfirm && !confirmLongRebuild(
          'Обновление контактов',
          'Backend догрузит и пересоберёт кеш авторов сообщений. Если данных много, процесс продолжится в фоне с progress/log.'
        )) {
          this.pushStatus('Обновление контактов отменено пользователем', 'idle');
          return;
        }
        this.refreshing = true;
        this.error = null;
        try {
          const result = await apiRefreshContacts();
          this.cacheStatus = result?.status || this.cacheStatus;
          await this.loadChatOptions(true);
          this.pushStatus(result?.message || 'Обновление кеша контактов запущено', 'loading');
          toast(result?.message || 'Обновление кеша контактов запущено', 'log');
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось запустить обновление контактов');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        } finally {
          this.refreshing = false;
        }
      },

      async saveAutoRefreshConfig() {
        try {
          const result = await apiSetContactsConfig({
            enabled: !!this.ui.autoRefreshEnabled,
            interval_sec: Number(this.ui.autoRefreshIntervalSec || 300),
          });
          this.cacheStatus = result?.status || this.cacheStatus;
          this.pushStatus(result?.message || 'Настройки контактов сохранены', 'success');
        } catch (e) {
          this.error = humanizeApiError(e, 'Не удалось сохранить настройки контактов');
          this.pushStatus(this.error, 'error');
          toast(this.error, 'error');
        }
      },

      async loadRows(silent = false) {
        if (!silent) this.loading = true;
        this.error = null;
        try {
          const data = await apiGetTelegramContacts({
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: this.ui.limit,
            query: (this.ui.query || '').trim(),
            lead: (this.ui.leadFilter || '').trim(),
            qualified_template: this.ui.qualificationFilter || 'all',
            lead_temperature: this.ui.leadTemperatureFilter || 'all',
            signals: this.signalFilterValue(),
          }, buildPagedRequestOptions('contacts', {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            limit: this.ui.limit,
            query: (this.ui.query || '').trim(),
            lead: (this.ui.leadFilter || '').trim(),
            qualified_template: this.ui.qualificationFilter || 'all',
            lead_temperature: this.ui.leadTemperatureFilter || 'all',
            signals: this.signalFilterValue(),
          }, {
            requestKey: 'contacts:rows',
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.rows = reconcileKeyedCollection(this.rows, data?.items || [], (row) => row?.contact_key || '');
          this.totalRows = Number(data?.total || 0);
          this.totalRowPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
          if (!silent) this.error = null;
          if (!silent && !this.chatOptionsLoading) this.loadChatOptions(true);

          if (this.selectedContact?.contact_key) {
            const refreshed = (this.rows || []).find(row => row.contact_key === this.selectedContact.contact_key);
            if (refreshed) {
              this.selectedContact = refreshed;
            } else if (this.rows.length) {
              this.selectedContact = this.rows[0];
              this.messagesError = null;
              await this.loadMessages(true);
            } else {
              this.selectedContact = null;
              this.messageRows = [];
              this.messagesError = null;
              this.messagesTotalRows = 0;
              this.messagesTotalPages = 1;
            }
          } else if (this.rows.length) {
            this.selectedContact = this.rows[0];
            this.messagesError = null;
            await this.loadMessages(true);
          }
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = humanizeApiError(e, 'Не удалось загрузить контакты');
          if (!silent) {
            this.pushStatus(this.error, 'error');
            toast(this.error, 'error');
          }
        } finally {
          if (!silent) this.loading = false;
        }
      },

      async loadMessages(silent = false) {
        if (!this.selectedContact?.contact_key) {
          this.messageRows = [];
          this.messagesTotalRows = 0;
          this.messagesTotalPages = 1;
          return;
        }
        if (!silent) this.messagesLoading = true;
        this.messagesError = null;
        try {
          const data = await apiGetTelegramContactMessages(this.selectedContact.contact_key, {
            page: this.ui.messagesPage,
            page_size: this.ui.messagesPageSize,
            query: (this.ui.messagesQuery || '').trim(),
            lead: (this.ui.messagesLeadFilter || '').trim(),
          }, buildPagedRequestOptions(`contacts:messages:${this.selectedContact.contact_key}`, {
            page: this.ui.messagesPage,
            page_size: this.ui.messagesPageSize,
            query: (this.ui.messagesQuery || '').trim(),
            lead: (this.ui.messagesLeadFilter || '').trim(),
          }, {
            requestKey: `contacts:messages:${this.selectedContact.contact_key}`,
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.messageRows = reconcileKeyedCollection(this.messageRows, data?.items || [], (row) => `${row?.lead || ''}:${row?.message_id || ''}`);
          this.messagesTotalRows = Number(data?.total || 0);
          this.messagesTotalPages = Number(data?.total_pages || 1);
          this.ui.messagesPage = Number(data?.page || this.ui.messagesPage || 1);
          this.ui.messagesPageSize = Number(data?.page_size || this.ui.messagesPageSize || 10);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          const message = humanizeApiError(e, 'Не удалось загрузить сообщения контакта');
          const normalizedMessage = message.toLowerCase();
          if (normalizedMessage.includes('contact not found') || (normalizedMessage.includes('контакт') && normalizedMessage.includes('не найден'))) {
            this.selectedContact = null;
            this.messageRows = [];
            this.messagesTotalRows = 0;
            this.messagesTotalPages = 1;
            this.messagesError = null;
            return;
          }
          this.messagesError = message;
          if (!silent) toast(this.messagesError, 'error');
        } finally {
          if (!silent) this.messagesLoading = false;
        }
      },

      resetPage() {
        this.ui.page = 1;
        this.loadRows();
      },

      resetMessagesPage() {
        this.ui.messagesPage = 1;
        this.loadMessages();
      },

      selectContact(row) {
        this.selectedContact = row;
        this.ui.messagesPage = 1;
        this.loadMessages();
      },

      applyContactDoNotContactPatch(contactKey, result) {
        const key = String(contactKey || '').trim();
        if (!key) return;
        const patch = {
          do_not_contact: !!result?.do_not_contact,
          do_not_contact_reason: String(result?.do_not_contact_reason || '').trim(),
          do_not_contact_updated_at: result?.do_not_contact_updated_at || null,
        };
        this.rows = (this.rows || []).map((row) => (
          String(row?.contact_key || '') === key ? { ...row, ...patch } : row
        ));
        if (this.selectedContact?.contact_key === key) {
          this.selectedContact = { ...this.selectedContact, ...patch };
        }
      },

      async toggleContactDoNotContact(row) {
        const contactKey = String(row?.contact_key || '').trim();
        if (!contactKey || this.contactDoNotContactBusyKey) return;
        const enabled = !row?.do_not_contact;
        this.contactDoNotContactBusyKey = contactKey;
        try {
          const result = await apiSetContactDoNotContact(contactKey, {
            enabled,
            reason: enabled ? 'Исключено пользователем из ручного outreach' : '',
          });
          this.applyContactDoNotContactPatch(contactKey, result);
          if (enabled) {
            await this.loadOutreachSelections(true);
          }
          toast(result?.message || (enabled ? 'Контакт исключён из enReach' : 'Контакт снова доступен для enReach'), 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          const message = humanizeApiError(e, 'Не удалось обновить do_not_contact');
          toast(message, 'error');
        } finally {
          this.contactDoNotContactBusyKey = '';
        }
      },

      async openQualificationDialog(row) {
        this.qualificationContact = row;
        this.qualificationDialogOpen = true;
        this.qualificationError = '';
        this.qualificationResults = [];
        await Promise.all([
          this.loadQualificationPrompts(true),
          this.loadContactQualifications(row?.contact_key),
        ]);
      },

      closeQualificationDialog() {
        this.qualificationDialogOpen = false;
        this.qualificationContact = null;
        this.qualificationResults = [];
        this.qualificationBusyTemplate = '';
        this.qualificationError = '';
        this.stopQualificationProgress();
      },

      async loadContactQualifications(contactKey) {
        const key = String(contactKey || '').trim();
        if (!key) return;
        try {
          const data = await apiGetContactQualifications(key, {
            requestKey: `contacts:qualifications:${key}`,
            cacheKey: `contacts:qualifications:${key}`,
            cacheTtlMs: 3000,
            forceFresh: true,
          });
          this.qualificationResults = Array.isArray(data?.items) ? data.items : [];
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.qualificationError = humanizeApiError(e, 'Не удалось загрузить квалификации контакта');
        }
      },

      qualificationResultByTemplate(templateId) {
        const id = String(templateId || '');
        return (this.qualificationResults || []).find((item) => String(item?.template_id || '') === id) || null;
      },

      isQualificationBusyFor(templateId) {
        const id = String(templateId || '');
        return this.qualificationBusyTemplate === id || String(this.qualificationProgress?.template_id || '') === id;
      },

      pushQualificationProgress(message, tone = 'info') {
        if (!this.qualificationProgress) return;
        this.qualificationProgress = {
          ...this.qualificationProgress,
          updated_at: Date.now(),
          log: [
            {
              id: `${Date.now()}-${++this._qualificationProgressSeq}`,
              ts: Date.now(),
              message: String(message || ''),
              tone,
            },
            ...(this.qualificationProgress.log || []),
          ].slice(0, 8),
        };
      },

      startQualificationProgress(prompt) {
        this.stopQualificationProgress();
        const templateId = String(prompt?.id || '').trim();
        this.qualificationProgress = {
          template_id: templateId,
          title: prompt?.title || templateId,
          started_at: Date.now(),
          updated_at: Date.now(),
          percent: 6,
          label: 'Готовлю сообщения контакта',
          waiting: false,
          log: [],
        };
        this.pushQualificationProgress('Собираю последние сообщения контакта из backend-кеша.');
        this._qualificationProgressTimer = window.setInterval(() => {
          if (!this.qualificationProgress || this.qualificationProgress.template_id !== templateId) return;
          const elapsedSec = Math.floor((Date.now() - Number(this.qualificationProgress.started_at || Date.now())) / 1000);
          let percent = Math.min(92, Number(this.qualificationProgress.percent || 0) + (elapsedSec < 20 ? 4 : 2));
          let label = 'Ожидаем ответ OpenRouter ...';
          if (elapsedSec < 3) label = 'Готовлю сообщения контакта';
          else if (elapsedSec < 8) label = 'Отправляю запрос в OpenRouter';
          else if (elapsedSec < 25) label = 'OpenRouter анализирует сообщения';
          if (elapsedSec > 10 && elapsedSec % 10 === 0) {
            this.pushQualificationProgress('Ожидаем ответ OpenRouter ... popup остаётся открытым.');
          }
          this.qualificationProgress = {
            ...this.qualificationProgress,
            percent,
            label,
            waiting: elapsedSec >= 8,
            updated_at: Date.now(),
          };
        }, 1000);
      },

      finishQualificationProgress(message = 'Квалификация готова') {
        if (this.qualificationProgress) {
          this.pushQualificationProgress(message, 'success');
          this.qualificationProgress = {
            ...this.qualificationProgress,
            percent: 100,
            label: message,
            waiting: false,
            updated_at: Date.now(),
          };
        }
        if (this._qualificationProgressTimer) {
          clearInterval(this._qualificationProgressTimer);
          this._qualificationProgressTimer = null;
        }
        if (this._qualificationPollTimer) {
          clearInterval(this._qualificationPollTimer);
          this._qualificationPollTimer = null;
        }
        window.setTimeout(() => {
          if (this.qualificationProgress && Number(this.qualificationProgress.percent || 0) >= 100) {
            this.qualificationProgress = null;
          }
        }, 2500);
      },

      stopQualificationProgress() {
        if (this._qualificationProgressTimer) {
          clearInterval(this._qualificationProgressTimer);
          this._qualificationProgressTimer = null;
        }
        if (this._qualificationPollTimer) {
          clearInterval(this._qualificationPollTimer);
          this._qualificationPollTimer = null;
        }
        this.qualificationProgress = null;
      },

      waitForQualificationResult(contactKey, templateId) {
        if (this._qualificationPollTimer) clearInterval(this._qualificationPollTimer);
        let attempts = 0;
        this._qualificationPollTimer = window.setInterval(async () => {
          attempts += 1;
          if (!this.qualificationDialogOpen || !this.qualificationProgress) {
            clearInterval(this._qualificationPollTimer);
            this._qualificationPollTimer = null;
            return;
          }
          this.pushQualificationProgress('Проверяю, появился ли сохранённый результат анализа.');
          await this.loadContactQualifications(contactKey);
          if (this.qualificationResultByTemplate(templateId)) {
            this.qualificationBusyTemplate = '';
            this.finishQualificationProgress('Ответ получен и сохранён');
            toast('Квалификация контакта готова', 'log');
          } else if (attempts >= 24) {
            clearInterval(this._qualificationPollTimer);
            this._qualificationPollTimer = null;
            if (this.qualificationProgress) {
              this.qualificationProgress = {
                ...this.qualificationProgress,
                percent: 92,
                label: 'Ожидаем ответ ... можно закрыть popup и вернуться позже',
                waiting: true,
              };
              this.pushQualificationProgress('Ответ пока не пришёл. Продолжаем ждать в фоне backend/OpenRouter.', 'warning');
            }
            this.qualificationBusyTemplate = '';
          }
        }, 5000);
      },

      isLongQualificationWait(error) {
        const raw = String(error?.message || error || '').toLowerCase();
        return raw.includes('слишком долго') || raw.includes('timeout') || raw.includes('failed to fetch') || raw.includes('load failed') || raw.includes('networkerror');
      },

      async qualifyContactWithTemplate(prompt) {
        const contactKey = String(this.qualificationContact?.contact_key || '').trim();
        const templateId = String(prompt?.id || '').trim();
        if (!contactKey || !templateId || this.qualificationBusyTemplate || this.qualificationProgress) return;
        this.qualificationBusyTemplate = templateId;
        this.qualificationError = '';
        this.startQualificationProgress(prompt);
        try {
          this.pushQualificationProgress('Запрос отправлен в OpenRouter. Ждём анализ сообщений.');
          const result = await apiQualifyContact(contactKey, templateId, {
            requestKey: `contacts:qualify:${contactKey}:${templateId}`,
            timeoutMs: 300000,
            force: !!this.qualificationResultByTemplate(templateId),
          });
          const existing = (this.qualificationResults || []).filter((item) => String(item?.template_id || '') !== templateId);
          this.qualificationResults = [result, ...existing];
          this.applyQualificationResultToContact(contactKey, templateId, result);
          this.finishQualificationProgress(result?.cache_hit ? 'Актуальная квалификация взята из кеша' : 'Ответ получен и сохранён');
          toast(result?.cache_hit ? 'Квалификация уже была актуальна, OpenRouter не вызывался' : 'Квалификация контакта готова', 'log');
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          if (this.isLongQualificationWait(e)) {
            this.qualificationError = '';
            if (this.qualificationProgress) {
              this.qualificationProgress = {
                ...this.qualificationProgress,
                percent: Math.max(76, Number(this.qualificationProgress.percent || 0)),
                label: 'Ожидаем ответ ...',
                waiting: true,
              };
            }
            this.pushQualificationProgress('Сервер отвечает дольше обычного. Ожидаем ответ ...', 'warning');
            this.waitForQualificationResult(contactKey, templateId);
            return;
          }
          this.qualificationError = humanizeApiError(e, 'Не удалось квалифицировать контакт');
          this.stopQualificationProgress();
          toast(this.qualificationError, 'error');
        } finally {
          if (!this.qualificationProgress?.waiting) {
            this.qualificationBusyTemplate = '';
          }
        }
      },

      applyQualificationResultToContact(contactKey, templateId, result) {
        const key = String(contactKey || '').trim();
        const id = String(templateId || '').trim();
        if (!key || !id) return;
        const resultText = String(result?.result_text || '').trim();
        const resultUpdatedAt = result?.updated_at || result?.created_at || '';
        const resultModel = result?.model || '';
        const resultPatch = {};
        if (id === 'first_message') {
          resultPatch.first_message_suggestion = resultText;
          resultPatch.first_message_updated_at = resultUpdatedAt;
          resultPatch.first_message_model = resultModel;
        } else if (id === 'product_offer') {
          resultPatch.product_offer_suggestion = resultText;
          resultPatch.product_offer_updated_at = resultUpdatedAt;
          resultPatch.product_offer_model = resultModel;
        }
        this.rows = (this.rows || []).map((row) => {
          if (String(row?.contact_key || '') !== key) return row;
          const ids = new Set([...(row.qualified_template_ids || []), id]);
          return {
            ...row,
            ...resultPatch,
            qualification_count: Math.max(Number(row.qualification_count || 0), ids.size),
            qualified_template_ids: [...ids],
            latest_qualification_at: result?.updated_at || row.latest_qualification_at,
          };
        });
        if (this.selectedContact?.contact_key === key) {
          const ids = new Set([...(this.selectedContact.qualified_template_ids || []), id]);
          this.selectedContact = {
            ...this.selectedContact,
            ...resultPatch,
            qualification_count: Math.max(Number(this.selectedContact.qualification_count || 0), ids.size),
            qualified_template_ids: [...ids],
            latest_qualification_at: result?.updated_at || this.selectedContact.latest_qualification_at,
          };
        }
      },

      pushBulkQualificationLog(message, tone = 'info') {
        if (!this.bulkQualification) return;
        this.bulkQualification = {
          ...this.bulkQualification,
          updated_at: Date.now(),
          log: [
            {
              id: `${Date.now()}-${++this._bulkQualificationSeq}`,
              ts: Date.now(),
              message: String(message || ''),
              tone,
            },
            ...(this.bulkQualification.log || []),
          ].slice(0, 10),
        };
      },

      bulkQualificationPercent() {
        const total = Number(this.bulkQualification?.total || 0);
        if (!total) return 0;
        return Math.max(0, Math.min(100, Math.round((Number(this.bulkQualification?.done || 0) / total) * 100)));
      },

      async qualifyVisibleContactsWithTemplate() {
        const templateId = String(this.ui.bulkQualificationTemplate || this.qualificationPrompts?.[0]?.id || '').trim();
        const prompt = (this.qualificationPrompts || []).find((item) => String(item?.id || '') === templateId);
        const contacts = (this.rows || []).filter((row) => String(row?.contact_key || '').trim());
        if (!templateId || !prompt || !contacts.length || this.bulkQualification?.running) return;
        this.bulkQualification = {
          running: true,
          template_id: templateId,
          title: prompt.title || templateId,
          total: contacts.length,
          done: 0,
          cached: 0,
          refreshed: 0,
          errors: 0,
          current: '',
          started_at: Date.now(),
          updated_at: Date.now(),
          log: [],
        };
        this.pushBulkQualificationLog(`Старт массовой квалификации: ${contacts.length} контактов, шаблон “${prompt.title || templateId}”.`);
        for (const row of contacts) {
          const contactKey = String(row?.contact_key || '').trim();
          const label = row?.display_name || row?.sender_username || contactKey;
          this.bulkQualification = { ...this.bulkQualification, current: label, updated_at: Date.now() };
          this.pushBulkQualificationLog(`Анализирую ${label}`);
          try {
            const result = await apiQualifyContact(contactKey, templateId, {
              requestKey: `contacts:bulk-qualify:${contactKey}:${templateId}`,
              timeoutMs: 300000,
            });
            this.applyQualificationResultToContact(contactKey, templateId, result);
            this.bulkQualification = {
              ...this.bulkQualification,
              done: Number(this.bulkQualification.done || 0) + 1,
              cached: Number(this.bulkQualification.cached || 0) + (result?.cache_hit ? 1 : 0),
              refreshed: Number(this.bulkQualification.refreshed || 0) + (result?.cache_hit ? 0 : 1),
              updated_at: Date.now(),
            };
            this.pushBulkQualificationLog(result?.cache_hit ? `${label}: актуально из кеша` : `${label}: OpenRouter результат сохранён`, result?.cache_hit ? 'info' : 'success');
          } catch (e) {
            if (isAbortedRequestError(e)) return;
            this.bulkQualification = {
              ...this.bulkQualification,
              done: Number(this.bulkQualification.done || 0) + 1,
              errors: Number(this.bulkQualification.errors || 0) + 1,
              updated_at: Date.now(),
            };
            this.pushBulkQualificationLog(`${label}: ${humanizeApiError(e, 'ошибка квалификации')}`, 'warning');
          }
        }
        this.bulkQualification = {
          ...this.bulkQualification,
          running: false,
          current: '',
          updated_at: Date.now(),
        };
        this.pushBulkQualificationLog(
          `Готово: ${this.bulkQualification.done}/${this.bulkQualification.total}, кеш ${this.bulkQualification.cached}, новых ${this.bulkQualification.refreshed}, ошибок ${this.bulkQualification.errors}.`,
          this.bulkQualification.errors ? 'warning' : 'success',
        );
        await this.loadRows(true);
      },

      contactRowClass(row) {
        return this.selectedContact?.contact_key === row?.contact_key
          ? { background: 'rgba(219,234,254,.55)' }
          : undefined;
      },

      visibleRangeText() {
        if (!this.totalRows) return '0 из 0';
        const start = (this.ui.page - 1) * this.ui.pageSize + 1;
        const end = Math.min(this.totalRows, start + this.rows.length - 1);
        return `${start}-${end} из ${this.totalRows}`;
      },

      messagesVisibleRangeText() {
        if (!this.messagesTotalRows) return '0 из 0';
        const start = (this.ui.messagesPage - 1) * this.ui.messagesPageSize + 1;
        const end = Math.min(this.messagesTotalRows, start + this.messageRows.length - 1);
        return `${start}-${end} из ${this.messagesTotalRows}`;
      },

      pageWindow() {
        const total = Math.max(1, this.totalRowPages || 1);
        const current = Math.min(Math.max(1, this.ui.page || 1), total);
        const start = Math.max(1, current - 2);
        const end = Math.min(total, start + 4);
        const pages = [];
        for (let page = Math.max(1, end - 4); page <= end; page++) pages.push(page);
        return pages;
      },

      messagesPageWindow() {
        const total = Math.max(1, this.messagesTotalPages || 1);
        const current = Math.min(Math.max(1, this.ui.messagesPage || 1), total);
        const start = Math.max(1, current - 2);
        const end = Math.min(total, start + 4);
        const pages = [];
        for (let page = Math.max(1, end - 4); page <= end; page++) pages.push(page);
        return pages;
      },

      goToPage(page) {
        this.ui.page = Number(page || 1);
        this.loadRows();
      },

      prevPage() {
        if (this.ui.page > 1) {
          this.ui.page -= 1;
          this.loadRows();
        }
      },

      nextPage() {
        if (this.ui.page < this.totalRowPages) {
          this.ui.page += 1;
          this.loadRows();
        }
      },

      goToMessagesPage(page) {
        this.ui.messagesPage = Number(page || 1);
        this.loadMessages();
      },

      prevMessagesPage() {
        if (this.ui.messagesPage > 1) {
          this.ui.messagesPage -= 1;
          this.loadMessages();
        }
      },

      nextMessagesPage() {
        if (this.ui.messagesPage < this.messagesTotalPages) {
          this.ui.messagesPage += 1;
          this.loadMessages();
        }
      },

      nextMessagePlaceholder(row) {
        const label = row?.display_name || row?.sender_name || row?.sender_username || 'контакта';
        const suggestion = String(row?.first_message_suggestion || '').trim();
        if (suggestion) {
          toast(`Первое сообщение для ${label}: ${suggestion}`, 'log');
          return;
        }
        this.openQualificationDialog(row);
        toast(`Запустите шаблон “Первое сообщение для знакомства” для ${label}. После анализа текст появится прямо в строке.`, 'log');
      },
    };
  };
  }
})();
