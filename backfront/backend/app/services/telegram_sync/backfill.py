"""Backfill decision helpers for Telegram sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass(frozen=True)
class BackfillLimits:
    history_months: int
    message_limit: int
    cutoff_dt: Optional[datetime]


def build_backfill_limits(*, history_months: int, message_limit: int, now: datetime) -> BackfillLimits:
    now_utc = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    safe_months = max(0, int(history_months or 0))
    return BackfillLimits(
        history_months=safe_months,
        message_limit=int(message_limit or 0),
        cutoff_dt=None if safe_months == 0 else now_utc - timedelta(days=safe_months * 31),
    )


def backfill_stop_reason(
    *,
    total: int,
    message_limit: int,
    message_date: Optional[datetime],
    cutoff_dt: Optional[datetime],
) -> Optional[str]:
    if int(message_limit or 0) > 0 and int(total or 0) >= int(message_limit):
        return "message_limit"
    if cutoff_dt is not None and isinstance(message_date, datetime):
        comparable_date = message_date if message_date.tzinfo else message_date.replace(tzinfo=timezone.utc)
        if comparable_date < cutoff_dt:
            return "history_months"
    return None
