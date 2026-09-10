"""Shared X-Files tariff catalog and backend-enforcement helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_TARIFF_DURATION_DAYS = 30
UNLIMITED_IMPORT_HISTORY_MONTHS_MAX = 0
UNLIMITED_IMPORT_MESSAGE_LIMIT_MAX = 0

BASE_FEATURES: dict[str, bool] = {
    "postgresql": True,
    "deals": True,
    "duckdb": True,
    "telegram_sync": True,
    "crm": True,
    "events": True,
    "calendar": True,
    "contacts": True,
    "routes": True,
    "openrouter": True,
    "ocr": False,
    "media": True,
    "outreach": True,
    "enreach": True,
    "painpay": True,
    "telegram_unlimited_import": False,
    "data_source_plugins": False,
    "data_source_writeback": False,
}

TARIFF_PLANS: dict[str, dict[str, Any]] = {
    "free-demo": {
        "key": "free-demo",
        "title": "Free demo",
        "description": "Минимальный демо-тариф: 1 канал, 1 личная переписка, LLM-анализ, PostgreSQL и Deals.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": 2,
        "example_allocation": {"channels": 1, "personal": 1, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": False},
        "upgrade_hint": "Введите invite-code Starter, чтобы включить OCR и 6 источников.",
    },
    "free-demo-first-touch-vip": {
        "key": "free-demo-first-touch-vip",
        "title": "Free demo first touch VIP",
        "description": "Первый VIP-показ: весь функционал по умолчанию, короткий срок, до 10 источников суммарно.",
        "duration_days": 7,
        "telegram_sources_total": 10,
        "example_allocation": {"channels": 5, "personal": 5, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": True, "telegram_unlimited_import": True, "data_source_plugins": True},
        "upgrade_hint": "Продлите VIP или выберите коммерческий тариф по реальной потребности.",
    },
    "starter": {
        "key": "starter",
        "title": "Starter",
        "description": "Стартовый коммерческий тариф: 6 источников суммарно, OCR включён.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": 6,
        "example_allocation": {"channels": 2, "personal": 4, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": True},
        "upgrade_hint": "Growth 20 даст больше источников для регулярной лидогенерации.",
    },
    "growth-20": {
        "key": "growth-20",
        "title": "Growth 20",
        "description": "Growth-тариф на 20 источников суммарно.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": 20,
        "example_allocation": {"channels": 1, "personal": 19, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": True},
        "upgrade_hint": "Growth 50 подходит, если нужно больше отраслевых каналов и личных диалогов.",
    },
    "growth-50": {
        "key": "growth-50",
        "title": "Growth 50",
        "description": "Growth-тариф на 50 источников суммарно.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": 50,
        "example_allocation": {"channels": 10, "personal": 40, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": True},
        "upgrade_hint": "Growth 100 подходит для широкой сетки продаж.",
    },
    "growth-100": {
        "key": "growth-100",
        "title": "Growth 100",
        "description": "Growth-тариф на 100 источников суммарно.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": 100,
        "example_allocation": {"channels": 10, "personal": 90, "groups": 0, "bots": 0},
        "features": {**BASE_FEATURES, "ocr": True},
        "upgrade_hint": "Enterprise нужен для custom-лимитов, сроков и offline bundle.",
    },
    "enterprise": {
        "key": "enterprise",
        "title": "Enterprise",
        "description": "Custom-лимиты, custom-срок, offline bundle и расширенные политики поставки.",
        "duration_days": DEFAULT_TARIFF_DURATION_DAYS,
        "telegram_sources_total": None,
        "example_allocation": {"channels": "custom", "personal": "custom", "groups": "custom", "bots": "custom"},
        "features": {
            **BASE_FEATURES,
            "ocr": True,
            "telegram_unlimited_import": True,
            "data_source_plugins": True,
            "data_source_writeback": True,
        },
        "upgrade_hint": "Настраивается владельцем продукта под договор.",
    },
}


def tariff_plan(plan_key: str | None) -> dict[str, Any]:
    key = str(plan_key or "free-demo").strip() or "free-demo"
    return deepcopy(TARIFF_PLANS.get(key) or TARIFF_PLANS["free-demo"])


def tariff_catalog() -> list[dict[str, Any]]:
    return [deepcopy(plan) for plan in TARIFF_PLANS.values()]


def tariff_features(plan_key: str | None) -> dict[str, bool]:
    features = tariff_plan(plan_key).get("features")
    return deepcopy(features if isinstance(features, dict) else BASE_FEATURES)


def tariff_source_limit(plan_key: str | None) -> int | None:
    value = tariff_plan(plan_key).get("telegram_sources_total")
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def tariff_license_limits(plan_key: str | None, *, override_source_limit: int | None = None) -> dict[str, Any]:
    source_limit = override_source_limit if override_source_limit is not None else tariff_source_limit(plan_key)
    limits: dict[str, Any] = {
        "users": 1,
        # Safe default for client demo delivery: do not read years of history by accident.
        "import_history_months_max": 1,
        "import_message_limit_max": 1000,
        "data_source_plugins_max": 0,
        "data_source_plugin_entities_max": 0,
        "data_source_plugin_rows_max": 0,
    }
    if str(plan_key or "").strip() == "enterprise":
        limits["import_history_months_max"] = UNLIMITED_IMPORT_HISTORY_MONTHS_MAX
        limits["import_message_limit_max"] = UNLIMITED_IMPORT_MESSAGE_LIMIT_MAX
    if source_limit is not None:
        limits["telegram_sources_total"] = int(source_limit)
        limits["channels_chats_bots_total"] = int(source_limit)
    return limits


def license_capabilities(plan_key: str | None) -> dict[str, Any]:
    limits = tariff_license_limits(plan_key)
    features = tariff_features(plan_key)
    return {
        "license_update": True,
        "license_upgrade": True,
        "license_renew": True,
        "local_import_limit_override": True,
        "telegram_unlimited_import": bool(features.get("telegram_unlimited_import"))
        or limits.get("import_history_months_max") == 0
        or limits.get("import_message_limit_max") == 0,
        "import_history_months_max": limits.get("import_history_months_max", 1),
        "import_message_limit_max": limits.get("import_message_limit_max", 1000),
        "telegram_sources_total": limits.get("telegram_sources_total"),
        "data_source_plugins": bool(features.get("data_source_plugins")),
        "data_source_writeback": bool(features.get("data_source_writeback")),
        "data_source_plugins_max": limits.get("data_source_plugins_max", 0),
        "data_source_plugin_entities_max": limits.get("data_source_plugin_entities_max", 0),
        "data_source_plugin_rows_max": limits.get("data_source_plugin_rows_max", 0),
        "features": features,
    }
