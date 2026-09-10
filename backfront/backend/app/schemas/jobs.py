"""Durable job progress schemas shared by dashboard and long-running popups."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


JobStatus = Union[Literal["idle", "queued", "pending", "running", "done", "failed", "error", "cancelled"], str]


class JobProgressDTO(BaseModel):
    job_id: str
    type: str = "unknown"
    queue_name: str = "default"
    status: JobStatus = "idle"
    progress_percent: float = Field(default=0, ge=0, le=100)
    progress_label: str = "очередь пуста"
    queue_started_at: Optional[str] = None
    chunks_done: int = Field(default=0, ge=0)
    chunks_total: int = Field(default=0, ge=0)
    last_chunk_at: Optional[str] = None
    eta_seconds: Optional[float] = None
    attempts: int = Field(default=0, ge=0)
    payload: Dict[str, Any] = Field(default_factory=dict)
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    updated_at: Optional[str] = None


class JobEventDTO(BaseModel):
    id: int = 0
    job_id: str
    level: str = "info"
    message: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class JobsPageDTO(BaseModel):
    items: List[JobProgressDTO]
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


class JobEventsPageDTO(BaseModel):
    items: List[JobEventDTO]
    total: int = 0
    page: int = 1
    page_size: int = 50
    total_pages: int = 1


class JobCreatePayload(BaseModel):
    type: str = Field(default="llm_analysis")
    queue_name: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class JobCreateDTO(BaseModel):
    ok: bool = True
    job_id: str
    status: JobStatus = "queued"
    queue_name: str
    message: str = "Задача поставлена в очередь"
    job: JobProgressDTO


class JobCancelDTO(BaseModel):
    ok: bool = True
    job_id: str
    status: JobStatus = "cancelled"
    message: str = "Задача отменена"
