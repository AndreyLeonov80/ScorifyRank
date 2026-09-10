"""SQLite/DuckDB table adapters with allowlisted schema mapping."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.schemas.data_sources import (
    CanonicalMessagePreviewDTO,
    DataSourceConnectResultDTO,
    DataSourceEntityDTO,
    DataSourcePluginManifestDTO,
    PluginCapabilitiesDTO,
)
from app.services.data_sources.base import BaseDataSourcePlugin


def _safe_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text or any(not (char.isalnum() or char == "_") for char in text):
        raise ValueError(f"Unsafe SQL identifier: {value}")
    return text


def _record_hash(parts: Iterable[Any]) -> str:
    raw = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SQLiteDataSourcePlugin(BaseDataSourcePlugin):
    manifest = DataSourcePluginManifestDTO(
        plugin_type="sqlite",
        title="SQLite database",
        database_types=["sqlite", "snapshot"],
        description="Read-only adapter for ready-made SQLite databases.",
        capabilities=PluginCapabilitiesDTO(
            read_only=True,
            incremental_sync=True,
            full_rescan=True,
            authors=True,
            message_links=False,
            pii_sensitive=True,
        ),
    )

    def _connect_raw(self, connection: Dict[str, Any]) -> sqlite3.Connection:
        path = Path(str(connection.get("path") or "")).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"SQLite database not found: {path}")
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    def connect(self, connection: Dict[str, Any]) -> DataSourceConnectResultDTO:
        with self._connect_raw(connection) as conn:
            version = conn.execute("select sqlite_version()").fetchone()[0]
        return DataSourceConnectResultDTO(
            ok=True,
            plugin_type=self.manifest.plugin_type,
            message="SQLite подключен",
            metadata={"sqlite_version": version},
        )

    def introspect(self, connection: Dict[str, Any]) -> List[DataSourceEntityDTO]:
        with self._connect_raw(connection) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            entities: List[DataSourceEntityDTO] = []
            for row in rows:
                table = str(row["name"])
                count = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                entities.append(DataSourceEntityDTO(entity_key=table, entity_type="table", title=table, row_count=count))
            return entities

    def preview(
        self,
        connection: Dict[str, Any],
        mapping: Dict[str, Any],
        *,
        limit: int = 20,
    ) -> List[CanonicalMessagePreviewDTO]:
        table = _safe_identifier(mapping.get("table"))
        id_column = _safe_identifier(mapping.get("id_column") or "id")
        author_column = _safe_identifier(mapping.get("author_column") or "author")
        text_column = _safe_identifier(mapping.get("text_column") or "text")
        created_at_column = _safe_identifier(mapping.get("created_at_column") or "created_at")
        limit_value = max(1, min(100, int(limit or 20)))
        with self._connect_raw(connection) as conn:
            query = (
                f'SELECT "{id_column}" AS external_message_id, '
                f'"{author_column}" AS author_display_name, '
                f'"{text_column}" AS text, '
                f'"{created_at_column}" AS created_at '
                f'FROM "{table}" ORDER BY "{created_at_column}" DESC LIMIT ?'
            )
            rows = conn.execute(query, (limit_value,)).fetchall()
        return [
            CanonicalMessagePreviewDTO(
                source_type=self.manifest.plugin_type,
                entity_key=table,
                external_message_id=str(row["external_message_id"]),
                author_display_name=str(row["author_display_name"] or ""),
                created_at=str(row["created_at"] or ""),
                text=str(row["text"] or ""),
                raw_text=str(row["text"] or ""),
                raw_record_hash=_record_hash([table, row["external_message_id"], row["text"], row["created_at"]]),
                payload_json={"mapping": {key: mapping.get(key) for key in sorted(mapping)}},
            )
            for row in rows
        ]


class DuckDBDataSourcePlugin(SQLiteDataSourcePlugin):
    manifest = DataSourcePluginManifestDTO(
        plugin_type="duckdb",
        title="DuckDB database",
        database_types=["duckdb", "snapshot"],
        description="Read-only adapter for ready-made DuckDB databases.",
        capabilities=PluginCapabilitiesDTO(
            read_only=True,
            incremental_sync=True,
            full_rescan=True,
            authors=True,
            message_links=False,
            pii_sensitive=True,
        ),
    )

    def _resolve_duckdb_path(self, connection: Dict[str, Any]) -> Tuple[Path, Path, bool, Optional[str]]:
        requested_path = Path(str(connection.get("path") or "")).expanduser()
        if not requested_path.exists():
            raise FileNotFoundError(f"DuckDB database not found: {requested_path}")
        prefer_snapshot = bool(connection.get("prefer_snapshot", True))
        snapshot_path = requested_path.with_name("gramlead-read.duckdb")
        if prefer_snapshot and requested_path.name == "gramlead.duckdb" and snapshot_path.exists():
            return (
                requested_path,
                snapshot_path,
                True,
                "Writer DuckDB path was redirected to gramlead-read.duckdb snapshot for read-only external access.",
            )
        return requested_path, requested_path, False, None

    def _connect_duckdb(self, connection: Dict[str, Any]):
        try:
            import duckdb  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on runtime image
            raise RuntimeError("duckdb package is not installed") from exc
        _requested_path, opened_path, _snapshot_used, _warning = self._resolve_duckdb_path(connection)
        return duckdb.connect(str(opened_path), read_only=True)

    def connect(self, connection: Dict[str, Any]) -> DataSourceConnectResultDTO:
        requested_path, opened_path, snapshot_used, warning = self._resolve_duckdb_path(connection)
        conn = self._connect_duckdb(connection)
        try:
            version = conn.execute("select version()").fetchone()[0]
        finally:
            conn.close()
        return DataSourceConnectResultDTO(
            ok=True,
            plugin_type=self.manifest.plugin_type,
            message="DuckDB подключен",
            metadata={
                "duckdb_version": version,
                "requested_path": str(requested_path),
                "opened_path": str(opened_path),
                "read_only": True,
                "snapshot_used": snapshot_used,
                "warning": warning,
            },
        )

    def introspect(self, connection: Dict[str, Any]) -> List[DataSourceEntityDTO]:
        conn = self._connect_duckdb(connection)
        try:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog') ORDER BY table_name"
            ).fetchall()
            entities = []
            for (table,) in rows:
                safe_table = _safe_identifier(table)
                count = conn.execute(f'SELECT count(*) FROM "{safe_table}"').fetchone()[0]
                entities.append(
                    DataSourceEntityDTO(entity_key=safe_table, entity_type="table", title=safe_table, row_count=int(count))
                )
            return entities
        finally:
            conn.close()

    def preview(
        self,
        connection: Dict[str, Any],
        mapping: Dict[str, Any],
        *,
        limit: int = 20,
    ) -> List[CanonicalMessagePreviewDTO]:
        table = _safe_identifier(mapping.get("table"))
        id_column = _safe_identifier(mapping.get("id_column") or "id")
        author_column = _safe_identifier(mapping.get("author_column") or "author")
        text_column = _safe_identifier(mapping.get("text_column") or "text")
        created_at_column = _safe_identifier(mapping.get("created_at_column") or "created_at")
        limit_value = max(1, min(100, int(limit or 20)))
        conn = self._connect_duckdb(connection)
        try:
            rows: Sequence[Sequence[Any]] = conn.execute(
                f'SELECT "{id_column}", "{author_column}", "{text_column}", "{created_at_column}" '
                f'FROM "{table}" ORDER BY "{created_at_column}" DESC LIMIT ?',
                [limit_value],
            ).fetchall()
        finally:
            conn.close()
        return [
            CanonicalMessagePreviewDTO(
                source_type=self.manifest.plugin_type,
                entity_key=table,
                external_message_id=str(row[0]),
                author_display_name=str(row[1] or ""),
                text=str(row[2] or ""),
                raw_text=str(row[2] or ""),
                created_at=str(row[3] or ""),
                raw_record_hash=_record_hash([table, row[0], row[2], row[3]]),
                payload_json={"mapping": {key: mapping.get(key) for key in sorted(mapping)}},
            )
            for row in rows
        ]
