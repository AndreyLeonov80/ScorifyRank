"""Selector normalization helpers for Telegram sync."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Union

Selector = Union[str, int]


def parse_selector_line(line: str) -> Selector:
    try:
        return int(line)
    except ValueError:
        return line


def selector_key(chat_selector: Selector) -> str:
    if isinstance(chat_selector, int):
        return f"id:{chat_selector}"
    return str(chat_selector).strip().lower()


def load_selected_chats_from_state(
    state: Dict[str, Any],
    *,
    state_key: str,
    parse_line: Callable[[str], Selector] = parse_selector_line,
) -> List[Selector]:
    raw_items = state.get(state_key)
    if not isinstance(raw_items, list):
        return []
    lines = [str(item).strip() for item in raw_items if str(item or "").strip()]
    return [parse_line(line) for line in lines]

