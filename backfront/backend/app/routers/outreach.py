"""enReach/outReach HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas import outreach as outreach_schemas
from app.services import outreach as outreach_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/outreach/items", response_model=outreach_schemas.OutreachCrmFieldsPageDTO)
def api_payme_outreach_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    field_type: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    return outreach_service.api_payme_outreach_items(
        page=page,
        page_size=page_size,
        query=query,
        field_type=field_type,
        limit=limit,
    )


@router.post("/api/payme/outreach/items", response_model=outreach_schemas.OutreachCrmFieldActionDTO)
def api_payme_outreach_add_item(payload: outreach_schemas.OutreachCrmFieldPayload):
    return outreach_service.api_payme_outreach_add_item(payload)


@router.post("/api/payme/outreach/expand-values")
async def api_payme_outreach_expand_values():
    return await outreach_service.api_payme_outreach_expand_values()


@router.delete("/api/payme/outreach/items/{item_id}", response_model=outreach_schemas.OutreachCrmFieldActionDTO)
def api_payme_outreach_delete_item(item_id: str):
    return outreach_service.api_payme_outreach_delete_item(item_id)


@router.get("/api/payme/outreach/sequences", response_model=outreach_schemas.XFilesOutreachSequencesPageDTO)
def api_payme_outreach_sequences(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    return outreach_service.api_payme_outreach_sequences(
        page=page,
        page_size=page_size,
        query=query,
        status=status,
        limit=limit,
    )


@router.get("/api/payme/outreach/stats", response_model=outreach_schemas.XFilesOutreachStatsDTO)
def api_payme_outreach_stats():
    return outreach_service.api_payme_outreach_stats()


@router.post("/api/payme/outreach/sequences", response_model=outreach_schemas.XFilesOutreachSequenceActionDTO)
def api_payme_outreach_sequence_create(payload: outreach_schemas.XFilesOutreachSequencePayload):
    return outreach_service.api_payme_outreach_sequence_create(payload)


@router.post(
    "/api/payme/outreach/sequences/from-enreach/{item_id}",
    response_model=outreach_schemas.XFilesOutreachSequenceActionDTO,
)
def api_payme_outreach_sequence_from_enreach(item_id: str):
    return outreach_service.api_payme_outreach_sequence_from_enreach(item_id)


@router.patch(
    "/api/payme/outreach/sequences/{sequence_id}",
    response_model=outreach_schemas.XFilesOutreachSequenceActionDTO,
)
def api_payme_outreach_sequence_update(sequence_id: str, payload: outreach_schemas.XFilesOutreachSequencePatchPayload):
    return outreach_service.api_payme_outreach_sequence_update(sequence_id, payload)


@router.patch(
    "/api/payme/outreach/sequences/{sequence_id}/touches/{touch_key}",
    response_model=outreach_schemas.XFilesOutreachSequenceActionDTO,
)
def api_payme_outreach_touch_status(
    sequence_id: str,
    touch_key: str,
    payload: outreach_schemas.XFilesOutreachTouchStatusPayload,
):
    return outreach_service.api_payme_outreach_touch_status(sequence_id, touch_key, payload)
