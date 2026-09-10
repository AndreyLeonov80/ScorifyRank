"""Canonical data source plugin schemas.

The plugin layer intentionally mirrors Telegram concepts: a source exposes
entities, entities expose message-like rows, and selected entities use a
namespaced selector that existing screens can understand.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PluginCapabilitiesDTO(BaseModel):
    read_only: bool = True
    incremental_sync: bool = False
    full_rescan: bool = False
    attachments: bool = False
    authors: bool = True
    message_links: bool = False
    writeback: bool = False
    pii_sensitive: bool = True


class DataSourcePluginManifestDTO(BaseModel):
    plugin_type: str
    title: str
    version: str = "0.1.0"
    database_types: List[str] = Field(default_factory=list)
    capabilities: PluginCapabilitiesDTO = Field(default_factory=PluginCapabilitiesDTO)
    description: str = ""


class DataSourceConnectResultDTO(BaseModel):
    ok: bool
    plugin_type: str
    message: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DataSourceEntityDTO(BaseModel):
    entity_key: str
    entity_type: str = "table"
    title: str = ""
    row_count: Optional[int] = None
    payload_json: Dict[str, Any] = Field(default_factory=dict)


class CanonicalMessagePreviewDTO(BaseModel):
    source_type: str
    entity_key: str
    external_message_id: str
    author_display_name: str = ""
    created_at: str = ""
    text: str = ""
    raw_text: str = ""
    message_url: str = ""
    raw_record_hash: str = ""
    payload_json: Dict[str, Any] = Field(default_factory=dict)


class DataSourceRegistrationPayload(BaseModel):
    source_type: str
    source_name: str
    external_id: str = ""
    connection: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)


class DataSourceEntitySelectionPayload(BaseModel):
    entity_key: str
    entity_type: str = "table"
    title: str = ""
    payload_json: Dict[str, Any] = Field(default_factory=dict)


class DataSourceRecordDTO(BaseModel):
    source_id: str
    source_type: str
    source_name: str
    external_id: str = ""
    enabled: bool = True
    scan_enabled: bool = True
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    entities: List["SelectedDataSourceEntityDTO"] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class SelectedDataSourceEntityDTO(BaseModel):
    selector: str
    source_id: str
    source_type: str
    entity_key: str
    entity_type: str = "table"
    title: str = ""
    enabled: bool = True
    is_selected: bool = True
    is_scan_enabled: bool = True
    payload_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class DataSourcePageDTO(BaseModel):
    items: List[DataSourceRecordDTO]
    total: int = 0


class DataSourcePluginPageDTO(BaseModel):
    items: List[DataSourcePluginManifestDTO]
    total: int = 0


class DataSourceEntityPageDTO(BaseModel):
    items: List[DataSourceEntityDTO]
    total: int = 0


class CanonicalPreviewPageDTO(BaseModel):
    items: List[CanonicalMessagePreviewDTO]
    total: int = 0


class DataSourceActionDTO(BaseModel):
    ok: bool = True
    message: str = ""
    source: Optional[DataSourceRecordDTO] = None
    selected: Optional[SelectedDataSourceEntityDTO] = None
    job: Optional[Dict[str, Any]] = None
