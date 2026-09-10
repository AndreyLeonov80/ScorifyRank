"""Shared schema constants and literal types."""

from __future__ import annotations

from typing import Literal

Stage = Literal["Новый", "Квалификация", "Демонстрация", "Обсуждение", "Договор", "Победа", "Проигрыш"]
AnalysisKind = Literal["crm", "events", "contacts"]
DealStage = Literal["idea", "lead", "qualified", "proposal", "negotiation", "contract", "won", "lost"]
OutreachTouchStatus = Literal[
    "draft",
    "approved",
    "sent",
    "replied",
    "meeting_booked",
    "no_reply",
    "do_not_contact",
]
XFilesContractStatus = Literal["needs_data", "proposal_ready", "sent", "negotiation", "signed", "paid"]
XFilesContractTemplateKind = Literal["proposal", "contract", "invoice", "appendix", "nda"]
DEFAULT_OPENROUTER_MODEL_ID = "openai/gpt-oss-120b:free"
DEFAULT_OPENROUTER_PAID_MODEL_ID = "openai/gpt-5-chat"
DEFAULT_LLM_PROVIDER = "openrouter"
DEFAULT_LMSTUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_OCR_SERVICE_URL = ""
