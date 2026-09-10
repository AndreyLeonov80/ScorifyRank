/* Legacy lead store extracted from script.api.js */
(function initLegacyStore() {
  const ctx = window.BackfrontLegacy;
  if (!ctx) {
    console.error("[Legacy] BackfrontLegacy runtime is unavailable for legacy.lead.store.js");
    return;
  }
  const leadDom = window.BackfrontLeadDom || {};
  with (ctx) {
  const LAST_OPEN_CHAT_KEY = 'xfiles.index.lastOpenChat.v1';
  const INDEX_UI_STATE_KEY = 'index.groups-default.v1';
  window.leadApp = function leadApp() {
    return {
      // --- UI/STATE ---
      ui: createPersistedUiState(INDEX_UI_STATE_KEY, {
        widthPct: 80,
        leadFilter: '',
        page: 1,
        pageSize: 5,
        messagesLimit: 30,
        messageRenderStart: 0,
        messageRenderSize: 30,
        autoStream: true,
        showChannels: false,
        showGroups: true,
        showPrivate: false,
        scanFilter: 'all',
      }, ['leadFilter', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'scanFilter']),
      loading: false,
      error: null,

      leads: [],
      current: null,
      messages: [],
      messagesLoadStartedAt: 0,
      _msgIds: new Set(),
      messagesLoadedOffset: 0,
      messagesLoadingMore: false,
      messagesHasOlder: false,
      messageScrollRatio: 1,
      _es: null,
      _globalEs: null,
      _leadEventsBatcher: null,
      _messageBatcher: null,
      _suspendLeadSort: false,
      _lastLeadRestoreTried: false,
      _authInflight: false,
      _leadInflight: false,

      llmHtml: '',
      _llmTimer: null,
      _llmInflight: false,
      _llmProgressTimer: null,
      _chatAnalysisProgressTimer: null,
      _llmLastLoadedFor: null,
      llmRunning: false,  // ← ЗДЕСЬ, в объекте
      llmProgress: {
        running: false,
        percent: 0,
        etaSec: 0,
        status: '',
        error: '',
        startedAt: 0,
        timeoutSec: 300,
        log: [],
      },
      settings: {
        openrouter_timeout_sec: 300,
      },
      sourceRefreshing: false,
      authStatus: null,
      totalLeads: 0,
      totalLeadPages: 1,
      authLoading: false,
      authForm: {
        apiId: '',
        apiHash: '',
        phone: '',
        code: '',
        password: '',
      },
      sourceForm: {
        selector: '',
      },
      leadActionBusyName: null,
      leadActionBusyType: '',
      _authTimer: null,
      _leadTimer: null,
      chatAnalysis: {
        stats: null,
        history: [],
        loadingStats: false,
        loadingHistory: false,
        running: false,
        error: '',
        provider: 'openrouter',
        model: 'openai/gpt-oss-120b:free',
        mode: 'last_messages',
        messageLimit: 10,
        tokenBudget: 4000,
        prompt: 'Проанализируй выбранные сообщения чата. Выдели темы, потребности, сигналы продаж, риски и предложи следующие действия.',
        selectedIds: {},
        lastPayload: null,
        progressLog: [],
        progressPercent: 0,
        progressStatus: '',
        progressEtaSec: 0,
        progressStartedAt: 0,
        progressAction: '',
        refreshing: false,
      },
      chatUsersRefresh: {
        running: false,
        percent: 0,
        status: '',
        added: 0,
      },
      ...createOutreachToggleState(),

      resetChatAnalysisForLead() {
        this._stopChatAnalysisProgress?.();
        this.chatAnalysis = {
          ...(this.chatAnalysis || {}),
          stats: null,
          history: [],
          loadingStats: false,
          loadingHistory: false,
          running: false,
          error: '',
          mode: 'last_messages',
          messageLimit: 10,
          tokenBudget: 4000,
          selectedIds: {},
          lastPayload: null,
          progressLog: [],
          progressPercent: 0,
          progressStatus: '',
          progressEtaSec: 0,
          progressStartedAt: 0,
          progressAction: '',
          refreshing: false,
        };
      },

      maxAnalysisMessages() {
        return Number(this.chatAnalysis?.stats?.max_messages || this.current?.count || this.messages?.length || 0);
      },

      selectedAnalysisMessageIds() {
        const selected = this.chatAnalysis?.selectedIds || {};
        return Object.keys(selected)
          .filter((id) => selected[id])
          .map((id) => Number(id))
          .filter((id) => Number.isFinite(id));
      },

      isMessageSelectedForAnalysis(message) {
        if (!message) return false;
        return !!(this.chatAnalysis?.selectedIds || {})[String(message.id)];
      },

      toggleAnalysisMessage(message) {
        if (!message) return;
        const id = String(message.id);
        const selectedIds = { ...(this.chatAnalysis?.selectedIds || {}) };
        if (selectedIds[id]) delete selectedIds[id];
        else selectedIds[id] = true;
        this.chatAnalysis = { ...(this.chatAnalysis || {}), selectedIds };
      },

      async loadChatAnalysisStats() {
        if (!this.current?.name) return;
        this.chatAnalysis.loadingStats = true;
        try {
          const stats = await apiGetChatAnalysisStats(this.current.name);
          this.chatAnalysis.stats = stats || null;
          const currentLimit = Number(this.chatAnalysis.messageLimit || 10);
          this.chatAnalysis.messageLimit = Math.max(1, currentLimit || 10);
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.chatAnalysis.error = String(e?.message || e);
        } finally {
          this.chatAnalysis.loadingStats = false;
        }
      },

      async loadChatAnalysisHistory() {
        if (!this.current?.name) return;
        this.chatAnalysis.loadingHistory = true;
        try {
          const data = await apiGetChatAnalysisHistory(this.current.name);
          this.chatAnalysis.history = Array.isArray(data?.items) ? data.items : [];
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.chatAnalysis.error = String(e?.message || e);
        } finally {
          this.chatAnalysis.loadingHistory = false;
        }
      },

      buildChatAnalysisPayload(overrides = {}) {
        const mode = String(overrides.mode || this.chatAnalysis.mode || 'last_messages');
        const selectedIds = Array.isArray(overrides.selected_message_ids)
          ? overrides.selected_message_ids
          : this.selectedAnalysisMessageIds();
        const messageLimit = Math.max(1, Number(overrides.message_limit || this.chatAnalysis.messageLimit || 10));
        return {
          mode,
          message_limit: messageLimit,
          token_budget: Math.max(100, Number(overrides.token_budget || this.chatAnalysis.tokenBudget || 4000)),
          selected_message_ids: selectedIds,
          prompt: String(overrides.prompt || this.chatAnalysis.prompt || '').trim(),
          provider: String(overrides.provider || this.chatAnalysis.provider || 'openrouter'),
          model: String(overrides.model || this.chatAnalysis.model || '').trim(),
          sender_key: String(overrides.sender_key || '').trim(),
        };
      },

      addChatAnalysisLog(message, details = null, kind = 'status') {
        const row = {
          ts: new Date().toLocaleTimeString('ru-RU'),
          message: String(message || ''),
          kind: String(kind || 'status'),
          details,
        };
        const previous = Array.isArray(this.chatAnalysis?.progressLog) ? this.chatAnalysis.progressLog : [];
        this.chatAnalysis = { ...(this.chatAnalysis || {}), progressLog: [row, ...previous].slice(0, 60) };
        if (typeof this.emit === 'function') this.emit();
      },

      _setChatAnalysisProgress(patch = {}) {
        this.chatAnalysis = {
          ...(this.chatAnalysis || {}),
          progressPercent: 0,
          progressStatus: '',
          progressEtaSec: 0,
          progressStartedAt: 0,
          progressAction: '',
          ...patch,
        };
        if (typeof this.emit === 'function') this.emit();
      },

      _chatAnalysisProgressStatus(action, elapsedSec) {
        const isRefresh = action === 'refresh';
        if (isRefresh) {
          if (elapsedSec < 3) return 'Обновляю локальную статистику чата…';
          if (elapsedSec < 9) return 'Загружаю историю рекомендаций и последние результаты…';
          return 'Проверяю обновлённые данные и готовлю отображение…';
        }
        if (elapsedSec < 3) return 'Готовлю сообщения, промт и параметры LLM…';
        if (elapsedSec < 12) return 'Запрос отправлен, LLM читает контекст…';
        if (elapsedSec < 45) return 'LLM формирует рекомендации по выбранному контексту…';
        if (elapsedSec > 120) return 'Запрос длинный, продолжаем ждать ответ LLM…';
        return 'Ожидаю ответ LLM…';
      },

      _startChatAnalysisProgress(action = 'run', timeoutSec = 300) {
        this._stopChatAnalysisProgress?.();
        const startedAt = Date.now();
        const total = Math.max(10, Math.min(300, Number(timeoutSec || 300)));
        const status = this._chatAnalysisProgressStatus(action, 0);
        this._setChatAnalysisProgress({
          progressAction: action,
          progressPercent: action === 'refresh' ? 8 : 3,
          progressStatus: status,
          progressEtaSec: total,
          progressStartedAt: startedAt,
        });
        this.addChatAnalysisLog(status, { action, elapsed_sec: 0 }, 'status');
        this._chatAnalysisProgressTimer = window.setInterval(() => {
          const elapsedSec = Math.max(3, Math.floor((Date.now() - startedAt) / 1000));
          const percentCap = action === 'refresh' ? 92 : 96;
          const base = action === 'refresh' ? 8 : 3;
          const percent = Math.min(percentCap, Math.max(base, Math.round((elapsedSec / total) * percentCap)));
          const nextStatus = this._chatAnalysisProgressStatus(action, elapsedSec);
          this._setChatAnalysisProgress({
            progressAction: action,
            progressPercent: percent,
            progressStatus: nextStatus,
            progressEtaSec: Math.max(1, total - elapsedSec),
            progressStartedAt: startedAt,
          });
          this.addChatAnalysisLog(nextStatus, { action, elapsed_sec: elapsedSec, percent }, 'status');
        }, 3000);
      },

      _stopChatAnalysisProgress() {
        if (this._chatAnalysisProgressTimer) {
          window.clearInterval(this._chatAnalysisProgressTimer);
          this._chatAnalysisProgressTimer = null;
        }
      },

      _finishChatAnalysisProgress({ ok = true, action = '', message = '' } = {}) {
        this._stopChatAnalysisProgress();
        this._setChatAnalysisProgress({
          progressAction: action || this.chatAnalysis?.progressAction || '',
          progressPercent: ok ? 100 : Math.max(1, Number(this.chatAnalysis?.progressPercent || 0)),
          progressStatus: ok ? (message || 'Готово') : (message || 'Ошибка выполнения'),
          progressEtaSec: 0,
        });
        this.addChatAnalysisLog(ok ? (message || 'Готово') : (message || 'Ошибка выполнения'), { action, ok }, ok ? 'done' : 'error');
      },

      async refreshChatAnalysis() {
        if (!this.current?.name || this.chatAnalysis?.running) return;
        this.chatAnalysis = { ...(this.chatAnalysis || {}), refreshing: true, error: '' };
        this._startChatAnalysisProgress('refresh', 30);
        try {
          this.addChatAnalysisLog('Запрашиваю статистику анализа.', { kind: 'request', endpoint: 'analysis/stats', lead: this.current.name }, 'request');
          await this.loadChatAnalysisStats();
          this.addChatAnalysisLog('Статистика анализа получена.', { kind: 'response', endpoint: 'analysis/stats', stats: this.chatAnalysis?.stats || null }, 'response');
          this.addChatAnalysisLog('Запрашиваю историю рекомендаций.', { kind: 'request', endpoint: 'analysis/history', lead: this.current.name }, 'request');
          await this.loadChatAnalysisHistory();
          this.addChatAnalysisLog('История рекомендаций получена.', { kind: 'response', endpoint: 'analysis/history', count: Array.isArray(this.chatAnalysis?.history) ? this.chatAnalysis.history.length : 0 }, 'response');
          this._finishChatAnalysisProgress({ ok: true, action: 'refresh', message: 'Обновление анализа завершено' });
        } catch (e) {
          const message = String(e?.message || e);
          this.chatAnalysis.error = message;
          this.addChatAnalysisLog(`Ошибка обновления анализа: ${message}`, { kind: 'error', error: message }, 'error');
          this._finishChatAnalysisProgress({ ok: false, action: 'refresh', message });
        } finally {
          this.chatAnalysis.refreshing = false;
          if (typeof this.emit === 'function') this.emit();
        }
      },

      async refreshChatUsers() {
        if (!this.current?.name || this.chatAnalysis?.running || this.chatUsersRefresh?.running) return;
        const beforeKeys = new Set((this.chatAnalysis?.stats?.by_sender || []).map((item) => String(item.sender_key || '')));
        this.chatUsersRefresh = {
          running: true,
          percent: 12,
          status: 'Обновляю пользователей из локального кеша сообщений…',
          added: 0,
        };
        if (typeof this.emit === 'function') this.emit();
        try {
          await this.loadChatAnalysisStats();
          this.chatUsersRefresh = {
            ...(this.chatUsersRefresh || {}),
            percent: 68,
            status: 'Сверяю авторов, сообщения и токены…',
          };
          if (typeof this.emit === 'function') this.emit();
          await this.loadChatAnalysisHistory();
          const afterRows = this.chatAnalysis?.stats?.by_sender || [];
          const added = afterRows.filter((item) => !beforeKeys.has(String(item.sender_key || ''))).length;
          this.chatUsersRefresh = {
            running: false,
            percent: 100,
            status: added > 0 ? `Добавлено пользователей: ${added}.` : 'Новых пользователей нет.',
            added,
          };
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          const message = String(e?.message || e);
          this.chatUsersRefresh = {
            running: false,
            percent: Math.max(1, Number(this.chatUsersRefresh?.percent || 0)),
            status: `Ошибка обновления пользователей: ${message}`,
            added: 0,
          };
          this.chatAnalysis.error = message;
          toast(message, 'error');
        } finally {
          if (typeof this.emit === 'function') this.emit();
        }
      },

      chatAnalysisPromptForSender(senderKey) {
        const key = String(senderKey || '').trim();
        return key ? (this.chatAnalysis?.userPromptBySender || {})[key] || null : null;
      },

      setChatAnalysisPromptForSender(senderKey, promptConfig) {
        const key = String(senderKey || '').trim();
        if (!key) return;
        const current = this.chatAnalysis?.userPromptBySender || {};
        this.chatAnalysis = {
          ...(this.chatAnalysis || {}),
          userPromptBySender: { ...current, [key]: promptConfig || null },
        };
        if (typeof this.emit === 'function') this.emit();
      },

      async copyChatAnalysisToComposer(text) {
        const value = String(text || '').trim();
        if (!value) return;
        try {
          if (navigator?.clipboard?.writeText) await navigator.clipboard.writeText(value);
        } catch (_) {}
        const input = leadDom.byId('msgInput');
        if (input) {
          input.value = value;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.focus();
        }
        toast('Рекомендация скопирована и вставлена в поле сообщения.', 'log');
      },

      async runUserRecommendation(sender, promptConfig = {}) {
        const senderKey = String(sender?.sender_key || '').trim();
        if (!senderKey) return;
        const prompt = String(promptConfig?.prompt || this.chatAnalysis?.prompt || '').trim();
        const provider = String(promptConfig?.provider || this.chatAnalysis?.provider || 'openrouter');
        const model = String(promptConfig?.model || this.chatAnalysis?.model || '').trim();
        await this.runChatAnalysis({ mode: 'all', sender_key: senderKey, prompt, provider, model });
      },

      async runChatAnalysis(overrides = {}) {
        if (!this.current?.name) return;
        const payload = this.buildChatAnalysisPayload(overrides);
        if (payload.mode === 'selected' && !payload.selected_message_ids.length) {
          this.chatAnalysis.error = 'Выберите сообщения галочками в чате или смените режим анализа.';
          toast(this.chatAnalysis.error, 'error');
          return;
        }
        this.chatAnalysis.running = true;
        this.chatAnalysis.error = '';
        this.chatAnalysis.lastPayload = payload;
        this.chatAnalysis.progressLog = [];
        this.chatAnalysis.userRunningKey = payload.sender_key || '';
        this._startChatAnalysisProgress('run', 300);
        this.addChatAnalysisLog(`Готовлю контекст ${payload.sender_key ? 'по выбранному пользователю' : 'по чату'}.`);
        this.addChatAnalysisLog(`Промт: ${payload.prompt ? 'выбран' : 'по умолчанию'}; LLM: ${payload.provider}/${payload.model || 'default'}.`);
        this.addChatAnalysisLog('Отправляю запрос и ожидаю ответ LLM.', { kind: 'request', payload }, 'request');
        try {
          const data = await apiRunChatAnalysis(this.current.name, payload);
          this.addChatAnalysisLog('Ответ LLM получен.', { kind: 'response', response: data }, 'response');
          this.chatAnalysis.history = Array.isArray(data?.history) ? data.history : this.chatAnalysis.history;
          if (data?.message && data.ok === false) {
            this.chatAnalysis.error = data.message;
            this.addChatAnalysisLog(`Ошибка: ${data.message}`, { kind: 'error', response: data }, 'error');
          }
          this.addChatAnalysisLog(`Готово: ${data?.item?.messages_count || 0} сообщений, ${data?.item?.tokens_estimate || 0} токенов.`);
          await this.loadChatAnalysisStats();
          this._finishChatAnalysisProgress({ ok: !this.chatAnalysis.error, action: 'run', message: 'LLM анализ завершён' });
        } catch (e) {
          this.chatAnalysis.error = String(e?.message || e);
          this.addChatAnalysisLog(`Ошибка LLM: ${this.chatAnalysis.error}`, { kind: 'error', error: this.chatAnalysis.error }, 'error');
          this._finishChatAnalysisProgress({ ok: false, action: 'run', message: this.chatAnalysis.error });
          toast(this.chatAnalysis.error, 'error');
        } finally {
          this.chatAnalysis.running = false;
          this.chatAnalysis.userRunningKey = '';
          if (typeof this.emit === 'function') this.emit();
        }
      },

      async repeatChatAnalysis(item) {
        if (!item) return;
        const payload = {
          mode: item.mode || 'last_messages',
          message_limit: item.message_limit || item.messages_count || 10,
          token_budget: item.token_budget || 4000,
          selected_message_ids: Array.isArray(item.selected_message_ids) ? item.selected_message_ids : [],
          prompt: item.prompt || this.chatAnalysis.prompt,
          provider: item.provider || this.chatAnalysis.provider,
          model: item.model || this.chatAnalysis.model,
          sender_key: item.sender_key || '',
        };
        this.chatAnalysis = {
          ...(this.chatAnalysis || {}),
          mode: payload.mode,
          messageLimit: payload.message_limit,
          tokenBudget: payload.token_budget,
          prompt: payload.prompt,
          provider: payload.provider,
          model: payload.model,
          selectedIds: Object.fromEntries(payload.selected_message_ids.map((id) => [String(id), true])),
        };
        await this.runChatAnalysis(payload);
      },

      sortLeadsInPlace() {
        this.leads = (this.leads || []).slice().sort((a, b) => {
          const da = a?.last_date_utc || '';
          const db = b?.last_date_utc || '';
          if (da === db) return (b?.count || 0) - (a?.count || 0);
          return db.localeCompare(da);
        });
      },

      updateLeadMeta(leadName, patch = {}) {
        if (!leadName) return;
        const applyPatch = (lead) => {
          if (!lead || lead.name !== leadName) return lead;
          Object.assign(lead, patch);
          return lead;
        };

        const found = this.leads.find(x => x?.name === leadName);
        if (found) applyPatch(found);
        if (this.current?.name === leadName) applyPatch(this.current);
        if (!this._suspendLeadSort) {
          this.sortLeadsInPlace();
        }
      },

      mergeLeadsData(data, { trackFresh = false } = {}) {
        const leadItems = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : []);
        const prevByName = new Map((this.leads || []).map(lead => [lead.name, lead]));
        const nextLeads = leadItems.map((lead) => {
          const prev = prevByName.get(lead.name);
          const nextLead = {
            ...lead,
            bump_delta: Number(prev?.bump_delta || 0),
            bump_until: Number(prev?.bump_until || 0),
          };

          if (trackFresh && prev) {
            const prevCount = Number(prev.count || 0);
            const nextCount = Number(lead.count || 0);
            if (nextCount > prevCount) {
              this.bumpLeadActivity(lead.name, nextCount - prevCount);
            }
          }

          return nextLead;
        });

        this.leads = reconcileKeyedCollection(this.leads, nextLeads, (lead) => lead?.name || '');
        this.sortLeadsInPlace();

        if (this.current) {
          const found = this.leads.find(x => x.name === this.current.name);
          if (found) this.current = found;
        }
      },

      leadHasFreshActivity(lead) {
        return Number(lead?.bump_delta || 0) > 0;
      },

      leadDeltaText(lead) {
        const delta = Number(lead?.bump_delta || 0);
        return delta > 0 ? `+${delta}` : '';
      },

      clearLeadActivity(leadName) {
        if (!leadName) return;
        this.updateLeadMeta(leadName, {
          bump_delta: 0,
          bump_until: 0,
        });
      },

      bumpLeadActivity(leadName, delta = 1) {
        if (!leadName || delta <= 0) return;
        if (this.current?.name === leadName) return;
        const currentDelta = this.current?.name === leadName
          ? Number(this.current?.bump_delta || 0)
          : Number(this.leads.find(x => x?.name === leadName)?.bump_delta || 0);

        this.updateLeadMeta(leadName, {
          bump_delta: currentDelta + delta,
          bump_until: Date.now(),
        });
      },

      syncCurrentLeadCountFromMessages() {
        if (!this.current) return;
        const loadedCount = this.messages.length;
        if (!loadedCount) return;
        this.updateLeadMeta(this.current.name, {
          count: Math.max(Number(this.current.count || 0), loadedCount),
          has_jsonl: true,
          sync_status: 'active',
        });
      },

      messageChunkSize() {
        return Math.max(10, Math.min(30, Number(this.ui.messagesLimit || 30)));
      },

      messageRenderWindowSize() {
        return Math.max(10, Math.min(30, Number(this.ui.messageRenderSize || 30)));
      },

      visibleMessages() {
        const rows = Array.isArray(this.messages) ? this.messages : [];
        return rows;
      },

      messageScrollProgressPercent() {
        const total = Math.max(1, Number(this.current?.count || this.messages.length || 1));
        const loaded = Math.min(total, Math.max(0, this.messages.length));
        return Math.round((loaded / total) * 100);
      },

      messageScrollProgressText() {
        const total = Math.max(0, Number(this.current?.count || 0));
        const loaded = Math.max(0, this.messages.length);
        if (!this.current) return '';
        if (!total) return `${loaded} сообщений загружено`;
        return `${loaded} из ${total} сообщений в локальном окне`;
      },

      messageLoadEtaText() {
        if (!this.loading && !this.messagesLoadingMore) return '';
        const startedAt = Number(this.messagesLoadStartedAt || 0);
        if (!startedAt) return 'ETA: считаю...';
        const elapsedSec = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
        const percent = Math.max(1, Number(this.messageScrollProgressPercent?.() || 1));
        if (percent <= 1) return `ETA: собираю данные, прошло ${elapsedSec} сек.`;
        const totalSec = Math.round((elapsedSec / percent) * 100);
        const leftSec = Math.max(0, totalSec - elapsedSec);
        return leftSec > 0 ? `ETA: ~${leftSec} сек.` : 'ETA: почти готово';
      },

      handleChatScroll(event) {
        const box = event?.currentTarget || event?.target;
        if (!box || !this.current) return;
        const maxScroll = Math.max(1, Number(box.scrollHeight || 0) - Number(box.clientHeight || 0));
        const ratio = Math.max(0, Math.min(1, Number(box.scrollTop || 0) / maxScroll));
        this.messageScrollRatio = ratio;
        if (box.scrollTop < 80) {
          this.preserveTopScrollAfterOlderLoad?.(box);
        }
      },

      lastOpenedLeadName() {
        try {
          return leadDom.getStorage(LAST_OPEN_CHAT_KEY);
        } catch (_) {
          return '';
        }
      },

      rememberCurrentLead(lead) {
        const name = String(lead?.name || '').trim();
        if (!name) return;
        try {
          leadDom.setStorage(LAST_OPEN_CHAT_KEY, name);
        } catch (_) {}
      },

      async openLastLeadAfterLoad() {
        if (this._lastLeadRestoreTried || this.current) return false;
        this._lastLeadRestoreTried = true;
        const leadName = this.lastOpenedLeadName();
        if (!leadName) return false;
        let lead = (this.leads || []).find((item) => item?.name === leadName);
        if (!lead) {
          try {
            const data = await apiGetLeads({
              page: 1,
              page_size: 5,
              query: leadName,
              show_channels: true,
              show_groups: true,
              show_private: true,
              show_bots: false,
              show_archived: false,
              scan_filter: 'all',
              sort_mode: 'recent',
            }, buildPagedRequestOptions('chat:last-open', {
              page: 1,
              page_size: 5,
              query: leadName,
            }, {
              requestKey: 'chat:last-open',
              cacheTtlMs: 5000,
            }));
            const rows = Array.isArray(data?.items) ? data.items : [];
            lead = rows.find((item) => item?.name === leadName) || rows[0] || null;
          } catch (e) {
            if (!isAbortedRequestError(e)) console.warn('[Lead] restore last chat failed:', e);
          }
        }
        if (!lead) return false;
        await this.openLead(lead);
        return true;
      },

      applyIncomingMessageToLead(dto) {
        if (!this.current) return;
        const previewText = (dto?.text || '').trim() || (dto?.has_media ? '[media]' : '');
        const nextCount = Math.max(Number(this.current.count || 0), this.messages.length);
        this.bumpLeadActivity(this.current.name, 1);
        this.updateLeadMeta(this.current.name, {
          count: nextCount,
          last_date_utc: dto?.date_utc || this.current.last_date_utc,
          last_text_preview: previewText || this.current.last_text_preview,
          has_jsonl: true,
          sync_status: 'active',
        });
      },

      applyGlobalLeadEvent(rec) {
        const leadName = String(rec?.chat?.username || rec?.chat?.title || rec?.lead || '').trim();
        if (!leadName) return;
        if (this.current?.name === leadName) return;

        const msg = rec?.message || {};
        const previewText = (msg.text || '').trim() || (msg.has_media ? '[media]' : '');
        const previousLead = this.leads.find(x => x?.name === leadName) || (this.current?.name === leadName ? this.current : null);
        const nextCount = Number(previousLead?.count || 0) + 1;

        this.bumpLeadActivity(leadName, 1);

        this.updateLeadMeta(leadName, {
          count: nextCount,
          last_date_utc: msg.date_utc || previousLead?.last_date_utc,
          last_text_preview: previewText || previousLead?.last_text_preview,
          has_jsonl: true,
          sync_status: 'active',
          chat_type: previousLead?.chat_type || 'channel',
          is_archived: Boolean(previousLead?.is_archived),
        });
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
      },

      applyIncomingMessagesBatch(batch) {
        if (!Array.isArray(batch) || !batch.length) return;
        let changed = false;
        for (const dto of batch) {
          const id = String(dto?.id || '');
          if (!id || this._msgIds.has(id)) continue;
          if (!dto?.optimistic && dto?.text) {
            const incomingText = String(dto.text || '').trim();
            const incomingTs = Date.parse(dto.date_utc || '') || Date.now();
            const duplicateIndex = this.messages.findIndex((item) => {
              if (!item?.optimistic) return false;
              if (String(item.text || '').trim() !== incomingText) return false;
              const optimisticTs = Date.parse(item.date_utc || '') || incomingTs;
              return Math.abs(incomingTs - optimisticTs) < 600000;
            });
            if (duplicateIndex >= 0) {
              const duplicate = this.messages[duplicateIndex];
              this._msgIds.delete(String(duplicate?.id || ''));
              this.messages.splice(duplicateIndex, 1);
            }
          }
          this._msgIds.add(id);
          this.messages.push(dto);
          this.applyIncomingMessageToLead(dto);
          changed = true;
        }
        if (!changed) return;
        this.messages.sort((a, b) => String(a.date_utc || '').localeCompare(String(b.date_utc || '')));
        this.messagesLoadedOffset = Math.max(this.messagesLoadedOffset || 0, this.messages.length);
        this.ui.messageRenderStart = Math.max(0, this.messages.length - this.messageRenderWindowSize());
        this.scrollToBottom();
      },

      appendOptimisticOutgoingMessage(text) {
        if (!this.current) return '';
        const id = `out-${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const dto = {
          id,
          role: 'assistant',
          text,
          date_utc: new Date().toISOString(),
          reply_to_msg_id: null,
          has_media: false,
          sender_username: null,
          sender_name: 'Вы',
          optimistic: true,
          send_status: 'sending',
        };
        this._msgIds.add(id);
        this.messages.push(dto);
        this.messages.sort((a, b) => String(a.date_utc || '').localeCompare(String(b.date_utc || '')));
        this.messagesLoadedOffset = Math.max(this.messagesLoadedOffset || 0, this.messages.length);
        this.ui.messageRenderStart = Math.max(0, this.messages.length - this.messageRenderWindowSize());
        this.applyIncomingMessageToLead(dto);
        this.scrollToBottom();
        if (typeof this.emit === 'function') this.emit();
        return id;
      },

      updateOptimisticOutgoingMessage(id, patch = {}) {
        if (!id) return;
        const index = this.messages.findIndex((item) => String(item?.id || '') === String(id));
        if (index < 0) return;
        this.messages[index] = { ...this.messages[index], ...patch };
        if (typeof this.emit === 'function') this.emit();
      },

      hasDeliveredOutgoingMessage(text, sentAtIso) {
        const expectedText = String(text || '').trim();
        if (!expectedText) return false;
        const sentAt = Date.parse(sentAtIso || '') || Date.now();
        return this.messages.some((item) => {
          if (!item || item.optimistic) return false;
          if (String(item.text || '').trim() !== expectedText) return false;
          const itemAt = Date.parse(item.date_utc || '') || sentAt;
          return Math.abs(itemAt - sentAt) < 600000;
        });
      },

      async verifyOutgoingDelivery(optimisticId, text, sentAtIso) {
        this.updateOptimisticOutgoingMessage(optimisticId, { send_status: 'checking' });
        try {
          await new Promise((resolve) => window.setTimeout(resolve, 900));
          await this.reloadMessages();
          return this.hasDeliveredOutgoingMessage(text, sentAtIso);
        } catch (e) {
          console.warn('[Lead] outgoing delivery verification failed:', e);
          return false;
        }
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

      pagedLeads() {
        return this.filteredLeads();
      },

      totalPages() {
        return Math.max(1, Number(this.totalLeadPages || 1));
      },

      visibleRangeText() {
        const total = Math.max(0, Number(this.totalLeads || 0));
        if (!total) return '0 из 0';
        const size = Math.max(1, Number(this.ui.pageSize || 1));
        const from = ((Math.max(1, Number(this.ui.page || 1)) - 1) * size) + 1;
        const to = Math.min(total, from + this.filteredLeads().length - 1);
        return `${from}-${to} из ${total}`;
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

      persistUi() {
        persistUiState(INDEX_UI_STATE_KEY, this.ui, ['leadFilter', 'page', 'pageSize', 'showChannels', 'showGroups', 'showPrivate', 'scanFilter']);
      },

      resetLeadPageAndLoad() {
        this.ui.page = 1;
        this.persistUi();
        this.loadLeads();
      },

      setScanFilter(value) {
        this.ui.scanFilter = String(value || 'all');
        this.resetLeadPageAndLoad();
      },

      goToPage(page) {
        const target = Number(page || 1);
        const total = this.totalPages();
        this.ui.page = Math.min(Math.max(1, target), total);
        this.persistUi();
        this.loadLeads({ silent: true });
      },

      prevPage() {
        this.goToPage(this.ui.page - 1);
      },

      nextPage() {
        this.goToPage(this.ui.page + 1);
      },

      async init() {
        this._leadEventsBatcher = createBatchedQueueProcessor({
          delayMs: 250,
          maxBatchSize: 100,
          onFlush: (batch) => this.applyGlobalLeadEventsBatch(batch),
        });
        this._messageBatcher = createBatchedQueueProcessor({
          delayMs: 250,
          maxBatchSize: 100,
          onFlush: (batch) => this.applyIncomingMessagesBatch(batch),
        });
        await this.refreshAuthStatus(true);
        await this.loadAppSettings();
        await this.loadLeads();
        await this.openLastLeadAfterLoad();
        this.startAuthPolling();
        this.startLeadPolling();
        this.startGlobalLeadStream();
        this.$nextTick(() => this.initLlmClickHandler());
      },

      async loadAppSettings() {
        try {
          const data = await apiGetAppSettings({ cacheKey: 'lead:settings', cacheTtlMs: 30000, timeoutMs: 5000 });
          const timeout = Math.max(5, Math.min(300, Number(data?.openrouter_timeout_sec || 300)));
          this.settings = {
            ...(this.settings || {}),
            openrouter_timeout_sec: timeout,
          };
          this._setLlmProgress({ timeoutSec: timeout, etaSec: Number(this.llmProgress?.running ? this.llmProgress?.etaSec : 0) });
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          console.warn('Lead settings failed:', e);
        }
      },

      authBadgeClass() {
        const status = this.authStatus?.auth_status;
        if (status === 'authorized') return 'badge-active';
        if (status === 'needs_api_credentials') return 'badge-pending';
        if (status === 'session_present') return 'badge-pending';
        return 'badge-archived';
      },

      authBannerVisible() {
        const status = this.authStatus?.auth_status;
        return status === 'needs_api_credentials' || status === 'needs_auth' || status === 'session_present' || status === 'unknown';
      },

      authStep() {
        if (this.authStatus?.auth_status === 'needs_api_credentials') return 'api';
        return this.authStatus?.auth_step || 'phone';
      },

      authNeedsUi() {
        return this.authStatus?.auth_status === 'needs_api_credentials' || this.authStatus?.auth_status === 'needs_auth';
      },

      canReauthorize() {
        return !!this.authStatus;
      },

      startAuthPolling() {
        this.stopAuthPolling();
        this._authTimer = setInterval(() => {
          if (leadDom.isDocumentHidden?.() || this._authInflight) return;
          this.refreshAuthStatus(true);
        }, 10000);
      },

      stopAuthPolling() {
        if (this._authTimer) {
          clearInterval(this._authTimer);
          this._authTimer = null;
        }
      },

      startLeadPolling() {
        this.stopLeadPolling();
        this._leadTimer = setInterval(() => {
          if (leadDom.isDocumentHidden?.() || this._leadInflight) return;
          this.loadLeads({ silent: true, trackFresh: true });
        }, 30000);
      },

      stopLeadPolling() {
        if (this._leadTimer) {
          clearInterval(this._leadTimer);
          this._leadTimer = null;
        }
      },

      startGlobalLeadStream() {
        this.stopGlobalLeadStream();
        try {
          const client = window.BackfrontRealtime;
          if (!client?.startTypedRealtimeStreamConsumer) throw new Error('typed realtime client unavailable');
          this._globalEs = client.startTypedRealtimeStreamConsumer({
            baseUrl: URL_REALTIME_STREAM,
            baseCandidates: API_BASE_CANDIDATES_UNIQUE,
            types: ['lead'],
            onEnvelope: (envelope) => {
              if (envelope?.type === 'lead_event' && envelope?.payload) {
                this._leadEventsBatcher?.push(envelope.payload);
              }
            },
            onError: (error) => {
              console.warn('Global leads SSE typed stream error:', error);
            },
          });
          if (!this._globalEs) throw new Error('typed realtime stream init failed');
        } catch (e) {
          console.warn('Global leads stream init failed:', e);
          return;
        }
      },

      stopGlobalLeadStream() {
        if (this._globalEs) {
          try { this._globalEs.close(); } catch {}
          this._globalEs = null;
        }
      },

      async refreshAuthStatus(silent = false) {
        if (this._authInflight) return;
        this._authInflight = true;
        try {
          const prevStatus = this.authStatus?.auth_status;
          const status = await apiGetRuntimeStatus();
          this.authStatus = status;
          if (status?.telegram_api_id && !this.authForm.apiId) {
            this.authForm.apiId = String(status.telegram_api_id || '');
          }
          if (status?.pending_phone && !this.authForm.phone) {
            this.authForm.phone = status.pending_phone;
          }
          if (prevStatus !== 'authorized' && status?.auth_status === 'authorized') {
            await this.loadLeads();
          }
          if (!silent && status?.auth_status === 'authorized') {
            toast('Telegram авторизован', 'log');
          }
        } catch (e) {
          if (!silent) {
            this.error = String(e?.message || e);
            toast(this.error, 'error');
          }
        } finally {
          this._authInflight = false;
        }
      },

      async submitApiCredentials() {
        if (this.authLoading) return;
        this.authLoading = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_AUTH_API_CREDENTIALS, {
            api_id: this.authForm.apiId,
            api_hash: this.authForm.apiHash,
          });
          this.authStatus = result.status;
          this.authForm.apiHash = '';
          toast(result.message || 'Telegram API ключи сохранены', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
          await this.refreshAuthStatus(true);
        } finally {
          this.authLoading = false;
        }
      },

      async submitPhoneAuth() {
        if (this.authLoading) return;
        this.authLoading = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_AUTH_PHONE, { phone: this.authForm.phone });
          this.authStatus = result.status;
          this.authForm.code = '';
          this.authForm.password = '';
          toast(result.message || 'Код отправлен', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
          await this.refreshAuthStatus(true);
        } finally {
          this.authLoading = false;
        }
      },

      async submitCodeAuth() {
        if (this.authLoading) return;
        this.authLoading = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_AUTH_CODE, { code: this.authForm.code });
          this.authStatus = result.status;
          if (result.status?.auth_status === 'authorized') {
            this.authForm.code = '';
            this.authForm.password = '';
            await this.loadLeads();
          }
          toast(result.message || 'Код подтвержден', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
          await this.refreshAuthStatus(true);
        } finally {
          this.authLoading = false;
        }
      },

      async submitPasswordAuth() {
        if (this.authLoading) return;
        this.authLoading = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_AUTH_PASSWORD, { password: this.authForm.password });
          this.authStatus = result.status;
          if (result.status?.auth_status === 'authorized') {
            this.authForm.code = '';
            this.authForm.password = '';
            await this.loadLeads();
          }
          toast(result.message || 'Пароль подтвержден', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
          await this.refreshAuthStatus(true);
        } finally {
          this.authLoading = false;
        }
      },

      async reauthorizeTelegram() {
        if (this.authLoading) return;
        if (!leadDom.confirm('Сбросить текущую Telegram-сессию и пройти авторизацию заново?')) return;

        this.authLoading = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_AUTH_REAUTHORIZE, {});
          this.authStatus = result.status;
          this.authForm.code = '';
          this.authForm.password = '';
          this.authForm.phone = '';
          toast(result.message || 'Telegram-сессия сброшена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
          await this.refreshAuthStatus(true);
        } finally {
          this.authLoading = false;
        }
      },

      previewText(text, maxLen = 90) {
        const value = String(text || '').trim();
        if (!value) return '';
        return value.length > maxLen ? `${value.slice(0, maxLen)}...` : value;
      },

      leadStatusText(lead) {
        if (!lead) return '';
        const telegramStatus = String(lead.telegram_status || '').trim();
        if (telegramStatus === 'blocked_privacy') return 'PRIVACY BLOCKED';
        if (telegramStatus === 'risk_blocked') return 'RISK · БЛОКИРОВКА';
        if (telegramStatus === 'risk_rate_limited') {
          return lead.retry_after ? `RISK · COOLDOWN до ${fmtDate(lead.retry_after, true)}` : 'RISK · COOLDOWN';
        }
        if (telegramStatus === 'cooldown') {
          return lead.retry_after ? `COOLDOWN до ${fmtDate(lead.retry_after, true)}` : 'COOLDOWN';
        }
        if (lead.in_source) {
          return lead.sync_status === 'pending' ? 'СКАНИРУЕТСЯ · ЖДЁТ ДАННЫЕ' : 'СКАНИРУЕТСЯ';
        }
        return lead.has_jsonl ? 'НЕ СКАНИРУЕТСЯ · ЕСТЬ В БАЗЕ' : 'НЕ СКАНИРУЕТСЯ';
      },

      leadStatusClass(lead) {
        if (!lead) return 'badge-archived';
        const telegramStatus = String(lead.telegram_status || '').trim();
        if (telegramStatus === 'risk_blocked' || telegramStatus === 'blocked_privacy') return 'badge-error';
        if (telegramStatus === 'risk_rate_limited' || telegramStatus === 'cooldown') return 'badge-pending';
        if (!lead.in_source) return 'badge-archived';
        if (lead.sync_status === 'active') return 'badge-active';
        if (lead.sync_status === 'pending') return 'badge-pending';
        return 'badge-archived';
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
        if (lead.last_text_preview) return this.previewText(lead.last_text_preview, 90);
        if (!lead.in_source) {
          return lead.has_jsonl ? 'Не сканируется, история сохранена в базе' : 'Не сканируется';
        }
        if (lead.sync_status === 'pending') return 'Сканируется: ждём первую выгрузку из Telegram';
        if (lead.sync_status === 'archived') return 'Не сканируется, jsonl сохранён';
        return '';
      },

      canRemoveLead(lead) {
        return !!lead?.in_source;
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

      async addChannel() {
        const selector = (this.sourceForm.selector || '').trim();
        if (!selector || this.sourceRefreshing) return;
        this.sourceRefreshing = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_ADD_SOURCE, { selector });
          this.sourceForm.selector = '';
          await this.loadLeads();
          if (this.current) {
            const found = this.leads.find(x => x.name === this.current.name);
            if (found) this.current = found;
          }
          toast(result.message || 'Канал добавлен', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
        }
      },

      async removeChannel(lead) {
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!selector || this.sourceRefreshing) return;
        if (!leadDom.confirm(`Удалить канал "${selector}" из выбранных источников?`)) return;

        this.sourceRefreshing = true;
        this.error = null;
        try {
          const result = await apiPostJson(URL_REMOVE_SOURCE, { selector });
          await this.loadLeads();
          if (this.current && this.current.name === lead?.name) {
            const found = this.leads.find(x => x.name === this.current.name);
            if (found) {
              this.current = found;
            }
          }
          toast(result.message || 'Канал удалён', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
        }
      },

      async deactivateLead(lead) {
        if (!lead?.name || this.sourceRefreshing) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!selector) return;
        if (!leadDom.confirm(`Отключить синхронизацию для "${selector}"?`)) return;

        this.sourceRefreshing = true;
        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'deactivate';
        this.error = null;
        try {
          const result = await apiDeactivateLead({ lead: lead.name, selector });
          await this.loadLeads();
          if (this.current?.name === lead.name) {
            const found = this.leads.find(x => x.name === lead.name);
            if (found) this.current = found;
          }
          toast(result.message || 'Синхронизация отключена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async activateLead(lead) {
        if (!lead?.name || this.sourceRefreshing) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!selector) return;

        this.sourceRefreshing = true;
        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'activate';
        this.error = null;
        try {
          const result = await apiActivateLead({ lead: lead.name, selector });
          await this.loadLeads();
          if (this.current?.name === lead.name) {
            const found = this.leads.find(x => x.name === lead.name);
            if (found) this.current = found;
          }
          toast(result.message || 'Синхронизация включена', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async deleteLead(lead) {
        if (!lead?.name || this.sourceRefreshing) return;
        const selector = (lead?.source_selector || lead?.name || '').trim();
        if (!leadDom.confirm(`Удалить "${selector}" из чатов и сетки полностью?`)) return;

        this.sourceRefreshing = true;
        this.leadActionBusyName = lead.name;
        this.leadActionBusyType = 'delete';
        this.error = null;
        try {
          const result = await apiDeleteLead({ lead: lead.name, selector });
          await this.loadLeads();
          if (this.current?.name === lead.name) {
            this.current = null;
            this.messages = [];
            this._msgIds.clear();
            this.closeStream();
            this.stopLlmPolling();
            this.llmHtml = '';
            try {
              if (this.lastOpenedLeadName() === lead.name) leadDom.removeStorage(LAST_OPEN_CHAT_KEY);
            } catch (_) {}
          }
          toast(result.message || 'Лид удалён', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
          this.leadActionBusyName = null;
          this.leadActionBusyType = '';
        }
      },

      async loadLeads(options = {}) {
        const { silent = false, trackFresh = false } = options;
        if (this._leadInflight) return;
        this._leadInflight = true;
        if (!silent) {
          this.loading = true;
        }
        this.error = null;
        try {
          const data = await apiGetLeads({
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.leadFilter || '').trim(),
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: false,
            show_archived: false,
            scan_filter: this.ui.scanFilter,
            sort_mode: 'recent',
          }, buildPagedRequestOptions('chat:leads', {
            page: this.ui.page,
            page_size: this.ui.pageSize,
            query: (this.ui.leadFilter || '').trim(),
            show_channels: this.ui.showChannels,
            show_groups: this.ui.showGroups,
            show_private: this.ui.showPrivate,
            show_bots: false,
            show_archived: false,
            scan_filter: this.ui.scanFilter,
            sort_mode: 'recent',
          }, {
            requestKey: 'chat:leads',
            cacheTtlMs: 5000,
            forceFresh: !!silent,
          }));
          this.totalLeads = Number(data?.total || 0);
          this.totalLeadPages = Number(data?.total_pages || 1);
          this.ui.page = Number(data?.page || this.ui.page || 1);
          this.ui.pageSize = Number(data?.page_size || this.ui.pageSize || 5);
          this.persistUi();
          this.mergeLeadsData((data?.items || []).slice(), { trackFresh });
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          if (!silent) {
            toast(this.error);
          }
        } finally {
          this._leadInflight = false;
          if (!silent) {
            this.loading = false;
          }
        }
      },

      async refreshChannels() {
        if (this.sourceRefreshing) return;
        this.sourceRefreshing = true;
        try {
          await apiReloadSource();
          await this.loadLeads();
          if (this.current) {
            const found = this.leads.find(x => x.name === this.current.name);
            if (found) this.current = found;
          }
          toast('Каналы обновлены', 'log');
        } catch (e) {
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.sourceRefreshing = false;
        }
      },

      async openLead(lead) {
        if (!lead) return;
        this.current = lead;
        this.rememberCurrentLead(lead);
        this.clearLeadActivity(lead.name);
        this.resetChatAnalysisForLead();

        this.messagesLoadedOffset = 0;
        this.messagesLoadingMore = false;
        this.messagesHasOlder = false;
        this.messageScrollRatio = 1;
        this.ui.messageRenderStart = 0;
        this._msgIds.clear();
        await this.reloadMessages();
        await Promise.allSettled([
          this.loadChatAnalysisStats(),
          this.loadChatAnalysisHistory(),
        ]);
        if (this.ui.autoStream && lead.has_jsonl) this.openStream();
        else this.closeStream();

        this.startLlmPolling();
      },

      async sendMessage() {
        let optimisticId = '';
        let input = null;
        let text = '';
        try {
          if (!this.current) {
            console.warn('Лид (чат) не выбран');
            return;
          }
          input = leadDom.byId('msgInput');
          text = (input?.value || '').trim();
          if (!text) return;
          optimisticId = this.appendOptimisticOutgoingMessage(text);
          const optimisticSentAt = this.messages.find((item) => String(item?.id || '') === String(optimisticId))?.date_utc || new Date().toISOString();
          input.value = '';
          if (typeof input.dispatchEvent === 'function') {
            input.dispatchEvent(new Event('input', { bubbles: true }));
          }

          const res = await fetch(`${API_BASE}/api/payme/send`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
              chat_id: this.current.name,
              message: text
            })
          });

          if (!res.ok) {
            const errorText = await res.text();
            console.error('HTTP ' + res.status + ':', errorText);
            const delivered = await this.verifyOutgoingDelivery(optimisticId, text, optimisticSentAt);
            if (delivered) {
              toast('Сообщение отправлено, статус обновлён из Telegram-кеша', 'success');
              return;
            }
            this.updateOptimisticOutgoingMessage(optimisticId, { send_status: 'failed' });
            toast(`Не удалось отправить сообщение: HTTP ${res.status}`, 'error');
            return;
          }

          this.updateOptimisticOutgoingMessage(optimisticId, { send_status: 'sent' });
        } catch (e) {
          const optimisticSentAt = this.messages.find((item) => String(item?.id || '') === String(optimisticId))?.date_utc || new Date().toISOString();
          const delivered = optimisticId ? await this.verifyOutgoingDelivery(optimisticId, text, optimisticSentAt) : false;
          if (!delivered && optimisticId) {
            this.updateOptimisticOutgoingMessage(optimisticId, { send_status: 'failed' });
          }
          if (!delivered && input && text && !input.value) {
            input.value = text;
            if (typeof input.dispatchEvent === 'function') {
              input.dispatchEvent(new Event('input', { bubbles: true }));
            }
          }
          console.error('sendMessage error:', e);
          toast(delivered ? 'Сообщение отправлено, статус обновлён из Telegram-кеша' : `Не удалось отправить сообщение: ${e?.message || e}`, delivered ? 'success' : 'error');
        }
      },

      async reloadMessages() {
        if (!this.current) return;
        this.loading = true; this.error = null;
        this.messagesLoadStartedAt = Date.now();
        try {
          const limit = this.messageChunkSize();
          const list = await apiGetMessages(this.current.name, 0, limit);
          this.messages = [];
          this._msgIds.clear();
          for (const m of (list || [])) {
            if (!this._msgIds.has(m.id)) {
              this._msgIds.add(m.id);
              this.messages.push(m);
            }
          }
          this.messages.sort((a, b) => String(a.date_utc || '').localeCompare(String(b.date_utc || '')));
          this.messagesLoadedOffset = this.messages.length;
          this.messagesHasOlder = Number(this.current?.count || 0) > this.messages.length;
          this.ui.messageRenderStart = Math.max(0, this.messages.length - this.messageRenderWindowSize());
          this.messageScrollRatio = 1;
          this.syncCurrentLeadCountFromMessages();
          this.scrollToBottom();
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e); toast(this.error);
        } finally { this.loading = false; this.messagesLoadStartedAt = 0; }
      },

      async loadOlderMessages() {
        if (!this.current || this.messagesLoadingMore || !this.messagesHasOlder) return;
        this.messagesLoadingMore = true;
        this.messagesLoadStartedAt = Date.now();
        if (typeof this.emit === 'function') this.emit();
        try {
          const limit = this.messageChunkSize();
          const offset = Math.max(this.messages.length, Number(this.messagesLoadedOffset || 0));
          const list = await apiGetMessages(this.current.name, offset, limit);
          const older = [];
          for (const m of (list || [])) {
            if (!this._msgIds.has(m.id)) {
              this._msgIds.add(m.id);
              older.push(m);
            }
          }
          if (older.length) {
            this.messages = [...older, ...this.messages]
              .sort((a, b) => String(a.date_utc || '').localeCompare(String(b.date_utc || '')));
            this.messagesLoadedOffset = this.messages.length;
            this.ui.messageRenderStart = 0;
          }
          this.messagesHasOlder = !!older.length && Number(this.current?.count || 0) > this.messages.length;
        } catch (e) {
          if (isAbortedRequestError(e)) return;
          this.error = String(e?.message || e);
          toast(this.error, 'error');
        } finally {
          this.messagesLoadingMore = false;
          this.messagesLoadStartedAt = 0;
          if (typeof this.emit === 'function') this.emit();
        }
      },

      async preserveTopScrollAfterOlderLoad(box) {
        if (!box || this.messagesLoadingMore || !this.messagesHasOlder) return;
        const previousHeight = Number(box.scrollHeight || 0);
        const previousTop = Number(box.scrollTop || 0);
        await this.loadOlderMessages();
        leadDom.requestFrame(() => {
          const nextHeight = Number(box.scrollHeight || 0);
          box.scrollTop = previousTop + Math.max(0, nextHeight - previousHeight);
        });
      },

      openStream() {
        this.closeStream();
        if (!this.current) return;
        if (!this.current.has_jsonl) return;
        try {
          const client = window.BackfrontRealtime;
          if (!client?.startTypedRealtimeStreamConsumer) throw new Error('typed realtime client unavailable');
          this._es = client.startTypedRealtimeStreamConsumer({
            baseUrl: URL_REALTIME_STREAM,
            baseCandidates: API_BASE_CANDIDATES_UNIQUE,
            types: ['lead'],
            lead: this.current.name,
            onEnvelope: (envelope) => {
              if (envelope?.type !== 'lead_event' || !envelope?.payload) return;
              const rec = envelope.payload;
              const msg = rec?.message || {};
              const sender = rec?.sender || {};
              const role = this._detectRole(rec);
              const id = (msg.id == null) ? ('auto-' + Math.random().toString(36).slice(2)) : String(msg.id);
              const dto = {
                id, role,
                text: msg.text || '',
                date_utc: msg.date_utc || '',
                reply_to_msg_id: msg.reply_to_msg_id ?? null,
                has_media: !!msg.has_media,
                sender_username: sender.username || null,
                sender_name: sender.name || null,
              };
              this._messageBatcher?.push(dto);
            },
            onError: (error) => {
              console.warn('Lead typed SSE stream error:', error);
            },
          });
          if (!this._es) throw new Error('typed realtime stream init failed');
        } catch (e) {
          toast('Не удалось открыть поток: ' + e, 'error'); return;
        }
      },

      closeStream() {
        this._messageBatcher?.flush();
        if (this._es) { try { this._es.close(); } catch {} this._es = null; }
      },
      toggleStream() { this.ui.autoStream = !this.ui.autoStream; if (this.ui.autoStream) this.openStream(); else this.closeStream(); },

      _detectRole(rec) {
        try {
          const chat = rec?.chat || {};
          const sender = rec?.sender || {};
          if (sender.id === chat.id) return 'assistant';
          if (sender.username && sender.username === chat.username) return 'assistant';
          return 'user';
        } catch { return 'user'; }
      },

      scrollToBottom() {
        const box = leadDom.byId('chatBox');
        const pinToLatest = () => scrollToBottomSmooth(box);
        leadDom.requestFrame(pinToLatest);
        leadDom.requestFrame(() => leadDom.requestFrame(pinToLatest));
        leadDom.setTimeout(pinToLatest, 0);
      },

      startLlmPolling() {
        this.stopLlmPolling();
        if (!this.current) { this.llmHtml = ''; return; }
        this.fetchLlmHtml();
        this._llmTimer = setInterval(() => this.fetchLlmHtml(), 15000);
      },

      stopLlmPolling() {
        if (this._llmTimer) { clearInterval(this._llmTimer); this._llmTimer = null; }
      },

      async fetchLlmHtml() {
        if (!this.current) { this.llmHtml = ''; return; }
        if (this._llmInflight) return;
        this._llmInflight = true;
        const name = this.current.name;
        const url = `${API_BASE}/api/payme/leads/${encodeURIComponent(name)}/llm`;
        try {
          const r = await fetch(url, { cache: 'no-store' });
          if (r.status === 204) { this.llmHtml = ''; this._llmLastLoadedFor = name; return; }
          if (!r.ok) { this.llmHtml = ''; this._llmLastLoadedFor = name; return; }
          const txt = await r.text();
          if (txt !== this.llmHtml || this._llmLastLoadedFor !== name) {
            this.llmHtml = txt;
            this._llmLastLoadedFor = name;
          }
        } catch {
          this.llmHtml = '';
          this._llmLastLoadedFor = name;
        } finally {
          this._llmInflight = false;
        }
      },

      _setLlmProgress(patch = {}) {
        const prev = this.llmProgress || {};
        this.llmProgress = {
          running: false,
          percent: 0,
          etaSec: 0,
          status: '',
          error: '',
          startedAt: 0,
          timeoutSec: 300,
          log: [],
          ...prev,
          ...patch,
        };
        if (typeof this.emit === 'function') this.emit();
      },

      _addLlmProgressLog(message, details = null, kind = 'status') {
        const row = {
          ts: new Date().toLocaleTimeString('ru-RU'),
          message: String(message || ''),
          kind: String(kind || 'status'),
          details,
        };
        const previous = Array.isArray(this.llmProgress?.log) ? this.llmProgress.log : [];
        this._setLlmProgress({ log: [row, ...previous].slice(0, 80) });
      },

      _startLlmProgress() {
        if (this._llmProgressTimer) {
          clearInterval(this._llmProgressTimer);
          this._llmProgressTimer = null;
        }
        const timeoutSec = Math.max(5, Math.min(300, Number(this.settings?.openrouter_timeout_sec || 300)));
        const startedAt = Date.now();
        this._setLlmProgress({
          running: true,
          percent: 3,
          etaSec: timeoutSec,
          status: 'Готовлю контекст чата и отправляю запрос в LLM…',
          error: '',
          startedAt,
          timeoutSec,
          log: [],
        });
        this._addLlmProgressLog('Готовлю контекст чата и параметры запроса.', { action: 'llm-run', elapsed_sec: 0 }, 'status');
        this._llmProgressTimer = setInterval(() => {
          const elapsedSec = Math.max(1, Math.floor((Date.now() - startedAt) / 1000));
          const percent = Math.min(92, Math.max(3, Math.round((elapsedSec / timeoutSec) * 92)));
          const etaSec = Math.max(1, timeoutSec - elapsedSec);
          let status = 'Ожидаю ответ LLM…';
          if (elapsedSec < 5) status = 'Готовлю контекст чата…';
          else if (elapsedSec < 15) status = 'LLM читает сообщения и формирует варианты ответов…';
          else if (elapsedSec > 120) status = 'Запрос длинный, продолжаем ждать ответ LLM…';
          this._setLlmProgress({ running: true, percent, etaSec, status });
          this._addLlmProgressLog(status, { action: 'llm-run', elapsed_sec: elapsedSec, percent }, 'status');
        }, 3000);
      },

      _finishLlmProgress({ ok = true, message = '' } = {}) {
        if (this._llmProgressTimer) {
          clearInterval(this._llmProgressTimer);
          this._llmProgressTimer = null;
        }
        this._setLlmProgress({
          running: false,
          percent: ok ? 100 : Math.max(1, Number(this.llmProgress?.percent || 0)),
          etaSec: 0,
          status: ok ? (message || 'Готово: ответы обновлены') : 'Не удалось получить ответ LLM',
          error: ok ? '' : (message || 'Ошибка LLM-запроса'),
        });
        this._addLlmProgressLog(
          ok ? (message || 'Готово: ответы обновлены') : (message || 'Ошибка LLM-запроса'),
          { action: 'llm-run', ok },
          ok ? 'done' : 'error'
        );
      },

      // ===== LLM RUN МЕТОД =====
      async llmRun(options = {}) {
        if (!this.current) {
          console.warn('[LLM-RUN] Лид не выбран');
          toast('Сначала выберите лида', 'error');
          return;
        }

        if (this.llmRunning) {
          console.warn('[LLM-RUN] Запрос уже выполняется');
          return;
        }

        this.llmRunning = true;
        this._startLlmProgress();
        const promptId = options && typeof options === 'object'
          ? String(options.promptId || options.prompt_id || '').trim()
          : '';
        const timeoutSec = Math.max(5, Math.min(300, Number(this.llmProgress?.timeoutSec || 300)));
        const controller = new AbortController();
        const timeoutHandle = window.setTimeout(() => controller.abort(), (timeoutSec + 5) * 1000);
        window.BackfrontDebug?.log('[LLM-RUN] Запуск анализа для:', this.current.name);
        window.BackfrontDebug?.log('[LLM-RUN] Параметры:', {
          chat_id: this.current.name,
          filename: this.current.file,
          prompt_id: promptId || '(default)'
        });
        const requestPayload = {
          chat_id: this.current.name,
          filename: this.current.file,
          prompt_id: promptId || undefined
        };
        this._addLlmProgressLog('Отправляю запрос на генерацию 3 ответов.', { kind: 'request', payload: requestPayload }, 'request');

        try {
          const response = await fetch(`${API_BASE}/api/payme/llm-run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: controller.signal,
            body: JSON.stringify(requestPayload)
          });

          if (!response.ok) {
            const errText = await response.text();
            console.error('[LLM-RUN] Ошибка:', errText);
            const friendly = humanizeApiError(
              new Error(`HTTP ${response.status} ${errText || ''}`),
              'LLM не ответила'
            );
            throw new Error(friendly);
          }

          const result = await response.json();
          window.BackfrontDebug?.log('[LLM-RUN] success:', result);
          this._addLlmProgressLog('Ответ генерации получен.', { kind: 'response', response: result }, 'response');
          this._finishLlmProgress({ ok: true, message: 'Готово: LLM сформировала 3 ответа' });
          await this.fetchLlmHtml();
          toast('LLM анализ завершен!', 'log');
        } catch (e) {
          console.error('[LLM-RUN] Ошибка запроса:', e);
          const message = e?.name === 'AbortError'
            ? `OpenRouter не ответил за ${timeoutSec} секунд. Можно повторить запрос или выбрать другую модель.`
            : (e.message || 'Ошибка LLM-запроса');
          this._finishLlmProgress({ ok: false, message });
          toast('Ошибка при запуске LLM: ' + message, 'error');
        } finally {
          window.clearTimeout(timeoutHandle);
          this.llmRunning = false;
        }
      },

      // ===== ОБРАБОТЧИК КЛИКОВ =====
      initLlmClickHandler() {
        window.BackfrontDebug?.log('[LLM] init click handler');
        const msgInput = leadDom.byId('msgInput');
        if (!msgInput) return;

        if (msgInput._llmHandlerAdded) return;
        msgInput._llmHandlerAdded = true;

        leadDom.addDocumentListener('click', (ev) => {
          const btn = ev.target.closest('button');
          if (!btn) return;

          const llmBox = leadDom.byId('llmBox');
          if (!llmBox || !llmBox.contains(btn)) return;

          // Обработка llm-run кнопки
          if (btn.classList.contains('llm-run')) {
            window.BackfrontDebug?.log('[LLM-RUN] run button click');
            this.llmRun();
            return;
          }

          if (!btn.classList.contains('btn') && !btn.classList.contains('llm-btn')) return;

          const text = btn.dataset && btn.dataset.text ? btn.dataset.text.trim() : btn.innerText.trim();
          if (!text) return;

          window.BackfrontDebug?.log('[LLM] button click:', text);

          msgInput.value = text;
          msgInput.focus();
          msgInput.setSelectionRange(msgInput.value.length, msgInput.value.length);
        }, true);
      }
    };
  };
  }
})();
