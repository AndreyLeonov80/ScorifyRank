"""Stable JSON error payloads for HTTP clients."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.error_taxonomy import classify_error_text, recovery_hint


def _error_text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        messages: list[str] = []
        for item in detail:
            if isinstance(item, dict):
                loc = ".".join(str(part) for part in item.get("loc", ()) if part is not None)
                message = str(item.get("msg") or item.get("type") or "").strip()
                if loc and message:
                    messages.append(f"{loc}: {message}")
                elif message:
                    messages.append(message)
        if messages:
            return "; ".join(messages)
    if isinstance(detail, dict):
        for key in ("error", "message", "detail"):
            value = detail.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "Ошибка API. Подробности сохранены в поле detail."


def api_error_payload(detail: Any, *, request_id: str | None = None) -> dict[str, Any]:
    error = _error_text(detail)
    error_code = classify_error_text(detail if isinstance(detail, str) else error)
    payload: dict[str, Any] = {
        "ok": False,
        "error": error,
        "detail": detail,
        "error_code": error_code,
        "recovery_hint": recovery_hint(error_code),
    }
    if request_id:
        payload["request_id"] = request_id
    return payload


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    headers = exc.headers if exc.headers else None
    return JSONResponse(
        status_code=exc.status_code,
        content=api_error_payload(exc.detail),
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=api_error_payload(exc.errors()),
    )


async def unhandled_exception_handler(request: Request, exc: Exception, public_message: str) -> JSONResponse:
    request_id = uuid.uuid4().hex[:12]
    return JSONResponse(
        status_code=500,
        content=api_error_payload(public_message, request_id=request_id),
    )

