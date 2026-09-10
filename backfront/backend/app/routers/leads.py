"""Lead, chat, and lead-analysis HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.schemas import leads as leads_schemas
from app.services import leads as leads_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/leads", response_model=leads_schemas.LeadsPageDTO)
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
    return await leads_service.api_payme_list_leads(
        page=page,
        page_size=page_size,
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


@router.get("/api/payme/source-stats", response_model=leads_schemas.SourceStatsPageDTO)
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
    return await leads_service.api_payme_source_stats(
        page=page,
        page_size=page_size,
        query=query,
        show_channels=show_channels,
        show_groups=show_groups,
        show_private=show_private,
        scan_filter=scan_filter,
        status_filter=status_filter,
        group_filter=group_filter,
        sort_mode=sort_mode,
    )


@router.get("/api/payme/sources/runtime-status", response_model=leads_schemas.SourceRuntimeStatusPageDTO)
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
    return await leads_service.api_payme_sources_runtime_status(
        page=page,
        page_size=page_size,
        query=query,
        show_channels=show_channels,
        show_groups=show_groups,
        show_private=show_private,
        scan_filter=scan_filter,
        status_filter=status_filter,
        group_filter=group_filter,
        sort_mode=sort_mode,
    )


@router.post("/api/payme/leads/deactivate", response_model=leads_schemas.LeadActionDTO)
async def api_payme_leads_deactivate(payload: leads_schemas.LeadActionPayload):
    return await leads_service.api_payme_leads_deactivate(payload)


@router.post("/api/payme/leads/activate", response_model=leads_schemas.LeadActionDTO)
async def api_payme_leads_activate(payload: leads_schemas.LeadActionPayload):
    return await leads_service.api_payme_leads_activate(payload)


@router.post("/api/payme/leads/group", response_model=leads_schemas.LeadGroupActionDTO)
async def api_payme_leads_group(payload: leads_schemas.LeadGroupPayload):
    return await leads_service.api_payme_leads_group(payload)


@router.post("/api/payme/leads/delete", response_model=leads_schemas.LeadActionDTO)
async def api_payme_leads_delete(payload: leads_schemas.LeadActionPayload):
    return await leads_service.api_payme_leads_delete(payload)


@router.get("/api/payme/leads/{lead}/messages", response_model=list[leads_schemas.MessageDTO])
def api_payme_lead_messages(
    lead: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(0, ge=0, le=200_000),
):
    return leads_service.api_payme_lead_messages(lead=lead, offset=offset, limit=limit)


@router.get("/api/payme/chat/messages", response_model=list[leads_schemas.MessageDTO])
def api_payme_chat_messages(
    selector: str = Query(..., min_length=1),
    before: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=30, ge=1, le=200),
):
    return leads_service.api_payme_chat_messages(selector=selector, before=before, limit=limit)


@router.get("/api/payme/leads/{lead}/jsonl")
def api_payme_lead_jsonl(lead: str):
    return leads_service.api_payme_lead_jsonl(lead)


@router.get("/api/payme/leads/{lead}/stream")
async def api_payme_stream(lead: str, request: Request):
    return await leads_service.api_payme_stream(lead, request)


@router.get("/api/payme/stream/leads")
async def api_payme_all_leads_stream(request: Request, lead: str = Query(default="")):
    return await leads_service.api_payme_all_leads_stream(request, lead=lead)


@router.get("/api/payme/leads/{lead}/llm", response_class=HTMLResponse)
def api_payme_lead_llm(lead: str):
    return leads_service.api_payme_lead_llm(lead)


@router.post("/api/payme/send")
async def api_payme_send(payload: leads_schemas.SendPayload):
    return await leads_service.api_payme_send(payload)
