"""X-Files deals/needs routes extracted from the monolith."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from app.schemas.deals import *  # noqa: F403
from app.services import deals as deals_service

router = APIRouter()

@router.get("/api/payme/deals/status", response_model=XFilesDealsStatusDTO, tags=["payme"])
def api_payme_deals_status():
    return deals_service.api_payme_deals_status()

@router.get("/api/payme/deals/reminders", response_model=XFilesDealRemindersDTO, tags=["payme"])
def api_payme_deals_reminders(
    limit: int = Query(default=50, ge=1, le=200),
    include_done: bool = Query(default=False),
):
    return deals_service.api_payme_deals_reminders(limit=limit, include_done=include_done)

@router.get("/api/payme/deals/conversion", response_model=XFilesDealConversionDTO, tags=["payme"])
def api_payme_deals_conversion():
    return deals_service.api_payme_deals_conversion()

@router.get("/api/payme/deals/profit-optimization", response_model=XFilesProfitOptimizationDTO, tags=["payme"])
def api_payme_deals_profit_optimization():
    return deals_service.api_payme_deals_profit_optimization()

@router.get("/api/payme/deals/opportunities", response_model=XFilesDealOpportunitiesDTO, tags=["payme"])
def api_payme_deals_opportunities(
    limit: int = Query(default=20, ge=1, le=100),
):
    return deals_service.api_payme_deals_opportunities(limit=limit)

@router.get("/api/payme/deals/north-star", response_model=XFilesNorthStarDTO, tags=["payme"])
def api_payme_deals_north_star():
    return deals_service.api_payme_deals_north_star()

@router.get("/api/payme/deals", response_model=XFilesDealsPageDTO, tags=["payme"])
def api_payme_deals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    stage: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    return deals_service.api_payme_deals(page=page, page_size=page_size, query=query, stage=stage, limit=limit)

@router.get("/api/payme/deals/kanban", response_model=XFilesDealsKanbanDTO, tags=["payme"])
def api_payme_deals_kanban(
    query: Optional[str] = Query(default=None),
    stage: Optional[str] = Query(default=None),
    limit_per_stage: int = Query(default=20, ge=1, le=100),
):
    return deals_service.api_payme_deals_kanban(query=query, stage=stage, limit_per_stage=limit_per_stage)

@router.get("/api/payme/deals/audit", response_model=XFilesDealAuditPageDTO, tags=["payme"])
def api_payme_deals_audit(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=200, ge=1, le=1000),
):
    return deals_service.api_payme_deals_audit(page=page, page_size=page_size, limit=limit)

@router.get("/api/payme/deals/contract-templates", response_model=XFilesContractTemplatesPageDTO, tags=["payme"])
def api_payme_deals_contract_templates():
    return deals_service.api_payme_deals_contract_templates()

@router.get("/api/payme/deals/contract-metrics", response_model=XFilesContractMetricsDTO, tags=["payme"])
def api_payme_deals_contract_metrics():
    return deals_service.api_payme_deals_contract_metrics()

@router.get("/api/payme/deals/product-margins", response_model=XFilesProductMarginsPageDTO, tags=["payme"])
def api_payme_deals_product_margins():
    return deals_service.api_payme_deals_product_margins()

@router.post("/api/payme/deals/product-margins", response_model=XFilesProductMarginDTO, tags=["payme"])
def api_payme_deals_product_margin_upsert(payload: XFilesProductMarginPayload):
    return deals_service.api_payme_deals_product_margin_upsert(payload=payload)

@router.delete("/api/payme/deals/product-margins/{item_id}", response_model=Dict[str, Any], tags=["payme"])
def api_payme_deals_product_margin_delete(item_id: str):
    return deals_service.api_payme_deals_product_margin_delete(item_id=item_id)

@router.post("/api/payme/deals", response_model=XFilesDealActionDTO, tags=["payme"])
def api_payme_deals_create(payload: XFilesDealPayload):
    return deals_service.api_payme_deals_create(payload=payload)

@router.get("/api/payme/deals/event-sales-plan", response_model=XFilesEventSalesPlanDTO, tags=["payme"])
def api_payme_deals_event_sales_plan(
    limit: int = Query(default=10, ge=1, le=50),
):
    return deals_service.api_payme_deals_event_sales_plan(limit=limit)

@router.get("/api/payme/deals/{deal_id}/assistant", response_model=XFilesDealAssistantDTO, tags=["payme"])
def api_payme_deal_assistant(deal_id: str):
    return deals_service.api_payme_deal_assistant(deal_id=deal_id)

@router.get("/api/payme/deals/{deal_id}/negotiation-brief", response_model=XFilesNegotiationBriefDTO, tags=["payme"])
def api_payme_deal_negotiation_brief(deal_id: str):
    return deals_service.api_payme_deal_negotiation_brief(deal_id=deal_id)

@router.get("/api/payme/deals/{deal_id}/contract-kit", response_model=XFilesDealContractKitDTO, tags=["payme"])
def api_payme_deal_contract_kit(deal_id: str):
    return deals_service.api_payme_deal_contract_kit(deal_id=deal_id)

@router.patch("/api/payme/deals/{deal_id}/contract-status", response_model=XFilesDealContractKitDTO, tags=["payme"])
def api_payme_deal_contract_status(deal_id: str, payload: XFilesDealContractStatusPayload):
    return deals_service.api_payme_deal_contract_status(deal_id=deal_id, payload=payload)

@router.patch("/api/payme/deals/{deal_id}", response_model=XFilesDealActionDTO, tags=["payme"])
def api_payme_deals_update(deal_id: str, payload: XFilesDealPatchPayload):
    return deals_service.api_payme_deals_update(deal_id=deal_id, payload=payload)

@router.delete("/api/payme/deals/{deal_id}", response_model=XFilesDealActionDTO, tags=["payme"])
def api_payme_deals_delete(deal_id: str):
    return deals_service.api_payme_deals_delete(deal_id=deal_id)

@router.post("/api/payme/deals/from-outreach/{item_id}", response_model=XFilesDealActionDTO, tags=["payme"])
def api_payme_deals_from_outreach(item_id: str):
    return deals_service.api_payme_deals_from_outreach(item_id=item_id)

@router.post("/api/payme/deals/{deal_id}/follow-up-sequence", response_model=XFilesOutreachSequenceActionDTO, tags=["payme"])
def api_payme_deal_follow_up_sequence(deal_id: str):
    return deals_service.api_payme_deal_follow_up_sequence(deal_id=deal_id)

@router.get("/api/payme/deals/daily-contacts", response_model=XFilesDailyContactsDTO, tags=["payme"])
def api_payme_deals_daily_contacts(
    limit: int = Query(default=10, ge=1, le=50),
    lead_temperature: str = Query(default="all"),
):
    return deals_service.api_payme_deals_daily_contacts(limit=limit, lead_temperature=lead_temperature)

@router.get("/api/payme/needs/signals", response_model=XFilesNeedSignalsPageDTO, tags=["payme"])
async def api_payme_needs_signals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    tag: str = Query(default="all"),
    source: str = Query(default="all"),
    limit: int = Query(default=3000, ge=100, le=10000),
):
    return await deals_service.api_payme_needs_signals(page=page, page_size=page_size, query=query, tag=tag, source=source, limit=limit)
