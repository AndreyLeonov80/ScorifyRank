"""Deals, outreach, and X-Files metric helpers for the legacy runtime."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime") or sys.modules.get("back")
    if runtime is None:
        return
    for name, value in vars(runtime).items():
        if not name.startswith("__") and name != "refresh_legacy_globals":
            globals()[name] = value


def _with_legacy_globals(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        refresh_legacy_globals()
        result = func(*args, **kwargs)
        runtime = sys.modules.get("app.legacy_runtime") or sys.modules.get("back")
        if runtime is not None:
            for name in (
                "_postgres_last_error",
                "_postgres_state_deals_migrated",
                "_postgres_state_deals_migration_last_error",
            ):
                if name in globals():
                    setattr(runtime, name, globals()[name])
        return result

    return wrapper


refresh_legacy_globals()

def _xfiles_outreach_item_deal_title(item: OutreachCrmFieldDTO) -> str:
    title_basis = item.value if len(item.value) <= 120 else item.value[:117].rstrip() + "..."
    return f"{item.field_label}: {title_basis}"


def _xfiles_attach_deals_to_outreach_items(items: List[OutreachCrmFieldDTO]) -> List[OutreachCrmFieldDTO]:
    if not items:
        return items
    deals = _xfiles_load_deals(limit=20000)
    by_message: Dict[tuple[str, str], XFilesDealDTO] = {}
    by_title: Dict[tuple[str, str], XFilesDealDTO] = {}
    for deal in deals:
        source_chat = _xfiles_norm_identity(deal.source_chat)
        message_id = _xfiles_norm_identity(deal.source_message_id)
        if source_chat and message_id:
            by_message[(source_chat, message_id)] = deal
        if _xfiles_norm_identity(deal.source) == "enreach" and source_chat and deal.title:
            by_title[(source_chat, _xfiles_norm_identity(deal.title))] = deal

    for item in items:
        source_chat = _xfiles_norm_identity(item.lead or item.source_selector)
        message_id = _xfiles_norm_identity(item.message_id)
        deal = by_message.get((source_chat, message_id)) if source_chat and message_id else None
        if not deal and source_chat:
            deal = by_title.get((source_chat, _xfiles_norm_identity(_xfiles_outreach_item_deal_title(item))))
        if deal:
            item.deal_id = deal.id
            item.deal_title = deal.title
            item.deal_stage = deal.stage
            item.deal_stage_label = _XFILES_STAGE_LABELS.get(deal.stage, deal.stage)
    return items


def _get_outreach_item_by_id(item_id: str) -> Optional[OutreachCrmFieldDTO]:
    target = str(item_id or "").strip()
    if not target:
        return None
    if duckdb is not None:
        _duckdb_init_schema_sync()
        conn = _duckdb_connect()
        try:
            row = conn.execute(
                """
                SELECT
                    item_id, field_type, field_label, value, contact_key, lead, source_selector,
                    message_id, date_utc_raw, text, sender_username, sender_name,
                    status, CAST(created_at AS VARCHAR) AS created_at_raw
                FROM outreach_crm_fields
                WHERE item_id = ?
                LIMIT 1
                """,
                [target],
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return _xfiles_attach_deals_to_outreach_items([_outreach_row_to_dto(row)])[0]
    item = next((item for item in _outreach_fallback_items() if item.id == target), None)
    return _xfiles_attach_deals_to_outreach_items([item])[0] if item else None


_XFILES_OUTREACH_TOUCH_BLUEPRINTS: List[tuple[str, str, str]] = [
    ("first_touch", "Первое сообщение", "знакомство"),
    ("follow_up_1", "Follow-up 1", "уточнение боли"),
    ("follow_up_2", "Follow-up 2", "встреча"),
    ("last_follow_up", "Последний follow-up", "КП / договор или закрыть ветку"),
]


def _xfiles_outreach_state() -> Dict[str, Any]:
    current = telegram_sync.state.get("_xfiles_outreach")
    if not isinstance(current, dict):
        current = {}
    sequences = current.get("sequences")
    if not isinstance(sequences, list):
        sequences = []
    current["sequences"] = sequences
    telegram_sync.state["_xfiles_outreach"] = current
    return current


def _xfiles_outreach_sequence_from_any(raw: Any) -> Optional[XFilesOutreachSequenceDTO]:
    if not isinstance(raw, dict):
        return None
    try:
        item = XFilesOutreachSequenceDTO(**raw)
        item.stable_key = item.stable_key or _xfiles_operational_stable_key("outreach", {"sequence_id": item.id})
        return item
    except Exception:
        return None


def _xfiles_outreach_sequence_id(payload: XFilesOutreachSequencePayload) -> str:
    explicit = _xfiles_stable_norm(getattr(payload, "stable_key", None), limit=120)
    if explicit:
        return explicit
    basis = {
        "source_item_id": str(payload.source_item_id or "").strip(),
        "contact_name": str(payload.contact_name or "").strip().lower(),
        "lead": str(payload.lead or "").strip().lower(),
        "need": _outreach_compact_text(payload.need)[:300],
        "product_match": str(payload.product_match or "").strip().lower(),
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return f"outseq_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:18]}"


def _xfiles_outreach_sequence_stable_key(payload: XFilesOutreachSequencePayload) -> str:
    sequence_id = _xfiles_outreach_sequence_id(payload)
    return _xfiles_operational_stable_key("outreach", {"sequence_id": sequence_id})


def _xfiles_outreach_variants(contact_name: str, need: str, product: str, lead: str) -> Dict[str, str]:
    compact_need = _xfiles_clean_text(need, 220) or "увидел рабочий контекст, где можно быстро снять часть нагрузки"
    product_text = _xfiles_clean_text(product, 160) or "X-Files / быстрый разбор потребности"
    first_name = str(contact_name or "").strip().split()[0] if str(contact_name or "").strip() else "Добрый день"
    source = f" в {lead}" if str(lead or "").strip() else ""
    greeting = f"{first_name}, добрый день." if first_name != "Добрый день" else "Добрый день."
    return {
        "soft": f"{greeting} Увидел{source}: {compact_need}. Кажется, тут может быть полезно {product_text}. Можно задам один короткий вопрос, чтобы понять, актуально ли это?",
        "direct": f"{greeting} По вашему сообщению вижу задачу: {compact_need}. Можем быстро проверить, даст ли {product_text} экономию времени или денег. Открыты к короткому созвону?",
        "expert": f"{greeting} В похожих кейсах с задачей “{compact_need}” сначала фиксируем цель, ограничения и следующий шаг. Если актуально, предложу короткую структуру диагностики под {product_text}.",
        "partner": f"{greeting} Похоже, у нас может быть полезная точка пересечения: {compact_need}. Предлагаю без продажи начать с обмена контекстом и понять, есть ли взаимная польза.",
    }


def _xfiles_outreach_touches(contact_name: str, need: str, product: str, lead: str) -> List[XFilesOutreachTouchDTO]:
    variants = _xfiles_outreach_variants(contact_name, need, product, lead)
    return [
        XFilesOutreachTouchDTO(
            touch_key="first_touch",
            label="Первое сообщение",
            goal="знакомство",
            message=variants["soft"],
        ),
        XFilesOutreachTouchDTO(
            touch_key="follow_up_1",
            label="Follow-up 1",
            goal="уточнение боли",
            message="Возвращаюсь коротко: если задача ещё актуальна, могу прислать 3 вопроса для быстрой квалификации и оценки потенциальной пользы.",
        ),
        XFilesOutreachTouchDTO(
            touch_key="follow_up_2",
            label="Follow-up 2",
            goal="встреча",
            message="Если удобнее, можно не переписываться долго: предложу 15 минут, чтобы сверить контекст, боль, бюджет и следующий шаг.",
        ),
        XFilesOutreachTouchDTO(
            touch_key="last_follow_up",
            label="Последний follow-up",
            goal="КП / договор или закрыть ветку",
            message="Закрою ветку, чтобы не отвлекать. Если тема вернётся, напишите — быстро восстановлю контекст и предложу следующий шаг.",
        ),
    ]


def _xfiles_outreach_sequence_from_payload(payload: XFilesOutreachSequencePayload) -> XFilesOutreachSequenceDTO:
    now = _utc_now().isoformat()
    contact_name = _xfiles_clean_text(payload.contact_name, 500)
    lead = _xfiles_clean_text(payload.lead, 500)
    need = _xfiles_clean_text(payload.need, 4000)
    product = _xfiles_clean_text(payload.product_match, 1200) or _xfiles_product_hint_from_catalog(need) or "быстрая диагностика потребности"
    title_basis = payload.title or contact_name or lead or need or "outReach последовательность"
    variants = _xfiles_outreach_variants(contact_name, need, product, lead or "")
    return XFilesOutreachSequenceDTO(
        id=_xfiles_outreach_sequence_id(payload),
        stable_key=_xfiles_outreach_sequence_stable_key(payload),
        title=_xfiles_clean_text(title_basis, 500) or "outReach последовательность",
        source_item_id=_xfiles_clean_text(payload.source_item_id, 200),
        contact_name=contact_name,
        lead=lead or None,
        source_selector=_xfiles_clean_text(payload.source_selector, 500) or None,
        need=need,
        product_match=product,
        variants=variants,
        selected_variant="soft",
        template_key="manual_ab",
        template_label="Ручные A/B варианты",
        touches=_xfiles_outreach_touches(contact_name, need, product, lead or ""),
        status="draft",
        created_at=now,
        updated_at=now,
    )


def _xfiles_outreach_payload_from_enreach_item(item: OutreachCrmFieldDTO) -> XFilesOutreachSequencePayload:
    contact_name = item.sender_name or item.sender_username or ""
    if not contact_name and item.field_type in {"fio", "telegram_contact", "contact"}:
        contact_name = item.value
    need = item.text or item.value or ""
    product = _xfiles_product_hint_from_catalog(" ".join([need, item.lead or "", item.field_label or ""])) or ""
    title = _xfiles_clean_text(f"{contact_name or item.lead or item.field_label}: {need}", 500)
    return XFilesOutreachSequencePayload(
        source_item_id=item.id,
        title=title,
        contact_name=contact_name,
        lead=item.lead,
        source_selector=item.source_selector,
        need=need,
        product_match=product,
    )


def _xfiles_load_outreach_sequences(
    query: str = "",
    status: str = "",
    limit: int = 5000,
) -> List[XFilesOutreachSequenceDTO]:
    rows: List[XFilesOutreachSequenceDTO] = []
    for raw in _xfiles_outreach_state().get("sequences") or []:
        item = _xfiles_outreach_sequence_from_any(raw)
        if item:
            rows.append(item)
    query_value = str(query or "").strip().lower()
    status_value = str(status or "").strip()
    filtered: List[XFilesOutreachSequenceDTO] = []
    for item in rows:
        if status_value and status_value != "all" and item.status != status_value:
            continue
        if query_value:
            hay = " ".join(
                [
                    item.title,
                    item.contact_name,
                    item.lead or "",
                    item.source_selector or "",
                    item.need,
                    item.product_match,
                    " ".join(touch.message for touch in item.touches),
                ]
            ).lower()
            if query_value not in hay:
                continue
        filtered.append(item)
    filtered.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
    return filtered[: max(1, int(limit or 1))]


def _xfiles_upsert_outreach_sequence(item: XFilesOutreachSequenceDTO) -> XFilesOutreachSequenceDTO:
    state = _xfiles_outreach_state()
    item.stable_key = item.stable_key or _xfiles_operational_stable_key("outreach", {"sequence_id": item.id})
    rows = [
        row
        for row in state.get("sequences") or []
        if not (
            isinstance(row, dict)
            and (
                row.get("id") == item.id
                or (
                    item.stable_key
                    and _xfiles_norm_identity(row.get("stable_key") or "") == _xfiles_norm_identity(item.stable_key)
                )
            )
        )
    ]
    rows.insert(0, item.model_dump())
    state["sequences"] = rows
    telegram_sync.save_state()
    return item


def _xfiles_create_outreach_sequence(payload: XFilesOutreachSequencePayload) -> XFilesOutreachSequenceDTO:
    item = _xfiles_outreach_sequence_from_payload(payload)
    existing = next(
        (
            row
            for row in _xfiles_load_outreach_sequences(limit=20000)
            if row.id == item.id
            or (
                item.stable_key
                and _xfiles_norm_identity(row.stable_key or "") == _xfiles_norm_identity(item.stable_key)
            )
        ),
        None,
    )
    if existing:
        return existing
    return _xfiles_upsert_outreach_sequence(item)


def _xfiles_create_outreach_sequence_from_enreach(item_id: str) -> XFilesOutreachSequenceDTO:
    item = _get_outreach_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="enReach item not found")
    return _xfiles_create_outreach_sequence(_xfiles_outreach_payload_from_enreach_item(item))


def _xfiles_outreach_payload_from_deal(deal: XFilesDealDTO) -> XFilesOutreachSequencePayload:
    contact_name = deal.contact_name or deal.contact_key or deal.company or ""
    need = deal.need or deal.notes or deal.title
    product = deal.product_match or _xfiles_product_hint_from_catalog(need) or "короткий пилот X-Files"
    title_basis = contact_name or deal.company or deal.title
    return XFilesOutreachSequencePayload(
        source_item_id=f"deal:{deal.id}",
        stable_key=f"deal_followup:{deal.id}",
        title=_xfiles_clean_text(f"{title_basis}: follow-up по сделке", 500),
        contact_name=contact_name,
        lead=deal.source_chat,
        source_selector=deal.source_chat,
        need=need,
        product_match=product,
    )


def _xfiles_create_outreach_sequence_from_deal(deal_id: str) -> XFilesOutreachSequenceDTO:
    deal = _xfiles_get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    return _xfiles_create_outreach_sequence(_xfiles_outreach_payload_from_deal(deal))


def _xfiles_update_outreach_touch_status(
    sequence_id: str,
    touch_key: str,
    status: OutreachTouchStatus,
) -> Optional[XFilesOutreachSequenceDTO]:
    rows = _xfiles_load_outreach_sequences(limit=20000)
    target = next((row for row in rows if row.id == sequence_id), None)
    if not target:
        return None
    now = _utc_now().isoformat()
    changed = False
    for touch in target.touches:
        if touch.touch_key == touch_key:
            touch.status = status
            touch.updated_at = now
            changed = True
            break
    if not changed:
        raise HTTPException(status_code=404, detail="outReach touch not found")
    target.status = status
    target.updated_at = now
    return _xfiles_upsert_outreach_sequence(target)


def _xfiles_update_outreach_sequence(
    sequence_id: str,
    payload: XFilesOutreachSequencePatchPayload,
) -> Optional[XFilesOutreachSequenceDTO]:
    target = next((row for row in _xfiles_load_outreach_sequences(limit=20000) if row.id == sequence_id), None)
    if not target:
        return None
    if payload.selected_variant is not None:
        selected = str(payload.selected_variant or "").strip()
        if selected and selected not in (target.variants or {}):
            raise HTTPException(status_code=400, detail="Unknown outReach variant")
        if selected:
            target.selected_variant = selected
    if payload.status is not None:
        target.status = payload.status
    target.updated_at = _utc_now().isoformat()
    return _xfiles_upsert_outreach_sequence(target)


_XFILES_OUTREACH_SENT_STATUSES = {"sent", "replied", "meeting_booked", "no_reply"}
_XFILES_OUTREACH_REPLY_STATUSES = {"replied", "meeting_booked"}


def _xfiles_outreach_reply_rate(sent: int, replies: int) -> float:
    return round((float(replies) / float(sent)) * 100.0, 1) if sent > 0 else 0.0


def _xfiles_outreach_stats_bucket(
    buckets: Dict[str, Dict[str, Any]],
    key: str,
    label: str,
    *,
    sent: bool,
    replied: bool,
) -> None:
    bucket_key = str(key or "unknown").strip() or "unknown"
    bucket = buckets.setdefault(
        bucket_key,
        {"key": bucket_key, "label": str(label or bucket_key).strip() or bucket_key, "total": 0, "sent": 0, "replies": 0},
    )
    bucket["total"] = int(bucket.get("total") or 0) + 1
    if sent:
        bucket["sent"] = int(bucket.get("sent") or 0) + 1
    if replied:
        bucket["replies"] = int(bucket.get("replies") or 0) + 1


def _xfiles_outreach_bucket_list(buckets: Dict[str, Dict[str, Any]]) -> List[XFilesOutreachReplyRateDTO]:
    rows: List[XFilesOutreachReplyRateDTO] = []
    for raw in buckets.values():
        sent = int(raw.get("sent") or 0)
        replies = int(raw.get("replies") or 0)
        rows.append(
            XFilesOutreachReplyRateDTO(
                key=str(raw.get("key") or ""),
                label=str(raw.get("label") or raw.get("key") or ""),
                total=int(raw.get("total") or 0),
                sent=sent,
                replies=replies,
                reply_rate_percent=_xfiles_outreach_reply_rate(sent, replies),
            )
        )
    rows.sort(key=lambda item: (-item.sent, -item.replies, item.label.lower()))
    return rows


def _xfiles_outreach_stats() -> XFilesOutreachStatsDTO:
    rows = _xfiles_load_outreach_sequences(limit=20000)
    sent_total = 0
    replies_total = 0
    by_template: Dict[str, Dict[str, Any]] = {}
    by_source: Dict[str, Dict[str, Any]] = {}
    by_group: Dict[str, Dict[str, Any]] = {}
    by_product: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        status = str(item.status or "draft")
        sent = status in _XFILES_OUTREACH_SENT_STATUSES
        replied = status in _XFILES_OUTREACH_REPLY_STATUSES
        if sent:
            sent_total += 1
        if replied:
            replies_total += 1
        variant = str(item.selected_variant or "soft").strip() or "soft"
        variant_label = f"{variant} · {item.template_label or item.template_key or 'A/B'}"
        source = item.source_selector or item.lead or "без источника"
        product = item.product_match or "без продукта"
        group_fields = _lead_scan_group_fields(item.lead or source, source)
        group_key = str(group_fields.get("scan_group") or "C")
        group_label = str(group_fields.get("scan_group_label") or group_key)
        _xfiles_outreach_stats_bucket(by_template, variant, variant_label, sent=sent, replied=replied)
        _xfiles_outreach_stats_bucket(by_source, source, source, sent=sent, replied=replied)
        _xfiles_outreach_stats_bucket(by_group, group_key, group_label, sent=sent, replied=replied)
        _xfiles_outreach_stats_bucket(by_product, product[:120], product[:120], sent=sent, replied=replied)
    return XFilesOutreachStatsDTO(
        total=len(rows),
        sent=sent_total,
        replies=replies_total,
        reply_rate_percent=_xfiles_outreach_reply_rate(sent_total, replies_total),
        by_template=_xfiles_outreach_bucket_list(by_template)[:20],
        by_source=_xfiles_outreach_bucket_list(by_source)[:20],
        by_group=_xfiles_outreach_bucket_list(by_group)[:20],
        by_product=_xfiles_outreach_bucket_list(by_product)[:20],
    )


def _postgres_connect():
    if psycopg is None or not POSTGRES_DSN:
        raise RuntimeError("PostgreSQL DSN is not configured")
    connect_kwargs = {"connect_timeout": POSTGRES_CONNECT_TIMEOUT_SEC}
    if dict_row is not None:
        return psycopg.connect(POSTGRES_DSN, row_factory=dict_row, **connect_kwargs)  # type: ignore[attr-defined]
    return psycopg.connect(POSTGRES_DSN, **connect_kwargs)  # type: ignore[attr-defined]


def _postgres_log_error_once(message: str) -> None:
    global _postgres_last_error_logged_at
    now = time.monotonic()
    if now - _postgres_last_error_logged_at < 60:
        return
    _postgres_last_error_logged_at = now
    _append_runtime_log("postgres", message)


_XFILES_POSTGRES_MIGRATIONS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "name": "xfiles_deals_base",
        "statements": [
            """
            CREATE TABLE IF NOT EXISTS xfiles_deals (
                id TEXT PRIMARY KEY,
                stable_key TEXT,
                title TEXT NOT NULL,
                stage TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                expected_value DOUBLE PRECISION NOT NULL DEFAULT 0,
                probability DOUBLE PRECISION NOT NULL DEFAULT 0,
                margin DOUBLE PRECISION NOT NULL DEFAULT 1,
                expected_profit DOUBLE PRECISION NOT NULL DEFAULT 0,
                contact_key TEXT,
                contact_name TEXT,
                company TEXT,
                source TEXT,
                source_chat TEXT,
                source_message_id TEXT,
                need TEXT,
                product_match TEXT,
                next_action TEXT,
                next_action_at TEXT,
                owner TEXT,
                notes TEXT,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            "ALTER TABLE xfiles_deals ADD COLUMN IF NOT EXISTS margin DOUBLE PRECISION NOT NULL DEFAULT 1",
            "ALTER TABLE xfiles_deals ADD COLUMN IF NOT EXISTS stable_key TEXT",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deals_stage ON xfiles_deals(stage)",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deals_updated ON xfiles_deals(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deals_contact ON xfiles_deals(contact_key)",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deals_stable_key ON xfiles_deals(stable_key)",
        ],
    },
    {
        "id": 2,
        "name": "xfiles_deal_audit",
        "statements": [
            """
            CREATE TABLE IF NOT EXISTS xfiles_deal_audit (
                id TEXT PRIMARY KEY,
                ts TIMESTAMPTZ NOT NULL,
                action TEXT NOT NULL,
                deal_id TEXT NOT NULL DEFAULT '',
                deal_title TEXT NOT NULL DEFAULT '',
                actor TEXT NOT NULL DEFAULT 'user',
                source TEXT NOT NULL DEFAULT 'ui',
                before_stage TEXT,
                after_stage TEXT,
                changes JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deal_audit_ts ON xfiles_deal_audit(ts DESC)",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deal_audit_deal_id ON xfiles_deal_audit(deal_id)",
            "CREATE INDEX IF NOT EXISTS idx_xfiles_deal_audit_source ON xfiles_deal_audit(source)",
        ],
    },
]


def _postgres_apply_xfiles_migrations(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS xfiles_schema_migrations (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for migration in _XFILES_POSTGRES_MIGRATIONS:
        migration_id = int(migration["id"])
        migration_name = str(migration["name"])
        for statement in migration.get("statements") or []:
            cur.execute(statement)
        cur.execute(
            """
            INSERT INTO xfiles_schema_migrations (id, name)
            VALUES (%s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                applied_at = NOW()
            """,
            [migration_id, migration_name],
        )


def _postgres_ensure_xfiles_schema() -> bool:
    global _postgres_schema_ready, _postgres_last_error
    if not POSTGRES_ENABLED:
        if POSTGRES_DSN and psycopg is None:
            _postgres_last_error = "psycopg не установлен в runtime"
        return False
    if _postgres_schema_ready:
        return True
    with _postgres_schema_lock:
        if _postgres_schema_ready:
            return True
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    _postgres_apply_xfiles_migrations(cur)
                conn.commit()
            _postgres_schema_ready = True
            _postgres_last_error = None
            return True
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_log_error_once(f"X-Files PostgreSQL недоступен, fallback в state.json: {exc}")
            return False


def _xfiles_deals_state() -> Dict[str, Any]:
    current = telegram_sync.state.get(XFILES_DEALS_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, list):
        items = []
    current["items"] = items
    telegram_sync.state[XFILES_DEALS_STATE_KEY] = current
    return current


def _xfiles_deal_audit_state() -> Dict[str, Any]:
    current = telegram_sync.state.get(XFILES_DEAL_AUDIT_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, list):
        items = []
    current["items"] = items
    telegram_sync.state[XFILES_DEAL_AUDIT_STATE_KEY] = current
    return current


def _xfiles_product_margins_state() -> Dict[str, Any]:
    current = telegram_sync.state.get(XFILES_PRODUCT_MARGINS_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, list):
        items = []
    current["items"] = items
    telegram_sync.state[XFILES_PRODUCT_MARGINS_STATE_KEY] = current
    return current


def _xfiles_clean_text(value: Any, max_len: int = 8000) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:max_len]


def _xfiles_clean_margin(value: Any, default: float = 1.0) -> float:
    try:
        return round(min(1.0, max(0.0, float(value if value is not None else default))), 4)
    except Exception:
        return round(min(1.0, max(0.0, float(default or 1.0))), 4)


def _xfiles_product_margin_from_any(raw: Any) -> Optional[XFilesProductMarginDTO]:
    if isinstance(raw, XFilesProductMarginDTO):
        return raw
    if not isinstance(raw, dict):
        return None
    try:
        payload = dict(raw)
        keywords = payload.get("keywords")
        if isinstance(keywords, str):
            payload["keywords"] = [part.strip() for part in re.split(r"[,;\n]+", keywords) if part.strip()]
        payload["updated_at"] = str(payload.get("updated_at") or _utc_now().isoformat())
        return XFilesProductMarginDTO(**payload)
    except Exception:
        return None


def _xfiles_load_product_margins() -> List[XFilesProductMarginDTO]:
    rows: List[XFilesProductMarginDTO] = []
    for raw in _xfiles_product_margins_state().get("items") or []:
        item = _xfiles_product_margin_from_any(raw)
        if item:
            rows.append(item)
    rows.sort(key=lambda item: item.updated_at, reverse=True)
    return rows


def _xfiles_product_margin_for_match(product_match: Any) -> float:
    text = str(product_match or "").strip().lower()
    if not text:
        return 1.0
    for item in _xfiles_load_product_margins():
        candidates = [
            item.name,
            *item.keywords,
            item.icp,
            item.pains,
            item.outcomes,
            item.sell_to,
        ]
        for candidate in candidates:
            needle = str(candidate or "").strip().lower()
            if needle and needle in text:
                return _xfiles_clean_margin(item.margin, 1.0)
    return 1.0


def _xfiles_product_catalog_text(item: XFilesProductMarginDTO) -> str:
    return " ".join(
        str(part or "")
        for part in [
            item.name,
            " ".join(item.keywords or []),
            item.icp,
            item.pains,
            item.outcomes,
            item.price,
            item.timeline,
            item.proofs,
            item.cases,
            item.limitations,
            item.sell_to,
            item.do_not_sell_to,
        ]
    ).lower()


def _xfiles_product_match_probability(score: Any, *, blocked: bool = False) -> float:
    try:
        value = max(0, min(100, int(score or 0)))
    except Exception:
        value = 0
    if blocked:
        return 0.05
    if value >= 82:
        return 0.62
    if value >= 60:
        return 0.48
    if value >= 35:
        return 0.30
    return 0.16


def _xfiles_product_match_candidates(text: Any, *, limit: int = 3) -> List[Dict[str, Any]]:
    hay = str(text or "").lower()
    if not hay:
        return []
    rows: List[Dict[str, Any]] = []
    for item in _xfiles_load_product_margins():
        catalog_text = _xfiles_product_catalog_text(item)
        keyword_hits = sum(1 for keyword in item.keywords if str(keyword or "").strip().lower() in hay)
        name_hit = 1 if str(item.name or "").strip().lower() and str(item.name or "").strip().lower() in hay else 0
        pain_hits = _xfiles_keyword_hits(hay, [part for part in re.split(r"[,;\n]+", item.pains or "") if part.strip()])
        icp_hits = _xfiles_keyword_hits(hay, [part for part in re.split(r"[,;\n]+", item.icp or "") if part.strip()])
        outcome_hits = _xfiles_keyword_hits(hay, [part for part in re.split(r"[,;\n]+", item.outcomes or "") if part.strip()])
        sell_to_hits = _xfiles_keyword_hits(hay, [part for part in re.split(r"[,;\n]+", item.sell_to or "") if part.strip()])
        do_not_sell_hits = _xfiles_keyword_hits(hay, [part for part in re.split(r"[,;\n]+", item.do_not_sell_to or "") if part.strip()])
        overlap_words = 0
        for word in set(re.findall(r"[a-zа-яё0-9]{4,}", hay, flags=re.IGNORECASE)):
            if word in catalog_text:
                overlap_words += 1
        score = min(
            100,
            name_hit * 24
            + keyword_hits * 14
            + len(pain_hits) * 12
            + len(icp_hits) * 10
            + len(outcome_hits) * 8
            + len(sell_to_hits) * 10
            + min(18, overlap_words * 2),
        )
        if do_not_sell_hits:
            score = max(0, score - 35)
        if score <= 0:
            continue
        margin = _xfiles_clean_margin(item.margin, 1.0)
        probability = _xfiles_product_match_probability(score, blocked=bool(do_not_sell_hits))
        value_hint = _xfiles_need_estimated_value_from_budget(item.price)
        expected_profit = _xfiles_expected_profit(value_hint, probability, margin) if value_hint > 0 else 0.0
        # If price is not filled yet, still keep a deterministic business rank
        # so stronger/high-margin products float up without pretending we know revenue.
        rank_value = expected_profit if expected_profit > 0 else round(float(score) * probability * margin * 1000, 2)
        recommendation = "лучший оффер" if score >= 60 and not do_not_sell_hits else "альтернативный оффер" if score >= 35 else "не продавать пока"
        rows.append(
            {
                "id": item.id,
                "name": item.name,
                "score": int(score),
                "margin": margin,
                "probability": probability,
                "expected_value_hint": value_hint,
                "expected_profit_rank": expected_profit,
                "rank_value": rank_value,
                "recommendation": recommendation,
                "why": ", ".join([*pain_hits[:3], *icp_hits[:2], *outcome_hits[:2], *sell_to_hits[:2]]) or "совпадение по описанию и ключевым словам",
                "do_not_sell_reason": ", ".join(do_not_sell_hits[:4]),
                "price": item.price,
                "timeline": item.timeline,
            }
        )
    rows.sort(
        key=lambda row: (
            float(row.get("rank_value") or 0),
            int(row.get("score") or 0),
            float(row.get("margin") or 0),
        ),
        reverse=True,
    )
    return rows[: max(1, min(int(limit or 3), 10))]


def _xfiles_product_pitch(product: Dict[str, Any], need: str, contact_name: str = "") -> str:
    product_name = str(product.get("name") or "подходящий оффер").strip()
    compact_need = _xfiles_clean_text(need, 180) or "вашу задачу"
    first_name = str(contact_name or "").strip().split()[0] if str(contact_name or "").strip() else "Добрый день"
    price = str(product.get("price") or "").strip()
    price_part = f" Обычно это {price}." if price else ""
    if first_name == "Добрый день":
        return f"Добрый день. По вашей задаче “{compact_need}” может подойти {product_name}.{price_part} Можно быстро сверить контекст и понять, есть ли смысл идти дальше?"
    return f"{first_name}, добрый день. По вашей задаче “{compact_need}” может подойти {product_name}.{price_part} Можно быстро сверить контекст и понять, есть ли смысл идти дальше?"


def _xfiles_upsert_product_margin(payload: XFilesProductMarginPayload) -> XFilesProductMarginDTO:
    name = _xfiles_clean_text(payload.name, 300)
    if not name:
        raise HTTPException(status_code=400, detail="Название продукта обязательно")
    now = _utc_now().isoformat()
    item_id = _xfiles_clean_text(payload.id, 120) or f"product_{uuid.uuid4().hex[:12]}"
    keywords = [
        str(keyword or "").strip()[:120]
        for keyword in (payload.keywords or [])
        if str(keyword or "").strip()
    ]
    item = XFilesProductMarginDTO(
        id=item_id,
        name=name,
        keywords=keywords,
        margin=_xfiles_clean_margin(payload.margin, 1.0),
        icp=_xfiles_clean_text(payload.icp, 2000) or "",
        pains=_xfiles_clean_text(payload.pains, 2000) or "",
        outcomes=_xfiles_clean_text(payload.outcomes, 2000) or "",
        price=_xfiles_clean_text(payload.price, 500) or "",
        timeline=_xfiles_clean_text(payload.timeline, 500) or "",
        proofs=_xfiles_clean_text(payload.proofs, 2000) or "",
        cases=_xfiles_clean_text(payload.cases, 2000) or "",
        limitations=_xfiles_clean_text(payload.limitations, 2000) or "",
        sell_to=_xfiles_clean_text(payload.sell_to, 2000) or "",
        do_not_sell_to=_xfiles_clean_text(payload.do_not_sell_to, 2000) or "",
        updated_at=now,
    )
    state = _xfiles_product_margins_state()
    rows = [
        row
        for row in state.get("items") or []
        if isinstance(row, dict)
        and str(row.get("id") or "").strip() != item.id
        and str(row.get("name") or "").strip().lower() != item.name.lower()
    ]
    rows.insert(0, item.model_dump())
    state["items"] = rows
    telegram_sync.save_state()
    return item


def _xfiles_delete_product_margin(item_id: str) -> bool:
    target = str(item_id or "").strip()
    if not target:
        return False
    state = _xfiles_product_margins_state()
    rows = [row for row in state.get("items") or [] if not (isinstance(row, dict) and str(row.get("id") or "") == target)]
    changed = len(rows) != len(state.get("items") or [])
    state["items"] = rows
    if changed:
        telegram_sync.save_state()
    return changed


def _xfiles_expected_profit(expected_value: Any, probability: Any, margin: Any = 1.0) -> float:
    try:
        value = max(0.0, float(expected_value or 0.0))
    except Exception:
        value = 0.0
    try:
        prob = min(1.0, max(0.0, float(probability or 0.0)))
    except Exception:
        prob = 0.0
    margin_value = _xfiles_clean_margin(margin, 1.0)
    return round(value * prob * margin_value, 2)


def _xfiles_stable_norm(value: Any, *, limit: int = 800) -> str:
    text = str(value or "").replace("ё", "е").replace("Ё", "е").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text[: max(1, int(limit or 1))]


def _xfiles_operational_stable_key(kind: str, fields: Dict[str, Any]) -> str:
    normalized = {
        str(key): _xfiles_stable_norm(value)
        for key, value in fields.items()
        if _xfiles_stable_norm(value)
    }
    raw = json.dumps({"kind": kind, "fields": normalized}, ensure_ascii=False, sort_keys=True)
    return f"{kind}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:24]}"


def _xfiles_deal_stable_key_from_parts(
    *,
    title: Any = "",
    source: Any = "",
    source_chat: Any = "",
    source_message_id: Any = "",
    contact_key: Any = "",
    need: Any = "",
    company: Any = "",
) -> str:
    source_value = _xfiles_stable_norm(source, limit=200)
    chat_value = _xfiles_stable_norm(source_chat, limit=200)
    message_value = _xfiles_stable_norm(source_message_id, limit=120)
    contact_value = _xfiles_stable_norm(contact_key, limit=220)
    if chat_value and message_value:
        return _xfiles_operational_stable_key(
            "deal",
            {"source_chat": chat_value, "source_message_id": message_value},
        )
    if source_value and contact_value:
        return _xfiles_operational_stable_key(
            "deal",
            {"source": source_value, "contact_key": contact_value},
        )
    return _xfiles_operational_stable_key(
        "deal",
        {
            "source": source_value,
            "source_chat": chat_value,
            "title": _xfiles_stable_norm(title, limit=300),
            "need": _xfiles_stable_norm(need, limit=300),
            "company": _xfiles_stable_norm(company, limit=200),
        },
    )


def _xfiles_deal_stable_key_from_payload(payload: XFilesDealPayload) -> str:
    explicit = _xfiles_stable_norm(getattr(payload, "stable_key", None), limit=120)
    if explicit:
        return explicit
    return _xfiles_deal_stable_key_from_parts(
        title=payload.title,
        source=payload.source,
        source_chat=payload.source_chat,
        source_message_id=payload.source_message_id,
        contact_key=payload.contact_key,
        need=payload.need,
        company=payload.company,
    )


def _xfiles_deal_stable_key(item: XFilesDealDTO) -> str:
    explicit = _xfiles_stable_norm(getattr(item, "stable_key", None), limit=120)
    if explicit:
        return explicit
    return _xfiles_deal_stable_key_from_parts(
        title=item.title,
        source=item.source,
        source_chat=item.source_chat,
        source_message_id=item.source_message_id,
        contact_key=item.contact_key,
        need=item.need,
        company=item.company,
    )


def _xfiles_need_stable_key(item: XFilesNeedSignalDTO) -> str:
    explicit = _xfiles_stable_norm(getattr(item, "stable_key", None), limit=120)
    if explicit:
        return explicit
    return _xfiles_operational_stable_key(
        "need",
        {
            "source": item.source,
            "lead": item.lead,
            "message_id": item.message_id,
            "contact_key": item.contact_key,
            "need": item.need or item.text,
        },
    )


def _xfiles_deal_from_payload(payload: XFilesDealPayload, deal_id: Optional[str] = None) -> XFilesDealDTO:
    now = _utc_now().isoformat()
    title = _xfiles_clean_text(payload.title, 500)
    if not title:
        raise HTTPException(status_code=400, detail="Название сделки обязательно")
    margin = _xfiles_clean_margin(payload.margin, _xfiles_product_margin_for_match(payload.product_match))
    expected_profit = _xfiles_expected_profit(payload.expected_value, payload.probability, margin)
    return XFilesDealDTO(
        id=deal_id or f"deal_{uuid.uuid4().hex[:16]}",
        stable_key=_xfiles_deal_stable_key_from_payload(payload),
        title=title,
        stage=payload.stage,
        score=max(0, min(100, int(payload.score or 0))),
        expected_value=float(payload.expected_value or 0.0),
        probability=float(payload.probability or 0.0),
        margin=margin,
        expected_profit=expected_profit,
        contact_key=_xfiles_clean_text(payload.contact_key, 500),
        contact_name=_xfiles_clean_text(payload.contact_name, 500),
        company=_xfiles_clean_text(payload.company, 500),
        source=_xfiles_clean_text(payload.source, 500),
        source_chat=_xfiles_clean_text(payload.source_chat, 500),
        source_message_id=_xfiles_clean_text(payload.source_message_id, 200),
        need=_xfiles_clean_text(payload.need),
        product_match=_xfiles_clean_text(payload.product_match),
        next_action=_xfiles_clean_text(payload.next_action),
        next_action_at=_xfiles_clean_text(payload.next_action_at, 200),
        owner=_xfiles_clean_text(payload.owner, 500),
        notes=_xfiles_clean_text(payload.notes),
        created_at=now,
        updated_at=now,
    )


def _xfiles_deal_to_payload(item: XFilesDealDTO) -> Dict[str, Any]:
    item.stable_key = item.stable_key or _xfiles_deal_stable_key(item)
    return item.model_dump(
        exclude={
            "sla_hours",
            "sla_status",
            "sla_reason",
            "sla_deadline_at",
            "stale_hours",
        }
    )


def _xfiles_deal_from_any(raw: Any) -> Optional[XFilesDealDTO]:
    if isinstance(raw, XFilesDealDTO):
        raw.stable_key = raw.stable_key or _xfiles_deal_stable_key(raw)
        return raw
    if isinstance(raw, dict):
        try:
            item = XFilesDealDTO(**raw)
            item.stable_key = item.stable_key or _xfiles_deal_stable_key(item)
            return item
        except Exception:
            return None
    return None


def _xfiles_audit_from_any(raw: Any) -> Optional[XFilesDealAuditDTO]:
    if isinstance(raw, XFilesDealAuditDTO):
        return raw
    if isinstance(raw, dict):
        try:
            return XFilesDealAuditDTO(**raw)
        except Exception:
            return None
    return None


def _xfiles_audit_from_pg_row(row: Any) -> Optional[XFilesDealAuditDTO]:
    if not row:
        return None

    def get(key: str, index: int = 0, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            return row[index]
        except Exception:
            return default

    def ts(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or "")

    changes = get("changes", 9, {})
    if isinstance(changes, str):
        try:
            changes = json.loads(changes)
        except Exception:
            changes = {}
    if not isinstance(changes, dict):
        changes = {}
    try:
        return XFilesDealAuditDTO(
            id=str(get("id", 0) or ""),
            ts=ts(get("ts", 1)),
            action=str(get("action", 2) or ""),
            deal_id=str(get("deal_id", 3) or ""),
            deal_title=str(get("deal_title", 4) or ""),
            actor=str(get("actor", 5) or "user"),
            source=str(get("source", 6) or "ui"),
            before_stage=_xfiles_clean_text(get("before_stage", 7), 100),
            after_stage=_xfiles_clean_text(get("after_stage", 8), 100),
            changes=changes,
        )
    except Exception:
        return None


def _xfiles_deal_from_pg_row(row: Any) -> XFilesDealDTO:
    def get(key: str, index: int = 0, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            return row[index]
        except Exception:
            return default

    def ts(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value or "")

    item = XFilesDealDTO(
        id=str(get("id", 0) or ""),
        stable_key=_xfiles_clean_text(get("stable_key", 22), 160),
        title=str(get("title", 1) or ""),
        stage=str(get("stage", 2) or "lead"),  # type: ignore[arg-type]
        score=int(get("score", 3) or 0),
        expected_value=float(get("expected_value", 4) or 0.0),
        probability=float(get("probability", 5) or 0.0),
        margin=_xfiles_clean_margin(get("margin", 6), 1.0),
        expected_profit=float(get("expected_profit", 7) or 0.0),
        contact_key=_xfiles_clean_text(get("contact_key", 8), 500),
        contact_name=_xfiles_clean_text(get("contact_name", 9), 500),
        company=_xfiles_clean_text(get("company", 10), 500),
        source=_xfiles_clean_text(get("source", 11), 500),
        source_chat=_xfiles_clean_text(get("source_chat", 12), 500),
        source_message_id=_xfiles_clean_text(get("source_message_id", 13), 200),
        need=_xfiles_clean_text(get("need", 14)),
        product_match=_xfiles_clean_text(get("product_match", 15)),
        next_action=_xfiles_clean_text(get("next_action", 16)),
        next_action_at=_xfiles_clean_text(get("next_action_at", 17), 200),
        owner=_xfiles_clean_text(get("owner", 18), 500),
        notes=_xfiles_clean_text(get("notes", 19)),
        created_at=ts(get("created_at", 20)),
        updated_at=ts(get("updated_at", 21)),
    )
    item.stable_key = item.stable_key or _xfiles_deal_stable_key(item)
    return item


_XFILES_DEAL_SELECT_SQL = """
SELECT
    id, title, stage, score, expected_value, probability, margin, expected_profit,
    contact_key, contact_name, company, source, source_chat, source_message_id,
    need, product_match, next_action, next_action_at, owner, notes,
    created_at, updated_at, stable_key
FROM xfiles_deals
"""


_XFILES_DEAL_UPSERT_SQL = """
INSERT INTO xfiles_deals (
    id, stable_key, title, stage, score, expected_value, probability, margin, expected_profit,
    contact_key, contact_name, company, source, source_chat, source_message_id,
    need, product_match, next_action, next_action_at, owner, notes,
    payload, created_at, updated_at
)
VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s,
    %s::jsonb, %s, %s
)
ON CONFLICT (id) DO UPDATE SET
    stable_key = EXCLUDED.stable_key,
    title = EXCLUDED.title,
    stage = EXCLUDED.stage,
    score = EXCLUDED.score,
    expected_value = EXCLUDED.expected_value,
    probability = EXCLUDED.probability,
    margin = EXCLUDED.margin,
    expected_profit = EXCLUDED.expected_profit,
    contact_key = EXCLUDED.contact_key,
    contact_name = EXCLUDED.contact_name,
    company = EXCLUDED.company,
    source = EXCLUDED.source,
    source_chat = EXCLUDED.source_chat,
    source_message_id = EXCLUDED.source_message_id,
    need = EXCLUDED.need,
    product_match = EXCLUDED.product_match,
    next_action = EXCLUDED.next_action,
    next_action_at = EXCLUDED.next_action_at,
    owner = EXCLUDED.owner,
    notes = EXCLUDED.notes,
    payload = EXCLUDED.payload,
    updated_at = EXCLUDED.updated_at
"""


_XFILES_DEAL_AUDIT_INSERT_SQL = """
INSERT INTO xfiles_deal_audit (
    id, ts, action, deal_id, deal_title, actor, source,
    before_stage, after_stage, changes
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT (id) DO NOTHING
"""


def _xfiles_postgres_existing_deal_id_by_stable_key(cur: Any, stable_key: Optional[str]) -> Optional[str]:
    normalized = str(stable_key or "").strip()
    if not normalized:
        return None
    cur.execute("SELECT id FROM xfiles_deals WHERE stable_key = %s LIMIT 1", [normalized])
    existing = cur.fetchone()
    if not existing:
        return None
    if isinstance(existing, dict):
        return str(existing.get("id") or "") or None
    try:
        return str(existing[0] or "") or None
    except Exception:
        return None


def _xfiles_postgres_upsert_deal_row(cur: Any, item: XFilesDealDTO) -> XFilesDealDTO:
    item.stable_key = item.stable_key or _xfiles_deal_stable_key(item)
    item.margin = _xfiles_clean_margin(item.margin, _xfiles_product_margin_for_match(item.product_match))
    item.expected_profit = _xfiles_expected_profit(item.expected_value, item.probability, item.margin)
    existing_id = _xfiles_postgres_existing_deal_id_by_stable_key(cur, item.stable_key)
    if existing_id:
        item.id = existing_id
    payload = json.dumps(_xfiles_deal_to_payload(item), ensure_ascii=False)
    cur.execute(
        _XFILES_DEAL_UPSERT_SQL,
        [
            item.id,
            item.stable_key,
            item.title,
            item.stage,
            item.score,
            item.expected_value,
            item.probability,
            item.margin,
            item.expected_profit,
            item.contact_key,
            item.contact_name,
            item.company,
            item.source,
            item.source_chat,
            item.source_message_id,
            item.need,
            item.product_match,
            item.next_action,
            item.next_action_at,
            item.owner,
            item.notes,
            payload,
            item.created_at,
            item.updated_at,
        ],
    )
    return item


def _xfiles_postgres_insert_deal_audit_row(cur: Any, item: XFilesDealAuditDTO) -> None:
    cur.execute(
        _XFILES_DEAL_AUDIT_INSERT_SQL,
        [
            item.id,
            item.ts,
            item.action,
            item.deal_id,
            item.deal_title,
            item.actor,
            item.source,
            item.before_stage,
            item.after_stage,
            json.dumps(item.changes or {}, ensure_ascii=False),
        ],
    )


def _xfiles_migrate_state_deals_to_postgres_once() -> bool:
    global _postgres_last_error, _postgres_state_deals_migrated, _postgres_state_deals_migration_last_error
    if _postgres_state_deals_migrated:
        return True
    with _postgres_state_deals_migration_lock:
        if _postgres_state_deals_migrated:
            return True
        raw_deals = list(_xfiles_deals_state().get("items") or [])
        raw_audit = list(_xfiles_deal_audit_state().get("items") or [])
        deals = [item for item in (_xfiles_deal_from_any(row) for row in raw_deals) if item is not None]
        audit_rows = [item for item in (_xfiles_audit_from_any(row) for row in raw_audit) if item is not None]
        if not deals and not audit_rows:
            _postgres_state_deals_migrated = True
            _postgres_state_deals_migration_last_error = None
            return True
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    for item in deals:
                        _xfiles_postgres_upsert_deal_row(cur, item)
                    for item in audit_rows:
                        _xfiles_postgres_insert_deal_audit_row(cur, item)
                conn.commit()
            _postgres_state_deals_migrated = True
            _postgres_state_deals_migration_last_error = None
            _postgres_last_error = None
            _append_runtime_log(
                "postgres",
                f"X-Files сделки перенесены из state.json в PostgreSQL: deals={len(deals)}, audit={len(audit_rows)}",
            )
            return True
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_state_deals_migration_last_error = str(exc)
            _postgres_log_error_once(f"X-Files PostgreSQL migration из state.json не выполнена: {exc}")
            return False


def _xfiles_postgres_storage_available() -> bool:
    if not _postgres_ensure_xfiles_schema():
        return False
    return _xfiles_migrate_state_deals_to_postgres_once()


def _xfiles_load_deals(query: str = "", stage: str = "", limit: int = 5000) -> List[XFilesDealDTO]:
    global _postgres_last_error
    normalized_stage = str(stage or "").strip().lower()
    query_value = str(query or "").strip().lower()
    limit_value = max(1, min(int(limit or 5000), 20000))

    if _xfiles_postgres_storage_available():
        try:
            clauses: List[str] = []
            params: List[Any] = []
            if normalized_stage and normalized_stage != "all":
                clauses.append("stage = %s")
                params.append(normalized_stage)
            if query_value:
                clauses.append(
                    """
                    (
                        LOWER(title) LIKE %s OR LOWER(COALESCE(contact_name, '')) LIKE %s OR
                        LOWER(COALESCE(company, '')) LIKE %s OR LOWER(COALESCE(need, '')) LIKE %s OR
                        LOWER(COALESCE(product_match, '')) LIKE %s OR LOWER(COALESCE(next_action, '')) LIKE %s
                    )
                    """
                )
                like = f"%{query_value}%"
                params.extend([like, like, like, like, like, like])
            where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        _XFILES_DEAL_SELECT_SQL + where_sql + " ORDER BY updated_at DESC LIMIT %s",
                        [*params, limit_value],
                    )
                    rows = cur.fetchall()
            return [_xfiles_enrich_deal_runtime(_xfiles_deal_from_pg_row(row)) for row in rows]
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_log_error_once(f"X-Files deals fallback после ошибки чтения PostgreSQL: {exc}")

    items: List[XFilesDealDTO] = []
    for raw in _xfiles_deals_state().get("items") or []:
        item = _xfiles_deal_from_any(raw)
        if not item:
            continue
        if normalized_stage and normalized_stage != "all" and item.stage != normalized_stage:
            continue
        if query_value:
            hay = " ".join(
                [
                    item.title,
                    item.contact_name or "",
                    item.company or "",
                    item.need or "",
                    item.product_match or "",
                    item.next_action or "",
                    item.source_chat or "",
                ]
            ).lower()
            if query_value not in hay:
                continue
        items.append(_xfiles_enrich_deal_runtime(item))
    items.sort(key=lambda row: row.updated_at or row.created_at, reverse=True)
    return items[:limit_value]


def _xfiles_get_deal(deal_id: str) -> Optional[XFilesDealDTO]:
    global _postgres_last_error
    target = str(deal_id or "").strip()
    if not target:
        return None
    if _xfiles_postgres_storage_available():
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(_XFILES_DEAL_SELECT_SQL + " WHERE id = %s LIMIT 1", [target])
                    row = cur.fetchone()
            return _xfiles_enrich_deal_runtime(_xfiles_deal_from_pg_row(row)) if row else None
        except Exception as exc:
            _postgres_last_error = str(exc)
    for item in _xfiles_load_deals(limit=20000):
        if item.id == target:
            return _xfiles_enrich_deal_runtime(item)
    return None


def _xfiles_compact_audit_value(value: Any, max_len: int = 500) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value).strip()
    if len(text) > max_len:
        return f"{text[:max_len]}…"
    return text


def _xfiles_append_deal_audit(
    action: str,
    deal: Optional[XFilesDealDTO],
    *,
    before: Optional[XFilesDealDTO] = None,
    changes: Optional[Dict[str, Any]] = None,
    source: str = "ui",
    actor: str = "user",
) -> XFilesDealAuditDTO:
    deal_id = str((deal or before).id if (deal or before) else "")
    deal_title = str((deal or before).title if (deal or before) else "")
    compact_changes = {
        str(key): _xfiles_compact_audit_value(value)
        for key, value in (changes or {}).items()
        if key and key not in {"notes"}
    }
    item = XFilesDealAuditDTO(
        id=f"audit_{uuid.uuid4().hex[:16]}",
        ts=_utc_now().isoformat(),
        action=str(action or "update"),
        deal_id=deal_id,
        deal_title=deal_title[:500],
        actor=str(actor or "user")[:100],
        source=str(source or "ui")[:120],
        before_stage=str(before.stage) if before else None,
        after_stage=str(deal.stage) if deal else None,
        changes=compact_changes,
    )
    global _postgres_last_error
    if _xfiles_postgres_storage_available():
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    _xfiles_postgres_insert_deal_audit_row(cur, item)
                conn.commit()
            return item
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_log_error_once(f"X-Files deal audit fallback после ошибки записи PostgreSQL: {exc}")

    state = _xfiles_deal_audit_state()
    rows = [row for row in state.get("items") or [] if isinstance(row, dict)]
    rows.insert(0, item.model_dump())
    state["items"] = rows[:1000]
    telegram_sync.save_state()
    return item


def _xfiles_load_deal_audit(limit: int = 200) -> List[XFilesDealAuditDTO]:
    global _postgres_last_error
    limit_value = max(1, min(int(limit or 200), 1000))
    if _xfiles_postgres_storage_available():
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, ts, action, deal_id, deal_title, actor, source,
                               before_stage, after_stage, changes
                        FROM xfiles_deal_audit
                        ORDER BY ts DESC
                        LIMIT %s
                        """,
                        [limit_value],
                    )
                    rows = cur.fetchall()
            parsed_rows = [_xfiles_audit_from_pg_row(row) for row in rows]
            return [item for item in parsed_rows if item is not None]
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_log_error_once(f"X-Files deal audit fallback после ошибки чтения PostgreSQL: {exc}")

    rows: List[XFilesDealAuditDTO] = []
    for raw in _xfiles_deal_audit_state().get("items") or []:
        item = _xfiles_audit_from_any(raw)
        if item:
            rows.append(item)
    rows.sort(key=lambda item: item.ts, reverse=True)
    return rows[:limit_value]


def _xfiles_deals_kanban_sync(query: str = "", stage: str = "", limit_per_stage: int = 20) -> XFilesDealsKanbanDTO:
    normalized_stage = str(stage or "").strip().lower()
    stage_filter = normalized_stage if normalized_stage and normalized_stage != "all" else ""
    per_stage = max(1, min(int(limit_per_stage or 20), 100))
    rows = _xfiles_load_deals(query=query, stage=stage_filter, limit=20000)
    columns: List[XFilesDealsKanbanColumnDTO] = []
    for stage_key in _XFILES_STAGE_ORDER:
        if stage_filter and stage_filter != stage_key:
            continue
        stage_rows = [item for item in rows if str(item.stage or "") == stage_key]
        columns.append(
            XFilesDealsKanbanColumnDTO(
                stage=stage_key,  # type: ignore[arg-type]
                label=_XFILES_STAGE_LABELS.get(stage_key, stage_key),
                items=stage_rows[:per_stage],
                total=len(stage_rows),
                expected_profit=round(sum(float(item.expected_profit or 0.0) for item in stage_rows), 2),
                overdue=sum(1 for item in stage_rows if item.sla_status == "red"),
                due_soon=sum(1 for item in stage_rows if item.sla_status == "yellow"),
            )
        )
    return XFilesDealsKanbanDTO(items=columns, total=len(rows), limit_per_stage=per_stage)


def _xfiles_norm_identity(value: Any) -> str:
    return str(value or "").strip().lower()


def _xfiles_find_existing_deal_for_payload(payload: XFilesDealPayload) -> Optional[XFilesDealDTO]:
    stable_key = _xfiles_deal_stable_key_from_payload(payload)
    source = _xfiles_norm_identity(payload.source)
    source_chat = _xfiles_norm_identity(payload.source_chat)
    source_message_id = _xfiles_norm_identity(payload.source_message_id)
    contact_key = _xfiles_norm_identity(payload.contact_key)
    title = _xfiles_norm_identity(payload.title)

    if not any([source_message_id, contact_key, source_chat, title]):
        return None

    for item in _xfiles_load_deals(limit=20000):
        item_stable_key = _xfiles_norm_identity(_xfiles_deal_stable_key(item))
        item_source = _xfiles_norm_identity(item.source)
        item_chat = _xfiles_norm_identity(item.source_chat)
        item_message_id = _xfiles_norm_identity(item.source_message_id)
        item_contact_key = _xfiles_norm_identity(item.contact_key)
        item_title = _xfiles_norm_identity(item.title)

        # Stable key is the primary guard across UI screens and background jobs:
        # the same source/message/contact should never create a second deal.
        if stable_key and item_stable_key == _xfiles_norm_identity(stable_key):
            return _xfiles_enrich_deal_runtime(item)

        # A Telegram message should become only one deal draft even when it is
        # surfaced by several screens: CRM, events, contacts or enReach.
        if source_chat and source_message_id and item_chat == source_chat and item_message_id == source_message_id:
            return _xfiles_enrich_deal_runtime(item)

        # Contact-based deals are intentionally one draft per source/contact.
        if source and contact_key and item_source == source and item_contact_key == contact_key:
            return item

        # Fallback for imported/manual rows that do not have message ids yet.
        if source and source_chat and title and item_source == source and item_chat == source_chat and item_title == title:
            return item

    return None


def _xfiles_upsert_deal(item: XFilesDealDTO) -> XFilesDealDTO:
    global _postgres_last_error
    item.stable_key = item.stable_key or _xfiles_deal_stable_key(item)
    item.margin = _xfiles_clean_margin(item.margin, _xfiles_product_margin_for_match(item.product_match))
    item.expected_profit = _xfiles_expected_profit(item.expected_value, item.probability, item.margin)
    if _xfiles_postgres_storage_available():
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    _xfiles_postgres_upsert_deal_row(cur, item)
                conn.commit()
            return item
        except Exception as exc:
            _postgres_last_error = str(exc)
            _postgres_log_error_once(f"X-Files deals fallback после ошибки записи PostgreSQL: {exc}")

    state = _xfiles_deals_state()
    rows = [
        row
        for row in state.get("items") or []
        if not (
            isinstance(row, dict)
            and (
                str(row.get("id") or "") == item.id
                or (
                    item.stable_key
                    and _xfiles_norm_identity(row.get("stable_key") or "") == _xfiles_norm_identity(item.stable_key)
                )
            )
        )
    ]
    rows.insert(0, _xfiles_deal_to_payload(item))
    state["items"] = rows
    telegram_sync.save_state()
    return _xfiles_enrich_deal_runtime(item)


def _xfiles_patch_deal(deal_id: str, patch: XFilesDealPatchPayload) -> Optional[XFilesDealDTO]:
    item = _xfiles_get_deal(deal_id)
    if not item:
        return None
    updates = patch.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is None:
            setattr(item, key, None)
        elif key in {"expected_value", "probability"}:
            setattr(item, key, float(value))
        elif key == "margin":
            setattr(item, key, _xfiles_clean_margin(value, item.margin))
        elif key == "score":
            setattr(item, key, max(0, min(100, int(value))))
        elif key == "stage":
            setattr(item, key, str(value).strip().lower() or item.stage)
        elif key == "title":
            cleaned = _xfiles_clean_text(value, 500)
            if cleaned:
                setattr(item, key, cleaned)
        else:
            setattr(item, key, _xfiles_clean_text(value))
    if "margin" not in updates and "product_match" in updates:
        item.margin = _xfiles_product_margin_for_match(item.product_match)
    if "stable_key" not in updates:
        item.stable_key = _xfiles_deal_stable_key_from_parts(
            title=item.title,
            source=item.source,
            source_chat=item.source_chat,
            source_message_id=item.source_message_id,
            contact_key=item.contact_key,
            need=item.need,
            company=item.company,
        )
    item.expected_profit = _xfiles_expected_profit(item.expected_value, item.probability, item.margin)
    item.updated_at = _utc_now().isoformat()
    return _xfiles_upsert_deal(item)


def _xfiles_delete_deal(deal_id: str) -> bool:
    global _postgres_last_error
    target = str(deal_id or "").strip()
    if not target:
        return False
    if _xfiles_postgres_storage_available():
        try:
            with _postgres_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM xfiles_deals WHERE id = %s", [target])
                    changed = int(cur.rowcount or 0) > 0
                conn.commit()
            return changed
        except Exception as exc:
            _postgres_last_error = str(exc)

    state = _xfiles_deals_state()
    rows = [row for row in state.get("items") or [] if not (isinstance(row, dict) and row.get("id") == target)]
    changed = len(rows) != len(state.get("items") or [])
    state["items"] = rows
    if changed:
        telegram_sync.save_state()
    return changed


from app.services.xfiles_deals_engine import (
    _xfiles_contact_recommendation,
    _xfiles_contact_signal_profile,
    _xfiles_daily_contacts_sync,
    _xfiles_deal_assistant_sync,
    _xfiles_deal_opportunities_sync,
    _xfiles_deals_status_sync,
    _xfiles_event_sales_plan_sync,
    _xfiles_function_impacts,
    _xfiles_need_signal_from_parts,
    _xfiles_need_signals_page_sync,
    _xfiles_template_model_benchmarks,
)



def _xfiles_parse_optional_dt(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_XFILES_STAGE_SLA_HOURS: Dict[str, int] = {
    "idea": 168,
    "lead": 48,
    "qualified": 48,
    "proposal": 72,
    "negotiation": 48,
    "contract": 72,
    "won": 0,
    "lost": 0,
}


def _xfiles_hours_text(hours: float) -> str:
    safe = max(0.0, float(hours or 0.0))
    if safe < 1:
        return "меньше часа"
    if safe < 24:
        return f"{int(round(safe))} ч"
    days = safe / 24.0
    if days < 10:
        return f"{days:.1f} дн"
    return f"{int(round(days))} дн"


def _xfiles_enrich_deal_runtime(item: XFilesDealDTO) -> XFilesDealDTO:
    stage = str(item.stage or "lead").strip().lower()
    sla_hours = int(_XFILES_STAGE_SLA_HOURS.get(stage, 72))
    now = _utc_now()
    item.margin = _xfiles_clean_margin(item.margin, _xfiles_product_margin_for_match(item.product_match))
    item.expected_profit = _xfiles_expected_profit(item.expected_value, item.probability, item.margin)
    updated_dt = _xfiles_parse_optional_dt(item.updated_at)
    created_dt = _xfiles_parse_optional_dt(item.created_at)
    next_action_dt = _xfiles_parse_optional_dt(item.next_action_at)
    stale_base = updated_dt or created_dt or now
    stale_hours = max(0.0, round((now - stale_base).total_seconds() / 3600.0, 1))

    item.sla_hours = sla_hours
    item.stale_hours = stale_hours

    if stage in {"won", "lost"}:
        item.sla_status = "done"
        item.sla_deadline_at = None
        item.sla_reason = "Сделка закрыта"
        return item

    deadline_dt = next_action_dt or ((updated_dt or created_dt or now) + timedelta(hours=sla_hours))
    item.sla_deadline_at = deadline_dt.isoformat()

    remaining_hours = (deadline_dt - now).total_seconds() / 3600.0
    yellow_threshold = max(6.0, float(sla_hours) * 0.25)
    if remaining_hours < 0:
        item.sla_status = "red"
        item.sla_reason = f"Просрочено на {_xfiles_hours_text(abs(remaining_hours))}"
    elif remaining_hours <= yellow_threshold:
        item.sla_status = "yellow"
        item.sla_reason = f"Нужно действие через {_xfiles_hours_text(remaining_hours)}"
    else:
        item.sla_status = "green"
        item.sla_reason = f"В норме, осталось {_xfiles_hours_text(remaining_hours)}"
    return item


def _xfiles_deal_reminder_text(item: XFilesDealDTO) -> str:
    action = _xfiles_clean_text(item.next_action, 500) or "назначить следующий шаг"
    contact = _xfiles_clean_text(item.contact_name or item.contact_key or item.company, 160)
    contact_part = f" для {contact}" if contact else ""
    if item.sla_status == "red":
        return f"Просрочено: {action}{contact_part}. {item.sla_reason}"
    if item.sla_status == "yellow":
        return f"Скоро дедлайн: {action}{contact_part}. {item.sla_reason}"
    if item.sla_status == "done":
        return "Сделка закрыта, reminder не нужен."
    return f"В плане: {action}{contact_part}. {item.sla_reason}"


def _xfiles_deal_reminder_from_deal(item: XFilesDealDTO) -> XFilesDealReminderDTO:
    status_urgency = {"red": 300, "yellow": 200, "green": 100, "done": 0}
    profit_urgency = min(99, int(float(item.expected_profit or item.expected_value or 0.0) / 10000.0))
    stage = str(item.stage or "lead").strip().lower() or "lead"
    return XFilesDealReminderDTO(
        deal_id=item.id,
        title=item.title,
        stage=item.stage,
        stage_label=_XFILES_STAGE_LABELS.get(stage, stage),
        contact_key=item.contact_key,
        contact_name=item.contact_name,
        company=item.company,
        source_chat=item.source_chat,
        next_action=_xfiles_clean_text(item.next_action, 500),
        next_action_at=item.next_action_at,
        sla_status=item.sla_status,
        sla_reason=item.sla_reason,
        sla_deadline_at=item.sla_deadline_at,
        stale_hours=float(item.stale_hours or 0.0),
        expected_profit=float(item.expected_profit or 0.0),
        urgency=int(status_urgency.get(item.sla_status, 0) + profit_urgency),
        reminder_text=_xfiles_deal_reminder_text(item),
    )


def _xfiles_deal_reminders_sync(limit: int = 50, include_done: bool = False) -> XFilesDealRemindersDTO:
    active_stages = {"idea", "lead", "qualified", "proposal", "negotiation", "contract"}
    rows = _xfiles_load_deals(limit=20000)
    reminders = [
        _xfiles_deal_reminder_from_deal(item)
        for item in rows
        if include_done or item.stage in active_stages or item.sla_status in {"red", "yellow"}
    ]
    status_order = {"red": 0, "yellow": 1, "green": 2, "done": 3}
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def reminder_deadline(item: XFilesDealReminderDTO) -> datetime:
        return _xfiles_parse_optional_dt(item.next_action_at or item.sla_deadline_at) or epoch

    reminders.sort(
        key=lambda item: (
            status_order.get(item.sla_status, 9),
            reminder_deadline(item).timestamp(),
            -float(item.expected_profit or 0.0),
            -float(item.stale_hours or 0.0),
            item.title.lower(),
        )
    )
    safe_limit = max(1, int(limit or 1))
    return XFilesDealRemindersDTO(
        items=reminders[:safe_limit],
        total=len(reminders),
        overdue=sum(1 for item in reminders if item.sla_status == "red"),
        due_soon=sum(1 for item in reminders if item.sla_status == "yellow"),
        generated_at=_utc_now().isoformat(),
    )


def _xfiles_deal_conversion_sync() -> XFilesDealConversionDTO:
    deals = _xfiles_load_deals(limit=20000)
    active_deals = [item for item in deals if item.stage in {"idea", "lead", "qualified", "proposal", "negotiation", "contract"}]
    outreach_rows = _xfiles_load_outreach_sequences(limit=20000)
    outreach_stats = _xfiles_outreach_stats()
    deal_status = _xfiles_deals_status_sync()
    outreach_meetings = sum(
        1
        for item in outreach_rows
        if item.status == "meeting_booked" or any(touch.status == "meeting_booked" for touch in item.touches)
    )
    proposals = sum(1 for item in deals if item.stage in {"proposal", "negotiation", "contract", "won"})

    def safe_rate(value: int, denominator: int) -> float:
        return round((float(value) / float(denominator)) * 100.0, 1) if denominator > 0 else 0.0

    meeting_denominator = int(outreach_stats.replies or outreach_stats.sent or 0)
    message = (
        "Conversion считается из двух источников: outReach даёт sent/reply/meeting, "
        "pipeline сделок даёт proposal и общий funnel."
    )
    return XFilesDealConversionDTO(
        generated_at=_utc_now().isoformat(),
        deal_total=len(deals),
        active_deals=len(active_deals),
        outreach_total=int(outreach_stats.total or 0),
        outreach_sent=int(outreach_stats.sent or 0),
        outreach_replies=int(outreach_stats.replies or 0),
        outreach_meetings=outreach_meetings,
        proposals=proposals,
        reply_rate_percent=float(outreach_stats.reply_rate_percent or 0.0),
        meeting_rate_percent=safe_rate(outreach_meetings, meeting_denominator),
        proposal_rate_percent=safe_rate(proposals, len(active_deals)),
        funnel=deal_status.conversion_funnel,
        bottleneck=deal_status.conversion_bottleneck,
        message=message,
    )




def _xfiles_profit_optimization_sync() -> XFilesProfitOptimizationDTO:
    status = _xfiles_deals_status_sync()
    ranked_tasks = sorted(
        status.priority_tasks,
        key=lambda row: (
            float(row.get("expected_profit") or 0.0),
            float(row.get("profit_per_user_hour") or 0.0),
            int(row.get("score") or 0),
        ),
        reverse=True,
    )
    message = (
        "Profit optimization читает готовую экономику сделок: expected profit, ROI источников, "
        "стоимость квалификации, сравнение OpenRouter-шаблонов и список действий на сегодня."
    )
    return XFilesProfitOptimizationDTO(
        generated_at=_utc_now().isoformat(),
        ranked_tasks=ranked_tasks[:25],
        quick_money_deals=status.quick_money_deals,
        strategic_deals=status.strategic_deals,
        source_roi=status.source_roi,
        source_group_recommendations=status.source_group_recommendations,
        cost_metrics=status.cost_metrics,
        template_model_benchmarks=_xfiles_template_model_benchmarks(limit=25),
        recommendations=status.recommended_actions,
        daily_plan=status.daily_plan,
        profit_per_user_hour=float(status.profit_per_user_hour or 0.0),
        message=message,
    )


def _xfiles_opportunity_money(item: XFilesDealDTO) -> float:
    expected_profit = float(item.expected_profit or 0.0)
    if expected_profit > 0:
        return round(expected_profit, 2)
    calculated = _xfiles_expected_profit(item.expected_value, item.probability, item.margin)
    if calculated > 0:
        return round(calculated, 2)
    return round(float(item.expected_value or 0.0), 2)


def _xfiles_opportunity_attention_hours(item: XFilesDealDTO) -> float:
    stage_cost = {
        "idea": 0.45,
        "lead": 0.35,
        "qualified": 0.6,
        "proposal": 0.9,
        "negotiation": 1.2,
        "contract": 1.5,
        "won": 0.2,
        "lost": 0.1,
    }.get(str(item.stage or "lead"), 0.5)
    if item.sla_status == "red":
        stage_cost += 0.35
    elif item.sla_status == "yellow":
        stage_cost += 0.2
    if not str(item.next_action or "").strip():
        stage_cost += 0.25
    return round(max(0.1, stage_cost), 2)


def _xfiles_opportunity_urgency_score(item: XFilesDealDTO) -> int:
    score = 0
    if item.sla_status == "red":
        score += 35
    elif item.sla_status == "yellow":
        score += 20
    action_at = _xfiles_parse_optional_dt(item.next_action_at)
    if action_at:
        now = _utc_now()
        if action_at <= now:
            score += 35
        elif action_at <= now + timedelta(days=1):
            score += 25
        elif action_at <= now + timedelta(days=3):
            score += 12
    if item.stage in {"qualified", "proposal", "negotiation", "contract"}:
        score += 15
    if str(item.next_action or "").strip():
        score += 10
    return min(100, max(0, score))


def _xfiles_opportunity_when_to_write(item: XFilesDealDTO, urgency_score: int) -> str:
    if item.next_action_at:
        return item.next_action_at
    if item.sla_status == "red" or urgency_score >= 60:
        return "сегодня, без откладывания"
    if item.sla_status == "yellow" or item.stage in {"qualified", "proposal", "negotiation", "contract"}:
        return "в ближайший рабочий слот"
    if str(item.next_action or "").strip():
        return "сегодня после короткой подготовки"
    return "после быстрой квалификации контекста"


def _xfiles_opportunity_first_message(item: XFilesDealDTO) -> str:
    if item.next_action:
        return item.next_action
    contact = item.contact_name or item.company or item.contact_key or "контакт"
    need = _xfiles_clean_text(item.need, 180) or "вашу задачу"
    offer = _xfiles_clean_text(item.product_match, 140) or "короткую диагностику и следующий шаг"
    return f"Написать {contact}: вижу контекст про “{need}”. Можем предложить {offer} и быстро понять, есть ли смысл созвониться."




def _xfiles_metric_history_items() -> List[XFilesMetricHistoryPointDTO]:
    current = telegram_sync.state.get(XFILES_METRIC_HISTORY_STATE_KEY)
    if not isinstance(current, dict):
        return []
    rows = current.get("items")
    if not isinstance(rows, list):
        return []
    parsed: List[XFilesMetricHistoryPointDTO] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            parsed.append(XFilesMetricHistoryPointDTO(**row))
        except Exception:
            continue
    parsed.sort(key=lambda item: item.date)
    return parsed


def _xfiles_metric_history_upsert(status: XFilesDealsStatusDTO) -> List[XFilesMetricHistoryPointDTO]:
    cost_metrics = status.cost_metrics if isinstance(status.cost_metrics, dict) else {}
    today = _utc_now().date().isoformat()
    point = XFilesMetricHistoryPointDTO(
        date=today,
        pipeline_profit=round(float(status.pipeline_profit or 0.0), 2),
        profit_per_user_hour=round(float(status.profit_per_user_hour or 0.0), 2),
        qualified_leads_per_day=round(float(status.qualified_leads_per_day or 0.0), 2),
        cost_per_qualified_lead_usd=round(float(cost_metrics.get("cost_per_qualified_lead_usd") or 0.0), 4),
        next_action_ready=int(status.next_action_ready or 0),
        active_deals=int(status.active or 0),
        source_roi_count=int(cost_metrics.get("source_roi_count") or len(status.source_roi or [])),
    )
    rows_by_date = {item.date: item for item in _xfiles_metric_history_items()}
    rows_by_date[today] = point
    rows = sorted(rows_by_date.values(), key=lambda item: item.date)[-90:]
    telegram_sync.state[XFILES_METRIC_HISTORY_STATE_KEY] = {
        "updated_at": _utc_now().isoformat(),
        "items": [item.model_dump() for item in rows],
    }
    try:
        telegram_sync.save_state()
    except Exception:
        pass
    return rows




def _xfiles_north_star_sync() -> XFilesNorthStarDTO:
    status = _xfiles_deals_status_sync()
    history = _xfiles_metric_history_upsert(status)
    message = (
        "North Star измеряет X-Files как revenue operating system: деньги в pipeline, "
        "скорость квалификации, экономию ручного времени и стоимость LLM-квалификации."
    )
    return XFilesNorthStarDTO(
        generated_at=_utc_now().isoformat(),
        pipeline_profit_per_attention_hour=float(status.profit_per_user_hour or 0.0),
        qualified_leads_per_day=float(status.qualified_leads_per_day or 0.0),
        avg_time_to_next_action_minutes=float(status.avg_time_to_next_action_minutes or 0.0),
        function_impacts=_xfiles_function_impacts(status),
        history=history,
        message=message,
    )


def _xfiles_existing_deals_by_contact() -> Dict[str, XFilesDealDTO]:
    index: Dict[str, XFilesDealDTO] = {}
    terminal_stages = {"won", "lost"}
    for item in _xfiles_load_deals(limit=20000):
        key = _xfiles_norm_identity(item.contact_key)
        if not key:
            continue
        previous = index.get(key)
        if not previous:
            index[key] = item
            continue
        previous_terminal = previous.stage in terminal_stages
        item_terminal = item.stage in terminal_stages
        if previous_terminal and not item_terminal:
            index[key] = item
        elif previous_terminal == item_terminal and str(item.updated_at or "") > str(previous.updated_at or ""):
            index[key] = item
    return index


for _name, _value in list(globals().items()):
    if _name.startswith("_") and callable(_value) and _name not in {"_with_legacy_globals"}:
        globals()[_name] = _with_legacy_globals(_value)

__all__ = (
    "annotations",
    "hashlib",
    "json",
    "logging",
    "re",
    "sys",
    "threading",
    "uuid",
    "datetime",
    "timedelta",
    "timezone",
    "wraps",
    "Any",
    "Dict",
    "List",
    "Literal",
    "Optional",
    "HTTPException",
    "_with_legacy_globals",
    "_xfiles_outreach_item_deal_title",
    "_xfiles_attach_deals_to_outreach_items",
    "_get_outreach_item_by_id",
    "_XFILES_OUTREACH_TOUCH_BLUEPRINTS",
    "_xfiles_outreach_state",
    "_xfiles_outreach_sequence_from_any",
    "_xfiles_outreach_sequence_id",
    "_xfiles_outreach_sequence_stable_key",
    "_xfiles_outreach_variants",
    "_xfiles_outreach_touches",
    "_xfiles_outreach_sequence_from_payload",
    "_xfiles_outreach_payload_from_enreach_item",
    "_xfiles_load_outreach_sequences",
    "_xfiles_upsert_outreach_sequence",
    "_xfiles_create_outreach_sequence",
    "_xfiles_create_outreach_sequence_from_enreach",
    "_xfiles_outreach_payload_from_deal",
    "_xfiles_create_outreach_sequence_from_deal",
    "_xfiles_update_outreach_touch_status",
    "_xfiles_update_outreach_sequence",
    "_XFILES_OUTREACH_SENT_STATUSES",
    "_XFILES_OUTREACH_REPLY_STATUSES",
    "_xfiles_outreach_reply_rate",
    "_xfiles_outreach_stats_bucket",
    "_xfiles_outreach_bucket_list",
    "_xfiles_outreach_stats",
    "_postgres_connect",
    "_postgres_log_error_once",
    "_XFILES_POSTGRES_MIGRATIONS",
    "_postgres_apply_xfiles_migrations",
    "_postgres_ensure_xfiles_schema",
    "_xfiles_deals_state",
    "_xfiles_deal_audit_state",
    "_xfiles_product_margins_state",
    "_xfiles_clean_text",
    "_xfiles_clean_margin",
    "_xfiles_product_margin_from_any",
    "_xfiles_load_product_margins",
    "_xfiles_product_margin_for_match",
    "_xfiles_product_catalog_text",
    "_xfiles_product_match_probability",
    "_xfiles_product_match_candidates",
    "_xfiles_product_pitch",
    "_xfiles_upsert_product_margin",
    "_xfiles_delete_product_margin",
    "_xfiles_expected_profit",
    "_xfiles_stable_norm",
    "_xfiles_operational_stable_key",
    "_xfiles_deal_stable_key_from_parts",
    "_xfiles_deal_stable_key_from_payload",
    "_xfiles_deal_stable_key",
    "_xfiles_need_stable_key",
    "_xfiles_deal_from_payload",
    "_xfiles_deal_to_payload",
    "_xfiles_deal_from_any",
    "_xfiles_audit_from_any",
    "_xfiles_audit_from_pg_row",
    "_xfiles_deal_from_pg_row",
    "_XFILES_DEAL_SELECT_SQL",
    "_XFILES_DEAL_UPSERT_SQL",
    "_XFILES_DEAL_AUDIT_INSERT_SQL",
    "_xfiles_postgres_existing_deal_id_by_stable_key",
    "_xfiles_postgres_upsert_deal_row",
    "_xfiles_postgres_insert_deal_audit_row",
    "_xfiles_migrate_state_deals_to_postgres_once",
    "_xfiles_postgres_storage_available",
    "_xfiles_load_deals",
    "_xfiles_get_deal",
    "_xfiles_compact_audit_value",
    "_xfiles_append_deal_audit",
    "_xfiles_load_deal_audit",
    "_xfiles_deals_kanban_sync",
    "_xfiles_norm_identity",
    "_xfiles_find_existing_deal_for_payload",
    "_xfiles_upsert_deal",
    "_xfiles_patch_deal",
    "_xfiles_delete_deal",
    "_xfiles_contact_recommendation",
    "_xfiles_contact_signal_profile",
    "_xfiles_daily_contacts_sync",
    "_xfiles_deal_assistant_sync",
    "_xfiles_deal_opportunities_sync",
    "_xfiles_deals_status_sync",
    "_xfiles_event_sales_plan_sync",
    "_xfiles_function_impacts",
    "_xfiles_need_signal_from_parts",
    "_xfiles_need_signals_page_sync",
    "_xfiles_template_model_benchmarks",
    "_xfiles_parse_optional_dt",
    "_XFILES_STAGE_SLA_HOURS",
    "_xfiles_hours_text",
    "_xfiles_enrich_deal_runtime",
    "_xfiles_deal_reminder_text",
    "_xfiles_deal_reminder_from_deal",
    "_xfiles_deal_reminders_sync",
    "_xfiles_deal_conversion_sync",
    "_xfiles_profit_optimization_sync",
    "_xfiles_opportunity_money",
    "_xfiles_opportunity_attention_hours",
    "_xfiles_opportunity_urgency_score",
    "_xfiles_opportunity_when_to_write",
    "_xfiles_opportunity_first_message",
    "_xfiles_metric_history_items",
    "_xfiles_metric_history_upsert",
    "_xfiles_north_star_sync",
    "_xfiles_existing_deals_by_contact",
)
