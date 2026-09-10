"""State normalization and JSONL cursor helpers for Telegram sync."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def normalize_chat_state(state: Dict[str, Any], chat_key: str) -> Dict[str, Any]:
    current = state.get(chat_key)
    if current is None:
        current = {}
    elif isinstance(current, int):
        current = {"backfill_offset_id": int(current)}
    elif not isinstance(current, dict):
        current = {}

    current.setdefault("last_message_id", 0)
    current.setdefault("max_saved_id", 0)
    current.setdefault("min_saved_id", 0)
    current.setdefault("cursor_state_version", 1)
    current.setdefault("cursor_resume_strategy", "jsonl_bounds_then_forward_min_id")
    current.setdefault("cursor_state_updated_at", None)
    current.setdefault("last_sync_at", None)
    current.setdefault("last_error", None)
    current.setdefault("retry_after", None)
    current.setdefault("telegram_status", "pending")
    current.setdefault("backfill_batch_size", 1000)
    current.setdefault("media_checked_count", 0)
    current.setdefault("media_downloaded_count", 0)
    current.setdefault("ocr_processed_count", 0)
    state[chat_key] = current
    return current


def existing_jsonl_message_bounds(path: Path) -> Dict[str, int]:
    min_id: Optional[int] = None
    max_id: Optional[int] = None
    total = 0
    if not path.exists():
        return {"min_id": 0, "max_id": 0, "total": 0}

    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("message") if isinstance(record.get("message"), dict) else {}
            try:
                message_id = int(message.get("id") or 0)
            except (TypeError, ValueError):
                message_id = 0
            if message_id <= 0:
                continue
            total += 1
            min_id = message_id if min_id is None else min(min_id, message_id)
            max_id = message_id if max_id is None else max(max_id, message_id)

    return {
        "min_id": int(min_id or 0),
        "max_id": int(max_id or 0),
        "total": int(total or 0),
    }

