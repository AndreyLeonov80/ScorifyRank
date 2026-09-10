"""Runtime monitoring services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

async def _dashboard_summary_payload_threaded(limit: int):
    return await asyncio.to_thread(lambda: asyncio.run(_dashboard_summary_payload(limit=limit)))

async def api_payme_dashboard_summary(
    limit: int = Query(default=10, ge=1, le=50),
):
    return await _cached_async_snapshot(
        f"dashboard_summary:{max(1, min(int(limit or 10), 50))}",
        lambda: _dashboard_summary_payload_threaded(limit=limit),
        ttl_sec=min(float(_DASHBOARD_SUMMARY_CACHE_TTL_SEC), 3.0),
        stale_ttl_sec=30.0,
    )


def _safe_lite_call(fn_name: str, default):
    try:
        fn = globals().get(fn_name)
        if not callable(fn):
            return default
        return fn()
    except Exception:
        return default


def _safe_lite_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _safe_lite_attr(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _dashboard_summary_lite_payload_sync() -> dict:
    now_fn = globals().get("_utc_now")
    now = now_fn() if callable(now_fn) else None
    duckdb_status = dict(_safe_lite_call("_build_duckdb_status", {}) or {})
    contacts_status = _safe_lite_call("_build_analysis_status", None)
    try:
        contacts_status = _build_analysis_status("contacts")
    except Exception:
        contacts_status = None
    try:
        deals_status = _cached_sync_snapshot_fast(
            "xfiles_deals_status",
            _xfiles_deals_status_sync,
            ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
        )
    except Exception:
        deals_status = None
    try:
        import_sync_status = _compute_import_sync_status()
        import_sync_payload = import_sync_status.model_dump()
    except Exception:
        import_sync_payload = {}
    try:
        source_selectors = list(_source_selectors_as_strings())
    except Exception:
        source_selectors = []
    try:
        telegram_job = None
        from app.services import jobs as jobs_service

        job = jobs_service.latest_active_job_by_type("telegram_sync") or jobs_service.latest_job_by_type("telegram_sync")
        if job is not None:
            raw = job.model_dump() if hasattr(job, "model_dump") else dict(job)
            result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
            telegram_job = {
                "job_id": raw.get("job_id"),
                "status": raw.get("status"),
                "progress_percent": raw.get("progress_percent"),
                "progress_label": raw.get("progress_label"),
                "chunks_done": raw.get("chunks_done"),
                "chunks_total": raw.get("chunks_total"),
                "updated_at": raw.get("updated_at"),
                "active_sources_count": result.get("active_sources_count"),
                "enabled_sources_count": result.get("enabled_sources_count"),
                "selected_sources_count": result.get("selected_sources_count"),
            }
    except Exception:
        telegram_job = None
    try:
        sync_control = telegram_sync.get_sync_control_status()
    except Exception:
        sync_control = {}
    try:
        lead_items = list(_lead_snapshot_cache.get("items") or [])
    except Exception:
        lead_items = []
    try:
        dialog_items = list(_telegram_dialogs_cache.get("items") or [])
    except Exception:
        dialog_items = []

    selected_count = len({str(item or "").strip().lower() for item in source_selectors if str(item or "").strip()})
    imported_count = sum(1 for item in lead_items if bool(_safe_lite_attr(item, "has_jsonl", False)))
    files_with_rows = sum(
        1
        for item in lead_items
        if bool(_safe_lite_attr(item, "has_jsonl", False)) and _safe_lite_int(_safe_lite_attr(item, "count", 0)) > 0
    )
    messages_count = _safe_lite_int(duckdb_status.get("message_rows"))
    if messages_count <= 0:
        messages_count = sum(_safe_lite_int(_safe_lite_attr(item, "count", 0)) for item in lead_items)
    try:
        jsonl_bytes = _sum_glob_file_sizes(PAYME_OUT_DIR, "*.jsonl")
    except Exception:
        jsonl_bytes = 0
    try:
        duckdb_bytes = _safe_file_size(DUCKDB_PATH)
    except Exception:
        duckdb_bytes = 0

    return {
        "ts": now.isoformat() if now is not None else None,
        "mode": "lite",
        "counts": {
            "leads": _safe_lite_int(
                duckdb_status.get("source_files_indexed")
                or duckdb_status.get("tracked_files")
                or duckdb_status.get("source_files_total")
                or len(lead_items)
            ),
            "dialogs": len(dialog_items),
            "contacts": _safe_lite_int(_safe_lite_attr(contacts_status, "total_rows", 0)),
            "deals": _safe_lite_int(_safe_lite_attr(deals_status, "total", 0)),
            "selected_sources": selected_count,
            "imported_sources": imported_count,
            "messages": messages_count,
        },
        "storage": {
            "jsonl_bytes": _safe_lite_int(jsonl_bytes),
            "duckdb_bytes": _safe_lite_int(duckdb_bytes),
            "duckdb_path": str(globals().get("DUCKDB_PATH") or duckdb_status.get("db_path") or ""),
            "duckdb_read_snapshot_path": str(
                globals().get("DUCKDB_READ_PATH")
                or duckdb_status.get("read_snapshot_path")
                or ""
            ),
        },
        "telegram": {
            "sync_control": sync_control,
            "selected_sources": selected_count,
            "job": telegram_job,
        },
        "duckdb_sync": {
            "available": bool(duckdb_status.get("available", True)),
            "enabled": bool(duckdb_status.get("enabled", True)),
            "running": bool(duckdb_status.get("running", False)),
            "cache_ready": bool(duckdb_status.get("cache_ready", False)),
            "message_rows": messages_count,
            "source_files_total": _safe_lite_int(duckdb_status.get("source_files_total")),
            "source_files_indexed": _safe_lite_int(duckdb_status.get("source_files_indexed")),
            "files_on_disk": _safe_lite_int(duckdb_status.get("files_on_disk") or duckdb_status.get("source_files_total")),
            "files_selected": selected_count,
            "files_indexed": _safe_lite_int(duckdb_status.get("files_indexed") or duckdb_status.get("source_files_indexed")),
            "files_with_rows": files_with_rows or _safe_lite_int(duckdb_status.get("files_with_rows")),
            "progress_percent": float(duckdb_status.get("progress_percent") or 0.0),
            "progress_label": duckdb_status.get("progress_label"),
            "last_refresh_at": duckdb_status.get("last_refresh_at"),
            "last_error": duckdb_status.get("last_error"),
            "db_path": str(globals().get("DUCKDB_PATH") or duckdb_status.get("db_path") or ""),
            "read_snapshot_path": str(
                globals().get("DUCKDB_READ_PATH")
                or duckdb_status.get("read_snapshot_path")
                or ""
            ),
        },
        "import_sync": import_sync_payload,
        "scanned_sources": {
            "totals": {
                "selected_sources": selected_count,
                "imported_sources": imported_count,
                "messages_count": messages_count,
            },
            "message": f"Выбрано источников: {selected_count}; кешей: {imported_count}; сообщений: {messages_count}",
        },
    }


async def _dashboard_summary_lite_payload_threaded():
    return await asyncio.to_thread(_dashboard_summary_lite_payload_sync)


async def api_payme_dashboard_summary_lite():
    return await _cached_async_snapshot(
        "dashboard_summary_lite",
        _dashboard_summary_lite_payload_threaded,
        ttl_sec=3.0,
        stale_ttl_sec=30.0,
    )


async def api_payme_dashboard_details(limit: int = Query(default=10, ge=1, le=50)):
    payload = await api_payme_dashboard_summary(limit=limit)
    if isinstance(payload, dict):
        return {key: value for key, value in payload.items() if key not in {"logs", "previews"}}
    return payload


async def api_payme_dashboard_logs(
    minutes: int = Query(default=10, ge=1, le=60),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    return {
        "ok": True,
        "items": api_payme_runtime_logs(minutes=minutes, after_id=after_id, limit=limit),
    }


async def api_payme_dashboard_previews(limit: int = Query(default=10, ge=1, le=50)):
    payload = await api_payme_dashboard_summary(limit=limit)
    previews = {}
    if isinstance(payload, dict):
        for key in ("previews", "recent", "runtime", "jobs"):
            if key in payload:
                previews[key] = payload[key]
    return {"ok": True, "previews": previews}


async def api_payme_duckdb_archive_legacy_cache():
    result = await asyncio.to_thread(_archive_legacy_cache_files_sync)
    archived_files = list(result.get("archived_files") or [])
    skipped_files = list(result.get("skipped_files") or [])
    return DuckDbLegacyCacheCleanupDTO(
        ok=True,
        message=f"Архивировано legacy cache-файлов: {len(archived_files)}",
        archive_dir=str(result.get("archive_dir") or ""),
        archived_files=archived_files,
        skipped_files=skipped_files,
        status=_build_duckdb_status(),
    )

async def api_payme_duckdb_export_parquet():
    if duckdb is None:
        raise HTTPException(status_code=503, detail="DuckDB dependency is not installed")
    exported_files = await asyncio.to_thread(_duckdb_export_parquet_sync)
    return DuckDbExportDTO(
        ok=True,
        message=f"Экспортировано parquet-файлов: {len(exported_files)}",
        parquet_dir=str(PARQUET_DIR),
        exported_files=exported_files,
        status=_build_duckdb_status(),
    )

async def api_payme_duckdb_materialize_parquet_sidecars(force: bool = Query(default=False)):
    if duckdb is None:
        raise HTTPException(status_code=503, detail="DuckDB dependency is not installed")
    result = await asyncio.to_thread(_duckdb_materialize_parquet_sidecars_sync, force)
    return DuckDbParquetSidecarsDTO(
        ok=True,
        message=f"Parquet sidecars: created {len(result.get('created_files') or [])}, reused {len(result.get('reused_files') or [])}",
        parquet_dir=str(result.get("parquet_dir") or ""),
        created_files=list(result.get("created_files") or []),
        reused_files=list(result.get("reused_files") or []),
        skipped_files=list(result.get("skipped_files") or []),
        parquet_files_total=int(result.get("parquet_files_total") or 0),
        parquet_bytes_total=int(result.get("parquet_bytes_total") or 0),
        selected_bytes_total=int(result.get("selected_bytes_total") or 0),
        status=_build_duckdb_status(),
    )

async def api_payme_duckdb_refresh(
    force_full: bool = Query(default=False),
    confirm_full_refresh: bool = Query(default=False),
):
    _require_confirmed_full_refresh(force_full, confirm_full_refresh, "DuckDB")
    if duckdb is None:
        raise HTTPException(status_code=503, detail="DuckDB dependency is not installed")
    scheduled = _schedule_duckdb_sync(force_full=force_full)
    if scheduled:
        message = "Обновление DuckDB запущено"
    else:
        message = "Обновление DuckDB уже выполняется"
    return DuckDbActionDTO(ok=True, message=message, status=_build_duckdb_status())

def api_payme_duckdb_status():
    return _cached_sync_snapshot("duckdb_status", _build_duckdb_status)

def api_payme_duckdb_lock_status():
    status = _build_duckdb_status()
    payload = status.model_dump() if hasattr(status, "model_dump") else dict(status)
    return {
        "ok": True,
        "lock_status": payload.get("lock_status") or {},
        "db_path": payload.get("db_path"),
        "read_snapshot_path": payload.get("read_snapshot_path"),
        "read_snapshot_exists": bool(payload.get("read_snapshot_exists")),
        "read_snapshot_mtime": payload.get("read_snapshot_mtime"),
        "running": bool(payload.get("running")),
        "progress_label": payload.get("progress_label"),
    }

async def api_payme_monitor_stream(
    request: Request,
    history_points: int = Query(default=60, ge=1, le=720),
):
    async def event_iter():
        heartbeat_every = 15
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await _monitor_snapshot_payload(history_points=history_points)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc), 'ts': _utc_now().isoformat()}, ensure_ascii=False)}\n\n"
            idle_ticks += 1
            if idle_ticks >= heartbeat_every:
                idle_ticks = 0
                yield ": monitor-ping\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

async def api_payme_realtime_stream(
    request: Request,
    types: str = Query(default="runtime_log,monitor,lead"),
    lead: str = Query(default=""),
    minutes: int = Query(default=10, ge=1, le=60),
    history_points: int = Query(default=60, ge=1, le=720),
    dashboard_limit: int = Query(default=10, ge=1, le=50),
):
    requested_types = {
        item.strip().lower()
        for item in str(types or "").split(",")
        if item.strip()
    }
    if not requested_types:
        requested_types = {"runtime_log", "monitor", "lead"}

    include_logs = bool({"runtime_log", "log", "logs"} & requested_types)
    include_monitor = bool({"monitor", "monitor_snapshot", "metrics", "status"} & requested_types)
    include_leads = bool({"lead", "lead_event", "leads"} & requested_types)
    include_dashboard = bool({"dashboard", "dashboard_summary"} & requested_types)
    lead_filter = str(lead or "").strip().lower()

    async def event_iter():
        queue: Optional[asyncio.Queue] = None
        last_ping = asyncio.get_event_loop().time()
        last_log_id = 0
        last_monitor_emit = 0.0
        last_dashboard_emit = 0.0
        heartbeat_sec = 15.0
        poll_sleep_sec = 0.5

        if include_leads:
            queue = asyncio.Queue()
            _lead_event_subscribers.add(queue)

        try:
            while True:
                if await request.is_disconnected():
                    break

                emitted = False
                now = asyncio.get_event_loop().time()

                if include_logs:
                    batch = _read_runtime_logs(minutes=minutes, after_id=last_log_id)
                    for item in batch:
                        last_log_id = max(last_log_id, int(item.get("id", 0)))
                        yield _typed_stream_packet("runtime_log", item)
                        emitted = True

                if include_monitor and (now - last_monitor_emit >= 5.0):
                    try:
                        snapshot = await _monitor_snapshot_payload(history_points=history_points)
                        yield _typed_stream_packet("monitor_snapshot", snapshot)
                        emitted = True
                    except Exception as exc:
                        yield _typed_stream_packet("stream_error", {"scope": "monitor", "error": str(exc)})
                        emitted = True
                    last_monitor_emit = now

                if include_dashboard and (now - last_dashboard_emit >= 5.0):
                    try:
                        dashboard_snapshot = await _dashboard_summary_payload_threaded(limit=dashboard_limit)
                        yield _typed_stream_packet("dashboard_summary", dashboard_snapshot)
                        emitted = True
                    except Exception as exc:
                        yield _typed_stream_packet("stream_error", {"scope": "dashboard", "error": str(exc)})
                        emitted = True
                    last_dashboard_emit = now

                if include_leads and queue is not None:
                    while True:
                        try:
                            event = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        event_lead = str(event.get("lead") or "").strip().lower()
                        if lead_filter and event_lead != lead_filter:
                            continue
                        yield _typed_stream_packet("lead_event", event)
                        emitted = True

                if emitted:
                    last_ping = asyncio.get_event_loop().time()
                elif (asyncio.get_event_loop().time() - last_ping) >= heartbeat_sec:
                    last_ping = asyncio.get_event_loop().time()
                    yield b": ping\n\n"

                await asyncio.sleep(poll_sleep_sec)
        finally:
            if queue is not None:
                _lead_event_subscribers.discard(queue)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

def api_payme_runtime_logs(
    minutes: int = Query(default=10, ge=1, le=60),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=200),
    channel: str = Query(default=""),
):
    cache_key = f"runtime_logs:{minutes}:{after_id}:{limit}:{str(channel or '').strip().lower()}"
    return _cached_sync_snapshot(
        cache_key,
        lambda: _read_runtime_logs(minutes=minutes, after_id=after_id, limit=limit, channel=channel),
    )

async def api_payme_runtime_logs_stream(
    request: Request,
    minutes: int = Query(default=10, ge=1, le=60),
    channel: str = Query(default=""),
):
    async def event_iter():
        last_id = 0
        heartbeat_every = 10
        idle_ticks = 0
        while True:
            if await request.is_disconnected():
                break
            batch = _read_runtime_logs(minutes=minutes, after_id=last_id, channel=channel)
            if batch:
                idle_ticks = 0
                for item in batch:
                    last_id = max(last_id, int(item.get("id", 0)))
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks >= heartbeat_every:
                    idle_ticks = 0
                    yield ": ping\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

async def api_payme_runtime_status():
    return await _cached_async_snapshot("runtime_status", _runtime_status, stale_ttl_sec=120.0)

def api_payme_server_status():
    return _cached_sync_snapshot("server_status", lambda: ServerRuntimeDTO(**_server_runtime_snapshot()))

def api_payme_system_metrics(
    history_points: int = Query(default=60, ge=1, le=720),
):
    return _cached_sync_snapshot(
        f"system_metrics:{history_points}",
        lambda: SystemMetricsDTO(**_system_metrics_payload(history_points=history_points)),
    )
