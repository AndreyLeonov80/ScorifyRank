"""Repository adapters for X-Files deals storage/status."""

from __future__ import annotations

from typing import Any, Callable, List


def load_deal_items(load_deals: Callable[..., List[Any]], *, limit: int = 20000) -> List[Any]:
    return list(load_deals(limit=limit) or [])


def postgres_waiting(*, postgres_dsn: str, psycopg_module: Any, postgresql_available: bool) -> bool:
    return bool(postgres_dsn and psycopg_module is not None and not postgresql_available)


def postgres_status_message(
    *,
    postgres_dsn: str,
    psycopg_module: Any,
    postgresql_available: bool,
    migration_error: str,
) -> str:
    if postgresql_available:
        return "Сделки читаются и пишутся в PostgreSQL"
    if not postgres_dsn:
        return "PostgreSQL DSN не настроен, сделки временно хранятся в state.json"
    if psycopg_module is None:
        return "PostgreSQL DSN настроен, но psycopg не установлен в runtime"
    if migration_error:
        return "PostgreSQL доступен, но миграция сделок из state.json пока не завершилась"
    return "PostgreSQL подключается или временно недоступен, сделки пока отображаются из state.json"

