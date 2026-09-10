"""Route-analysis services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

ROUTES_LLM_BATCH_SIZE = _ROUTES_LLM_BATCH_SIZE

def api_payme_routes_addresses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
):
    normalized_query = str(query or "").strip().lower()
    rows = _routes_address_directory()
    if normalized_query:
        rows = [
            row for row in rows
            if normalized_query in " ".join([
                str(row.get("address") or ""),
                " ".join(row.get("leads") or []),
            ]).lower()
        ]
    return _paginate_items(rows, page=page, page_size=page_size)

def api_payme_routes_geocode(payload: RouteGeocodePayload):
    address_key = _route_address_key(payload.address_key)
    if not address_key:
        raise HTTPException(status_code=400, detail="address_key is required")
    rows = _routes_cache_rows()
    changed = 0
    for row in rows:
        if _route_address_key(row.get("address_key") or row.get("address")) != address_key:
            continue
        row["lat"] = float(payload.lat)
        row["lon"] = float(payload.lon)
        changed += 1
    if changed:
        _save_routes_cache_rows(rows)
        state = _analysis_state(_ROUTES_ANALYSIS_KIND)  # type: ignore[arg-type]
        state["gps_points"] = sum(
            1 for item in _routes_address_directory(rows)
            if item.get("lat") is not None and item.get("lon") is not None
        )
        telegram_sync.save_state()
    return {"ok": True, "changed": changed, "status": _routes_status_payload()}

def api_payme_routes_map_points(
    query: str = Query(default=""),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    normalized_query = str(query or "").strip().lower()
    rows = _routes_address_directory()
    if normalized_query:
        rows = [
            row for row in rows
            if normalized_query in " ".join([
                str(row.get("address") or ""),
                " ".join(row.get("leads") or []),
                " ".join(
                    str(example.get("text") or "")
                    for example in (row.get("examples") or [])
                    if isinstance(example, dict)
                ),
            ]).lower()
        ]
    rows = rows[: max(1, int(limit or 1))]
    return {
        "items": rows,
        "total": len(rows),
        "gps_points": sum(1 for row in rows if row.get("lat") is not None and row.get("lon") is not None),
    }

def api_payme_routes_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    only_with_address: bool = Query(default=False),
):
    normalized_query = str(query or "").strip().lower()
    rows = _routes_cache_rows()
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if only_with_address and not row.get("address"):
            continue
        haystack = " ".join(
            [
                str(row.get("lead") or ""),
                str(row.get("source_selector") or ""),
                str(row.get("sender_username") or ""),
                str(row.get("sender_name") or ""),
                str(row.get("address") or ""),
                str(row.get("text") or ""),
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        filtered.append(row)
    return _paginate_items(filtered, page=page, page_size=page_size)

async def api_payme_routes_refresh(
    force_full: bool = Query(default=False),
    confirm_full_refresh: bool = Query(default=False),
    max_llm: int = Query(default=_ROUTES_LLM_BATCH_SIZE, ge=1, le=500),
    model: str = Query(default=""),
):
    _require_confirmed_full_refresh(force_full, confirm_full_refresh, "Маршруты")
    model_override = _normalize_openrouter_model_id(model) if str(model or "").strip() else None
    started = _schedule_routes_refresh(force_full=force_full, max_llm=max_llm, model_override=model_override)
    return {
        "ok": True,
        "message": "Анализ маршрутов запущен" if started else "Анализ маршрутов уже выполняется",
        "status": _routes_status_payload(),
    }

def api_payme_routes_status():
    return _routes_status_payload()
