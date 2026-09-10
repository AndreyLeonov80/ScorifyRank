"""Rate-limit helpers isolated from JSONL writer/backfill code."""

from __future__ import annotations

import re
from typing import Any, Dict


def flood_wait_seconds(exc: Exception) -> int:
    raw_seconds = getattr(exc, "seconds", None)
    if raw_seconds is None:
        match = re.search(r"wait of (\d+) seconds", str(exc or ""), re.IGNORECASE)
        raw_seconds = match.group(1) if match else 60
    try:
        return max(1, int(float(raw_seconds)))
    except (TypeError, ValueError):
        return 60


def rate_limit_state(state: Dict[str, Any], state_key: str) -> Dict[str, Any]:
    current = state.get(state_key)
    if not isinstance(current, dict):
        current = {}
    current.setdefault("global_flood_wait", {})
    current.setdefault("risks", {})
    current.setdefault("operation_cooldowns", {})
    state[state_key] = current
    return current

