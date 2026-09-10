"""Telegram source and channel services extracted from the legacy backend route handlers."""

from __future__ import annotations

import asyncio
import os

from app.repositories import legacy
from app.schemas.jobs import JobProgressDTO

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

async def _delayed_telegram_sync_start(delay_sec: float = 5.0) -> None:
    await asyncio.sleep(max(0.0, float(delay_sec or 0.0)))
    await telegram_sync.start(sync_in_background=True)


def _schedule_telegram_sync_start() -> None:
    if str(os.environ.get("XFILES_WEB_TELEGRAM_SYNC_START", "0")).strip() != "1":
        return
    try:
        asyncio.get_running_loop().create_task(_delayed_telegram_sync_start())
    except RuntimeError:
        pass


def _ensure_telegram_sync_worker_job(reason: str = "source-change"):
    """Start/keep Telegram live-sync in the telegram Celery worker."""
    try:
        from app.services import jobs as jobs_service

        return jobs_service.ensure_telegram_sync_job(reason=reason)
    except Exception as exc:
        try:
            _append_runtime_log("telegram-sync", f"Не удалось поставить Telegram sync в worker: {exc}")
        except Exception:
            pass
        return None


def _invalidate_source_dependent_caches() -> None:
    """Refresh lead/grid snapshots immediately after selected source changes."""
    try:
        _api_snapshot_cache_clear_prefix("leads:")
        _api_snapshot_cache_clear_prefix("dashboard_summary:")
    except Exception:
        pass
    try:
        _lead_snapshot_cache["items"] = None
        _lead_snapshot_cache["updated_at"] = 0.0
    except Exception:
        pass

async def api_payme_import_sync_disable():
    config = telegram_sync.get_import_sync_state()
    now_iso = _utc_now().isoformat()
    config["enabled"] = False
    config["selectors"] = []
    config["updated_at"] = now_iso
    telegram_sync.save_state()

    _schedule_telegram_sync_start()
    telegram_sync.request_source_reload()

    return ImportSyncActionDTO(
        ok=True,
        message="Синхронизация всех данных из Import выключена",
        status=_compute_import_sync_status(),
    )

async def api_payme_import_sync_enable():
    dialogs = await _get_telegram_dialogs_for_api(force_refresh=False)
    selectors = [dialog.selector for dialog in dialogs]
    if not selectors:
        selectors = _source_selectors_as_strings()

    config = telegram_sync.get_import_sync_state()
    now_iso = _utc_now().isoformat()
    config["enabled"] = True
    config["selectors"] = selectors
    config["started_at"] = now_iso
    config["updated_at"] = now_iso
    telegram_sync.save_state()

    _schedule_telegram_sync_start()
    telegram_sync.request_source_reload()
    _ensure_telegram_sync_worker_job(reason="import-sync-enable")

    return ImportSyncActionDTO(
        ok=True,
        message=f"Включена синхронизация всех данных из Import: {len(selectors)} диалогов",
        status=_compute_import_sync_status(),
    )

def api_payme_import_sync_status():
    return _cached_sync_snapshot("import_sync_status", _compute_import_sync_status)

async def api_payme_source_add(payload: SourceSelectorPayload):
    try:
        normalized = _normalize_source_selector(payload.selector)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Введите username канала, @username или numeric id") from exc

    selectors = _source_selectors_as_strings()
    identities = {_selector_identity(item) for item in selectors}
    target_identity = _selector_identity(normalized)

    if target_identity not in identities:
        source_limit = _xfiles_telegram_source_limit()
        if source_limit is not None and _xfiles_current_telegram_source_count(selectors) >= source_limit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Лимит тарифа на Telegram-источники исчерпан: "
                    f"{source_limit} из {source_limit}. Повысите тариф или удалите источник из сканирования."
                ),
            )
        selectors.append(normalized)
        _write_source_selectors(selectors)
        _invalidate_source_dependent_caches()
    _remember_selector(normalized)
    telegram_sync.save_state()

    _schedule_telegram_sync_start()
    telegram_sync.request_source_reload()
    _ensure_telegram_sync_worker_job(reason="source-add")
    selected = [str(item) for item in _load_source_selectors_for_ui()]
    return SourceEditDTO(
        ok=True,
        message=f"Канал '{normalized}' добавлен",
        source_path="state:_source_selectors",
        selected=selected,
    )

def api_payme_source_policies():
    items = _source_policy_all()
    return SourcePolicyPageDTO(items=items, total=len(items))

async def api_payme_source_policy(payload: SourcePolicyPayload):
    lead_name = _selector_to_lead_name(payload.lead)
    selector_value = str(payload.selector or payload.lead or "").strip() or None
    item = _set_source_policy(
        lead_name,
        selector_value,
        payload.mode,
        payload.reason,
        source="manual",
    )
    if not item.scan_allowed:
        telegram_sync._enabled_chat_keys.discard(item.lead)
    telegram_sync.request_source_reload()
    message = "Источник заблокирован для Telegram-сканирования" if not item.scan_allowed else "Политика источника сохранена"
    return SourcePolicyActionDTO(ok=True, message=message, item=item)

