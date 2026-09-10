"""DTO assembly helpers for X-Files deals."""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Literal


def build_plan_item(
    item: Any,
    action: str,
    *,
    attention_hours: Callable[[Any], float],
    profit_per_hour: Callable[[Any], float],
) -> Dict[str, Any]:
    return {
        "deal_id": item.id,
        "title": item.title,
        "stage": item.stage,
        "score": int(item.score or 0),
        "expected_value": float(item.expected_value or 0.0),
        "expected_profit": float(item.expected_profit or 0.0),
        "margin": float(item.margin or 1.0),
        "attention_hours": attention_hours(item),
        "profit_per_user_hour": profit_per_hour(item),
        "contact_key": item.contact_key,
        "contact_name": item.contact_name,
        "company": item.company,
        "source_chat": item.source_chat,
        "source_message_id": item.source_message_id,
        "next_action": item.next_action,
        "next_action_at": item.next_action_at,
        "sla_status": item.sla_status,
        "action": action,
    }


def build_daily_plan_bucket(
    bucket_cls: Callable[..., Any],
    *,
    key: str,
    label: str,
    target: int,
    candidates: Iterable[Any],
    action: str,
    plan_item: Callable[[Any, str], Dict[str, Any]],
) -> Any:
    seen: set[str] = set()
    rows: List[Dict[str, Any]] = []
    for candidate in candidates:
        if candidate.id in seen:
            continue
        seen.add(candidate.id)
        rows.append(plan_item(candidate, action))
        if len(rows) >= target:
            break
    if len(rows) >= target:
        tone: Literal["green", "yellow", "red"] = "green"
    elif rows:
        tone = "yellow"
    else:
        tone = "red"
    return bucket_cls(
        key=key,
        label=label,
        target=target,
        count=len(rows),
        tone=tone,
        items=rows,
    )

