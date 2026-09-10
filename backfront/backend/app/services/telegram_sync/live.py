"""Live Telegram sync task bookkeeping helpers."""

from __future__ import annotations

from typing import Any, Dict


def forget_completed_task(tasks: Dict[str, Any], chat_key: str, task: Any) -> None:
    current = tasks.get(chat_key)
    if current is task:
        tasks.pop(chat_key, None)