async def api_payme_source_reload():
    telegram_sync.request_source_reload()
    job = _ensure_telegram_sync_worker_job(reason="source-reload")
    return {
        "ok": True,
        "source_path": "state:_source_selectors",
        "selected": [str(item) for item in _load_source_selectors_for_ui()],
        "job": job.model_dump() if hasattr(job, "model_dump") else job,
    }

async def api_payme_source_remove(payload: SourceSelectorPayload):
    try:
        normalized = _normalize_source_selector(payload.selector)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Укажите канал для удаления") from exc

    target_identity = _selector_identity(normalized)
    selectors = _source_selectors_as_strings()
    filtered = [item for item in selectors if _selector_identity(item) != target_identity]

    if len(filtered) != len(selectors):
        _write_source_selectors(filtered)
        _invalidate_source_dependent_caches()
        _mark_telegram_dialogs_cache_removed([normalized])
        purge = await asyncio.to_thread(_purge_removed_source_data, normalized)
    else:
        purge = None
    _remember_selector(normalized)
    telegram_sync.save_state()

    _schedule_telegram_sync_start()
    telegram_sync.request_source_reload()
    _ensure_telegram_sync_worker_job(reason="source-remove")
    selected = [str(item) for item in _load_source_selectors_for_ui()]
    purge_count = int((purge or {}).get("total_removed") or 0)
    return SourceEditDTO(
        ok=True,
        message=(
            f"Канал '{normalized}' удалён"
            + (f"; очищено связанных записей: {purge_count}" if purge is not None else "")
        ),
        source_path="state:_source_selectors",
        selected=selected,
        purge=purge,
    )

async def api_payme_telegram_dialogs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    show_channels: bool = Query(default=True),
    show_groups: bool = Query(default=True),
    show_private: bool = Query(default=True),
    show_bots: bool = Query(default=False),
    show_archived: bool = Query(default=False),
    membership_filter: str = Query(default="all"),
    sort_by: str = Query(default="last_date_desc"),
    force_refresh: bool = Query(default=False),
):
    membership_value = str(membership_filter or "all")
    dialogs = _merge_added_source_selectors_into_dialogs(
        await _get_telegram_dialogs_for_api(force_refresh=bool(force_refresh)),
        include_missing_added=membership_value == "added",
    )
    query_value = str(query or "").strip().lower()
    filtered = [
        dialog
        for dialog in dialogs
        if _dialog_matches_filters(
            dialog,
            query=query_value,
            show_channels=show_channels,
            show_groups=show_groups,
            show_private=show_private,
            show_bots=show_bots,
            show_archived=show_archived,
            membership_filter=membership_value,
        )
    ]

    reverse = str(sort_by or "last_date_desc") != "last_date_asc"
    filtered.sort(
        key=lambda item: (
            item.last_date_utc or "",
            str(item.title or "").lower(),
        ),
        reverse=reverse,
    )
    return TelegramDialogsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

async def api_payme_telegram_dialogs_import(payload: TelegramDialogsImportPayload):
    raw_selectors = payload.selectors or []
    if not raw_selectors:
        raise HTTPException(status_code=400, detail="Не переданы диалоги для импорта")

    selectors = _source_selectors_as_strings()
    identities = {_selector_identity(item) for item in selectors}
    added_selectors: List[str] = []
    source_limit = _xfiles_telegram_source_limit()
    skipped_by_limit = 0

    for raw_selector in raw_selectors:
        try:
            normalized = _normalize_source_selector(raw_selector)
        except ValueError:
            continue

        identity = _selector_identity(normalized)
        if identity in identities:
            continue

        if source_limit is not None and _xfiles_current_telegram_source_count(selectors) >= source_limit:
            skipped_by_limit += 1
            continue

        selectors.append(normalized)
        identities.add(identity)
        added_selectors.append(normalized)
        _remember_selector(normalized)

    if added_selectors:
        _write_source_selectors(selectors)
        _invalidate_source_dependent_caches()
        _mark_telegram_dialogs_cache_added(added_selectors)
        telegram_sync.save_state()

    _schedule_telegram_sync_start()
    telegram_sync.request_source_reload()
    _ensure_telegram_sync_worker_job(reason="dialogs-import")

    selected = [str(item) for item in _load_source_selectors_for_ui()]
    message = f"Добавлено диалогов: {len(added_selectors)}"
    if skipped_by_limit:
        message += f"; пропущено из-за лимита тарифа: {skipped_by_limit}"
    return TelegramDialogsImportDTO(
        ok=True,
        message=message,
        source_path="state:_source_selectors",
        selected=selected,
        added_count=len(added_selectors),
        added_selectors=added_selectors,
    )

