import importlib
import inspect
import unittest
from collections import Counter

LICENSE_ROUTE_PATHS = {
    "/api/payme/license/status",
    "/api/payme/tariffs",
    "/api/payme/update/status",
    "/api/payme/license/activate",
    "/api/payme/license/upgrade",
    "/api/payme/license/renew",
    "/api/payme/license/email/import",
    "/api/payme/license/audit",
    "/api/payme/license/menus",
    "/api/payme/license/menus/check",
}

LEADS_ROUTE_PATHS = {
    "/api/payme/leads",
    "/api/payme/leads/deactivate",
    "/api/payme/leads/activate",
    "/api/payme/leads/group",
    "/api/payme/leads/delete",
    "/api/payme/leads/{lead}/messages",
    "/api/payme/leads/{lead}/jsonl",
    "/api/payme/chat/messages",
    "/api/payme/source-stats",
    "/api/payme/sources/runtime-status",
    "/api/payme/leads/{lead}/stream",
    "/api/payme/stream/leads",
    "/api/payme/leads/{lead}/llm",
    "/api/payme/send",
}

ANALYSIS_ROUTE_PATHS = {
    "/api/payme/leads/{lead}/analysis/stats",
    "/api/payme/leads/{lead}/analysis/history",
    "/api/payme/leads/{lead}/analysis/run",
    "/api/payme/llm-run",
}

CHANNEL_ROUTE_PATHS = {
    "/api/payme/source/reload",
    "/api/payme/source/add",
    "/api/payme/source/remove",
    "/api/payme/source-policies",
    "/api/payme/source-policy",
    "/api/payme/telegram/dialogs",
    "/api/payme/telegram/dialogs/import",
    "/api/payme/telegram/dialogs/settings",
    "/api/payme/telegram/dialogs/remove-added",
    "/api/payme/import-sync/status",
    "/api/payme/import-sync/enable",
    "/api/payme/import-sync/disable",
    "/api/payme/telegram-sync/control",
    "/api/payme/telegram-sync/job",
    "/api/payme/telegram-sync/run",
    "/api/payme/telegram-sync/pause",
    "/api/payme/telegram-sync/resume",
}

ROUTES_ROUTE_PATHS = {
    "/api/payme/routes/status",
    "/api/payme/routes/refresh",
    "/api/payme/routes/messages",
    "/api/payme/routes/addresses",
    "/api/payme/routes/map-points",
    "/api/payme/routes/geocode",
}

CONFIG_ROUTE_PATHS = {
    "/api/payme/settings",
    "/api/payme/settings/import/unlimited",
    "/api/payme/settings/import/limits-all",
    "/api/payme/system/reset-data/status",
    "/api/payme/system/reset-data",
    "/api/payme/openrouter/models",
    "/api/payme/auth/phone",
    "/api/payme/auth/api-credentials",
    "/api/payme/auth/code",
    "/api/payme/auth/password",
    "/api/payme/auth/reauthorize",
    "/api/payme/auth/logout",
}

MONITORING_ROUTE_PATHS = {
    "/api/payme/runtime-logs",
    "/api/payme/runtime-logs/stream",
    "/api/payme/runtime-status",
    "/api/payme/server-status",
    "/api/payme/system-metrics",
    "/api/payme/duckdb/status",
    "/api/payme/duckdb/lock-status",
    "/api/payme/duckdb/refresh",
    "/api/payme/duckdb/export-parquet",
    "/api/payme/duckdb/materialize-parquet-sidecars",
    "/api/payme/duckdb/archive-legacy-cache",
    "/api/payme/stream/realtime",
    "/api/payme/runtime/status-stream",
    "/api/payme/dashboard/summary",
    "/api/payme/dashboard/summary-lite",
    "/api/payme/dashboard/details",
    "/api/payme/dashboard/logs",
    "/api/payme/dashboard/previews",
    "/api/payme/monitor/stream",
}

