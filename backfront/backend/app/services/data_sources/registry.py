"""Registry of built-in data source plugins."""

from __future__ import annotations

from typing import Dict, List

from app.schemas.data_sources import (
    DataSourceConnectResultDTO,
    DataSourceEntityDTO,
    DataSourcePluginManifestDTO,
    PluginCapabilitiesDTO,
)
from app.services.data_sources.base import BaseDataSourcePlugin
from app.services.data_sources.sql_table import DuckDBDataSourcePlugin, SQLiteDataSourcePlugin


class TelegramDataSourcePlugin(BaseDataSourcePlugin):
    manifest = DataSourcePluginManifestDTO(
        plugin_type="telegram",
        title="Telegram",
        version="1.0.0",
        database_types=["telegram"],
        description="Built-in Telegram adapter backed by Telethon, JSONL, DuckDB and PostgreSQL-compatible state.",
        capabilities=PluginCapabilitiesDTO(
            read_only=False,
            incremental_sync=True,
            full_rescan=True,
            attachments=True,
            authors=True,
            message_links=True,
            writeback=True,
            pii_sensitive=True,
        ),
    )

    def connect(self, connection):
        return DataSourceConnectResultDTO(ok=True, plugin_type="telegram", message="Telegram adapter встроен")

    def introspect(self, connection):
        return []

    def preview(self, connection, mapping, *, limit=20):
        return []


class UnsupportedManifestOnlyPlugin(BaseDataSourcePlugin):
    def __init__(self, plugin_type: str, title: str, database_types: List[str]):
        self.manifest = DataSourcePluginManifestDTO(
            plugin_type=plugin_type,
            title=title,
            database_types=database_types,
            description="Manifest is available; runtime adapter is planned after SQLite/DuckDB MVP.",
            capabilities=PluginCapabilitiesDTO(read_only=True, incremental_sync=True, pii_sensitive=True),
        )

    def connect(self, connection):
        return DataSourceConnectResultDTO(
            ok=False,
            plugin_type=self.manifest.plugin_type,
            message=f"{self.manifest.title} adapter planned; enable SQLite/DuckDB MVP first",
        )

    def introspect(self, connection):
        return []

    def preview(self, connection, mapping, *, limit=20):
        return []


class DataSourcePluginRegistry:
    def __init__(self):
        plugins = [
            TelegramDataSourcePlugin(),
            SQLiteDataSourcePlugin(),
            DuckDBDataSourcePlugin(),
            UnsupportedManifestOnlyPlugin("postgres", "PostgreSQL database", ["postgresql", "supabase"]),
            UnsupportedManifestOnlyPlugin("mysql", "MySQL/MariaDB database", ["mysql", "mariadb"]),
            UnsupportedManifestOnlyPlugin("clickhouse", "ClickHouse database", ["clickhouse"]),
            UnsupportedManifestOnlyPlugin("custom", "Custom SDK adapter", ["custom"]),
        ]
        self._plugins: Dict[str, BaseDataSourcePlugin] = {plugin.manifest.plugin_type: plugin for plugin in plugins}

    def list_manifests(self) -> List[DataSourcePluginManifestDTO]:
        return [plugin.manifest for plugin in self._plugins.values()]

    def get(self, plugin_type: str) -> BaseDataSourcePlugin:
        key = str(plugin_type or "").strip().lower()
        if key not in self._plugins:
            raise KeyError(f"Unknown data source plugin: {plugin_type}")
        return self._plugins[key]


_registry = DataSourcePluginRegistry()


def plugin_registry() -> DataSourcePluginRegistry:
    return _registry
