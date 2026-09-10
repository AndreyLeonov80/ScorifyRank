"""Jur-entity parser routes extracted from the monolith."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from app.schemas.jur_entities import *  # noqa: F403
from app.services import jur_entities as jur_entities_service

router = APIRouter()

@router.get("/api/payme/jur-entities", response_model=JurEntityFilesPageDTO, tags=["payme"])
async def api_payme_jur_entities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    parser_filter: str = Query(default="all"),
    sync: bool = Query(default=False),
):
    return await jur_entities_service.api_payme_jur_entities(page=page, page_size=page_size, query=query, parser_filter=parser_filter, sync=sync)

@router.post("/api/payme/jur-entities/sync", response_model=JurEntitySyncDTO, tags=["payme"])
async def api_payme_jur_entities_sync():
    return await jur_entities_service.api_payme_jur_entities_sync()

@router.post("/api/payme/jur-entities/parser-add", response_model=JurEntityActionDTO, tags=["payme"])
def api_payme_jur_entities_parser_add(payload: JurEntityActionPayload):
    return jur_entities_service.api_payme_jur_entities_parser_add(payload=payload)

@router.post("/api/payme/jur-entities/parser-remove", response_model=JurEntityActionDTO, tags=["payme"])
def api_payme_jur_entities_parser_remove(payload: JurEntityActionPayload):
    return jur_entities_service.api_payme_jur_entities_parser_remove(payload=payload)