async def api_payme_telegram_dialogs_remove_added(payload: TelegramDialogsRemoveAddedPayload):
    raw_selectors = payload.selectors or []
    if not raw_selectors:
        raise HTTPException(status_code=400, detail="Не переданы диалоги для снятия со сканирования")

    normalized_selectors: List[str] = []
    target_identities: set[str] = set()
    for raw_selector in raw_selectors:
        try:
            normalized = _normalize_source_selector(raw_selector)
        except ValueError:
            continue
        identity = _selector_identity(normalized)
        if not identity or identity in target_identities:
            continue
        normalized_selectors.append(normalized)
        target_identities.add(identity)
        _remember_selector(normalized)

    if not target_identities:
        raise HTTPException(status_code=400, detail="Не удалось распознать selectors для снятия со сканирования")

    selectors = _source_selectors_as_strings()
    filtered: List[str] = []
    removed_selectors: List[str] = []
    for selector in selectors:
        identity = _selector_identity(selector)
        if identity in target_identities:
            removed_selectors.append(selector)
            continue
        filtered.append(selector)

    source_changed = len(filtered) != len(selectors)
    if source_changed:
        _write_source_selectors(filtered)
        _invalidate_source_dependent_caches()

    import_sync_changed = False
    removed_identity_set = {_selector_identity(selector) for selector in removed_selectors}
    for identity in target_identities:
        if _remove_import_sync_selector_by_identity(identity):
            import_sync_changed = True
            removed_identity_set.add(identity)

    if source_changed or import_sync_changed:
        _mark_telegram_dialogs_cache_removed(normalized_selectors)
        telegram_sync.save_state()
        telegram_sync.request_source_reload()
        _schedule_telegram_sync_start()
        _ensure_telegram_sync_worker_job(reason="dialogs-remove-added")

    selected = [str(item) for item in _load_source_selectors_for_ui()]
    removed_count = len(removed_identity_set)
    if removed_count and not removed_selectors:
        removed_selectors = [
            selector
            for selector in normalized_selectors
            if _selector_identity(selector) in removed_identity_set
        ]
    return TelegramDialogsRemoveAddedDTO(
        ok=True,
        message=(
            f"Снято со сканирования: {removed_count}. "
            "История в JSONL/DuckDB не удалялась."
        ),
        source_path="state:_source_selectors",
        selected=selected,
        removed_count=removed_count,
        removed_selectors=removed_selectors,
    )

async def api_payme_telegram_dialogs_settings(payload: TelegramDialogSettingsPayload):
    selector = _normalize_source_selector(payload.selector)
    limits = _set_import_limits_for_selector(
        selector,
        import_history_months=payload.import_history_months,
        import_message_limit=payload.import_message_limit,
    )
    _api_snapshot_cache_clear_prefix("leads:")
    _lead_snapshot_cache["items"] = None
    telegram_sync.request_source_reload()
    _schedule_telegram_sync_start()
    _ensure_telegram_sync_worker_job(reason="dialog-import-settings")
    return TelegramDialogSettingsDTO(
        ok=True,
        message=(
            "Лимиты импорта сохранены: "
            f"{limits['import_history_months']} мес., {limits['import_message_limit']} сообщений"
        ),
        selector=selector,
        import_history_months=limits["import_history_months"],
        import_message_limit=limits["import_message_limit"],
        import_max_history_months=limits["import_max_history_months"],
        import_max_message_limit=limits["import_max_message_limit"],
    )

def api_payme_telegram_sync_control():
    return telegram_sync.get_sync_control_status()

async def api_payme_telegram_sync_pause(reason: str = Query(default="manual dashboard")):
    status = telegram_sync.set_sync_paused(True, reason=reason)
    telegram_sync.request_source_reload()
    try:
        await telegram_sync.stop()
    except Exception as exc:
        try:
            _append_runtime_log("telegram-sync", f"Не удалось полностью остановить Telegram sync при паузе: {exc}")
        except Exception:
            pass
    _api_snapshot_cache_clear_prefix("dashboard_summary:")
    return {"ok": True, "status": status}

async def api_payme_telegram_sync_resume(reason: str = Query(default="manual dashboard")):
    status = telegram_sync.set_sync_paused(False, reason=reason)
    telegram_sync.request_source_reload()
    _api_snapshot_cache_clear_prefix("dashboard_summary:")
    _ensure_telegram_sync_worker_job(reason="resume")
    return {"ok": True, "status": status}


def api_payme_telegram_sync_job_status():
    try:
        from app.services import jobs as jobs_service

        job = jobs_service.latest_job_by_type("telegram_sync")
        if job is not None:
            return job
    except Exception as exc:
        return JobProgressDTO(
            job_id="telegram_sync",
            type="telegram_sync",
            queue_name="telegram.sync",
            status="error",
            progress_percent=0,
            progress_label="Не удалось прочитать статус Telegram sync job",
            error=str(exc),
        )
    return JobProgressDTO(
        job_id="telegram_sync",
        type="telegram_sync",
        queue_name="telegram.sync",
        status="idle",
        progress_percent=0,
        progress_label="Telegram live-sync job еще не запускался",
    )


def api_payme_telegram_sync_run(reason: str = Query(default="manual")):
    telegram_sync.request_source_reload()
    try:
        _api_snapshot_cache_clear_prefix("dashboard_summary:")
    except Exception:
        pass
    job = _ensure_telegram_sync_worker_job(reason=reason)
    if job is None:
        raise HTTPException(status_code=503, detail="Telegram sync worker queue недоступен")
    return job
