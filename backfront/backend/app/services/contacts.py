"""Telegram contact services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)


def _refresh_legacy_globals() -> None:
    legacy.refresh_globals(globals(), exclude={"_refresh_legacy_globals"})


def api_payme_contact_do_not_contact(contact_key: str, payload: ContactDoNotContactPayload):
    _refresh_legacy_globals()
    target = str(contact_key or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Contact key is empty")
    source_rows = _contact_source_rows_for_filters(limit=200000)
    contact = next((item for item in source_rows if str(item.get("contact_key") or "") == target), None)
    summary = _set_contact_do_not_contact(target, bool(payload.enabled), str(payload.reason or ""))
    removed = _delete_outreach_items_for_contact(target, contact) if bool(payload.enabled) else 0
    message = (
        f"Контакт помечен как do_not_contact; удалено из enReach: {removed}"
        if bool(payload.enabled)
        else "Контакт снова доступен для ручного enReach"
    )
    return ContactDoNotContactActionDTO(
        ok=True,
        message=message,
        contact_key=target,
        do_not_contact=bool(summary.get("do_not_contact")),
        do_not_contact_reason=str(summary.get("do_not_contact_reason") or ""),
        do_not_contact_updated_at=summary.get("do_not_contact_updated_at"),
        removed_outreach_items=removed,
    )

def api_payme_contact_messages(
    contact_key: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    lead: str = Query(default=""),
):
    _refresh_legacy_globals()
    target = str(contact_key or "").strip()
    source_rows = _duckdb_load_contact_rows(limit=200000) if _duckdb_contacts_ready() else _analysis_rows("contacts")
    row = next((item for item in source_rows if str(item.get("contact_key") or "") == target), None)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="Contact not found")
    items = []
    if _duckdb_contacts_ready():
        for item in _duckdb_load_contact_message_rows(target, limit=50000):
            try:
                items.append(TelegramContactMessageDTO(**item))
            except Exception:
                continue
    else:
        for item in _iter_contact_message_cache(target):
            payload = {key: item.get(key) for key in TelegramContactMessageDTO.__fields__.keys()}
            try:
                items.append(TelegramContactMessageDTO(**payload))
            except Exception:
                continue
        items.sort(key=lambda entry: (str(entry.date_utc or ""), int(entry.message_id or 0)), reverse=True)
    filtered = _filter_telegram_contact_messages(
        items,
        query=str(query or "").strip().lower(),
        lead_filter=str(lead or "").strip().lower(),
    )
    return TelegramContactMessagesPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

def api_payme_contact_qualification_prompts():
    _refresh_legacy_globals()
    prompts = [
        ContactQualificationPromptDTO(**item)
        for item in _coerce_contact_qualification_prompts(_get_app_settings().get("contact_qualification_prompts"))
    ]
    return ContactQualificationPromptsDTO(items=prompts, total=len(prompts))

def api_payme_contact_qualifications(contact_key: str):
    _refresh_legacy_globals()
    target = str(contact_key or "").strip()
    entries = _contact_qualifications_state().get(target, {})
    items: List[ContactQualificationDTO] = []
    for item in entries.values():
        if not isinstance(item, dict):
            continue
        try:
            items.append(ContactQualificationDTO(**item))
        except Exception:
            continue
    items.sort(key=lambda row: str(row.updated_at or row.created_at or ""), reverse=True)
    return ContactQualificationsDTO(items=items, total=len(items))

def api_payme_contact_qualify(contact_key: str, payload: ContactQualificationRequestDTO):
    _refresh_legacy_globals()
    target = str(contact_key or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="Contact key is empty")

    prompt_template = _contact_prompt_by_id(payload.template_id)
    if not prompt_template:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    source_rows = _duckdb_load_contact_rows(limit=200000) if _duckdb_contacts_ready() else _analysis_rows("contacts")
    contact = next((item for item in source_rows if str(item.get("contact_key") or "") == target), None)
    if not isinstance(contact, dict):
        raise HTTPException(status_code=404, detail="Contact not found")

    messages = _contact_messages_for_qualification(target, limit=220)
    messages_fingerprint = _contact_messages_fingerprint(messages)
    latest_message_at = _contact_latest_message_at(messages)
    now = _utc_now().isoformat()
    template_id = str(prompt_template["id"])
    state = _contact_qualifications_state()
    state.setdefault(target, {})
    previous = state[target].get(template_id) if isinstance(state[target].get(template_id), dict) else {}
    if (
        previous
        and not bool(payload.force)
        and str(previous.get("status") or "") == "ready"
        and str(previous.get("messages_fingerprint") or "") == messages_fingerprint
    ):
        cached = dict(previous)
        cached["cache_hit"] = True
        cached.setdefault("latest_message_at", latest_message_at)
        return ContactQualificationDTO(**cached)

    try:
        llm_result = _call_openrouter_contact_qualification_sync(contact, prompt_template, messages)
        item = {
            "contact_key": target,
            "template_id": template_id,
            "template_title": str(prompt_template.get("title") or template_id),
            "prompt": str(prompt_template.get("prompt") or ""),
            "result_text": str(llm_result.get("result_text") or "").strip(),
            "model": str(llm_result.get("model") or ""),
            "messages_count": len(messages),
            "status": "ready",
            "error": None,
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
            "messages_fingerprint": messages_fingerprint,
            "latest_message_at": latest_message_at,
            "cache_hit": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        item = {
            "contact_key": target,
            "template_id": template_id,
            "template_title": str(prompt_template.get("title") or template_id),
            "prompt": str(prompt_template.get("prompt") or ""),
            "result_text": "",
            "model": _normalize_openrouter_model_id(_get_app_settings().get("openrouter_model")),
            "messages_count": len(messages),
            "status": "error",
            "error": str(exc),
            "created_at": previous.get("created_at") or now,
            "updated_at": now,
            "messages_fingerprint": messages_fingerprint,
            "latest_message_at": latest_message_at,
            "cache_hit": False,
        }

    state[target][template_id] = item
    telegram_sync.state[CONTACT_QUALIFICATIONS_STATE_KEY] = state
    telegram_sync.save_state()
    return ContactQualificationDTO(**item)

def api_payme_contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=5000, ge=1, le=50000),
    query: str = Query(default=""),
    lead: str = Query(default=""),
    qualified_template: str = Query(default="all"),
    lead_temperature: str = Query(default="all"),
    signals: str = Query(default=""),
):
    _refresh_legacy_globals()
    items: List[TelegramContactDTO] = []
    source_rows: List[Dict[str, Any]]
    contacts_state = _analysis_state("contacts")
    if bool(contacts_state.get("running")) and _analysis_cache_path("contacts").exists():
        source_rows = _load_analysis_cache_rows_limited("contacts", max(1, int(limit or 1)))
    elif _duckdb_contacts_ready():
        source_rows = _duckdb_load_contact_rows(limit=max(1, limit))
    else:
        source_rows = _analysis_rows("contacts", limit=max(1, limit))
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        summary = _decorate_contact_summary_with_qualifications(row)
        summary = _xfiles_apply_contact_signal_summary(summary)
        summary = _decorate_contact_summary_with_signals(summary)
        summary = _decorate_contact_summary_with_provenance(summary)
        summary["related_messages"] = []
        items.append(TelegramContactDTO(**summary))
    filtered = _filter_telegram_contacts(
        items,
        query=str(query or "").strip().lower(),
        lead_filter=str(lead or "").strip().lower(),
    )
    filtered = _filter_telegram_contacts_by_qualification(
        filtered,
        qualification_filter=str(qualified_template or "").strip(),
    )
    filtered = _filter_telegram_contacts_by_temperature(
        filtered,
        lead_temperature=str(lead_temperature or "").strip(),
    )
    filtered = _filter_telegram_contacts_by_signals(
        filtered,
        signal_filter=str(signals or "").strip(),
    )
    return TelegramContactsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

def api_payme_contacts_chats(
    limit: int = Query(default=50000, ge=1, le=50000),
):
    _refresh_legacy_globals()
    normalized_limit = max(1, int(limit or 1))
    return _cached_sync_snapshot(
        f"contacts_chats:{normalized_limit}",
        lambda: _build_contact_chat_filter_options(limit=normalized_limit),
        ttl_sec=30,
    )

def api_payme_contacts_config(payload: AnalysisConfigPayload):
    _refresh_legacy_globals()
    state = _analysis_state("contacts")
    state["enabled"] = bool(payload.enabled)
    state["interval_sec"] = int(payload.interval_sec)
    state["next_refresh_at"] = _analysis_next_refresh_at("contacts")
    telegram_sync.save_state()
    return AnalysisActionDTO(
        ok=True,
        message="Настройки автообновления контактов сохранены",
        status=_build_analysis_status("contacts"),
    )

async def api_payme_contacts_refresh():
    _refresh_legacy_globals()
    started = _schedule_analysis_refresh("contacts")
    return AnalysisActionDTO(
        ok=True,
        message="Обновление кеша контактов запущено" if started else "Обновление контактов уже выполняется",
        status=_build_analysis_status("contacts"),
    )

def api_payme_contacts_status():
    _refresh_legacy_globals()
    return _cached_sync_snapshot("contacts_status", lambda: _build_analysis_status("contacts"))
