from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    ok: bool = True
    data: T | None = None
    error: str | None = None


class ContactDTO(BaseModel):
    id: str
    title: str
    source_id: str | None = None
    source_title: str | None = None
    username: str | None = None
    telegram_id: str | None = None
    messages_count: int = 0
    last_message_at: str | None = None


class MessageDTO(BaseModel):
    id: str
    contact_id: str
    source_id: str | None = None
    sender_name: str | None = None
    sender_username: str | None = None
    text: str
    date_utc: str | None = None


class PromptTemplateDTO(BaseModel):
    id: str
    name: str
    provider: str = "openrouter"
    model: str = "openai/gpt-oss-120b:free"
    temperature: float = 0.2
    max_tokens: int = 2048
    language: str = "ru"
    prompt: str
    is_default: bool = False
    updated_at: str | None = None


class BriefContentDTO(BaseModel):
    client_summary: str = ""
    conversation_summary: str = ""
    pain_hypotheses: list[str] = Field(default_factory=list)
    buying_signals: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    arguments: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    next_step: str = ""
    follow_up_message: str = ""
    manager_checklist: list[str] = Field(default_factory=list)
    data_confidence: str = "medium"
    missing_context: list[str] = Field(default_factory=list)
    recommended_offer: str = ""
    do_not_say: list[str] = Field(default_factory=list)


class BriefArtifactDTO(BaseModel):
    kind: Literal["docx", "html", "markdown", "json", "input_context", "llm_request", "llm_response"]
    path: str
    url: str


class NegotiationBriefDTO(BaseModel):
    id: str
    contact_id: str
    source_id: str | None = None
    prompt_id: str
    status: Literal["draft", "ready", "error"] = "ready"
    content: BriefContentDTO
    artifacts: list[BriefArtifactDTO] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GenerateBriefRequest(BaseModel):
    contact_id: str
    prompt_id: str | None = None
    message_limit: int | None = None
    force_llm: bool = False


class GenerateBriefResponse(BaseModel):
    job_id: str
    brief_id: str
    status: str


class JobDTO(BaseModel):
    id: str
    kind: str = "generate_brief"
    status: Literal["queued", "running", "done", "error"] = "queued"
    progress_percent: float = 0.0
    eta_sec: int | None = None
    message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error: str | None = None


class LLMRunLogDTO(BaseModel):
    id: str
    brief_id: str
    prompt_id: str
    provider: str
    model: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

