"""CRM services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)


def _refresh_legacy_globals() -> None:
    legacy.refresh_globals(globals(), exclude={"_refresh_legacy_globals"})


async def api_payme_crm_cleanup_telemost_phones():
    _refresh_legacy_globals()
    return await asyncio.to_thread(_cleanup_crm_telemost_false_phones_sync)

def api_payme_crm_config(payload: AnalysisConfigPayload):
    _refresh_legacy_globals()
    state = _analysis_state("crm")
    state["enabled"] = bool(payload.enabled)
    state["interval_sec"] = int(payload.interval_sec)
    state["next_refresh_at"] = _analysis_next_refresh_at("crm")
    telegram_sync.save_state()
    return AnalysisActionDTO(
        ok=True,
        message="Настройки автообновления CRM сохранены",
        status=_build_analysis_status("crm"),
    )

def api_payme_crm_contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=1000, ge=1, le=5000),
    lead: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    only_name: bool = Query(default=False),
    only_phone: bool = Query(default=False),
    only_email: bool = Query(default=False),
    only_company: bool = Query(default=False),
    only_city: bool = Query(default=False),
    only_title: bool = Query(default=False),
):
    _refresh_legacy_globals()
    source_rows: List[Dict[str, Any]]
    crm_state = _analysis_state("crm")
    if bool(crm_state.get("running")) and _analysis_cache_path("crm").exists():
        source_rows = _load_analysis_cache_rows_limited("crm", max(1, int(limit or 1)))
    elif _duckdb_crm_ready():
        source_rows = _duckdb_load_crm_rows(limit=max(1, limit))
    else:
        source_rows = _analysis_rows("crm", limit=max(1, limit))
    items = [CrmContactDTO(**_crm_sanitize_contact_payload(row)) for row in source_rows]
    filtered = _filter_crm_contacts(
        items,
        query=str(query or "").strip().lower(),
        lead_filter=str(lead or "").strip().lower(),
        only_name=only_name,
        only_phone=only_phone,
        only_email=only_email,
        only_company=only_company,
        only_city=only_city,
        only_title=only_title,
    )
    return CrmContactsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

async def api_payme_crm_refresh():
    _refresh_legacy_globals()
    started = _schedule_analysis_refresh("crm")
    return AnalysisActionDTO(
        ok=True,
        message="Обновление кеша CRM запущено" if started else "Обновление CRM уже выполняется",
        status=_build_analysis_status("crm"),
    )

def api_payme_crm_status():
    _refresh_legacy_globals()
    return _cached_sync_snapshot("crm_status", lambda: _build_analysis_status("crm"))
