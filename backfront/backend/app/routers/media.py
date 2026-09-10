"""Media/image routes extracted from the monolith."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from app.schemas.media import *  # noqa: F403
from app.services import media as media_service

router = APIRouter()

@router.get("/api/payme/images", response_model=ImageAssetsPageDTO, tags=["payme"])
def api_payme_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=1000, ge=1, le=5000),
    query: str = Query(default=""),
    lead_filter: str = Query(default=""),
    recognized_only: bool = Query(default=False),
    pending_only: bool = Query(default=False),
):
    return media_service.api_payme_images(page=page, page_size=page_size, limit=limit, query=query, lead_filter=lead_filter, recognized_only=recognized_only, pending_only=pending_only)

@router.get("/api/payme/images/text", response_model=ImageAssetTextDTO, tags=["payme"])
def api_payme_image_text(media_path: str = Query(..., min_length=1)):
    return media_service.api_payme_image_text(media_path=media_path)

@router.get("/api/payme/media/config", response_model=MediaConfigDTO, tags=["payme"])
def api_payme_media_config():
    return media_service.api_payme_media_config()

@router.get("/api/payme/media/status", response_model=MediaStatusDTO, tags=["payme"])
def api_payme_media_status():
    return media_service.api_payme_media_status()

@router.post("/api/payme/media/add", response_model=MediaConfigDTO, tags=["payme"])
def api_payme_media_add(payload: MediaLeadPayload):
    return media_service.api_payme_media_add(payload=payload)

@router.post("/api/payme/media/add-many", response_model=MediaConfigDTO, tags=["payme"])
def api_payme_media_add_many(payload: MediaLeadsPayload):
    return media_service.api_payme_media_add_many(payload=payload)

@router.post("/api/payme/media/remove", response_model=MediaConfigDTO, tags=["payme"])
def api_payme_media_remove(payload: MediaLeadPayload):
    return media_service.api_payme_media_remove(payload=payload)

@router.post("/api/payme/media/clear", response_model=MediaClearDTO, tags=["payme"])
def api_payme_media_clear(payload: MediaLeadPayload):
    return media_service.api_payme_media_clear(payload=payload)

@router.post("/api/payme/media/clear-all", response_model=MediaClearDTO, tags=["payme"])
def api_payme_media_clear_all():
    return media_service.api_payme_media_clear_all()

@router.post("/api/payme/images/ocr-pending", response_model=ImageOcrActionDTO, tags=["payme"])
async def api_payme_images_ocr_pending():
    return await media_service.api_payme_images_ocr_pending()
