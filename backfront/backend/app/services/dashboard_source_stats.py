"""Dashboard source statistics payload builder.

The dashboard reads this payload to show which selected data sources are scanned,
how many messages are cached, and what each source is waiting on.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Set


def _dashboard_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _read_progress_payload(*, message_count: int, chat_state: Dict[str, Any], message_limit: Any) -> Dict[str, Any]:
    read_count = max(int(message_count or 0), _safe_int(chat_state.get("backfill_items_processed")))
    latest_id = _safe_int(chat_state.get("backfill_latest_id") or chat_state.get("max_saved_id"))
    limit = _safe_int(message_limit)
    if limit > 0:
        total_estimate = max(read_count, min(limit, latest_id if latest_id > 0 else limit))
    elif latest_id > 0:
        total_estimate = max(read_count, latest_id)
    else:
        total_estimate = read_count
    remaining = max(0, total_estimate - read_count)
    percent = 100.0 if total_estimate <= 0 else min(100.0, round((read_count / max(1, total_estimate)) * 100.0, 1))
    return {
        "read_messages_count": read_count,
        "total_messages_estimate": total_estimate,
        "remaining_messages_estimate": remaining,
        "read_progress_percent": percent,
    }


def build_dashboard_scanned_sources_payload(
    *,
    lead_items: List[Any],
    dialog_items: List[Any],
    telegram_flood_wait: Dict[str, Any],
    telegram_rate_limits: Dict[str, Any],
    limit: int,
    source_selectors: Iterable[str],
    import_sync_selectors: Iterable[str],
    telegram_sync: Any,
    selector_to_lead_name: Callable[[str], str],
    lead_scan_group_fields: Callable[[str, str], Dict[str, Any]],
    telegram_chat_state_for_lead: Callable[[str, str], Dict[str, Any]],
    utc_now: Callable[[], Any],
) -> Dict[str, Any]:
    selected_selectors: List[str] = []
    seen_selectors: Set[str] = set()
    for selector in source_selectors:
        value = str(selector or "").strip()
        if not value or value in seen_selectors:
            continue
        seen_selectors.add(value)
        selected_selectors.append(value)
    import_sync_queue_selectors = {
        str(item or "").strip()
        for item in import_sync_selectors
        if str(item or "").strip()
    }

    lead_by_name: Dict[str, Any] = {}
    for lead in lead_items:
        name = str(_dashboard_value(lead, "name", "") or "").strip().lower()
        if name:
            lead_by_name[name] = lead

    dialog_by_name: Dict[str, Any] = {}
    for dialog in dialog_items:
        for key in (
            _dashboard_value(dialog, "username", ""),
            _dashboard_value(dialog, "title", ""),
            _dashboard_value(dialog, "name", ""),
            _dashboard_value(dialog, "selector", ""),
        ):
            normalized = selector_to_lead_name(str(key or ""))
            if normalized:
                dialog_by_name.setdefault(normalized, dialog)

    cooldowns = [
        value
        for value in (telegram_rate_limits.get("operation_cooldowns") or {}).values()
        if isinstance(value, dict) and value.get("active")
    ]
    flood_active = bool((telegram_flood_wait or {}).get("active"))
    sync_status = telegram_sync.get_sync_control_status() if hasattr(telegram_sync, "get_sync_control_status") else {}
    sync_paused = bool((sync_status or {}).get("paused"))
    backfill_tasks = getattr(telegram_sync, "_chat_backfill_tasks", {}) or {}
    setup_tasks = getattr(telegram_sync, "_chat_setup_tasks", {}) or {}

    rows: List[Dict[str, Any]] = []
    totals = {
        "selected_sources": len(selected_selectors),
        "active_sources": 0,
        "pending_sources": 0,
        "idle_sources": 0,
        "error_sources": 0,
        "messages_count": 0,
        "groups": 0,
        "channels": 0,
        "private": 0,
        "bots": 0,
        "import_sync_queued_sources": len(import_sync_queue_selectors),
    }

    for selector in selected_selectors:
        lead_name = selector_to_lead_name(selector)
        source_type = "telegram"
        if ":" in selector and not selector.startswith("@"):
            source_type = selector.split(":", 1)[0] or "plugin"

        lead = lead_by_name.get(lead_name)
        dialog = dialog_by_name.get(lead_name)
        chat_state = telegram_chat_state_for_lead(lead_name, selector) if source_type == "telegram" else {}
        group_fields = lead_scan_group_fields(lead_name, selector)
        message_count = int(
            _dashboard_value(lead, "count", 0)
            or _dashboard_value(dialog, "messages_count", 0)
            or chat_state.get("messages_count", 0)
            or 0
        )
        last_message_at = (
            _dashboard_value(lead, "last_date_utc", None)
            or chat_state.get("last_message_date_utc")
            or chat_state.get("backfill_completed_at")
            or chat_state.get("backfill_updated_at")
        )
        last_sync_at = (
            _dashboard_value(lead, "last_sync_at", None)
            or chat_state.get("backfill_updated_at")
            or chat_state.get("backfill_completed_at")
            or chat_state.get("last_live_update_at")
        )
        last_error = _dashboard_value(lead, "last_error", None) or chat_state.get("last_error")
        chat_type = str(
            _dashboard_value(lead, "chat_type", "")
            or _dashboard_value(dialog, "chat_type", "")
            or "group"
        )
        if chat_type == "channel":
            totals["channels"] += 1
        elif chat_type == "private":
            totals["private"] += 1
        elif chat_type == "bot":
            totals["bots"] += 1
        else:
            totals["groups"] += 1

        status = "idle"
        status_label = "ожидает расписания"
        tone = "green"
        active = False
        pending = False
        try:
            selector_key = telegram_sync._selector_key(selector)
        except Exception:
            selector_key = str(selector or "").strip().lower()
        chat_key = str(chat_state.get("chat_key") or selector_key or lead_name)

        if last_error:
            status = "error"
            status_label = "ошибка"
            tone = "red"
            totals["error_sources"] += 1
        elif flood_active:
            status = "paused"
            status_label = "Telegram FloodWait"
            tone = "red"
        elif cooldowns:
            status = "cooldown"
            status_label = "Telegram cooldown"
            tone = "yellow"
        elif sync_paused:
            status = "paused"
            status_label = "sync на паузе"
            tone = "yellow"
        elif source_type != "telegram":
            status = "plugin"
            status_label = "plugin подключён"
            tone = "yellow"
        elif chat_key in backfill_tasks and not backfill_tasks[chat_key].done():
            status = "active"
            status_label = "читает историю"
            tone = "green"
            active = True
        elif selector_key in setup_tasks and not setup_tasks[selector_key].done():
            status = "active"
            status_label = "готовит источник"
            tone = "green"
            active = True
        elif not bool(chat_state.get("backfill_done")) and int(chat_state.get("backfill_latest_id", 0) or 0) > 0:
            status = "pending"
            status_label = "ожидает догрузки"
            tone = "yellow"
            pending = True
        elif message_count <= 0:
            status = "pending"
            status_label = "нет сообщений в кеше"
            tone = "yellow"
            pending = True

        if active:
            totals["active_sources"] += 1
        elif pending:
            totals["pending_sources"] += 1
        elif status != "error":
            totals["idle_sources"] += 1
        progress_fields = _read_progress_payload(
            message_count=message_count,
            chat_state=chat_state,
            message_limit=_dashboard_value(lead, "import_message_limit", 0),
        )
        totals["messages_count"] += max(message_count, int(progress_fields.get("read_messages_count") or 0))
        rows.append(
            {
                "selector": selector,
                "source": lead_name or selector,
                "title": _dashboard_value(dialog, "title", None) or _dashboard_value(lead, "name", None) or lead_name or selector,
                "source_type": source_type,
                "chat_type": chat_type,
                "status": status,
                "status_label": status_label,
                "tone": tone,
                "messages_count": message_count,
                **progress_fields,
                "last_message_at": last_message_at,
                "last_sync_at": last_sync_at,
                "last_error": last_error,
                "scan_group": group_fields.get("scan_group") or "C",
                "scan_group_label": group_fields.get("scan_group_label"),
                "scan_group_frequency": group_fields.get("scan_group_frequency"),
                "scan_group_interval_minutes": group_fields.get("scan_group_interval_minutes"),
                "jsonl_file": _dashboard_value(lead, "file", None),
                "has_jsonl": bool(_dashboard_value(lead, "has_jsonl", False)),
            }
        )

    rows.sort(
        key=lambda item: (
            0 if item.get("status") == "active" else 1,
            0 if item.get("status") == "pending" else 1,
            str(item.get("last_message_at") or ""),
            int(item.get("messages_count") or 0),
        ),
        reverse=True,
    )

    return {
        "items": rows[: max(1, min(len(rows), max(int(limit or 10), 1000)))],
        "total": len(rows),
        "totals": totals,
        "message": (
            f"Сканируется/выбрано источников: {totals['selected_sources']}; "
            f"активно {totals['active_sources']}, ожидают {totals['pending_sources']}, сообщений {totals['messages_count']}"
        ),
        "updated_at": utc_now().isoformat(),
    }
