"""Persistent metadata service for external data source plugins."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from app.core.runtime_paths import STATE_PATH
from app.core.state import StateRepository
from app.schemas.data_sources import (
    DataSourceActionDTO,
    DataSourceEntitySelectionPayload,
    DataSourcePageDTO,
    DataSourceRecordDTO,
    DataSourceRegistrationPayload,
    SelectedDataSourceEntityDTO,
)

DATA_SOURCES_STATE_KEY = "_data_source_plugins"
SELECTED_PLUGIN_SOURCES_STATE_KEY = "_selected_plugin_sources"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(value: Dict[str, Any]) -> str:
    raw = repr(sorted((str(key), str(val)) for key, val in value.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _selector(source_type: str, source_id: str, entity_key: str) -> str:
    return f"{source_type}:{source_id}:{entity_key}"


class DataSourceService:
    def __init__(self, state_path: Path | None = None):
        self.state_path = state_path or STATE_PATH
        self._state_repository = StateRepository(self.state_path)

    def _load_state(self) -> Dict[str, Any]:
        state = self._state_repository.load()
        state.setdefault(DATA_SOURCES_STATE_KEY, {})
        state.setdefault(SELECTED_PLUGIN_SOURCES_STATE_KEY, {})
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        self._state_repository.save(state)

    def register_source(self, payload: Dict[str, Any] | DataSourceRegistrationPayload) -> DataSourceRecordDTO:
        data = payload if isinstance(payload, DataSourceRegistrationPayload) else DataSourceRegistrationPayload(**payload)
        state = self._load_state()
        source_id = f"ds_{uuid.uuid4().hex[:16]}"
        now = _now_iso()
        external_id = data.external_id or _fingerprint(data.connection)
        record = DataSourceRecordDTO(
            source_id=source_id,
            source_type=data.source_type.strip().lower(),
            source_name=data.source_name.strip() or data.source_type,
            external_id=external_id,
            enabled=True,
            scan_enabled=True,
            payload_json={
                **data.payload,
                "connection_metadata": {
                    key: ("***" if "password" in key.lower() or "token" in key.lower() else value)
                    for key, value in data.connection.items()
                },
            },
            created_at=now,
            updated_at=now,
        )
        state[DATA_SOURCES_STATE_KEY][source_id] = record.model_dump()
        self._save_state(state)
        return record

    def list_sources(self) -> List[DataSourceRecordDTO]:
        state = self._load_state()
        selected = state.get(SELECTED_PLUGIN_SOURCES_STATE_KEY, {})
        records: List[DataSourceRecordDTO] = []
        for raw in state.get(DATA_SOURCES_STATE_KEY, {}).values():
            record = DataSourceRecordDTO(**raw)
            record.entities = [
                SelectedDataSourceEntityDTO(**item)
                for item in selected.values()
                if isinstance(item, dict) and item.get("source_id") == record.source_id
            ]
            records.append(record)
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records

    def page(self) -> DataSourcePageDTO:
        items = self.list_sources()
        return DataSourcePageDTO(items=items, total=len(items))

    def select_entity(
        self,
        source_id: str,
        payload: Dict[str, Any] | DataSourceEntitySelectionPayload,
    ) -> SelectedDataSourceEntityDTO:
        data = payload if isinstance(payload, DataSourceEntitySelectionPayload) else DataSourceEntitySelectionPayload(**payload)
        state = self._load_state()
        source = state.get(DATA_SOURCES_STATE_KEY, {}).get(source_id)
        if not isinstance(source, dict):
            raise KeyError(f"Unknown data source: {source_id}")
        now = _now_iso()
        selector = _selector(str(source["source_type"]), source_id, data.entity_key)
        selected = SelectedDataSourceEntityDTO(
            selector=selector,
            source_id=source_id,
            source_type=str(source["source_type"]),
            entity_key=data.entity_key,
            entity_type=data.entity_type,
            title=data.title or data.entity_key,
            enabled=True,
            is_selected=True,
            is_scan_enabled=True,
            payload_json={
                **data.payload_json,
                "display_name": data.title or data.entity_key,
                "plugin_source_name": source.get("source_name", ""),
            },
            created_at=now,
            updated_at=now,
        )
        state[SELECTED_PLUGIN_SOURCES_STATE_KEY][selector] = selected.model_dump()
        self._save_state(state)
        return selected

    def disconnect_source(self, source_id: str) -> DataSourceRecordDTO:
        state = self._load_state()
        source = state.get(DATA_SOURCES_STATE_KEY, {}).get(source_id)
        if not isinstance(source, dict):
            raise KeyError(f"Unknown data source: {source_id}")
        source["enabled"] = False
        source["scan_enabled"] = False
        source["updated_at"] = _now_iso()
        for item in state.get(SELECTED_PLUGIN_SOURCES_STATE_KEY, {}).values():
            if isinstance(item, dict) and item.get("source_id") == source_id:
                item["enabled"] = False
                item["is_scan_enabled"] = False
                item["updated_at"] = source["updated_at"]
        self._save_state(state)
        return DataSourceRecordDTO(**source)


default_service = DataSourceService()