JOBS_ROUTE_PATHS = {
    "/api/payme/analysis/run",
    "/api/payme/jobs",
    "/api/payme/jobs/{job_id}",
    "/api/payme/jobs/{job_id}/cancel",
    "/api/payme/jobs/{job_id}/events",
}

EVENTS_ROUTE_PATHS = {
    "/api/payme/event-keywords",
    "/api/payme/events/status",
    "/api/payme/events/refresh",
    "/api/payme/events/config",
    "/api/payme/event-messages",
    "/api/payme/event-messages/delete",
    "/api/payme/calendar-events",
}

CRM_ROUTE_PATHS = {
    "/api/payme/crm/status",
    "/api/payme/crm/refresh",
    "/api/payme/crm/config",
    "/api/payme/crm/contacts",
    "/api/payme/crm/cleanup-telemost-phones",
}

OUTREACH_ROUTE_PATHS = {
    "/api/payme/outreach/items",
    "/api/payme/outreach/expand-values",
    "/api/payme/outreach/items/{item_id}",
    "/api/payme/outreach/sequences",
    "/api/payme/outreach/stats",
    "/api/payme/outreach/sequences/from-enreach/{item_id}",
    "/api/payme/outreach/sequences/{sequence_id}",
    "/api/payme/outreach/sequences/{sequence_id}/touches/{touch_key}",
}

CONTACTS_ROUTE_PATHS = {
    "/api/payme/contacts/status",
    "/api/payme/contacts/refresh",
    "/api/payme/contacts/config",
    "/api/payme/contacts/qualification-prompts",
    "/api/payme/contacts/{contact_key}/qualifications",
    "/api/payme/contacts/{contact_key}/qualify",
    "/api/payme/contacts/{contact_key}/do-not-contact",
    "/api/payme/contacts/chats",
    "/api/payme/contacts",
    "/api/payme/contacts/{contact_key}/messages",
}

JUR_ENTITIES_ROUTE_PATHS = {
    "/api/payme/jur-entities",
    "/api/payme/jur-entities/sync",
    "/api/payme/jur-entities/parser-add",
    "/api/payme/jur-entities/parser-remove",
}

MEDIA_ROUTE_PATHS = {
    "/api/payme/images",
    "/api/payme/images/text",
    "/api/payme/media/config",
    "/api/payme/media/status",
    "/api/payme/media/add",
    "/api/payme/media/add-many",
    "/api/payme/media/remove",
    "/api/payme/media/clear",
    "/api/payme/media/clear-all",
    "/api/payme/images/ocr-pending",
}

SEARCH_ROUTE_PATHS = {
    "/api/payme/search/messages",
    "/api/payme/search/context",
}

DEALS_ROUTE_PATHS = {
    "/api/payme/deals/status",
    "/api/payme/deals/reminders",
    "/api/payme/deals/conversion",
    "/api/payme/deals/profit-optimization",
    "/api/payme/deals/opportunities",
    "/api/payme/deals/north-star",
    "/api/payme/deals",
    "/api/payme/deals/kanban",
    "/api/payme/deals/audit",
    "/api/payme/deals/contract-templates",
    "/api/payme/deals/contract-metrics",
    "/api/payme/deals/product-margins",
    "/api/payme/deals/product-margins/{item_id}",
    "/api/payme/deals/event-sales-plan",
    "/api/payme/deals/{deal_id}/assistant",
    "/api/payme/deals/{deal_id}/negotiation-brief",
    "/api/payme/deals/{deal_id}/contract-kit",
    "/api/payme/deals/{deal_id}/contract-status",
    "/api/payme/deals/{deal_id}",
    "/api/payme/deals/from-outreach/{item_id}",
    "/api/payme/deals/{deal_id}/follow-up-sequence",
    "/api/payme/deals/daily-contacts",
    "/api/payme/needs/signals",
}

DATA_SOURCE_ROUTE_PATHS = {
    "/api/payme/data-sources/plugins",
    "/api/payme/data-sources",
    "/api/payme/data-sources/{plugin_type}/connect",
    "/api/payme/data-sources/{plugin_type}/introspect",
    "/api/payme/data-sources/{plugin_type}/preview",
    "/api/payme/data-sources/{source_id}/entities",
    "/api/payme/data-sources/{source_id}/disconnect",
    "/api/payme/data-sources/{source_id}/sync",
}

