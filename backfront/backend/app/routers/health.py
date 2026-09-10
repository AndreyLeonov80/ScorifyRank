"""Small health endpoints for split-backend smoke checks."""

from __future__ import annotations

import os

from fastapi import APIRouter

from app.core.config import settings
from app.core.runtime_paths import CACHE_DIR, DUCKDB_PATH, PAYME_OUT_DIR, STATE_PATH
from app.core.telethon_compat import TELETHON_AVAILABLE, TELETHON_IMPORT_ERROR
from app.services import jobs_runtime

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "service": "x-files-backfront-new-back",
        "web_port": settings.web_port,
        "frontend_origin": settings.frontend_origin,
    }


def _path_payload(path) -> dict[str, object]:
    try:
        resolved = path.resolve()
        return {
            "path": str(resolved),
            "exists": resolved.exists(),
            "is_dir": resolved.is_dir(),
            "size_bytes": resolved.stat().st_size if resolved.exists() and resolved.is_file() else 0,
        }
    except Exception as exc:
        return {
            "path": str(path),
            "exists": False,
            "is_dir": False,
            "size_bytes": 0,
            "error": str(exc),
        }


def _jsonl_count_payload() -> dict[str, object]:
    if not PAYME_OUT_DIR.exists():
        return {"count": 0, "error": "PAYME_OUT_DIR does not exist"}
    try:
        return {"count": sum(1 for _ in PAYME_OUT_DIR.glob("*.jsonl"))}
    except Exception as exc:
        return {"count": 0, "error": str(exc)}


def _redis_payload() -> dict[str, object]:
    configured = bool(jobs_runtime.REDIS_URL)
    if not configured:
        return {"configured": False, "ok": False}
    client = jobs_runtime._redis()
    if client is None:
        return {"configured": True, "ok": False}
    try:
        client.ping()
        return {"configured": True, "ok": True}
    except Exception as exc:
        return {"configured": True, "ok": False, "error": str(exc)}


@router.get("/api/payme/preflight-report")
def preflight_report() -> dict[str, object]:
    rabbitmq_url = os.environ.get("CELERY_BROKER_URL") or os.environ.get("RABBITMQ_URL") or ""
    return {
        "ok": True,
        "service": "x-files-backfront-new-back",
        "paths": {
            "out": _path_payload(PAYME_OUT_DIR),
            "duckdb": _path_payload(DUCKDB_PATH),
            "state": _path_payload(STATE_PATH),
            "cache": _path_payload(CACHE_DIR),
        },
        "jsonl": _jsonl_count_payload(),
        "telethon": {
            "available": TELETHON_AVAILABLE,
            "error": "" if TELETHON_AVAILABLE else str(TELETHON_IMPORT_ERROR or ""),
        },
        "redis": _redis_payload(),
        "rabbitmq": {
            "configured": bool(rabbitmq_url),
            "url_masked": rabbitmq_url.split("@", 1)[-1] if rabbitmq_url else "",
        },
        "license": {
            "runtime_dir": os.environ.get("XFILES_LICENSE_RUNTIME_DIR", ""),
            "server_url": os.environ.get("XFILES_LICENSE_SERVER_URL", ""),
        },
    }
