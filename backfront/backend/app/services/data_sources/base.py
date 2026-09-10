"""Base interfaces for pluggable external data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.schemas.data_sources import (
    CanonicalMessagePreviewDTO,
    DataSourceConnectResultDTO,
    DataSourceEntityDTO,
    DataSourcePluginManifestDTO,
)


class BaseDataSourcePlugin(ABC):
    manifest: DataSourcePluginManifestDTO

    @abstractmethod
    def connect(self, connection: Dict[str, Any]) -> DataSourceConnectResultDTO:
        """Validate access without importing client data."""

    @abstractmethod
    def introspect(self, connection: Dict[str, Any]) -> List[DataSourceEntityDTO]:
        """Return externally available tables/entities."""

    @abstractmethod
    def preview(
        self,
        connection: Dict[str, Any],
        mapping: Dict[str, Any],
        *,
        limit: int = 20,
    ) -> List[CanonicalMessagePreviewDTO]:
        """Return normalized message-like rows."""

    def sync(self, connection: Dict[str, Any], mapping: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "mode": "metadata-only", "rows": len(self.preview(connection, mapping, limit=100))}