EXTRACTED_ROUTE_PATHS = (
    LICENSE_ROUTE_PATHS
    | ANALYSIS_ROUTE_PATHS
    | LEADS_ROUTE_PATHS
    | CHANNEL_ROUTE_PATHS
    | ROUTES_ROUTE_PATHS
    | CONFIG_ROUTE_PATHS
    | MONITORING_ROUTE_PATHS
    | JOBS_ROUTE_PATHS
    | EVENTS_ROUTE_PATHS
    | CRM_ROUTE_PATHS
    | OUTREACH_ROUTE_PATHS
    | CONTACTS_ROUTE_PATHS
    | JUR_ENTITIES_ROUTE_PATHS
    | MEDIA_ROUTE_PATHS
    | SEARCH_ROUTE_PATHS
    | DEALS_ROUTE_PATHS
    | DATA_SOURCE_ROUTE_PATHS
)

RAW_PAYLOAD_ROUTE_PATHS = {
    "/api/payme/tariffs",
    "/api/payme/update/status",
    "/api/payme/leads/{lead}/stream",
    "/api/payme/stream/leads",
    "/api/payme/leads/{lead}/jsonl",
    "/api/payme/leads/{lead}/llm",
    "/api/payme/send",
    "/api/payme/llm-run",
    "/api/payme/source/reload",
    "/api/payme/telegram-sync/control",
    "/api/payme/telegram-sync/pause",
    "/api/payme/telegram-sync/resume",
    "/api/payme/routes/status",
    "/api/payme/routes/refresh",
    "/api/payme/routes/messages",
    "/api/payme/routes/addresses",
    "/api/payme/routes/map-points",
    "/api/payme/routes/geocode",
    "/api/payme/system/reset-data/status",
    "/api/payme/system/reset-data",
    "/api/payme/runtime-logs/stream",
    "/api/payme/stream/realtime",
    "/api/payme/runtime/status-stream",
    "/api/payme/dashboard/summary",
    "/api/payme/dashboard/summary-lite",
    "/api/payme/dashboard/details",
    "/api/payme/dashboard/logs",
    "/api/payme/dashboard/previews",
    "/api/payme/monitor/stream",
    "/api/payme/crm/cleanup-telemost-phones",
    "/api/payme/outreach/expand-values",
}

EXTRACTED_ROUTER_MODULES = (
    "app.routers.license",
    "app.routers.analysis",
    "app.routers.leads",
    "app.routers.channels",
    "app.routers.routes",
    "app.routers.config",
    "app.routers.monitoring",
    "app.routers.jobs",
    "app.routers.events",
    "app.routers.crm",
    "app.routers.outreach",
    "app.routers.contacts",
    "app.routers.jur_entities",
    "app.routers.media",
    "app.routers.search",
    "app.routers.deals",
    "app.routers.data_sources",
)

EXTRACTED_SERVICE_MODULES = (
    "app.services.analysis",
    "app.services.channels",
    "app.services.config",
    "app.services.contacts",
    "app.services.crm",
    "app.services.deals",
    "app.services.events",
    "app.services.jur_entities",
    "app.services.leads",
    "app.services.legacy_api",
    "app.services.license",
    "app.services.media",
    "app.services.monitoring",
    "app.services.outreach",
    "app.services.routes",
    "app.services.search",
    "app.services.data_sources.api",
)

SCHEMA_MODULES = (
    "app.schemas.analysis",
    "app.schemas.channels",
    "app.schemas.config",
    "app.schemas.contacts",
    "app.schemas.crm",
    "app.schemas.deals",
    "app.schemas.events",
    "app.schemas.jur_entities",
    "app.schemas.leads",
    "app.schemas.legacy_api",
    "app.schemas.license",
    "app.schemas.media",
    "app.schemas.models",
    "app.schemas.monitoring",
    "app.schemas.outreach",
    "app.schemas.routes",
    "app.schemas.search",
    "app.schemas.data_sources",
)


