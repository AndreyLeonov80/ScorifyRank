"""Lead and messaging services extracted from the legacy backend route handlers."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.repositories import legacy
from app.schemas.compat_models import (
    SourceRuntimeStatusDTO,
    SourceRuntimeStatusPageDTO,
    SourceStatsPageDTO,
    SourceStatsSummaryDTO,
)

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)


def _safe_int_value(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _lead_read_progress_payload(lead, active_info=None):
    source_selector = str(getattr(lead, "source_selector", None) or getattr(lead, "name", "") or "").strip()
    lead_name = str(getattr(lead, "name", "") or "").strip()
    try:
        chat_state = _telegram_chat_state_for_lead(lead_name.lower(), source_selector)
    except Exception:
        chat_state = {}
    read_count = max(
        _safe_int_value(getattr(lead, "count", 0)),
        _safe_int_value(chat_state.get("backfill_items_processed")),
    )
    latest_id = _safe_int_value(chat_state.get("backfill_latest_id") or chat_state.get("max_saved_id"))
    message_limit = _safe_int_value(getattr(lead, "import_message_limit", 0))
    if message_limit > 0:
        total_estimate = max(read_count, min(message_limit, latest_id if latest_id > 0 else message_limit))
    elif latest_id > 0:
        total_estimate = max(read_count, latest_id)
    else:
        total_estimate = read_count
    remaining = max(0, total_estimate - read_count)
    percent = 100.0 if total_estimate <= 0 else min(100.0, round((read_count / max(1, total_estimate)) * 100.0, 1))
    stage = str((active_info or {}).get("stage") or "").strip().lower()
    telegram_status = str(getattr(lead, "telegram_status", "") or "").strip().lower()
    in_source = bool(getattr(lead, "in_source", False))
    return {
        "telegram_active": bool(active_info),
        "telegram_active_stage": stage or None,
        "last_live_update_at": (active_info or {}).get("last_live_update_at")
        or (active_info or {}).get("last_message_at")
        or (active_info or {}).get("updated_at"),
        "live_connected": bool(active_info) and stage in {"live", "stream", "event"},
        "backfill_running": bool(active_info) and stage in {"history", "backfill"},
        "setup_running": bool(active_info) and stage == "setup",
        "paused": telegram_status == "paused",
        "cooldown": telegram_status in {"cooldown", "risk_rate_limited"},
        "waiting_schedule": in_source and not bool(active_info) and telegram_status not in {"paused", "cooldown", "risk_rate_limited"},
        "read_messages_count": read_count,
        "total_messages_estimate": total_estimate,
        "remaining_messages_estimate": remaining,
        "read_progress_percent": percent,
    }


def _active_telegram_sources_by_identity():
    try:
        from app.services import jobs as jobs_service

        job = jobs_service.latest_active_job_by_type("telegram_sync") or jobs_service.latest_job_by_type("telegram_sync")
        result = getattr(job, "result", None) or {}
        if not isinstance(result, dict):
            return {}
        rows = result.get("active_sources")
    except Exception:
        rows = []
    if not isinstance(rows, list):
        rows = []
    active = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        for value in (row.get("selector"), row.get("title")):
            raw = str(value or "").strip()
            if not raw:
                continue
            try:
                active[_selector_identity(raw)] = row
            except Exception:
                active[raw.lower()] = row
            try:
                active[_selector_to_lead_name(raw).lower()] = row
            except Exception:
                pass
    return active


def _enrich_leads_with_telegram_progress(items):
    active_map = _active_telegram_sources_by_identity()
    enriched = []
    for lead in items:
        keys = []
        for value in (getattr(lead, "source_selector", None), getattr(lead, "name", None)):
            raw = str(value or "").strip()
            if not raw:
                continue
            keys.append(raw.lower())
            try:
                keys.append(_selector_identity(raw))
            except Exception:
                pass
            try:
                keys.append(_selector_to_lead_name(raw).lower())
            except Exception:
                pass
        active_info = next((active_map.get(key) for key in keys if key in active_map), None)
        payload = _lead_read_progress_payload(lead, active_info)
        if hasattr(lead, "model_copy"):
            enriched.append(lead.model_copy(update=payload))
        else:
            enriched.append(lead.copy(update=payload))
    return enriched


def _sort_active_leads_first(items):
    return sorted(
        items,
        key=lambda lead: (
            0 if getattr(lead, "telegram_active", False) else 1,
            -float(getattr(lead, "read_progress_percent", 0.0) or 0.0),
            -(getattr(lead, "count", 0) or 0),
            str(getattr(lead, "name", "") or "").lower(),
        ),
    )


def _lead_matches_status_filter(lead, status_filter: str) -> bool:
    value = str(status_filter or "all").strip().lower()
    if value in {"", "all"}:
        return True

    telegram_status = str(getattr(lead, "telegram_status", "") or "").strip().lower()
    sync_status = str(getattr(lead, "sync_status", "") or "").strip().lower()
    in_source = bool(getattr(lead, "in_source", False))
    has_jsonl = bool(getattr(lead, "has_jsonl", False))
    count = _safe_int_value(getattr(lead, "count", 0))
    active = bool(getattr(lead, "telegram_active", False))

    if value == "reading":
        return active
    if value == "waiting":
        return in_source and not active and count > 0 and sync_status != "pending"
    if value == "pending":
        return in_source and not active and (sync_status == "pending" or count <= 0)
    if value == "error":
        return telegram_status in {"blocked_privacy", "risk_blocked", "risk_rate_limited", "cooldown"}
    if value == "archived":
        return (not in_source) and has_jsonl
    if value == "empty":
        return in_source and not has_jsonl and count <= 0
    return True


def _lead_matches_group_filter(lead, group_filter: str) -> bool:
    value = str(group_filter or "all").strip().upper()
    if value in {"", "ALL"}:
        return True
    return str(getattr(lead, "scan_group", "") or "C").strip().upper() == value


async def _load_leads_for_source_view(
    *,
    query: str = "",
    show_channels: bool = True,
    show_groups: bool = True,
    show_private: bool = True,
    show_bots: bool = False,
    show_archived: bool = False,
    scan_filter: str = "all",
    status_filter: str = "all",
    group_filter: str = "all",
    sort_mode: str = "recent",
):
    dialog_meta_catalog = _cached_dialog_meta_catalog()
    private_only = _is_private_only_leads_filter(
        query=query,
        show_channels=show_channels,
        show_groups=show_groups,
        show_private=show_private,
        show_bots=show_bots,
        show_archived=show_archived,
    )
    if private_only and not dialog_meta_catalog:
        _schedule_telegram_dialogs_refresh()

    cached_items = _lead_snapshot_cache.get("items")
    cached_updated_at = float(_lead_snapshot_cache.get("updated_at") or 0.0)
    cached_items_fresh = (
        isinstance(cached_items, list)
        and cached_updated_at > 0.0
        and (time.monotonic() - cached_updated_at) <= _LEAD_SNAPSHOT_CACHE_TTL_SEC
    )
    if cached_items_fresh:
        items = list(cached_items)
    elif isinstance(cached_items, list) and cached_items:
        items = list(cached_items)
        _schedule_lead_snapshot_refresh()
    elif _duckdb_leads_ready():
        items = await asyncio.to_thread(_build_lightweight_leads, dialog_meta_catalog)
        _lead_snapshot_cache["items"] = list(items)
        _lead_snapshot_cache["updated_at"] = time.monotonic()
    else:
        if isinstance(cached_items, list):
            items = list(cached_items)
        else:
            items = await asyncio.to_thread(_build_lightweight_leads, dialog_meta_catalog)
            _schedule_lead_snapshot_refresh()

    filtered = [
        lead
        for lead in items
        if _lead_matches_filters(
            lead,
            query=str(query or "").strip().lower(),
            show_channels=show_channels,
            show_groups=show_groups,
            show_private=show_private,
            show_bots=show_bots,
            show_archived=show_archived,
            scan_filter=scan_filter,
        )
    ]
    enriched_items = _enrich_leads_with_telegram_progress(filtered)
    enriched_items = [
        lead
        for lead in enriched_items
        if _lead_matches_status_filter(lead, status_filter)
        and _lead_matches_group_filter(lead, group_filter)
    ]
    sorted_items = _sort_leads_for_view(enriched_items, sort_mode=str(sort_mode or "recent"))
    if str(sort_mode or "recent") == "status":
        sorted_items = _sort_active_leads_first(sorted_items)
    return sorted_items


def _source_stats_summary(items):
    total = len(items)
    selected = sum(1 for item in items if bool(getattr(item, "in_source", False)))
    imported = sum(1 for item in items if bool(getattr(item, "has_jsonl", False)))
    active = sum(1 for item in items if bool(getattr(item, "telegram_active", False)))
    errors = sum(1 for item in items if _lead_matches_status_filter(item, "error"))
    empty = sum(1 for item in items if _lead_matches_status_filter(item, "empty"))
    archived = sum(1 for item in items if _lead_matches_status_filter(item, "archived"))
    pending = sum(1 for item in items if _lead_matches_status_filter(item, "pending"))
    waiting = sum(1 for item in items if _lead_matches_status_filter(item, "waiting"))
    messages_read = sum(_safe_int_value(getattr(item, "read_messages_count", 0)) for item in items)
    messages_total = sum(_safe_int_value(getattr(item, "total_messages_estimate", 0)) for item in items)
    messages_remaining = sum(_safe_int_value(getattr(item, "remaining_messages_estimate", 0)) for item in items)
    progress = 100.0 if messages_total <= 0 else min(100.0, round((messages_read / max(1, messages_total)) * 100.0, 2))
    return SourceStatsSummaryDTO(
        total_sources=total,
        selected_sources=selected,
        imported_sources=imported,
        active_sources=active,
        pending_sources=pending,
        waiting_sources=waiting,
        error_sources=errors,
        empty_sources=empty,
        archived_sources=archived,
        messages_total=messages_total,
        messages_read=messages_read,
        messages_remaining=messages_remaining,
        progress_percent=progress,
        generated_at=_utc_now().isoformat(),
    )


def _runtime_status_reason(lead) -> str:
    if bool(getattr(lead, "paused", False)):
        return "пауза: запросы в Telegram не выполняются"
    if bool(getattr(lead, "telegram_active", False)):
        stage = str(getattr(lead, "telegram_active_stage", "") or "").strip()
        return f"читает сейчас: {stage}" if stage else "читает сейчас"
    if bool(getattr(lead, "cooldown", False)):
        return "Telegram cooldown: ждём безопасное окно"
    if str(getattr(lead, "telegram_status", "") or "").strip().lower() in {
        "blocked_privacy",
        "risk_blocked",
        "risk_rate_limited",
        "cooldown",
    }:
        return str(getattr(lead, "telegram_status", "") or "ошибка Telegram")
    if bool(getattr(lead, "in_source", False)) and not bool(getattr(lead, "has_jsonl", False)):
        return "выбран для сканирования, но JSONL/DuckDB кеш ещё пустой"
    if bool(getattr(lead, "in_source", False)) and _safe_int_value(getattr(lead, "count", 0)) <= 0:
        return "выбран для сканирования, сообщений пока нет"
    if bool(getattr(lead, "in_source", False)):
        return "выбран и ожидает следующего шага worker/scheduler"
    if bool(getattr(lead, "has_jsonl", False)):
        return "есть локальный кеш, но источник не выбран для сканирования"
    return "источник не выбран"


def _source_runtime_status_from_lead(lead) -> SourceRuntimeStatusDTO:
    selector = str(getattr(lead, "source_selector", None) or getattr(lead, "name", "") or "").strip()
    title = str(getattr(lead, "name", "") or selector or "").strip()
    rows = _safe_int_value(getattr(lead, "count", 0))
    status = str(getattr(lead, "sync_status", "") or "archived").strip().lower()
    if bool(getattr(lead, "telegram_active", False)):
        status = "reading"
    elif _lead_matches_status_filter(lead, "error"):
        status = "error"
    elif _lead_matches_status_filter(lead, "pending"):
        status = "pending"
    elif _lead_matches_status_filter(lead, "waiting"):
        status = "waiting"
    elif _lead_matches_status_filter(lead, "empty"):
        status = "empty"
    elif _lead_matches_status_filter(lead, "archived"):
        status = "archived"

    return SourceRuntimeStatusDTO(
        selector=selector or title,
        title=title or selector,
        chat_type=getattr(lead, "chat_type", "group") or "group",
        is_selected=bool(getattr(lead, "in_source", False)),
        has_jsonl=bool(getattr(lead, "has_jsonl", False)),
        duckdb_rows=rows,
        read_now=bool(getattr(lead, "telegram_active", False)),
        read_stage=getattr(lead, "telegram_active_stage", None),
        live_connected=bool(getattr(lead, "live_connected", False)),
        backfill_running=bool(getattr(lead, "backfill_running", False)),
        setup_running=bool(getattr(lead, "setup_running", False)),
        paused=bool(getattr(lead, "paused", False)),
        cooldown=bool(getattr(lead, "cooldown", False)),
        waiting_schedule=bool(getattr(lead, "waiting_schedule", False)),
        read_done=_safe_int_value(getattr(lead, "read_messages_count", rows)),
        read_total=_safe_int_value(getattr(lead, "total_messages_estimate", rows)),
        remaining=_safe_int_value(getattr(lead, "remaining_messages_estimate", 0)),
        progress_percent=float(getattr(lead, "read_progress_percent", 0.0) or 0.0),
        scan_group=str(getattr(lead, "scan_group", "") or "C"),
        scan_group_label=getattr(lead, "scan_group_label", None),
        limit_months=_safe_int_value(getattr(lead, "import_history_months", 1), 1),
        limit_messages=_safe_int_value(getattr(lead, "import_message_limit", 1000), 1000),
        last_message_at=getattr(lead, "last_date_utc", None),
        last_live_update_at=getattr(lead, "last_live_update_at", None),
        last_worker_heartbeat_at=getattr(lead, "last_sync_at", None),
        status=status,
        status_reason=_runtime_status_reason(lead),
        source_policy_mode=getattr(lead, "source_policy_mode", "unknown") or "unknown",
        source_scan_allowed=bool(getattr(lead, "source_scan_allowed", True)),
    )


async def api_payme_sources_runtime_status(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    query: str = Query(default=""),
    show_channels: bool = Query(default=True),
    show_groups: bool = Query(default=True),
    show_private: bool = Query(default=True),
    scan_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    group_filter: str = Query(default="all"),
    sort_mode: str = Query(default="status"),
):
    async def _factory() -> SourceRuntimeStatusPageDTO:
        leads = await _load_leads_for_source_view(
            query=query,
            show_channels=show_channels,
            show_groups=show_groups,
            show_private=show_private,
            show_bots=False,
            show_archived=False,
            scan_filter=scan_filter,
            status_filter=status_filter,
            group_filter=group_filter,
            sort_mode=sort_mode,
        )
        items = [_source_runtime_status_from_lead(lead) for lead in leads]
        items = sorted(
            items,
            key=lambda item: (
                0 if bool(getattr(item, "read_now", False)) else 1,
                -float(getattr(item, "progress_percent", 0.0) or 0.0),
                -(getattr(item, "duckdb_rows", 0) or 0),
                str(getattr(item, "title", "") or "").lower(),
            ),
        )
        page_payload = _paginate_items(items, page=page, page_size=page_size)
        return SourceRuntimeStatusPageDTO(
            **page_payload,
            summary=_source_stats_summary(leads),
        )

    cache_key = (
        f"sources_runtime_status:{page}:{page_size}:{str(query or '').strip().lower()}:"
        f"{int(bool(show_channels))}:{int(bool(show_groups))}:{int(bool(show_private))}:"
        f"{str(scan_filter or 'all').strip().lower()}:"
        f"{str(status_filter or 'all').strip().lower()}:{str(group_filter or 'all').strip().upper()}:"
        f"{str(sort_mode or 'status')}"
    )
    return await _cached_async_snapshot(cache_key, _factory, ttl_sec=_LEAD_SNAPSHOT_CACHE_TTL_SEC, stale_ttl_sec=120.0)


async def api_payme_all_leads_stream(request: Request, lead: str = Query(default="")):
    generator = await _sse_lead_events(lead_filter=lead)
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

def api_payme_lead_analysis_history(lead: str):
    return ChatAnalysisHistoryDTO(lead=lead, items=_chat_analysis_history_for_lead(lead))

async def api_payme_lead_analysis_run(lead: str, payload: ChatAnalysisPayload):
    try:
        result = await asyncio.to_thread(_run_chat_analysis_sync, lead, payload)
        return ChatAnalysisRunDTO(
            ok=True,
            lead=lead,
            item=result.get("item") or {},
            history=result.get("history") or [],
            message="Анализ готов",
        )
    except HTTPException:
        raise
    except Exception as exc:
        item = {
            "analysis_id": uuid.uuid4().hex,
            "lead": lead,
            "status": "error",
            "provider": payload.provider,
            "model": payload.model,
            "mode": payload.mode,
            "prompt": payload.prompt,
            "message_limit": payload.message_limit,
            "token_budget": payload.token_budget,
            "selected_message_ids": payload.selected_message_ids,
            "messages_count": 0,
            "tokens_estimate": 0,
            "created_at": _utc_now().isoformat(),
            "finished_at": _utc_now().isoformat(),
            "result": "",
            "error": str(exc),
        }
        history = _save_chat_analysis_item(lead, item)
        return ChatAnalysisRunDTO(ok=False, lead=lead, item=item, history=history, message=str(exc))

def api_payme_lead_analysis_stats(lead: str):
    return ChatTokenStatsDTO(**_chat_analysis_stats_payload(lead))

def api_payme_lead_llm(lead: str):
    """
    Возвращает содержимое HTML-файла ассистента: <lead>-llm.html из PAYME_OUT_DIR.
    Нет файла — 204 No Content.
    """
    _ensure_dir_exists()

    stem = _resolve_lead_basename(lead)
    if not stem:
        # нет даже jsonl — расцениваем как отсутствие данных
        return Response(status_code=204)

    html_path = PAYME_OUT_DIR / f"{stem}-llm.html"
    if not html_path.exists():
        html_path = _ensure_llm_html(stem)
    if not html_path or not html_path.exists():
        return Response(status_code=204)

    stat = html_path.stat()
    cache_key = f"llm_html:{stem}:{int(stat.st_mtime_ns)}:{int(stat.st_size)}"
    content = _cached_sync_snapshot(
        cache_key,
        lambda: html_path.read_text(encoding="utf-8", errors="replace"),
        ttl_sec=_LLM_HTML_CACHE_TTL_SEC,
    )
    return HTMLResponse(
        content=content,
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
        },
    )

def api_payme_lead_messages(
    lead: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(0, ge=0, le=200_000),   # <-- 0 разрешён и трактуется как «все»
):
    return _read_messages(lead, offset=offset, limit=limit)


def _resolve_chat_messages_lead(selector: str) -> Optional[str]:
    raw = str(selector or "").strip()
    if not raw:
        return None
    candidates = []
    for value in (
        raw,
        raw.lstrip("@"),
        Path(raw).stem if raw.endswith(".jsonl") else raw,
    ):
        value = str(value or "").strip()
        if value and value not in candidates:
            candidates.append(value)
        try:
            lead_name = _selector_to_lead_name(value)
            if lead_name and lead_name not in candidates:
                candidates.append(lead_name)
        except Exception:
            pass
        try:
            identity = _selector_identity(value)
            if identity and identity not in candidates:
                candidates.append(identity)
        except Exception:
            pass
    try:
        meta = _cached_dialog_meta_catalog()
    except Exception:
        meta = {}
    if isinstance(meta, dict):
        for value in list(candidates):
            row = meta.get(str(value or "").strip().lower())
            if not isinstance(row, dict):
                continue
            for key in ("selector", "username", "title", "name"):
                candidate = str(row.get(key) or "").strip()
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
                try:
                    lead_name = _selector_to_lead_name(candidate)
                    if lead_name and lead_name not in candidates:
                        candidates.append(lead_name)
                except Exception:
                    pass
    for candidate in candidates:
        stem = _resolve_lead_basename(candidate)
        if stem:
            return stem
    return None


def api_payme_chat_messages(
    selector: str,
    before: Optional[int] = None,
    limit: int = 30,
):
    stem = _resolve_chat_messages_lead(selector)
    if not stem:
        raise HTTPException(status_code=404, detail=f"Chat messages for '{selector}' not found")
    if before is None:
        return _read_messages(stem, offset=0, limit=limit)
    all_messages = _read_messages(stem, offset=0, limit=0)
    older = [message for message in all_messages if int(getattr(message, "id", 0) or 0) < int(before)]
    older.sort(key=lambda message: (str(getattr(message, "date_utc", "") or ""), int(getattr(message, "id", 0) or 0)))
    return older[-limit:]


def api_payme_lead_jsonl(lead: str):
    stem = _resolve_lead_basename(lead)
    if not stem:
        raise HTTPException(status_code=404, detail=f"JSONL for '{lead}' not found")
    path = PAYME_OUT_DIR / f"{stem}.jsonl"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"JSONL for '{lead}' not found")
    return FileResponse(
        path,
        media_type="application/x-ndjson",
        filename=path.name,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


async def api_payme_leads_activate(payload: LeadActionPayload):
    normalized_selector = _normalize_source_selector(payload.selector or payload.lead)
    lead_name = _selector_identity(normalized_selector)

    selectors = _source_selectors_as_strings()
    identities = {_selector_identity(item) for item in selectors}
    if lead_name not in identities:
        selectors.append(normalized_selector)
        _write_source_selectors(selectors)

    _remember_selector(normalized_selector)
    telegram_sync.save_state()

    await telegram_sync.start(sync_in_background=True)
    telegram_sync.request_source_reload()

    return LeadActionDTO(
        ok=True,
        message=f"Синхронизация для '{lead_name}' включена",
        lead=lead_name,
        selected=[str(item) for item in _load_source_selectors_for_ui()],
    )

async def api_payme_leads_deactivate(payload: LeadActionPayload):
    lead_name = _selector_to_lead_name(payload.lead)
    normalized_selector = _normalize_source_selector(payload.selector or payload.lead)
    target_identity = _selector_identity(normalized_selector)
    _remember_selector(normalized_selector)

    selectors = _source_selectors_as_strings()
    filtered = [item for item in selectors if _selector_identity(item) != target_identity]
    source_changed = len(filtered) != len(selectors)
    if source_changed:
        _write_source_selectors(filtered)

    import_sync_changed = _remove_import_sync_selector_by_identity(target_identity)

    if source_changed or import_sync_changed:
        telegram_sync.save_state()

    await telegram_sync.start(sync_in_background=True)
    telegram_sync.request_source_reload()

    return LeadActionDTO(
        ok=True,
        message=f"Синхронизация для '{lead_name}' отключена",
        lead=lead_name,
        selected=[str(item) for item in _load_source_selectors_for_ui()],
    )

async def api_payme_leads_delete(payload: LeadActionPayload):
    normalized_selector = _normalize_source_selector(payload.selector or payload.lead)
    lead_name = _selector_identity(normalized_selector)
    target_identity = _selector_identity(normalized_selector)

    selectors = _source_selectors_as_strings()
    filtered = [item for item in selectors if _selector_identity(item) != target_identity]
    if len(filtered) != len(selectors):
        _write_source_selectors(filtered)

    _remove_import_sync_selector_by_identity(target_identity)
    _mark_telegram_dialogs_cache_removed([normalized_selector])
    telegram_sync.save_state()

    await telegram_sync.start(sync_in_background=True)
    telegram_sync.request_source_reload()
    _api_snapshot_cache_clear_prefix("leads:")
    _lead_snapshot_cache["items"] = None

    return LeadActionDTO(
        ok=True,
        message=f"Лид '{lead_name}' удалён из сетки и сканирования, данные в базе сохранены",
        lead=lead_name,
        selected=[str(item) for item in _load_source_selectors_for_ui()],
    )

async def api_payme_leads_group(payload: LeadGroupPayload):
    lead_name = _selector_to_lead_name(payload.lead)
    selector_value = str(payload.selector or payload.lead or "").strip()
    group_id = _normalize_scan_group_id(payload.scan_group)

    settings = _get_app_settings()
    groups = _coerce_telegram_scan_groups(settings.get("telegram_scan_groups"))
    groups_by_id = {
        _normalize_scan_group_id(item.get("id")): item
        for item in groups
        if isinstance(item, dict)
    }
    if group_id not in groups_by_id:
        raise HTTPException(status_code=400, detail="Укажите существующую группу сканирования")

    assignments = _coerce_telegram_scan_group_assignments(
        settings.get("telegram_scan_group_assignments"),
        groups,
    )
    assignment_keys = {
        _normalize_scan_group_assignment_key(lead_name),
        _normalize_scan_group_assignment_key(selector_value),
    }
    if selector_value:
        try:
            assignment_keys.add(_selector_identity(selector_value))
        except Exception:
            pass

    for key in assignment_keys:
        if key:
            assignments[key] = group_id

    settings["telegram_scan_groups"] = groups
    settings["telegram_scan_group_assignments"] = assignments
    _save_app_settings(settings)
    telegram_sync.save_state()
    telegram_sync.request_source_reload()
    try:
        from app.services import jobs as jobs_service

        jobs_service.ensure_telegram_sync_job(reason="lead-group-change")
    except Exception:
        pass
    _api_snapshot_cache_clear_prefix("leads:")
    _api_snapshot_cache_clear_prefix("sources_runtime_status:")
    _api_snapshot_cache_clear_prefix("source_stats:")
    _lead_snapshot_cache["items"] = None

    group_fields = _lead_scan_group_fields(lead_name, selector_value)
    return LeadGroupActionDTO(
        ok=True,
        message=f"Группа для '{lead_name}' изменена на {group_id}",
        lead=lead_name,
        scan_group=group_fields.get("scan_group") or group_id,
        scan_group_label=group_fields.get("scan_group_label"),
        scan_group_frequency=group_fields.get("scan_group_frequency"),
        scan_group_interval_minutes=group_fields.get("scan_group_interval_minutes"),
    )

async def api_payme_list_leads(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    show_channels: bool = Query(default=True),
    show_groups: bool = Query(default=True),
    show_private: bool = Query(default=True),
    show_bots: bool = Query(default=False),
    show_archived: bool = Query(default=False),
    scan_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    group_filter: str = Query(default="all"),
    sort_mode: str = Query(default="recent"),
):
    """
    Список лидов с серверной фильтрацией и пагинацией.
    """
    async def _factory() -> LeadsPageDTO:
        sorted_items = await _load_leads_for_source_view(
            query=query,
            show_channels=show_channels,
            show_groups=show_groups,
            show_private=show_private,
            show_bots=show_bots,
            show_archived=show_archived,
            scan_filter=scan_filter,
            status_filter=status_filter,
            group_filter=group_filter,
            sort_mode=sort_mode,
        )
        return LeadsPageDTO(**_paginate_items(sorted_items, page=page, page_size=page_size))

    cache_key = (
        f"leads:{page}:{page_size}:{str(query or '').strip().lower()}:"
        f"{int(bool(show_channels))}:{int(bool(show_groups))}:{int(bool(show_private))}:"
        f"{int(bool(show_bots))}:{int(bool(show_archived))}:"
        f"{str(scan_filter or 'all').strip().lower()}:"
        f"{str(status_filter or 'all').strip().lower()}:{str(group_filter or 'all').strip().upper()}:"
        f"{str(sort_mode or 'recent')}"
    )
    return await _cached_async_snapshot(cache_key, _factory, ttl_sec=_LEAD_SNAPSHOT_CACHE_TTL_SEC, stale_ttl_sec=300.0)


async def api_payme_source_stats(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    query: str = Query(default=""),
    show_channels: bool = Query(default=True),
    show_groups: bool = Query(default=True),
    show_private: bool = Query(default=True),
    scan_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    group_filter: str = Query(default="all"),
    sort_mode: str = Query(default="status"),
):
    async def _factory() -> SourceStatsPageDTO:
        items = await _load_leads_for_source_view(
            query=query,
            show_channels=show_channels,
            show_groups=show_groups,
            show_private=show_private,
            show_bots=False,
            show_archived=False,
            scan_filter=scan_filter,
            status_filter=status_filter,
            group_filter=group_filter,
            sort_mode=sort_mode,
        )
        page_payload = _paginate_items(items, page=page, page_size=page_size)
        return SourceStatsPageDTO(
            **page_payload,
            summary=_source_stats_summary(items),
        )

    cache_key = (
        f"source_stats:{page}:{page_size}:{str(query or '').strip().lower()}:"
        f"{int(bool(show_channels))}:{int(bool(show_groups))}:{int(bool(show_private))}:"
        f"{str(scan_filter or 'all').strip().lower()}:"
        f"{str(status_filter or 'all').strip().lower()}:{str(group_filter or 'all').strip().upper()}:"
        f"{str(sort_mode or 'status')}"
    )
    return await _cached_async_snapshot(cache_key, _factory, ttl_sec=_LEAD_SNAPSHOT_CACHE_TTL_SEC, stale_ttl_sec=120.0)

async def api_payme_llm_run(payload: LlmRunPayload):
    """
    Заглушка для запуска LLM анализа.
    Параметры: chat_id (name лида), filename (*.jsonl)
    Ожидает 5 сек и возвращает результат.
    """
    print(f"[LLM-RUN] Получены параметры: chat_id={payload.chat_id}, filename={payload.filename}")

    # Заглушка: имитируем длительную обработку
    # await asyncio.sleep(1)

    requested_stem = Path(payload.filename).stem or payload.chat_id
    stem = _resolve_lead_basename(requested_stem) or requested_stem

    try:
        path = send_to_llm_and_store_response(stem, payload.prompt_id)
        print("Ответ сохранён:", path)
        _ensure_llm_html(stem)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM run failed: {exc}")

    print(f"[LLM-RUN] ✓ Обработка завершена для {stem}")
    return {
        "ok": True,
        "message": f"LLM анализ выполнен для {stem}",
        "chat_id": stem,
        "filename": f"{stem}.jsonl",
        "response_path": str(path),
    }

async def api_payme_send(payload: SendPayload):
    """
    Отправляет payload.message в Telegram-чат, заданный в payload.chat_id.
    chat_id может быть:
      - числовым id чата/пользователя
      - @username или username без @
      - t.me/ссылка
    """
    # Лог в консоль — оставляем как просили
    print(f"[SEND] chat_id={payload.chat_id} message={payload.message}")

    # Нормализуем идентификатор: Telethon понимает и username, и numeric id, и t.me ссылки
    chat = (payload.chat_id or "").strip()
    if not chat:
        raise HTTPException(status_code=400, detail="chat_id is empty")
    if not payload.message:
        raise HTTPException(status_code=400, detail="message is empty")

    try:
        await telegram_sync.send_message(chat, payload.message)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Telegram send failed: {e}")

async def api_payme_stream(lead: str, request: Request):
    generator = await _sse_lead_events(lead_filter=lead)
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
