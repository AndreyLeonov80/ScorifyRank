"""Menu catalog and license menu routing constants."""

from __future__ import annotations

from typing import Dict, List

XFILES_MENU_CATALOG: List[Dict[str, str]] = [
    {"key": "chats", "href": "/index.html", "label": "Чаты", "group": "core"},
    {"key": "contacts", "href": "/contacts.html", "label": "Контакты", "group": "core"},
    {"key": "import", "href": "/import.html", "label": "Импорт", "group": "core"},
    {"key": "grid", "href": "/grid.html", "label": "Sync", "group": "core"},
    {"key": "calendar", "href": "/calendar.html", "label": "Календарь", "group": "core"},
    {"key": "dashboard", "href": "/dashboard.html", "label": "Dashboard", "group": "ext"},
    {"key": "logs", "href": "/logs.html", "label": "Логи", "group": "ext"},
    {"key": "media", "href": "/media.html", "label": "Media", "group": "ext"},
    {"key": "settings", "href": "/settings.html", "label": "Настройки", "group": "ext"},
    {"key": "needs", "href": "/needs.html", "label": "Потребности", "group": "core"},
    {"key": "crm", "href": "/crm.html", "label": "CRM", "group": "core"},
    {"key": "outreach", "href": "/outreach.html", "label": "enReach", "group": "core"},
    {"key": "outreach-future", "href": "/outreach-future.html", "label": "outReach", "group": "core"},
    {"key": "events", "href": "/events.html", "label": "Мероприятия", "group": "core"},
    {"key": "routes", "href": "/routes.html", "label": "Маршруты", "group": "core"},
    {"key": "jur-entities", "href": "/jur-entities.html", "label": "ЮР. Лица", "group": "core"},
    {"key": "deals", "href": "/deals.html", "label": "Сделки", "group": "core"},
    {"key": "tariffs", "href": "/tariffs.html", "label": "Тарифы", "group": "ext"},
    {"key": "autodeal-10pl-xpl", "href": "/autodeal-10pl-xpl.html", "label": "10PL & xPL = m&a автозаказ", "group": "ext"},
    {"key": "buypower", "href": "/buypower.html", "label": "BuyPower", "group": "ext"},
    {"key": "producers-match", "href": "/producers-match.html", "label": "Продюсеры мэтч сделок", "group": "ext"},
    {"key": "data-sources", "href": "/data-sources.html", "label": "Источники данных", "group": "ext"},
    {"key": "gramlead-earnings", "href": "/gramlead-earnings.html", "label": "Как зарабатывать", "group": "ext"},
    {"key": "licenses", "href": "/licenses.html", "label": "Лицензии", "group": "ext"},
    {"key": "sales-department", "href": "/sales-department.html", "label": "Отдел продаж", "group": "ext"},
    {"key": "my-products", "href": "/my-products.html", "label": "Мои продукты", "group": "ext"},
    {"key": "sales-systems-100", "href": "/sales-systems-100.html", "label": "100 систем продаж", "group": "ext"},
    {"key": "ai-agent-chat", "href": "/ai-agent-chat.html", "label": "Чат с ИИ-агентами", "group": "ext"},
    {"key": "telegram-reauthorize", "href": "/setup_wizard.html", "label": "Переавторизовать Telegram", "group": "ext"},
    {"key": "telegram-logout", "href": "#", "label": "Выйти", "group": "ext", "action": "logoutTelegram"},
]
XFILES_DEFAULT_DISABLED_MENU_KEYS = {
    "contacts",
    "calendar",
    "media",
    "needs",
    "crm",
    "outreach",
    "outreach-future",
    "events",
    "routes",
    "jur-entities",
    "deals",
    "tariffs",
    "producers-match",
    "autodeal-10pl-xpl",
    "buypower",
    "data-sources",
    "gramlead-earnings",
    "licenses",
    "sales-department",
    "my-products",
    "sales-systems-100",
    "ai-agent-chat",
    "telegram-reauthorize",
    "logs",
}
XFILES_CLIENT_DELIVERY_HIDDEN_MENU_KEYS = {
    "producers-match",
    "autodeal-10pl-xpl",
    "buypower",
    "jur-entities",
    "data-sources",
    "gramlead-earnings",
    "licenses",
    "sales-department",
    "my-products",
    "sales-systems-100",
    "ai-agent-chat",
}
XFILES_CLIENT_DELIVERY_MENU_KEYS = [
    item["key"]
    for item in XFILES_MENU_CATALOG
    if item["key"] not in XFILES_CLIENT_DELIVERY_HIDDEN_MENU_KEYS
]
XFILES_LICENSE_FALLBACK_MENU_KEYS = [
    "chats",
    "import",
    "grid",
    "dashboard",
    "settings",
    "telegram-logout",
]
XFILES_LICENSE_PUBLIC_API_PREFIXES = (
    "/api/payme/license",
    "/api/payme/auth",
    "/api/payme/tariffs",
)
XFILES_LICENSE_PUBLIC_API_PATHS = {
    "/api/payme/settings",
}
XFILES_LICENSE_RENEWAL_MENU_KEYS = {"settings"}
XFILES_LICENSE_RENEWAL_PUBLIC_HTML = {"/settings.html"}
XFILES_LICENSE_BLOCKED_STATUSES = {
    "missing",
    "verifier_missing",
    "invite_invalid",
    "not_activated",
    "inactive",
    "expired",
    "revoked",
    "blocked",
    "denied",
    "tampered",
    "clock_tampered",
    "clock_rollback",
    "rollback_detected",
    "device_mismatch",
    "license_server_unavailable",
    "license_server_invalid_response",
}
XFILES_API_MENU_PREFIXES: List[tuple[str, str]] = [
    ("/api/payme/deals", "deals"),
    ("/api/payme/outreach", "outreach"),
    ("/api/payme/contacts", "contacts"),
    ("/api/payme/crm", "crm"),
    ("/api/payme/calendar-events", "calendar"),
    ("/api/payme/event", "events"),
    ("/api/payme/routes", "routes"),
    ("/api/payme/media", "media"),
    ("/api/payme/images", "media"),
    ("/api/payme/jur-entities", "jur-entities"),
    ("/api/payme/telegram/dialogs", "import"),
    ("/api/payme/import-sync", "import"),
    ("/api/payme/source", "grid"),
    ("/api/payme/leads", "chats"),
    ("/api/payme/send", "chats"),
    ("/api/payme/llm-run", "chats"),
    ("/api/payme/settings", "settings"),
    ("/api/payme/openrouter", "settings"),
    ("/api/payme/runtime-logs", "logs"),
    ("/api/payme/runtime-status", "dashboard"),
    ("/api/payme/server-status", "dashboard"),
    ("/api/payme/system-metrics", "dashboard"),
    ("/api/payme/duckdb", "dashboard"),
    ("/api/payme/telegram-sync", "dashboard"),
    ("/api/payme/dashboard", "dashboard"),
]
XFILES_HTML_MENU_PATHS: Dict[str, str] = {
    str(item.get("href") or ""): str(item.get("key") or "")
    for item in XFILES_MENU_CATALOG
    if str(item.get("href") or "").endswith(".html")
}