class BackendRouterExtractionTest(unittest.TestCase):
    def test_license_router_declares_license_endpoint_paths(self):
        license_router = importlib.import_module("app.routers.license").router
        paths = {route.path for route in license_router.routes}
        self.assertEqual(LICENSE_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_license_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in LICENSE_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(LICENSE_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.license", route.endpoint.__module__)

    def test_leads_router_declares_leads_endpoint_paths(self):
        leads_router = importlib.import_module("app.routers.leads").router
        paths = {route.path for route in leads_router.routes}
        self.assertEqual(LEADS_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_leads_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in LEADS_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(LEADS_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.leads", route.endpoint.__module__)

    def test_analysis_router_declares_analysis_endpoint_paths(self):
        analysis_router = importlib.import_module("app.routers.analysis").router
        paths = {route.path for route in analysis_router.routes}
        self.assertEqual(ANALYSIS_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_analysis_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in ANALYSIS_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(ANALYSIS_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.analysis", route.endpoint.__module__)

    def test_channels_router_declares_channel_endpoint_paths(self):
        channels_router = importlib.import_module("app.routers.channels").router
        paths = {route.path for route in channels_router.routes}
        self.assertEqual(CHANNEL_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_channel_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in CHANNEL_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(CHANNEL_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.channels", route.endpoint.__module__)

    def test_routes_router_declares_routes_endpoint_paths(self):
        routes_router = importlib.import_module("app.routers.routes").router
        paths = {route.path for route in routes_router.routes}
        self.assertEqual(ROUTES_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_routes_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in ROUTES_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(ROUTES_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.routes", route.endpoint.__module__)

    def test_config_router_declares_config_endpoint_paths(self):
        config_router = importlib.import_module("app.routers.config").router
        paths = {route.path for route in config_router.routes}
        self.assertEqual(CONFIG_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_config_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in CONFIG_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(CONFIG_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.config", route.endpoint.__module__)

    def test_monitoring_router_declares_monitoring_endpoint_paths(self):
        monitoring_router = importlib.import_module("app.routers.monitoring").router
        paths = {route.path for route in monitoring_router.routes}
        self.assertEqual(MONITORING_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_monitoring_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in MONITORING_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(MONITORING_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.monitoring", route.endpoint.__module__)

    def test_jobs_router_declares_job_endpoint_paths(self):
        jobs_router = importlib.import_module("app.routers.jobs").router
        paths = {route.path for route in jobs_router.routes}
        self.assertEqual(JOBS_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_job_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in JOBS_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(JOBS_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.jobs", route.endpoint.__module__)

    def test_events_router_declares_event_endpoint_paths(self):
        events_router = importlib.import_module("app.routers.events").router
        paths = {route.path for route in events_router.routes}
        self.assertEqual(EVENTS_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_event_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in EVENTS_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(EVENTS_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.events", route.endpoint.__module__)

    def test_crm_router_declares_crm_endpoint_paths(self):
        crm_router = importlib.import_module("app.routers.crm").router
        paths = {route.path for route in crm_router.routes}
        self.assertEqual(CRM_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_crm_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in CRM_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(CRM_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.crm", route.endpoint.__module__)

    def test_outreach_router_declares_outreach_endpoint_paths(self):
        outreach_router = importlib.import_module("app.routers.outreach").router
        paths = {route.path for route in outreach_router.routes}
        self.assertEqual(OUTREACH_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_outreach_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in OUTREACH_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(OUTREACH_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.outreach", route.endpoint.__module__)

    def test_contacts_router_declares_contacts_endpoint_paths(self):
        contacts_router = importlib.import_module("app.routers.contacts").router
        paths = {route.path for route in contacts_router.routes}
        self.assertEqual(CONTACTS_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_contacts_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in CONTACTS_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(CONTACTS_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.contacts", route.endpoint.__module__)

    def test_data_sources_router_declares_data_source_endpoint_paths(self):
        data_sources_router = importlib.import_module("app.routers.data_sources").router
        paths = {route.path for route in data_sources_router.routes}
        self.assertEqual(DATA_SOURCE_ROUTE_PATHS, paths)

    def test_app_main_prefers_extracted_data_source_routes(self):
        main = importlib.import_module("app.main")
        first_routes = {}
        for route in main.app.routes:
            path = getattr(route, "path", "")
            if path in DATA_SOURCE_ROUTE_PATHS and path not in first_routes:
                first_routes[path] = route

        self.assertEqual(DATA_SOURCE_ROUTE_PATHS, set(first_routes))
        for path, route in first_routes.items():
            with self.subTest(path=path):
                self.assertEqual("app.routers.data_sources", route.endpoint.__module__)

    def test_extracted_routers_use_services_and_schemas(self):
        for module_name in EXTRACTED_ROUTER_MODULES:
            with self.subTest(module=module_name):
                source = inspect.getsource(importlib.import_module(module_name))
                self.assertIn("app.services", source)
                self.assertNotIn("import back", source)
                self.assertNotIn("back.", source)

    def test_route_snapshot_has_tags_and_declared_response_contract(self):
        for module_name in EXTRACTED_ROUTER_MODULES:
            router = importlib.import_module(module_name).router
            for route in router.routes:
                with self.subTest(module=module_name, path=route.path, methods=route.methods):
                    self.assertEqual(["payme"], route.tags)
                    if route.path not in RAW_PAYLOAD_ROUTE_PATHS:
                        self.assertIsNotNone(route.response_model)

    def test_backend_decomposition_packages_are_importable(self):
        for module_name in (
            "app.schemas.license",
            "app.schemas.analysis",
            "app.schemas.leads",
            "app.schemas.channels",
            "app.schemas.routes",
            "app.schemas.config",
            "app.schemas.monitoring",
            "app.schemas.jobs",
            "app.schemas.events",
            "app.schemas.crm",
            "app.schemas.outreach",
            "app.schemas.contacts",
            "app.schemas.jur_entities",
            "app.schemas.media",
            "app.schemas.search",
            "app.schemas.deals",
            "app.schemas.data_sources",
            "app.services.license",
            "app.services.analysis",
            "app.services.leads",
            "app.services.channels",
            "app.services.routes",
            "app.services.config",
            "app.services.monitoring",
            "app.services.jobs",
            "app.services.events",
            "app.services.crm",
            "app.services.outreach",
            "app.services.contacts",
            "app.services.jur_entities",
            "app.services.media",
            "app.services.search",
            "app.services.deals",
            "app.services.data_sources.api",
            "app.services.data_sources.registry",
            "app.services.data_sources.service",
            "app.services.telegram_sync",
            "app.repositories.legacy",
        ):
            with self.subTest(module=module_name):
                importlib.import_module(module_name)

    def test_schema_modules_do_not_import_back_after_dto_split(self):
        for module_name in SCHEMA_MODULES:
            with self.subTest(module=module_name):
                source = inspect.getsource(importlib.import_module(module_name))
                self.assertNotIn("from back import", source)
                self.assertNotIn("import back", source)

    def test_extracted_services_do_not_bulk_import_back(self):
        for module_name in EXTRACTED_SERVICE_MODULES:
            with self.subTest(module=module_name):
                source = inspect.getsource(importlib.import_module(module_name))
                self.assertNotIn("vars(legacy.back)", source)
                self.assertNotIn("legacy.back", source)

    def test_app_main_prunes_shadowed_legacy_routes(self):
        main = importlib.import_module("app.main")
        route_counts = Counter(
            (
                getattr(route, "path", ""),
                frozenset(getattr(route, "methods", ()) or ()),
            )
            for route in main.app.routes
            if getattr(route, "path", "") in EXTRACTED_ROUTE_PATHS
        )

        duplicates = {
            (path, tuple(sorted(methods))): count for (path, methods), count in route_counts.items() if count > 1
        }
        self.assertEqual({}, duplicates)


if __name__ == "__main__":
    unittest.main()
