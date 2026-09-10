"""FastAPI entrypoint for the optimized backend layout.

The monolithic legacy module is still the source of truth while we move
domains out one by one. Keeping this shim lets Docker and future tests depend
on a stable `app.main:app` import path without changing API contracts.
"""

from app.routers.analysis import router as analysis_router
from app.routers.channels import router as channels_router
from app.routers.config import router as config_router
from app.routers.contacts import router as contacts_router
from app.routers.crm import router as crm_router
from app.routers.data_sources import router as data_sources_router
from app.routers.deals import router as deals_router
from app.routers.events import router as events_router
from app.routers.health import router as health_router
from app.routers.jur_entities import router as jur_entities_router
from app.routers.jobs import router as jobs_router
from app.routers.leads import router as leads_router
from app.routers.legacy_api import router as legacy_api_router
from app.routers.license import router as license_router
from app.routers.media import router as media_router
from app.routers.monitoring import router as monitoring_router
from app.routers.outreach import router as outreach_router
from app.routers.routes import router as routes_router
from app.routers.search import router as search_router
from back import app


def _route_key(route):
    return getattr(route, "path", ""), frozenset(getattr(route, "methods", ()) or ())


_legacy_route_count = len(app.routes)
app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(config_router)
app.include_router(license_router)
app.include_router(analysis_router)
app.include_router(leads_router)
app.include_router(channels_router)
app.include_router(routes_router)
app.include_router(monitoring_router)
app.include_router(events_router)
app.include_router(crm_router)
app.include_router(outreach_router)
app.include_router(contacts_router)
app.include_router(jur_entities_router)
app.include_router(media_router)
app.include_router(search_router)
app.include_router(deals_router)
app.include_router(data_sources_router)
app.include_router(legacy_api_router)
_extracted_routes = app.routes[_legacy_route_count:]
if _extracted_routes:
    _extracted_route_keys = {_route_key(route) for route in _extracted_routes}
    _legacy_routes = [
        route for route in app.routes[:_legacy_route_count] if _route_key(route) not in _extracted_route_keys
    ]
    app.routes[:] = _extracted_routes + _legacy_routes

__all__ = ["app"]
