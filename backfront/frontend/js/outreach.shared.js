/* Shared enReach field helpers and selection toggle state */
'use strict';

(function initBackfrontOutreach() {
  if (window.BackfrontOutreach) return;

  const OUTREACH_FIELD_LABELS = {
    fio: 'ФИО',
    job_title: 'Должность',
    company: 'Компании',
    contact: 'Контакты',
    city: 'Город',
    message: 'Сообщение',
    event_message: 'Мероприятие',
    chat: 'Чат',
    media: 'Media',
    telegram_contact: 'Контакт',
    import_dialog: 'Import',
    jur_entity: 'ЮР.ЛИЦА.',
  };

  function normalizeOutreachFieldType(fieldType) {
    const normalized = String(fieldType || 'message')
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_]+/g, '_')
      .replace(/^_+|_+$/g, '');
    const aliases = {
      text: 'message',
      message_text: 'message',
      phone: 'contact',
      email: 'contact',
      contacts: 'contact',
      name: 'fio',
      full_name: 'fio',
      title: 'job_title',
      position: 'job_title',
      companies: 'company',
      event: 'event_message',
      events: 'event_message',
      lead: 'chat',
      dialog: 'import_dialog',
      telegram_dialog: 'import_dialog',
      author: 'telegram_contact',
      contact_author: 'telegram_contact',
      jur: 'jur_entity',
      jur_entities: 'jur_entity',
      ur_entity: 'jur_entity',
      ur_entities: 'jur_entity',
    };
    return aliases[normalized] || (OUTREACH_FIELD_LABELS[normalized] ? normalized : 'message');
  }

  function outreachFieldLabel(fieldType, customLabel = '') {
    const custom = String(customLabel || '').trim();
    if (custom) return custom;
    return OUTREACH_FIELD_LABELS[normalizeOutreachFieldType(fieldType)] || 'Сообщение';
  }

  function normalizeOutreachPayload(payload = {}) {
    const fieldType = normalizeOutreachFieldType(payload.field_type || payload.fieldType);
    const text = String(payload.text || '').trim();
    const value = String(payload.value || text || '').trim();
    return {
      field_type: fieldType,
      field_label: outreachFieldLabel(fieldType, payload.field_label || payload.fieldLabel),
      value,
      contact_key: String(payload.contact_key || payload.contactKey || '').trim(),
      lead: String(payload.lead || '').trim(),
      source_selector: String(payload.source_selector || payload.sourceSelector || '').trim(),
      sender_name: String(payload.sender_name || payload.senderName || '').trim(),
      sender_username: String(payload.sender_username || payload.senderUsername || '').trim(),
      message_id: payload.message_id ?? payload.messageId ?? null,
      date_utc: String(payload.date_utc || payload.dateUtc || '').trim(),
      text,
    };
  }

  function outreachPayloadKey(payload = {}) {
    const normalized = normalizeOutreachPayload(payload);
    if (
      ['message', 'event_message'].includes(normalized.field_type)
      && normalized.lead
      && (normalized.message_id || normalized.date_utc)
    ) {
      return [
        normalized.field_type,
        normalized.lead,
        normalized.message_id ?? '',
        normalized.date_utc,
      ].join('::');
    }
    return [
      normalized.field_type,
      normalized.value,
      normalized.lead,
      normalized.message_id ?? '',
      normalized.date_utc,
    ].join('::');
  }

  function createOutreachToggleState(deps) {
    const {
      apiGetOutreachItems,
      apiAddOutreachItem,
      apiDeleteOutreachItem,
      isAbortedRequestError,
      humanizeApiError,
      toast,
    } = deps;
    return {
      outreachBusyKey: null,
      outreachSelectedByKey: {},
      _outreachSelectionsRequested: false,
      _outreachSelectionsLoading: false,
      outreachFieldLabel,
      outreachPayloadKey(payload) { return outreachPayloadKey(payload); },
      outreachPayloadBusyKey(payload) { return `outreach:${this.outreachPayloadKey(payload)}`; },
      isOutreachPayloadSelected(payload) { return !!this.outreachSelectedByKey[this.outreachPayloadKey(payload)]; },
      async ensureOutreachSelections() {
        if (this._outreachSelectionsRequested || this._outreachSelectionsLoading) return;
        this._outreachSelectionsRequested = true;
        await this.loadOutreachSelections(true);
      },
      async loadOutreachSelections(silent = true) {
        if (this._outreachSelectionsLoading) return;
        this._outreachSelectionsLoading = true;
        try {
          const selected = {};
          let page = 1;
          let totalPages = 1;
          do {
            const data = await apiGetOutreachItems({
              page,
              page_size: 100,
            }, {
              requestKey: `outreach-toggle:selections:${page}`,
              cacheKey: `outreach-toggle:selections:${page}`,
              cacheTtlMs: 1500,
              timeoutMs: 5000,
            });
            const items = Array.isArray(data?.items) ? data.items : [];
            for (const item of items) {
              const key = outreachPayloadKey(item);
              if (key) selected[key] = item.id;
            }
            totalPages = Number(data?.total_pages || 1);
            page += 1;
          } while (page <= totalPages && page <= 50);
          this.outreachSelectedByKey = selected;
        } catch (e) {
          if (!isAbortedRequestError(e) && !silent) {
            toast(humanizeApiError(e, 'Не удалось загрузить выбранные элементы enReach'), 'error');
          }
        } finally {
          this._outreachSelectionsLoading = false;
        }
      },
      async addOutreachPayload(payload) {
        const normalized = normalizeOutreachPayload(payload);
        if (!normalized.value) {
          toast('Нечего добавить в enReach: пустое значение', 'error');
          return;
        }
        const busyKey = this.outreachPayloadBusyKey(normalized);
        this.outreachBusyKey = busyKey;
        try {
          const result = await apiAddOutreachItem(normalized);
          const key = outreachPayloadKey(normalized);
          this.outreachSelectedByKey = {
            ...this.outreachSelectedByKey,
            [key]: result?.item?.id || true,
          };
          toast(result?.message || `${normalized.field_label} добавлено в enReach`, 'log');
        } catch (e) {
          toast(humanizeApiError(e, `Не удалось добавить ${normalized.field_label} в enReach`), 'error');
        } finally {
          this.outreachBusyKey = null;
        }
      },
      async removeOutreachPayload(payload) {
        const normalized = normalizeOutreachPayload(payload);
        const key = outreachPayloadKey(normalized);
        let itemId = this.outreachSelectedByKey[key];
        if (!itemId || itemId === true) {
          await this.loadOutreachSelections(true);
          itemId = this.outreachSelectedByKey[key];
        }
        if (!itemId || itemId === true) return;
        const busyKey = this.outreachPayloadBusyKey(normalized);
        this.outreachBusyKey = busyKey;
        try {
          const result = await apiDeleteOutreachItem(itemId);
          const next = { ...this.outreachSelectedByKey };
          delete next[key];
          this.outreachSelectedByKey = next;
          toast(result?.message || `${normalized.field_label} удалено из enReach`, 'log');
        } catch (e) {
          toast(humanizeApiError(e, `Не удалось удалить ${normalized.field_label} из enReach`), 'error');
        } finally {
          this.outreachBusyKey = null;
        }
      },
      async toggleOutreachPayload(payload) {
        if (this.isOutreachPayloadSelected(payload)) {
          await this.removeOutreachPayload(payload);
        } else {
          await this.addOutreachPayload(payload);
        }
      },
    };
  }

  window.BackfrontOutreach = {
    OUTREACH_FIELD_LABELS,
    normalizeOutreachFieldType,
    outreachFieldLabel,
    normalizeOutreachPayload,
    outreachPayloadKey,
    createOutreachToggleState,
  };
})();
