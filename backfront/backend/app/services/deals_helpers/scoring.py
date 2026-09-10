"""Scoring helpers for X-Files deals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Tuple


def deal_profit(item: Any) -> float:
    return float(getattr(item, "expected_profit", None) or getattr(item, "expected_value", None) or 0.0)


def deal_attention_hours(item: Any) -> float:
    stage_cost = {
        "idea": 0.45,
        "lead": 0.35,
        "qualified": 0.6,
        "proposal": 0.9,
        "negotiation": 1.2,
        "contract": 1.5,
        "won": 0.2,
        "lost": 0.1,
    }.get(str(getattr(item, "stage", None) or "lead"), 0.5)
    if getattr(item, "sla_status", None) == "red":
        stage_cost += 0.35
    elif getattr(item, "sla_status", None) == "yellow":
        stage_cost += 0.2
    if not str(getattr(item, "next_action", None) or "").strip():
        stage_cost += 0.25
    return round(max(0.1, stage_cost), 2)


def deal_profit_per_hour(item: Any) -> float:
    return round(deal_profit(item) / max(0.1, deal_attention_hours(item)), 2)


def deal_priority(item: Any, parse_dt: Callable[[Any], datetime]) -> Tuple[float, float, int, int, float, float, float]:
    urgency = 2 if getattr(item, "sla_status", None) == "red" else 1 if getattr(item, "sla_status", None) == "yellow" else 0
    return (
        deal_profit(item),
        deal_profit_per_hour(item),
        int(getattr(item, "score", None) or 0),
        urgency,
        -deal_attention_hours(item),
        parse_dt(getattr(item, "updated_at", None)).timestamp(),
        parse_dt(getattr(item, "created_at", None)).timestamp(),
    )


def epoch_utc() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)

