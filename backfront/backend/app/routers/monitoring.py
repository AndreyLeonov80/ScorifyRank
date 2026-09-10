"""Runtime logs, metrics, and dashboard monitoring routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.schemas import monitoring as monitoring_schemas
from app.services import monitoring as monitoring_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/runtime-logs", response_model=list[monitoring_schemas.RuntimeLogDTO])
def api_payme_runtime_logs(
    minutes: int = Query(default=10, ge=1, le=60),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=200),
    channel: str = Query(default=""),
):
    return monitoring_service.api_payme_runtime_logs(
        minutes=minutes,
        after_id=after_id,
        limit=limit,
        channel=channel,
    )


@router.get("/api/payme/runtime-logs/stream")
async def api_payme_runtime_logs_stream(
    request: Request,
    minutes: int = Query(default=10, ge=1, le=60),
    channel: str = Query(default=""),
):
    return await monitoring_service.api_payme_runtime_logs_stream(
        request=request,
        minutes=minutes,
        channel=channel,
    )


@router.get("/api/payme/runtime-status", response_model=monitoring_schemas.RuntimeStatusDTO)
async def api_payme_runtime_status():
    return await monitoring_service.api_payme_runtime_status()


@router.get("/api/payme/server-status", response_model=monitoring_schemas.ServerRuntimeDTO)
def api_payme_server_status():
    return monitoring_service.api_payme_server_status()


@router.get("/api/payme/system-metrics", response_model=monitoring_schemas.SystemMetricsDTO)
def api_payme_system_metrics(
    history_points: int = Query(default=60, ge=1, le=720),
):
    return monitoring_service.api_payme_system_metrics(history_points=history_points)


@router.get("/api/payme/duckdb/status", response_model=monitoring_schemas.DuckDbStatusDTO)
def api_payme_duckdb_status():
    return monitoring_service.api_payme_duckdb_status()


@router.get("/api/payme/duckdb/lock-status", response_model=dict)
def api_payme_duckdb_lock_status():
    return monitoring_service.api_payme_duckdb_lock_status()


@router.post("/api/payme/duckdb/refresh", response_model=monitoring_schemas.DuckDbActionDTO)
async def api_payme_duckdb_refresh(
    force_full: bool = Query(default=False),
    confirm_full_refresh: bool = Query(default=False),
):
    return await monitoring_service.api_payme_duckdb_refresh(
        force_full=force_full,
        confirm_full_refresh=confirm_full_refresh,
    )


@router.post("/api/payme/duckdb/export-parquet", response_model=monitoring_schemas.DuckDbExportDTO)
async def api_payme_duckdb_export_parquet():
    return await monitoring_service.api_payme_duckdb_export_parquet()


@router.post(
    "/api/payme/duckdb/materialize-parquet-sidecars", response_model=monitoring_schemas.DuckDbParquetSidecarsDTO
)
async def api_payme_duckdb_materialize_parquet_sidecars(force: bool = Query(default=False)):
    return await monitoring_service.api_payme_duckdb_materialize_parquet_sidecars(force=force)


@router.post("/api/payme/duckdb/archive-legacy-cache", response_model=monitoring_schemas.DuckDbLegacyCacheCleanupDTO)
async def api_payme_duckdb_archive_legacy_cache():
    return await monitoring_service.api_payme_duckdb_archive_legacy_cache()


@router.get("/api/payme/stream/realtime")
async def api_payme_realtime_stream(
    request: Request,
    types: str = Query(default="runtime_log,monitor,lead"),
    lead: str = Query(default=""),
    minutes: int = Query(default=10, ge=1, le=60),
    history_points: int = Query(default=60, ge=1, le=720),
    dashboard_limit: int = Query(default=10, ge=1, le=50),
):
    return await monitoring_service.api_payme_realtime_stream(
        request=request,
        types=types,
        lead=lead,
        minutes=minutes,
        history_points=history_points,
        dashboard_limit=dashboard_limit,
    )


@router.get("/api/payme/runtime/status-stream")
async def api_payme_runtime_status_stream(
    request: Request,
    types: str = Query(default="runtime_log,monitor,lead"),
    lead: str = Query(default=""),
    minutes: int = Query(default=10, ge=1, le=60),
    history_points: int = Query(default=60, ge=1, le=720),
    dashboard_limit: int = Query(default=10, ge=1, le=50),
):
    return await monitoring_service.api_payme_realtime_stream(
        request=request,
        types=types,
        lead=lead,
        minutes=minutes,
        history_points=history_points,
        dashboard_limit=dashboard_limit,
    )


@router.get("/api/payme/dashboard/summary")
async def api_payme_dashboard_summary(
    limit: int = Query(default=10, ge=1, le=50),
):
    return await monitoring_service.api_payme_dashboard_summary(limit=limit)


@router.get("/api/payme/dashboard/summary-lite")
async def api_payme_dashboard_summary_lite():
    return await monitoring_service.api_payme_dashboard_summary_lite()


@router.get("/api/payme/dashboard/details")
async def api_payme_dashboard_details(
    limit: int = Query(default=10, ge=1, le=50),
):
    return await monitoring_service.api_payme_dashboard_details(limit=limit)


@router.get("/api/payme/dashboard/logs")
async def api_payme_dashboard_logs(
    minutes: int = Query(default=10, ge=1, le=60),
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    return await monitoring_service.api_payme_dashboard_logs(minutes=minutes, after_id=after_id, limit=limit)


@router.get("/api/payme/dashboard/previews")
async def api_payme_dashboard_previews(
    limit: int = Query(default=10, ge=1, le=50),
):
    return await monitoring_service.api_payme_dashboard_previews(limit=limit)


@router.get("/api/payme/monitor/stream")
async def api_payme_monitor_stream(
    request: Request,
    history_points: int = Query(default=60, ge=1, le=720),
):
    return await monitoring_service.api_payme_monitor_stream(
        request=request,
        history_points=history_points,
    )
