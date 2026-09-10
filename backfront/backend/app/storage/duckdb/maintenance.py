"""DuckDB maintenance helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple


LIGHT_DUCKDB_INDEXES: Tuple[Tuple[str, str], ...] = (
    ("idx_messages_raw_source", "CREATE INDEX IF NOT EXISTS idx_messages_raw_source ON messages_raw(source_jsonl)"),
    ("idx_messages_raw_source_key", "CREATE INDEX IF NOT EXISTS idx_messages_raw_source_key ON messages_raw(source_key)"),
    ("idx_file_registry_name", "CREATE INDEX IF NOT EXISTS idx_file_registry_name ON file_registry(file_name)"),
    ("idx_file_registry_source_key", "CREATE INDEX IF NOT EXISTS idx_file_registry_source_key ON file_registry(source_key)"),
)


HEAVY_DUCKDB_INDEXES: Tuple[Tuple[str, str], ...] = (
    (
        "idx_messages_raw_source_date_message",
        "CREATE INDEX IF NOT EXISTS idx_messages_raw_source_date_message ON messages_raw(source_jsonl, date_utc, message_id)",
    ),
    (
        "idx_messages_raw_source_key_message",
        "CREATE INDEX IF NOT EXISTS idx_messages_raw_source_key_message ON messages_raw(source_key, message_id)",
    ),
    (
        "idx_messages_raw_source_key_date_raw",
        "CREATE INDEX IF NOT EXISTS idx_messages_raw_source_key_date_raw ON messages_raw(source_key, date_utc_raw, message_id)",
    ),
    ("idx_messages_raw_chat_message", "CREATE INDEX IF NOT EXISTS idx_messages_raw_chat_message ON messages_raw(chat_username, message_id)"),
    ("idx_messages_raw_sender", "CREATE INDEX IF NOT EXISTS idx_messages_raw_sender ON messages_raw(sender_username, sender_id)"),
    ("idx_crm_contacts_lead_date", "CREATE INDEX IF NOT EXISTS idx_crm_contacts_lead_date ON crm_contacts(lead, date_utc_raw)"),
    ("idx_crm_contacts_sender", "CREATE INDEX IF NOT EXISTS idx_crm_contacts_sender ON crm_contacts(sender_username, sender_name)"),
    ("idx_event_messages_date", "CREATE INDEX IF NOT EXISTS idx_event_messages_date ON event_messages(date_utc_raw)"),
    ("idx_event_messages_event_date", "CREATE INDEX IF NOT EXISTS idx_event_messages_event_date ON event_messages(event_date)"),
    ("idx_event_messages_hash", "CREATE INDEX IF NOT EXISTS idx_event_messages_hash ON event_messages(keyword_hash)"),
)


def _execute_index_statements(conn: Any, statements: Iterable[Tuple[str, str]]) -> None:
    for _, sql in statements:
        conn.execute(sql)


def ensure_indexes(conn: Any, *, include_heavy: bool = True) -> None:
    _execute_index_statements(conn, LIGHT_DUCKDB_INDEXES)
    if include_heavy:
        _execute_index_statements(conn, HEAVY_DUCKDB_INDEXES)


def indexes_ready_after_bootstrap(*, defer_heavy_indexes: bool, bootstrap_mode: bool, status_snapshot: Dict[str, object]) -> bool:
    if defer_heavy_indexes and bootstrap_mode:
        return True
    if not defer_heavy_indexes:
        return True
    return bool(status_snapshot.get("indexes_ready") or not bootstrap_mode)
