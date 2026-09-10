"""Event analysis services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

def api_payme_calendar_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=5000, ge=1, le=50000),
    query: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    source_rows = _filter_deleted_event_rows(_analysis_rows("events", limit=max(1, limit)))
    items = [EventMessageDTO(**row) for row in source_rows]
    normalized_query = str(query or "").strip().lower()
    normalized_from = str(date_from or "").strip()
    normalized_to = str(date_to or "").strip()
    filtered = []
    for item in items:
        event_date = str(item.event_date or "")
        if not event_date:
            continue
        if normalized_from and event_date < normalized_from:
            continue
        if normalized_to and event_date > normalized_to:
            continue
        if normalized_query and normalized_query not in " ".join(
            [
                event_date,
                item.lead,
                item.source_selector or "",
                item.text,
                item.sender_username or "",
                item.sender_name or "",
                " ".join(item.matched_keywords),
            ]
        ).lower():
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: (str(item.event_date or ""), str(item.date_utc or "")), reverse=False)
    return EventMessagesPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

def api_payme_event_keywords():
    return EventKeywordsDTO(
        keywords=_get_event_keywords(),
        message="Ключевые слова для поиска мероприятий загружены",
    )

def api_payme_event_keywords_update(payload: EventKeywordsPayload):
    keywords = _set_event_keywords(payload.keywords)
    state = _analysis_state("events")
    state["last_keywords_hash"] = "__stale__"
    telegram_sync.save_state()
    return EventKeywordsDTO(
        keywords=keywords,
        message=f"Сохранено ключевых слов: {len(keywords)}",
    )

def api_payme_event_message_delete(payload: EventMessageDeletePayload):
    result = _delete_event_message(payload)
    removed_count = int(result.get("removed_count") or 0)
    return EventMessageDeleteDTO(
        ok=True,
        message=f"Удалено одинаковых сообщений мероприятий: {removed_count}",
        removed_count=removed_count,
    )

def api_payme_event_messages(
    background_tasks: BackgroundTasks,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=500, ge=1, le=5000),
    query: str = Query(default=""),
    lead_filter: str = Query(default=""),
    sender_filter: str = Query(default=""),
    keyword_filter: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    events_state = _analysis_state("events")
    if bool(events_state.get("running")) and _analysis_cache_path("events").exists():
        source_rows = _load_analysis_cache_rows_limited("events", max(1, int(limit or 1)))
    else:
        source_rows = _analysis_rows("events", limit=max(1, limit))
    source_rows = _filter_deleted_event_rows(source_rows)
    items = [EventMessageDTO(**row) for row in source_rows]
    filtered = _filter_event_messages(
        items,
        query=str(query or "").strip().lower(),
        lead_filter=str(lead_filter or "").strip().lower(),
        sender_filter=str(sender_filter or "").strip().lower(),
        keyword_filter=str(keyword_filter or "").strip().lower(),
        date_from=str(date_from or "").strip(),
        date_to=str(date_to or "").strip(),
    )
    page_payload = _paginate_items(filtered, page=page, page_size=page_size)
    _schedule_event_date_extraction(
        [item.model_dump() for item in page_payload.get("items", [])],
        background_tasks=background_tasks,
    ) or _schedule_event_date_pending_batch(background_tasks=background_tasks, max_rows=8)
    return EventMessagesPageDTO(**page_payload)

def api_payme_events_config(payload: AnalysisConfigPayload):
    state = _analysis_state("events")
    state["enabled"] = bool(payload.enabled)
    state["interval_sec"] = int(payload.interval_sec)
    state["next_refresh_at"] = _analysis_next_refresh_at("events")
    telegram_sync.save_state()
    return AnalysisActionDTO(
        ok=True,
        message="Настройки автообновления мероприятий сохранены",
        status=_build_analysis_status("events"),
    )

async def api_payme_events_refresh():
    started = _schedule_analysis_refresh("events")
    return AnalysisActionDTO(
        ok=True,
        message="Обновление кеша мероприятий запущено" if started else "Обновление мероприятий уже выполняется",
        status=_build_analysis_status("events"),
    )

def api_payme_events_status(background_tasks: BackgroundTasks):
    status = _build_analysis_status("events")
    if status.event_date_pending > 0 and not status.event_date_running:
        _schedule_event_date_pending_batch(background_tasks=background_tasks, max_rows=8)
    return status
