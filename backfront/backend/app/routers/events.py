"""Event analysis HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query

from app.schemas import events as events_schemas
from app.services import events as events_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/event-keywords", response_model=events_schemas.EventKeywordsDTO)
def api_payme_event_keywords():
    return events_service.api_payme_event_keywords()


@router.post("/api/payme/event-keywords", response_model=events_schemas.EventKeywordsDTO)
def api_payme_event_keywords_update(payload: events_schemas.EventKeywordsPayload):
    return events_service.api_payme_event_keywords_update(payload)


@router.get("/api/payme/events/status", response_model=events_schemas.AnalysisStatusDTO)
def api_payme_events_status(background_tasks: BackgroundTasks):
    return events_service.api_payme_events_status(background_tasks)


@router.post("/api/payme/events/refresh", response_model=events_schemas.AnalysisActionDTO)
async def api_payme_events_refresh():
    return await events_service.api_payme_events_refresh()


@router.post("/api/payme/events/config", response_model=events_schemas.AnalysisActionDTO)
def api_payme_events_config(payload: events_schemas.AnalysisConfigPayload):
    return events_service.api_payme_events_config(payload)


@router.get("/api/payme/event-messages", response_model=events_schemas.EventMessagesPageDTO)
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
    return events_service.api_payme_event_messages(
        background_tasks=background_tasks,
        page=page,
        page_size=page_size,
        limit=limit,
        query=query,
        lead_filter=lead_filter,
        sender_filter=sender_filter,
        keyword_filter=keyword_filter,
        date_from=date_from,
        date_to=date_to,
    )


@router.post("/api/payme/event-messages/delete", response_model=events_schemas.EventMessageDeleteDTO)
def api_payme_event_message_delete(payload: events_schemas.EventMessageDeletePayload):
    return events_service.api_payme_event_message_delete(payload)


@router.get("/api/payme/calendar-events", response_model=events_schemas.EventMessagesPageDTO)
def api_payme_calendar_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=5000, ge=1, le=50000),
    query: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    return events_service.api_payme_calendar_events(
        page=page,
        page_size=page_size,
        limit=limit,
        query=query,
        date_from=date_from,
        date_to=date_to,
    )
