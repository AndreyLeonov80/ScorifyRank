"""Route-analysis HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import routes as routes_schemas
from app.services import routes as routes_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/routes/status")
def api_payme_routes_status():
    return routes_service.api_payme_routes_status()


@router.post("/api/payme/routes/refresh")
async def api_payme_routes_refresh(
    force_full: bool = Query(default=False),
    confirm_full_refresh: bool = Query(default=False),
    max_llm: int = Query(default=routes_service.ROUTES_LLM_BATCH_SIZE, ge=1, le=500),
    model: str = Query(default=""),
):
    return await routes_service.api_payme_routes_refresh(
        force_full=force_full,
        confirm_full_refresh=confirm_full_refresh,
        max_llm=max_llm,
        model=model,
    )


@router.get("/api/payme/routes/messages")
def api_payme_routes_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    only_with_address: bool = Query(default=False),
):
    return routes_service.api_payme_routes_messages(
        page=page,
        page_size=page_size,
        query=query,
        only_with_address=only_with_address,
    )


@router.get("/api/payme/routes/addresses")
def api_payme_routes_addresses(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
):
    return routes_service.api_payme_routes_addresses(page=page, page_size=page_size, query=query)


@router.get("/api/payme/routes/map-points")
def api_payme_routes_map_points(
    query: str = Query(default=""),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    return routes_service.api_payme_routes_map_points(query=query, limit=limit)


@router.post("/api/payme/routes/geocode")
def api_payme_routes_geocode(payload: routes_schemas.RouteGeocodePayload):
    return routes_service.api_payme_routes_geocode(payload)
