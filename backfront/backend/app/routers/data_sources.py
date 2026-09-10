"""Data source plugin API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import data_sources as schemas
from app.services.data_sources import api as service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/data-sources/plugins", response_model=schemas.DataSourcePluginPageDTO)
def api_payme_data_source_plugins():
    return service.list_plugins()


@router.get("/api/payme/data-sources", response_model=schemas.DataSourcePageDTO)
def api_payme_data_sources():
    return service.list_sources()


@router.post("/api/payme/data-sources/{plugin_type}/connect", response_model=schemas.DataSourceConnectResultDTO)
def api_payme_data_source_connect(plugin_type: str, payload: dict):
    return service.connect_plugin(plugin_type, payload)


@router.post("/api/payme/data-sources/{plugin_type}/introspect", response_model=schemas.DataSourceEntityPageDTO)
def api_payme_data_source_introspect(plugin_type: str, payload: dict):
    return service.introspect_plugin(plugin_type, payload)


@router.post("/api/payme/data-sources/{plugin_type}/preview", response_model=schemas.CanonicalPreviewPageDTO)
def api_payme_data_source_preview(plugin_type: str, payload: dict):
    return service.preview_plugin(plugin_type, payload)


@router.post("/api/payme/data-sources", response_model=schemas.DataSourceActionDTO)
def api_payme_data_source_register(payload: schemas.DataSourceRegistrationPayload):
    return service.register_source(payload)


@router.post("/api/payme/data-sources/{source_id}/entities", response_model=schemas.DataSourceActionDTO)
def api_payme_data_source_select_entity(source_id: str, payload: schemas.DataSourceEntitySelectionPayload):
    return service.select_entity(source_id, payload)


@router.post("/api/payme/data-sources/{source_id}/disconnect", response_model=schemas.DataSourceActionDTO)
def api_payme_data_source_disconnect(source_id: str):
    return service.disconnect_source(source_id)


@router.post("/api/payme/data-sources/{source_id}/sync", response_model=schemas.DataSourceActionDTO)
def api_payme_data_source_sync(source_id: str):
    return service.enqueue_sync(source_id)
