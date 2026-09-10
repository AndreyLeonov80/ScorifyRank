"""X-Files deals/needs routes extracted from the monolith."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
legacy.refresh_globals(globals(), setdefault=True)

from app.services.xfiles_contracts import (
    _xfiles_contract_metrics_sync,
    _xfiles_contract_templates,
    _xfiles_contract_templates_page_sync,
    _xfiles_deal_contract_kit_sync,
    _xfiles_deal_negotiation_brief_sync,
)
from app.services.xfiles_deals_engine import (
    _xfiles_contact_recommendation,
    _xfiles_contact_signal_profile,
    _xfiles_daily_contacts_sync,
    _xfiles_deal_assistant_sync,
    _xfiles_deal_opportunities_sync,
    _xfiles_deals_status_sync,
    _xfiles_event_sales_plan_sync,
    _xfiles_function_impacts,
    _xfiles_need_signal_from_parts,
    _xfiles_need_signals_page_sync,
    _xfiles_template_model_benchmarks,
)

def api_payme_deals_status():
    return _cached_sync_snapshot_fast(
        "xfiles_deals_status",
        _xfiles_deals_status_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_reminders(
    limit: int = Query(default=50, ge=1, le=200),
    include_done: bool = Query(default=False),
):
    normalized_limit = max(1, int(limit or 1))
    return _cached_sync_snapshot_fast(
        f"xfiles_deal_reminders:{normalized_limit}:{bool(include_done)}",
        lambda: _xfiles_deal_reminders_sync(limit=normalized_limit, include_done=include_done),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_conversion():
    return _cached_sync_snapshot_fast(
        "xfiles_deal_conversion",
        _xfiles_deal_conversion_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_profit_optimization():
    return _cached_sync_snapshot_fast(
        "xfiles_profit_optimization",
        _xfiles_profit_optimization_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_opportunities(
    limit: int = Query(default=20, ge=1, le=100),
):
    normalized_limit = max(1, min(int(limit or 20), 100))
    return _cached_sync_snapshot_fast(
        f"xfiles_deal_opportunities:{normalized_limit}",
        lambda: _xfiles_deal_opportunities_sync(limit=normalized_limit),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_north_star():
    return _cached_sync_snapshot_fast(
        "xfiles_north_star",
        _xfiles_north_star_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    stage: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    normalized_query = str(query or "").strip()
    normalized_stage = str(stage or "").strip()
    normalized_limit = max(1, int(limit or 1))
    return _cached_sync_snapshot_fast(
        f"xfiles_deals:{page}:{page_size}:{normalized_limit}:{normalized_query}:{normalized_stage}",
        lambda: XFilesDealsPageDTO(
            **_paginate_items(
                _xfiles_load_deals(
                    query=normalized_query,
                    stage=normalized_stage,
                    limit=normalized_limit,
                ),
                page=page,
                page_size=page_size,
            )
        ),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_kanban(
    query: Optional[str] = Query(default=None),
    stage: Optional[str] = Query(default=None),
    limit_per_stage: int = Query(default=20, ge=1, le=100),
):
    normalized_query = str(query or "").strip()
    normalized_stage = str(stage or "").strip()
    return _cached_sync_snapshot_fast(
        f"xfiles_deals_kanban:{normalized_query}:{normalized_stage}:{limit_per_stage}",
        lambda: _xfiles_deals_kanban_sync(
            query=normalized_query,
            stage=normalized_stage,
            limit_per_stage=limit_per_stage,
        ),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return _cached_sync_snapshot_fast(
        f"xfiles_deals_audit:{page}:{page_size}:{limit}",
        lambda: XFilesDealAuditPageDTO(
            **_paginate_items(
                _xfiles_load_deal_audit(limit=limit),
                page=page,
                page_size=page_size,
            )
        ),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_contract_templates():
    return _cached_sync_snapshot_fast(
        "xfiles_contract_templates",
        _xfiles_contract_templates_page_sync,
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deals_contract_metrics():
    return _xfiles_contract_metrics_sync()

def api_payme_deals_product_margins():
    items = _xfiles_load_product_margins()
    return XFilesProductMarginsPageDTO(items=items, total=len(items))

def api_payme_deals_product_margin_upsert(payload: XFilesProductMarginPayload):
    item = _xfiles_upsert_product_margin(payload)
    _xfiles_clear_deal_api_caches()
    return item

def api_payme_deals_product_margin_delete(item_id: str):
    removed = _xfiles_delete_product_margin(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Product margin not found")
    _xfiles_clear_deal_api_caches()
    return {"ok": True, "message": "Маржинальность продукта удалена"}

def api_payme_deals_create(payload: XFilesDealPayload):
    existing = _xfiles_find_existing_deal_for_payload(payload)
    if existing:
        return XFilesDealActionDTO(ok=True, message="Сделка уже есть", item=existing)
    item = _xfiles_upsert_deal(_xfiles_deal_from_payload(payload))
    _xfiles_append_deal_audit("create", item, changes=payload.model_dump(exclude_unset=True), source=str(payload.source or "ui"))
    _xfiles_clear_deal_api_caches()
    return XFilesDealActionDTO(ok=True, message="Сделка создана", item=item)

def api_payme_deals_event_sales_plan(
    limit: int = Query(default=10, ge=1, le=50),
):
    return _cached_sync_snapshot_fast(
        f"xfiles_event_sales_plan:{int(limit or 10)}",
        lambda: _xfiles_event_sales_plan_sync(limit=limit),
        ttl_sec=20,
    )

def api_payme_deal_assistant(deal_id: str):
    return _cached_sync_snapshot_fast(
        f"xfiles_deal_assistant:{deal_id}",
        lambda: _xfiles_deal_assistant_sync(deal_id),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deal_negotiation_brief(deal_id: str):
    return _cached_sync_snapshot_fast(
        f"xfiles_deal_negotiation_brief:{deal_id}",
        lambda: _xfiles_deal_negotiation_brief_sync(deal_id),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deal_contract_kit(deal_id: str):
    return _cached_sync_snapshot_fast(
        f"xfiles_deal_contract_kit:{deal_id}",
        lambda: _xfiles_deal_contract_kit_sync(deal_id),
        ttl_sec=_XFILES_DEAL_API_CACHE_TTL_SEC,
    )

def api_payme_deal_contract_status(deal_id: str, payload: XFilesDealContractStatusPayload):
    deal = _xfiles_get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    _xfiles_set_contract_status(deal_id, payload.contract_status)
    _xfiles_append_deal_audit(
        "contract_status",
        deal,
        changes={"contract_status": payload.contract_status},
        source="contract-kit",
    )
    _api_snapshot_cache_clear_prefix(f"xfiles_deal_contract_kit:{deal_id}")
    _api_snapshot_cache_clear_prefix("xfiles_contract_metrics")
    return _xfiles_deal_contract_kit_sync(deal_id)

def api_payme_deals_update(deal_id: str, payload: XFilesDealPatchPayload):
    before = _xfiles_get_deal(deal_id)
    item = _xfiles_patch_deal(deal_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Deal not found")
    _xfiles_append_deal_audit("update", item, before=before, changes=payload.model_dump(exclude_unset=True), source="ui")
    _xfiles_clear_deal_api_caches()
    return XFilesDealActionDTO(ok=True, message="Сделка обновлена", item=item)

def api_payme_deals_delete(deal_id: str):
    before = _xfiles_get_deal(deal_id)
    removed = _xfiles_delete_deal(deal_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Deal not found")
    _xfiles_append_deal_audit("delete", None, before=before, source="ui")
    _xfiles_clear_deal_api_caches()
    return XFilesDealActionDTO(ok=True, message="Сделка удалена", item=None)

def api_payme_deals_from_outreach(item_id: str):
    item = _xfiles_deal_from_outreach_item(item_id)
    _xfiles_append_deal_audit("create_from_enreach", item, source="enReach", changes={"item_id": item_id})
    _xfiles_clear_deal_api_caches()
    return XFilesDealActionDTO(ok=True, message="Сделка создана из enReach", item=item)

def api_payme_deal_follow_up_sequence(deal_id: str):
    item = _xfiles_create_outreach_sequence_from_deal(deal_id)
    return XFilesOutreachSequenceActionDTO(
        ok=True,
        message="Follow-up sequence подготовлена по сделке. Автоотправка отключена.",
        item=item,
    )

def api_payme_deals_daily_contacts(
    limit: int = Query(default=10, ge=1, le=50),
    lead_temperature: str = Query(default="all"),
):
    normalized_temperature = str(lead_temperature or "all").strip()
    return _cached_sync_snapshot_fast(
        f"xfiles_daily_contacts:{int(limit or 10)}:{normalized_temperature}",
        lambda: _xfiles_daily_contacts_sync(limit=limit, lead_temperature=normalized_temperature),
        ttl_sec=20,
    )

async def api_payme_needs_signals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    tag: str = Query(default="all"),
    source: str = Query(default="all"),
    limit: int = Query(default=3000, ge=100, le=10000),
):
    return await asyncio.to_thread(
        _xfiles_need_signals_page_sync,
        page=page,
        page_size=page_size,
        query=str(query or "").strip(),
        tag=str(tag or "all").strip(),
        source=str(source or "all").strip(),
        limit=limit,
    )








































































    return event_stream
