"""API facade for data source plugins."""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas.data_sources import (
    CanonicalPreviewPageDTO,
    DataSourceActionDTO,
    DataSourceConnectResultDTO,
    DataSourceEntityPageDTO,
    DataSourceEntitySelectionPayload,
    DataSourcePluginPageDTO,
    DataSourceRegistrationPayload,
)
from app.schemas.jobs import JobCreatePayload
from app.services import jobs as jobs_service
from app.services.data_sources.registry import plugin_registry
from app.services.data_sources.service import default_service


def list_plugins() -> DataSourcePluginPageDTO:
    items = plugin_registry().list_manifests()
    return DataSourcePluginPageDTO(items=items, total=len(items))


def list_sources():
    return default_service.page()


def connect_plugin(plugin_type: str, payload: dict) -> DataSourceConnectResultDTO:
    try:
        return plugin_registry().get(plugin_type).connect(payload.get("connection") or payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def introspect_plugin(plugin_type: str, payload: dict) -> DataSourceEntityPageDTO:
    try:
        items = plugin_registry().get(plugin_type).introspect(payload.get("connection") or payload)
        return DataSourceEntityPageDTO(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def preview_plugin(plugin_type: str, payload: dict) -> CanonicalPreviewPageDTO:
    try:
        adapter = plugin_registry().get(plugin_type)
        items = adapter.preview(
            payload.get("connection") or {},
            payload.get("mapping") or {},
            limit=int(payload.get("limit") or 20),
        )
        return CanonicalPreviewPageDTO(items=items, total=len(items))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def register_source(payload: DataSourceRegistrationPayload) -> DataSourceActionDTO:
    source = default_service.register_source(payload)
    return DataSourceActionDTO(ok=True, message="Источник данных подключен", source=source)


def select_entity(source_id: str, payload: DataSourceEntitySelectionPayload) -> DataSourceActionDTO:
    try:
        selected = default_service.select_entity(source_id, payload)
        return DataSourceActionDTO(ok=True, message="Сущность источника добавлена", selected=selected)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def disconnect_source(source_id: str) -> DataSourceActionDTO:
    try:
        source = default_service.disconnect_source(source_id)
        return DataSourceActionDTO(ok=True, message="Источник данных отключён без удаления кеша", source=source)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def enqueue_sync(source_id: str):
    job = jobs_service.enqueue_job(
        JobCreatePayload(
            type="data_source_sync",
            payload={"source_id": source_id, "chunks_total": 1, "origin": "data_sources"},
        )
    )
    return DataSourceActionDTO(ok=True, message="Sync источника поставлен в очередь", job=job.model_dump())
