"""Contact scoring, contract helpers, event signals, and LLM audit helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Union

import requests
from fastapi import HTTPException

from app.services.contact_llm.signals import (
    _XFILES_ABILITY_KEYWORDS,
    _XFILES_BUYING_SIGNAL_KEYWORDS,
    _XFILES_CONTACT_PAIN_KEYWORDS,
    _XFILES_CONTACT_TOPIC_KEYWORDS,
    _XFILES_LEAD_TEMPERATURE_LABELS,
    _XFILES_OBJECTION_KEYWORDS,
    _xfiles_contact_temperature,
    _xfiles_keyword_hits,
    _xfiles_score_explanation,
)


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
        return func(*args, **kwargs)

    return wrapper


refresh_legacy_globals()

def _xfiles_product_hint_from_catalog(text: str) -> Optional[str]:
    candidates = _xfiles_product_match_candidates(text, limit=1)
    if not candidates:
        return None
    best_item = candidates[0]
    margin = int(round(float(best_item.get("margin") or 0) * 100))
    suffix = f" · маржа {margin}%" if margin else ""
    return f"{best_item.get('name')}{suffix}"

def _xfiles_why_now(profile: Dict[str, Any], days_since: Optional[int], existing_deal: Optional[XFilesDealDTO] = None) -> str:
    if existing_deal and existing_deal.stage not in {"won", "lost"}:
        return f"Уже есть активная сделка на стадии {existing_deal.stage}; лучше обновить следующий шаг, а не создавать дубль."
    buying_signals = profile.get("buying_signals") or []
    if buying_signals:
        return "Есть свежие buying-сигналы: " + ", ".join(str(item) for item in buying_signals[:4])
    if days_since is not None:
        if days_since <= 1:
            return "Контакт был активен в последние сутки, окно для первого касания тёплое."
        if days_since <= 7:
            return f"Последняя активность {days_since} дн. назад: ещё можно писать по текущему контексту."
    if profile.get("pains"):
        return "В сообщениях есть боли/задачи: " + ", ".join(str(item) for item in (profile.get("pains") or [])[:3])
    if profile.get("topics"):
        return "Есть понятная тема для мягкого первого касания: " + ", ".join(str(item) for item in (profile.get("topics") or [])[:3])
    return "Лучше сначала добрать контекст: пока мало сигналов для уверенного касания."


def _xfiles_apply_contact_signal_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(summary)
    profile = _xfiles_contact_signal_profile(enriched)
    total_messages = max(0, int(enriched.get("total_messages") or enriched.get("related_messages_count") or 0))
    qualification_count = max(0, int(enriched.get("qualification_count") or 0))
    last_dt = _xfiles_parse_optional_dt(enriched.get("last_message_at"))
    days_since = max(0, int((_utc_now() - last_dt).total_seconds() // 86400)) if last_dt else None
    temperature = _xfiles_contact_temperature(profile, total_messages=total_messages, qualification_count=qualification_count)
    enriched.update(
        fit_score=int(profile.get("fit_score") or 0),
        intent_score=int(profile.get("intent_score") or 0),
        urgency_score=int(profile.get("urgency_score") or 0),
        ability_to_pay_score=int(profile.get("ability_to_pay_score") or 0),
        deal_score=int(profile.get("deal_score") or 0),
        lead_temperature=temperature["key"],
        lead_temperature_label=temperature["label"],
        score_explanation=_xfiles_score_explanation(profile, temperature),
        why_now=_xfiles_why_now(profile, days_since),
        best_product_hint=str(profile.get("best_product_hint") or ""),
        product_match_score=int(profile.get("product_match_score") or 0),
        offer_recommendation=str(profile.get("offer_recommendation") or ""),
        missing_qualification=str(profile.get("missing_qualification") or ""),
    )
    return enriched




def _xfiles_assistant_short_text(value: Any, max_len: int = 420) -> str:
    return _xfiles_clean_text(_outreach_compact_text(value), max_len) or ""


def _xfiles_deal_assistant_messages(deal: XFilesDealDTO, limit: int = 80) -> List[TelegramContactMessageDTO]:
    contact_key = str(deal.contact_key or "").strip()
    if contact_key:
        return _contact_messages_for_qualification(contact_key, limit=limit)
    return []


def _xfiles_objection_reply(objection: str, product_hint: str) -> str:
    normalized = str(objection or "").lower()
    if "дорого" in normalized or "бюджет" in normalized:
        return "Сначала предложить короткую диагностику и маленький пилот, чтобы показать экономию времени/денег до большого бюджета."
    if "позже" in normalized or "не готов" in normalized:
        return "Согласиться с темпом контакта и предложить один конкретный next step без давления: чек-лист, пример или 15 минут."
    if "не понимаю" in normalized or "сомнева" in normalized:
        return "Объяснить через 1 бизнес-кейс и спросить, какой показатель для него важнее: скорость, деньги или снижение ручной работы."
    if "не подходит" in normalized:
        return "Не спорить: уточнить критерии fit/no-fit и предложить альтернативный формат или честно закрыть сделку."
    return f"Связать ответ с пользой “{product_hint or 'решения'}” и задать один уточняющий вопрос вместо длинной презентации."




from app.services.xfiles_contracts import (
    _xfiles_contract_metrics_sync,
    _xfiles_contract_templates,
    _xfiles_contract_templates_page_sync,
    _xfiles_deal_contract_kit_sync,
    _xfiles_deal_negotiation_brief_sync,
)



def _xfiles_contracts_state() -> Dict[str, Any]:
    current = telegram_sync.state.get(XFILES_CONTRACTS_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    statuses = current.get("statuses")
    if not isinstance(statuses, dict):
        statuses = {}
    current["statuses"] = statuses
    telegram_sync.state[XFILES_CONTRACTS_STATE_KEY] = current
    return current






def _xfiles_contract_status_for_deal(deal: XFilesDealDTO, missing_fields: Optional[List[str]] = None) -> XFilesContractStatus:
    stored = str(_xfiles_contracts_state().get("statuses", {}).get(deal.id) or "").strip()
    if stored in {"needs_data", "proposal_ready", "sent", "negotiation", "signed", "paid"}:
        return stored  # type: ignore[return-value]
    if deal.stage == "won":
        return "paid"
    if deal.stage == "contract":
        return "negotiation"
    if deal.stage == "negotiation":
        return "sent"
    if deal.stage == "proposal" and not (missing_fields or []):
        return "proposal_ready"
    return "needs_data"


def _xfiles_set_contract_status(deal_id: str, status: XFilesContractStatus) -> None:
    state = _xfiles_contracts_state()
    statuses = state.get("statuses")
    if not isinstance(statuses, dict):
        statuses = {}
    statuses[str(deal_id)] = status
    state["statuses"] = statuses
    telegram_sync.save_state()


def _xfiles_has_email(*values: Any) -> bool:
    hay = "\n".join(str(value or "") for value in values)
    return bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", hay, flags=re.IGNORECASE))


def _xfiles_has_inn(*values: Any) -> bool:
    hay = "\n".join(str(value or "") for value in values)
    return bool(re.search(r"\b\d{10}\b|\b\d{12}\b", hay))


def _xfiles_has_signer_role(*values: Any) -> bool:
    hay = "\n".join(str(value or "") for value in values).lower()
    return bool(
        re.search(
            r"\b(директор|гендир|генеральн|ceo|founder|основатель|собственник|подписант|руководител|лпр|cfo|финансовый директор)\b",
            hay,
            flags=re.IGNORECASE,
        )
    )


def _xfiles_has_deadline(*values: Any) -> bool:
    hay = "\n".join(str(value or "") for value in values).lower()
    return bool(
        hay.strip()
        and (
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", hay)
            or re.search(r"\b(дедлайн|срок|до конца|сегодня|завтра|недел|месяц|квартал|дата)\b", hay)
        )
    )


def _xfiles_jur_matches_for_deal(deal: XFilesDealDTO, limit: int = 5) -> List[Dict[str, Any]]:
    tokens = [
        str(deal.company or "").strip().lower(),
        str(deal.contact_name or "").strip().lower(),
        str(deal.source_chat or "").strip().lower(),
        str(deal.contact_key or "").strip().lower(),
    ]
    tokens = [item for item in tokens if len(item) >= 3]
    if not tokens:
        return []
    result: List[Dict[str, Any]] = []
    try:
        rows = _list_jur_entities_rows()
    except Exception:
        rows = []
    for row in rows:
        hay = " ".join(
            [
                str(row.file_name or ""),
                str(row.channel or ""),
                str(row.caption_preview or ""),
                str(row.file_key or ""),
            ]
        ).lower()
        score = sum(1 for token in tokens if token and token in hay)
        if score <= 0:
            continue
        result.append(
            {
                "file_key": row.file_key,
                "file_name": row.file_name,
                "channel": row.channel,
                "caption_preview": row.caption_preview or "",
                "message_date_utc": row.message_date_utc,
                "parser_enabled": row.parser_enabled,
                "structure_label": row.structure_label,
                "score": score,
            }
        )
    result.sort(key=lambda item: (int(item.get("score") or 0), str(item.get("message_date_utc") or "")), reverse=True)
    return result[: max(1, min(int(limit or 5), 20))]


def _xfiles_contract_checklist(deal: XFilesDealDTO, jur_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context_values = [deal.title, deal.company, deal.contact_name, deal.need, deal.product_match, deal.next_action, deal.notes]
    checks = [
        ("jur_entity", "юрлицо", bool(deal.company or jur_matches), deal.company or (jur_matches[0].get("file_name") if jur_matches else "")),
        ("inn", "ИНН", _xfiles_has_inn(*context_values), "найден в сделке/заметках" if _xfiles_has_inn(*context_values) else ""),
        ("email", "email", _xfiles_has_email(*context_values), "найден в сделке/заметках" if _xfiles_has_email(*context_values) else ""),
        ("signer_role", "роль подписанта", _xfiles_has_signer_role(*context_values), "роль найдена в контексте" if _xfiles_has_signer_role(*context_values) else ""),
        ("budget", "бюджет", float(deal.expected_value or 0.0) > 0, f"{deal.expected_value:g} ₽" if float(deal.expected_value or 0.0) > 0 else ""),
        ("deadline", "дедлайн", bool(deal.next_action_at or _xfiles_has_deadline(*context_values)), deal.next_action_at or ("найден в тексте" if _xfiles_has_deadline(*context_values) else "")),
        ("subject", "предмет договора", bool(deal.need or deal.product_match), deal.product_match or deal.need or ""),
    ]
    return [
        {
            "key": key,
            "label": label,
            "ok": bool(ok),
            "value": _xfiles_clean_text(value, 300) or "",
        }
        for key, label, ok, value in checks
    ]


def _xfiles_contract_missing_fields(checklist: List[Dict[str, Any]]) -> List[str]:
    return [str(item.get("label") or item.get("key") or "") for item in checklist if not bool(item.get("ok"))]


def _xfiles_deal_price_text(deal: XFilesDealDTO) -> str:
    value = float(deal.expected_value or 0.0)
    if value > 0:
        return f"{value:,.0f} ₽".replace(",", " ")
    for product in _xfiles_product_match_candidates(f"{deal.product_match or ''}\n{deal.need or ''}", limit=1):
        price = str(product.get("price") or "").strip()
        if price:
            return price
    return "уточняется после согласования объёма"


def _xfiles_short_proposal(deal: XFilesDealDTO, missing_fields: List[str]) -> str:
    contact = deal.contact_name or deal.company or deal.contact_key or "клиент"
    product = deal.product_match or "короткая диагностика и пилот X-Files"
    need = deal.need or "задача ещё не описана полностью"
    result = (
        "быстрее квалифицировать спрос, сократить ручную подготовку к продажам и довести лидов до следующего шага"
        if "x-files" in product.lower() or not deal.product_match
        else "получить измеримый бизнес-результат по согласованным критериям"
    )
    deadline = deal.next_action_at or "срок фиксируем после подтверждения состава работ"
    data_note = f"\nНужно добрать перед договором: {', '.join(missing_fields)}." if missing_fields else ""
    return (
        f"КП для {contact}\n"
        f"Контекст: {need}\n"
        f"Предлагаем: {product}\n"
        f"Ожидаемый результат: {result}\n"
        f"Коммерческие условия: {_xfiles_deal_price_text(deal)}\n"
        f"Дедлайн/следующий шаг: {deadline}\n"
        f"Следующее действие: {deal.next_action or 'согласовать короткий созвон и финализировать предмет договора'}."
        f"{data_note}"
    )


def _xfiles_proposal_document(deal: XFilesDealDTO, checklist: List[Dict[str, Any]], jur_matches: List[Dict[str, Any]]) -> str:
    checklist_text = "\n".join(
        f"- [{'x' if item.get('ok') else ' '}] {item.get('label')}: {item.get('value') or 'нужно уточнить'}"
        for item in checklist
    )
    jur_text = "\n".join(
        f"- {item.get('file_name')} ({item.get('channel')}) — {item.get('caption_preview') or 'без подписи'}"
        for item in jur_matches[:5]
    ) or "- Совпадения в ЮР.ЛИЦА пока не найдены."
    return (
        f"# Коммерческое предложение: {deal.title}\n\n"
        f"## 1. Клиент и контакт\n"
        f"- Контакт: {deal.contact_name or deal.contact_key or 'нужно уточнить'}\n"
        f"- Компания/юрлицо: {deal.company or 'нужно уточнить'}\n"
        f"- Источник: {deal.source or 'manual'}{f' / {deal.source_chat}' if deal.source_chat else ''}\n\n"
        f"## 2. Контекст и потребность\n{deal.need or 'Потребность нужно уточнить перед финальным КП.'}\n\n"
        f"## 3. Предлагаемое решение\n{deal.product_match or 'Диагностика, пилот и настройка revenue workflow под задачу клиента.'}\n\n"
        f"## 4. Ожидаемый результат\n"
        f"- Сократить время квалификации и подготовки к продаже.\n"
        f"- Зафиксировать следующий шаг, ответственных и критерии успеха.\n"
        f"- Перевести потребность в договорной контур без потери контекста.\n\n"
        f"## 5. Коммерческие условия\n"
        f"- Оценка сделки: {_xfiles_deal_price_text(deal)}\n"
        f"- Вероятность: {round(float(deal.probability or 0.0) * 100)}%\n"
        f"- Ожидаемая прибыль: {deal.expected_profit:,.0f} ₽\n\n".replace(",", " ")
        + f"## 6. Дедлайн и следующий шаг\n"
        f"- Дедлайн: {deal.next_action_at or 'нужно согласовать'}\n"
        f"- Следующий шаг: {deal.next_action or 'согласовать созвон и финализировать предмет договора'}\n\n"
        f"## 7. Чеклист договора\n{checklist_text}\n\n"
        f"## 8. Связанные файлы ЮР.ЛИЦА\n{jur_text}\n"
    )


def _xfiles_contract_duration_metrics() -> Dict[str, Any]:
    audits = list(reversed(_xfiles_load_deal_audit(limit=1000)))
    stage_times: Dict[str, Dict[str, datetime]] = {}
    for item in audits:
        if not item.after_stage:
            continue
        parsed = _xfiles_parse_optional_dt(item.ts)
        if not parsed:
            continue
        stages = stage_times.setdefault(item.deal_id, {})
        stages.setdefault(str(item.after_stage), parsed)

    def avg_hours(start: str, end: str) -> Dict[str, Any]:
        values: List[float] = []
        for stages in stage_times.values():
            if start not in stages or end not in stages:
                continue
            delta = (stages[end] - stages[start]).total_seconds() / 3600
            if delta >= 0:
                values.append(delta)
        if not values:
            return {"hours": 0.0, "label": "нет истории", "sample": 0}
        avg = round(sum(values) / len(values), 2)
        return {"hours": avg, "label": f"{avg:.1f} ч", "sample": len(values)}

    return {
        "qualified_to_proposal": avg_hours("qualified", "proposal"),
        "proposal_to_contract": avg_hours("proposal", "contract"),
    }






def _xfiles_event_date_from_row(row: Dict[str, Any]) -> Optional[datetime]:
    raw = str(row.get("event_date") or "").strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            pass
    return _xfiles_parse_optional_dt(row.get("date_utc"))


def _xfiles_event_topic(row: Dict[str, Any]) -> str:
    text = _outreach_compact_text(row.get("text") or "")
    keywords = [
        str(item).strip()
        for item in (row.get("matched_keywords") or [])
        if str(item).strip()
    ]
    if keywords:
        return ", ".join(keywords[:4])
    sentence = re.split(r"(?<=[.!?])\s+|\n+", text)[0] if text else ""
    return _xfiles_clean_text(sentence, 160) or "событие / повод для касания"


def _xfiles_event_contact_key(row: Dict[str, Any]) -> str:
    username = str(row.get("sender_username") or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    sender = _xfiles_clean_text(row.get("sender_name"), 200)
    if sender:
        return sender
    lead = _xfiles_clean_text(row.get("lead"), 200)
    message_id = str(row.get("message_id") or "").strip()
    return f"{lead}:{message_id}" if lead or message_id else ""


def _xfiles_event_sales_windows(event_dt: Optional[datetime], message_dt: Optional[datetime]) -> List[XFilesEventSalesWindowDTO]:
    now = _utc_now()
    base = event_dt or message_dt or now
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    base = base.astimezone(timezone.utc)
    if event_dt:
        candidates = [
            ("before_7d", "за 7 дней", base - timedelta(days=7), "Написать заранее: предложить встречу, демо или подготовку к событию"),
            ("before_1d", "за день", base - timedelta(days=1), "Коротко напомнить и предложить быстрый слот до события"),
            ("after_1d", "после события", base + timedelta(days=1), "Сделать follow-up по событию и предложить следующий шаг"),
        ]
    else:
        candidates = [
            ("now", "сейчас", now, "Использовать сообщение как свежий повод для касания"),
            ("after_2d", "через 2 дня", now + timedelta(days=2), "Вернуться с follow-up, если ответа не было"),
        ]
    windows: List[XFilesEventSalesWindowDTO] = []
    for key, label, action_dt, action in candidates:
        if action_dt < now:
            tone: Literal["green", "yellow", "red"] = "red"
        elif action_dt <= now + timedelta(days=2):
            tone = "green"
        else:
            tone = "yellow"
        windows.append(
            XFilesEventSalesWindowDTO(
                key=key,
                label=label,
                action=action,
                action_at=action_dt.isoformat(),
                tone=tone,
            )
        )
    return windows


def _xfiles_pick_next_event_window(windows: List[XFilesEventSalesWindowDTO]) -> Optional[XFilesEventSalesWindowDTO]:
    now = _utc_now()

    def window_dt(item: XFilesEventSalesWindowDTO) -> datetime:
        parsed = _xfiles_parse_optional_dt(item.action_at)
        return parsed or now

    future = [item for item in windows if window_dt(item) >= now]
    if future:
        return sorted(future, key=window_dt)[0]
    return windows[-1] if windows else None


def _xfiles_event_product_offer(text: str) -> Dict[str, Any]:
    candidates = _xfiles_product_match_candidates(text, limit=1)
    if candidates:
        best = candidates[0]
        return {
            "offer": str(best.get("recommendation") or "уместный оффер"),
            "product_match": str(best.get("name") or ""),
            "score": int(best.get("score") or 0),
            "probability": float(best.get("probability") or 0.25),
            "margin": _xfiles_clean_margin(best.get("margin"), 1.0),
            "expected_value": float(best.get("expected_value_hint") or 0.0),
        }
    lowered = text.lower()
    if any(word in lowered for word in ("вебинар", "конференц", "форум", "митап", "нетворк", "мероприят")):
        return {
            "offer": "подготовка outreach, встреч и follow-up вокруг события",
            "product_match": "X-Files event outreach / meeting prep",
            "score": 42,
            "probability": 0.28,
            "margin": 1.0,
            "expected_value": 0.0,
        }
    return {
        "offer": "короткая диагностика потребности и предложение next step",
        "product_match": "X-Files qualification workflow",
        "score": 30,
        "probability": 0.2,
        "margin": 1.0,
        "expected_value": 0.0,
    }






_XFILES_NEED_SIGNAL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "urgent": {
        "label": "Срочно",
        "keywords": ["срочно", "сегодня", "завтра", "до конца", "дедлайн", "горит", "быстро", "немедленно"],
        "score": 18,
    },
    "budget": {
        "label": "Есть деньги",
        "keywords": ["бюджет", "оплат", "счёт", "счет", "руб", "₽", "тыс", "млн", "стоимость", "цена", "сколько стоит"],
        "score": 16,
    },
    "contractor": {
        "label": "Ищет подрядчика",
        "keywords": ["ищу подряд", "подрядчик", "исполнитель", "кто может", "нужен специалист", "нужна команда", "найти команду"],
        "score": 20,
    },
    "recommendation": {
        "label": "Просит рекомендацию",
        "keywords": ["посоветуйте", "порекомендуйте", "кто знает", "подскажите", "есть контакты", "дайте контакт"],
        "score": 16,
    },
    "complaint": {
        "label": "Жалуется",
        "keywords": ["не работает", "ошибка", "сломал", "сломалось", "завис", "проблема", "болит", "боль", "устал", "дорого"],
        "score": 14,
    },
    "event": {
        "label": "Планирует мероприятие",
        "keywords": ["мероприят", "вебинар", "конференц", "митап", "выставк", "форум", "встреч", "нетворк"],
        "score": 12,
    },
    "hiring": {
        "label": "Нанимает",
        "keywords": ["нанима", "ваканс", "ищем человека", "ищем сотруд", "нужен менеджер", "резюме", "hr"],
        "score": 12,
    },
    "service_purchase": {
        "label": "Покупает сервис",
        "keywords": ["купить", "заказать", "нужен сервис", "решение", "подписка", "интеграция", "crm", "автоматизац"],
        "score": 18,
    },
}
_XFILES_NEED_SOURCE_LABELS: Dict[str, str] = {
    "message": "Сообщение",
    "enReach": "enReach",
    "crm": "CRM",
    "ocr": "OCR",
    "event": "Мероприятие",
    "route": "Маршрут",
    "import": "Import",
}


def _xfiles_need_search_keywords() -> List[str]:
    keywords: List[str] = []
    for config in _XFILES_NEED_SIGNAL_DEFINITIONS.values():
        keywords.extend(str(item or "") for item in (config.get("keywords") or []))
    keywords.extend(_XFILES_BUYING_SIGNAL_KEYWORDS)
    unique: List[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        normalized = str(keyword or "").strip().lower()
        if len(normalized) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _xfiles_need_detect_tags(text: str) -> tuple[List[str], List[str], int]:
    normalized = str(text or "").lower()
    tags: List[str] = []
    labels: List[str] = []
    score = 20
    for key, config in _XFILES_NEED_SIGNAL_DEFINITIONS.items():
        hits = _xfiles_keyword_hits(normalized, [str(item) for item in (config.get("keywords") or [])])
        if not hits:
            continue
        tags.append(key)
        labels.append(str(config.get("label") or key))
        score += int(config.get("score") or 0)
    if re.search(r"(?:\+?\d[\d\s().-]{8,}\d)|(?:[\w.+-]+@[\w.-]+\.[a-zа-я]{2,})", normalized, re.IGNORECASE):
        score += 8
    return tags, labels, max(0, min(100, score))


def _xfiles_need_pick_sentence(text: str, tags: List[str], max_len: int = 520) -> str:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return ""
    tag_keywords: List[str] = []
    for tag in tags:
        tag_keywords.extend([str(item) for item in (_XFILES_NEED_SIGNAL_DEFINITIONS.get(tag, {}).get("keywords") or [])])
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", normalized_text)
    for sentence in sentences:
        compact = _outreach_compact_text(sentence)
        if not compact:
            continue
        if any(keyword and keyword.lower() in compact.lower() for keyword in tag_keywords):
            return _xfiles_clean_text(compact, max_len) or ""
    return _xfiles_clean_text(_outreach_compact_text(normalized_text), max_len) or ""


def _xfiles_need_extract_budget(text: str) -> str:
    normalized = _outreach_compact_text(text)
    patterns = [
        r"(?:бюджет|стоимость|цена|оплата|сч[её]т)[^.!?\n]{0,80}",
        r"\d[\d\s]{2,}(?:\s?(?:₽|руб\.?|тыс\.?|млн\.?|k|m))",
    ]
    hits: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
            value = _outreach_compact_text(match)
            if value and value not in hits:
                hits.append(value)
    return _xfiles_clean_text("; ".join(hits[:3]), 400) or ""


def _xfiles_need_extract_deadline(text: str) -> str:
    normalized = _outreach_compact_text(text)
    patterns = [
        r"(?:сегодня|завтра|на этой неделе|до конца [^.!?,;]{1,40}|дедлайн[^.!?,;]{0,40}|к \d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)",
        r"\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\b",
    ]
    hits: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, normalized, flags=re.IGNORECASE):
            value = _outreach_compact_text(match)
            if value and value.lower() not in [item.lower() for item in hits]:
                hits.append(value)
    return _xfiles_clean_text("; ".join(hits[:3]), 300) or ""


def _xfiles_need_source_label(source: str, field_label: Optional[str] = None) -> str:
    custom = str(field_label or "").strip()
    if custom:
        lowered = custom.lower()
        if "ocr" in lowered or "изображ" in lowered or "media" in lowered:
            return "OCR"
        if "мероприят" in lowered or "event" in lowered:
            return "Мероприятие"
        if "crm" in lowered:
            return "CRM"
        return custom
    return _XFILES_NEED_SOURCE_LABELS.get(str(source or ""), "Сообщение")


def _xfiles_need_first_touch(contact_name: str, lead: str, need: str, product: str) -> str:
    compact_need = _xfiles_clean_text(need, 180) or "вашу задачу"
    first_name = str(contact_name or "").strip().split()[0] if str(contact_name or "").strip() else "Добрый день"
    source_part = f" в {lead}" if str(lead or "").strip() else ""
    product_part = product or "быстро понять, где можно сэкономить время и получить результат"
    if first_name == "Добрый день":
        return f"Добрый день. Увидел{source_part} задачу: {compact_need}. Похоже, тут может быть полезно {product_part}. Можно задам один короткий уточняющий вопрос?"
    return f"{first_name}, добрый день. Увидел{source_part} задачу: {compact_need}. Похоже, тут может быть полезно {product_part}. Можно задам один короткий уточняющий вопрос?"


def _xfiles_need_probability(score: Any) -> float:
    try:
        value = max(0, min(100, int(score or 0)))
    except Exception:
        value = 0
    if value >= 86:
        return 0.55
    if value >= 72:
        return 0.45
    if value >= 48:
        return 0.30
    return 0.18


def _xfiles_need_estimated_value_from_budget(budget: Any) -> float:
    text = str(budget or "").lower()
    if not text:
        return 0.0
    numbers: List[float] = []
    for raw in re.findall(r"\d[\d\s.,]*", text):
        normalized = raw.replace(" ", "").replace(",", ".").strip(".")
        try:
            numbers.append(float(normalized))
        except Exception:
            continue
    if not numbers:
        return 0.0
    value = max(numbers)
    if any(marker in text for marker in ["млн", "million", "kk"]):
        value *= 1_000_000
    elif any(marker in text for marker in ["тыс", "k", "к "]):
        value *= 1_000
    return round(max(0.0, min(value, 999_999_999.0)), 2)


def _xfiles_need_deal_payload(item: XFilesNeedSignalDTO, *, auto: bool = False) -> XFilesDealPayload:
    source_message_id = str(item.message_id) if item.message_id is not None else item.id
    title_basis = item.need or item.text or item.contact_name or item.lead or "Покупательский сигнал"
    source_name = "needs:auto" if auto else "needs"
    score = max(0, min(100, int(item.score or 0)))
    expected_value = _xfiles_need_estimated_value_from_budget(item.budget)
    if expected_value <= 0 and float(item.product_expected_value_hint or 0.0) > 0:
        expected_value = float(item.product_expected_value_hint or 0.0)
    probability = max(_xfiles_need_probability(score), float(item.product_match_probability or 0.0))
    return XFilesDealPayload(
        title=_xfiles_clean_text(f"Draft: {title_basis}", 500) or "Draft: покупательский сигнал",
        stage="idea",
        score=score,
        expected_value=expected_value,
        probability=probability,
        margin=_xfiles_clean_margin(item.product_margin, 1.0),
        contact_key=item.contact_key or item.sender_username or item.contact_name or item.lead,
        contact_name=item.contact_name or item.sender_username or "",
        company=item.company or "",
        source=source_name,
        source_chat=item.lead or item.source_selector or item.source_label,
        source_message_id=source_message_id,
        need=_xfiles_clean_text(item.need or item.text, 4000),
        product_match=_xfiles_clean_text(item.product_match, 1200),
        next_action=_xfiles_clean_text(item.first_touch or "Квалифицировать потребность и подготовить первое касание", 1600),
        notes=_xfiles_clean_text(
            "Автоматический draft из сильного покупательского сигнала. "
            f"Источник: {item.source_label or item.source}. "
            f"Сигналы: {', '.join(item.tag_labels or [])}.",
            2000,
        ),
    )


def _xfiles_need_is_strong_enough_for_auto_deal(item: XFilesNeedSignalDTO) -> bool:
    if item.has_deal:
        return False
    score = int(item.score or 0)
    tags = set(item.tags or [])
    if score >= 82:
        return True
    return score >= 72 and bool(tags.intersection({"budget", "contractor", "service_purchase", "urgent"}))


def _xfiles_auto_create_need_deal_drafts(
    items: List[XFilesNeedSignalDTO],
    existing_deals_by_contact: Dict[str, XFilesDealDTO],
    *,
    max_items: int = 10,
) -> int:
    created = 0
    candidates = sorted(
        [item for item in items if _xfiles_need_is_strong_enough_for_auto_deal(item)],
        key=lambda item: (int(item.score or 0), str(item.date_utc or "")),
        reverse=True,
    )
    for item in candidates[: max(0, int(max_items or 0))]:
        payload = _xfiles_need_deal_payload(item, auto=True)
        if _xfiles_find_existing_deal_for_payload(payload):
            continue
        deal = _xfiles_upsert_deal(_xfiles_deal_from_payload(payload))
        _xfiles_append_deal_audit(
            "auto_create_need_draft",
            deal,
            changes={
                "need_signal_id": item.id,
                "score": item.score,
                "tags": item.tags,
                "source": item.source,
            },
            source="needs:auto",
            actor="system",
        )
        item.has_deal = True
        item.deal_id = deal.id
        item.deal_title = deal.title
        if item.contact_key:
            existing_deals_by_contact[_xfiles_norm_identity(item.contact_key)] = deal
        created += 1
    if created:
        _xfiles_clear_deal_api_caches()
    return created


def _xfiles_need_signal_id(source: str, lead: str, message_id: Optional[int], contact_key: str, text: str) -> str:
    basis = {
        "source": source,
        "lead": lead,
        "message_id": message_id,
        "contact_key": contact_key,
        "text": _outreach_compact_text(text)[:260],
    }
    raw = json.dumps(basis, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]




def _xfiles_need_signals_from_duckdb(limit: int, existing_deals_by_contact: Dict[str, XFilesDealDTO]) -> List[XFilesNeedSignalDTO]:
    if duckdb is None or not DUCKDB_PATH.exists() or not _duckdb_contacts_ready():
        return []
    keywords = _xfiles_need_search_keywords()
    if not keywords:
        return []
    where_parts = ["lower(coalesce(text, '')) LIKE ?" for _ in keywords]
    params: List[Any] = [f"%{keyword.lower()}%" for keyword in keywords]
    selector_map = _managed_selector_map()
    conn = _duckdb_connect_readonly()
    try:
        rows = conn.execute(
            f"""
            SELECT
                source_jsonl,
                message_id,
                CAST(date_utc_raw AS VARCHAR) AS date_utc_raw,
                text,
                sender_id,
                sender_username,
                sender_name,
                chat_username,
                chat_title
            FROM messages_raw
            WHERE length(trim(coalesce(text, ''))) > 0
              AND ({" OR ".join(where_parts)})
            ORDER BY
                coalesce(date_utc_raw, '') DESC,
                source_offset DESC
            LIMIT ?
            """,
            [*params, max(1, int(limit or 1))],
        ).fetchall()
    finally:
        conn.close()

    items: List[XFilesNeedSignalDTO] = []
    for row in rows:
        lead = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
        source_selector = selector_map.get(str(lead or "").lower()) or str(row[7] or "").strip() or None
        item = _xfiles_need_signal_from_parts(
            source="message",
            source_label=None,
            lead=lead,
            source_selector=source_selector,
            message_id=_duckdb_optional_int(row[1]),
            date_utc=str(row[2] or "") or None,
            text=str(row[3] or ""),
            sender_id=_duckdb_optional_int(row[4]),
            sender_username=str(row[5] or "") or None,
            sender_name=str(row[6] or "") or None,
            company=str(row[8] or "") or None,
            existing_deals_by_contact=existing_deals_by_contact,
        )
        if item:
            items.append(item)
    return items


def _xfiles_need_signals_from_enreach(limit: int, existing_deals_by_contact: Dict[str, XFilesDealDTO]) -> List[XFilesNeedSignalDTO]:
    items: List[XFilesNeedSignalDTO] = []
    for row in _load_outreach_items(limit=max(1, int(limit or 1))):
        field_type = _normalize_outreach_field_type(row.field_type)
        source = "enReach"
        if field_type in {"fio", "job_title", "company", "contact", "city"}:
            source = "crm"
        if field_type == "media" or "ocr" in str(row.field_label or "").lower():
            source = "ocr"
        if field_type == "event_message":
            source = "event"
        if field_type == "import_dialog":
            source = "import"
        text = row.text or row.value
        item = _xfiles_need_signal_from_parts(
            source=source,
            source_label=row.field_label,
            lead=row.lead,
            source_selector=row.source_selector,
            message_id=row.message_id,
            date_utc=row.date_utc,
            text=text,
            sender_username=row.sender_username,
            sender_name=row.sender_name,
            existing_deals_by_contact=existing_deals_by_contact,
        )
        if item:
            items.append(item)
    return items




def _xfiles_deal_from_outreach_item(item_id: str) -> XFilesDealDTO:
    item = _get_outreach_item_by_id(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="enReach item not found")
    payload = XFilesDealPayload(
        title=_xfiles_outreach_item_deal_title(item),
        stage="lead",
        score=20,
        probability=0.2,
        contact_name=item.sender_name,
        source="enReach",
        source_chat=item.lead or item.source_selector,
        source_message_id=str(item.message_id or ""),
        need=item.text or item.value,
        next_action="Квалифицировать потребность и выбрать первый шаг",
        notes=f"Создано из enReach: {item.field_label}",
    )
    existing = _xfiles_find_existing_deal_for_payload(payload)
    if existing:
        return existing
    return _xfiles_upsert_deal(_xfiles_deal_from_payload(payload))


def _expand_existing_outreach_values_sync(limit: int = 20000) -> Dict[str, Any]:
    if duckdb is None or not DUCKDB_PATH.exists():
        return {"checked": 0, "changed": 0, "examples": [], "message": "DuckDB is unavailable"}

    _duckdb_init_schema_sync()
    conn = _duckdb_connect()
    try:
        rows = conn.execute(
            """
            SELECT
                item_id, field_type, field_label, value, lead, source_selector,
                message_id, CAST(date_utc_raw AS VARCHAR) AS date_utc_raw,
                text, sender_username, sender_name, status,
                CAST(created_at AS VARCHAR) AS created_at_raw
            FROM outreach_crm_fields
            ORDER BY created_at_raw DESC
            LIMIT ?
            """,
            [max(1, int(limit or 1))],
        ).fetchall()
    finally:
        conn.close()

    checked = 0
    changed = 0
    examples: List[Dict[str, Any]] = []
    for row in rows:
        checked += 1
        item_id = str(row[0] or "")
        field_type = _normalize_outreach_field_type(str(row[1] or ""))
        value = str(row[3] or "")
        lead = str(row[4] or "") or None
        source_selector = str(row[5] or "") or None
        message_id = _duckdb_optional_int(row[6])
        date_utc = str(row[7] or "") or None
        text = str(row[8] or "")
        if field_type not in _OUTREACH_MESSAGE_FIELD_TYPES | _OUTREACH_CONTEXT_MESSAGE_FIELD_TYPES:
            continue
        full_text = _outreach_full_text_candidate(
            lead=lead,
            source_selector=source_selector,
            message_id=message_id,
            date_utc=date_utc,
            value=value,
            text=text,
        )
        next_value = _outreach_expand_value_with_full_text(field_type, value, text, full_text)
        next_text = str(full_text or text or "").strip() or None
        if next_value == value and (next_text or "") == text:
            continue
        conn = _duckdb_connect()
        try:
            conn.execute(
                """
                UPDATE outreach_crm_fields
                SET value = ?, text = ?
                WHERE item_id = ?
                """,
                [next_value, next_text, item_id],
            )
        finally:
            conn.close()
        changed += 1
        if len(examples) < 5:
            examples.append(
                {
                    "id": item_id,
                    "field_type": field_type,
                    "lead": lead,
                    "before_len": len(value),
                    "after_len": len(next_value),
                }
            )

    return {"checked": checked, "changed": changed, "examples": examples}


def _filter_telegram_contacts(
    items: List[TelegramContactDTO],
    query: str = "",
    lead_filter: str = "",
) -> List[TelegramContactDTO]:
    result: List[TelegramContactDTO] = []
    for row in items:
        if lead_filter:
            lead_hay = " ".join(
                [
                    row.latest_lead or "",
                    *(row.leads or []),
                    *(row.source_selectors or []),
                ]
            ).lower()
            if lead_filter not in lead_hay:
                continue
        if query:
            hay = " ".join(
                [
                    row.display_name or "",
                    row.sender_name or "",
                    row.sender_username or "",
                    row.contact_key or "",
                    row.latest_lead or "",
                    row.latest_message_preview or "",
                    " ".join(row.leads),
                    " ".join(row.source_selectors),
                ]
            ).lower()
            if query not in hay:
                continue
        result.append(row)
    return result


def _contact_source_rows_for_filters(limit: int = 50000) -> List[Dict[str, Any]]:
    contacts_state = _analysis_state("contacts")
    normalized_limit = max(1, int(limit or 1))
    if bool(contacts_state.get("running")) and _analysis_cache_path("contacts").exists():
        return _load_analysis_cache_rows_limited("contacts", normalized_limit)
    if _duckdb_contacts_ready():
        return _duckdb_load_contact_rows(limit=normalized_limit)
    return _analysis_rows("contacts", limit=normalized_limit)


def _build_contact_chat_filter_options(limit: int = 50000) -> TelegramContactChatFiltersDTO:
    source_rows = _contact_source_rows_for_filters(limit=limit)
    selector_map = _managed_selector_map()
    counts: Dict[str, int] = {}
    selectors: Dict[str, str] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        try:
            contact = TelegramContactDTO(**{**row, "related_messages": []})
        except Exception:
            continue
        seen_in_contact: set[str] = set()
        for lead in contact.leads or []:
            normalized = str(lead or "").strip()
            if not normalized or normalized in seen_in_contact:
                continue
            seen_in_contact.add(normalized)
            counts[normalized] = counts.get(normalized, 0) + 1
            selector = selector_map.get(normalized.lower())
            if selector:
                selectors[normalized] = selector
        for selector in contact.source_selectors or []:
            normalized_selector = str(selector or "").strip()
            if not normalized_selector:
                continue
            for lead, known_selector in selector_map.items():
                if known_selector == normalized_selector and lead not in selectors:
                    selectors[lead] = normalized_selector

    items = [
        TelegramContactChatFilterDTO(
            value=lead,
            label=lead,
            selector=selectors.get(lead),
            total_contacts=count,
        )
        for lead, count in counts.items()
    ]
    items.sort(key=lambda item: (-item.total_contacts, item.label.lower()))
    return TelegramContactChatFiltersDTO(items=items, total=len(items))


def _filter_telegram_contact_messages(
    items: List[TelegramContactMessageDTO],
    query: str = "",
    lead_filter: str = "",
) -> List[TelegramContactMessageDTO]:
    result: List[TelegramContactMessageDTO] = []
    for row in items:
        if lead_filter:
            lead_hay = f"{row.lead} {row.source_selector or ''}".lower()
            if lead_filter not in lead_hay:
                continue
        if query:
            hay = " ".join(
                [
                    row.lead,
                    row.source_selector or "",
                    row.sender_username or "",
                    row.sender_name or "",
                    row.text or "",
                ]
            ).lower()
            if query not in hay:
                continue
        result.append(row)
    return result


CONTACT_QUALIFICATIONS_STATE_KEY = "_contact_qualifications"
CONTACT_EXCLUSIONS_STATE_KEY = "_contact_exclusions"


def _contact_qualifications_state() -> Dict[str, Dict[str, Dict[str, Any]]]:
    current = telegram_sync.state.get(CONTACT_QUALIFICATIONS_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    normalized: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for raw_contact_key, raw_items in current.items():
        contact_key = str(raw_contact_key or "").strip()
        if not contact_key or not isinstance(raw_items, dict):
            continue
        normalized[contact_key] = {}
        for raw_template_id, raw_item in raw_items.items():
            template_id = _normalize_contact_prompt_id(raw_template_id)
            if template_id and isinstance(raw_item, dict):
                normalized[contact_key][template_id] = dict(raw_item)
    telegram_sync.state[CONTACT_QUALIFICATIONS_STATE_KEY] = normalized
    return normalized


def _contact_exclusions_state() -> Dict[str, Dict[str, Any]]:
    current = telegram_sync.state.get(CONTACT_EXCLUSIONS_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_contact_key, raw_item in current.items():
        contact_key = str(raw_contact_key or "").strip()
        if not contact_key or not isinstance(raw_item, dict):
            continue
        normalized[contact_key] = {
            "do_not_contact": bool(raw_item.get("do_not_contact")),
            "reason": str(raw_item.get("reason") or "").strip(),
            "updated_at": str(raw_item.get("updated_at") or "").strip() or None,
        }
    telegram_sync.state[CONTACT_EXCLUSIONS_STATE_KEY] = normalized
    return normalized


def _contact_do_not_contact_summary(contact_key: Any) -> Dict[str, Any]:
    key = str(contact_key or "").strip()
    item = _contact_exclusions_state().get(key, {}) if key else {}
    enabled = bool(item.get("do_not_contact")) if isinstance(item, dict) else False
    return {
        "do_not_contact": enabled,
        "do_not_contact_reason": str(item.get("reason") or "").strip() if enabled else "",
        "do_not_contact_updated_at": str(item.get("updated_at") or "").strip() or None if enabled else None,
    }


def _set_contact_do_not_contact(contact_key: Any, enabled: bool, reason: str = "") -> Dict[str, Any]:
    key = str(contact_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="Contact key is empty")
    state = _contact_exclusions_state()
    if bool(enabled):
        state[key] = {
            "do_not_contact": True,
            "reason": str(reason or "").strip()[:1000],
            "updated_at": _utc_now().isoformat(),
        }
    else:
        state.pop(key, None)
    telegram_sync.state[CONTACT_EXCLUSIONS_STATE_KEY] = state
    telegram_sync.save_state()
    return _contact_do_not_contact_summary(key)


def _contact_qualification_summary(contact_key: Any) -> Dict[str, Any]:
    key = str(contact_key or "").strip()
    entries = _contact_qualifications_state().get(key, {}) if key else {}
    ready_entries = [
        item
        for item in entries.values()
        if isinstance(item, dict) and str(item.get("status") or "ready") == "ready"
    ]
    template_ids = sorted(
        str(item.get("template_id") or template_id)
        for template_id, item in entries.items()
        if isinstance(item, dict) and str(item.get("status") or "ready") == "ready"
    )
    latest = ""
    for item in ready_entries:
        updated_at = str(item.get("updated_at") or item.get("created_at") or "")
        if updated_at > latest:
            latest = updated_at
    first_message_entry = entries.get("first_message")
    if not isinstance(first_message_entry, dict):
        first_message_entry = {}
    if str(first_message_entry.get("status") or "") != "ready":
        first_message_entry = {}
    first_message_text = _xfiles_clean_text(first_message_entry.get("result_text"), 1600) or ""
    product_offer_entry = entries.get("product_offer")
    if not isinstance(product_offer_entry, dict):
        product_offer_entry = {}
    if str(product_offer_entry.get("status") or "") != "ready":
        product_offer_entry = {}
    product_offer_text = _xfiles_clean_text(product_offer_entry.get("result_text"), 1600) or ""
    return {
        "qualification_count": len(ready_entries),
        "qualified_template_ids": template_ids,
        "latest_qualification_at": latest or None,
        "first_message_suggestion": first_message_text,
        "first_message_updated_at": str(
            first_message_entry.get("updated_at") or first_message_entry.get("created_at") or ""
        )
        or None,
        "first_message_model": str(first_message_entry.get("model") or "").strip(),
        "product_offer_suggestion": product_offer_text,
        "product_offer_updated_at": str(
            product_offer_entry.get("updated_at") or product_offer_entry.get("created_at") or ""
        )
        or None,
        "product_offer_model": str(product_offer_entry.get("model") or "").strip(),
    }


def _decorate_contact_summary_with_qualifications(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(row)
    summary.update(_contact_qualification_summary(summary.get("contact_key")))
    summary.update(_contact_do_not_contact_summary(summary.get("contact_key")))
    return summary




def _filter_telegram_contacts_by_qualification(
    items: List[TelegramContactDTO],
    qualification_filter: str = "",
) -> List[TelegramContactDTO]:
    normalized = str(qualification_filter or "").strip()
    if not normalized or normalized == "all":
        return items
    result: List[TelegramContactDTO] = []
    for row in items:
        template_ids = set(str(item) for item in (row.qualified_template_ids or []))
        if normalized == "qualified":
            if row.qualification_count > 0:
                result.append(row)
        elif normalized in template_ids:
            result.append(row)
    return result


def _filter_telegram_contacts_by_temperature(
    items: List[TelegramContactDTO],
    lead_temperature: str = "",
) -> List[TelegramContactDTO]:
    normalized = str(lead_temperature or "").strip()
    if not normalized or normalized == "all":
        return items
    return [
        row
        for row in items
        if str(row.lead_temperature or "") == normalized
    ]


_CONTACT_SIGNAL_FILTER_ALIASES = {
    "contact": "contact",
    "contacts": "contact",
    "phone": "contact",
    "phones": "contact",
    "email": "contact",
    "emails": "contact",
    "need": "need",
    "needs": "need",
    "event": "event",
    "events": "event",
    "company": "company",
    "companies": "company",
    "city": "city",
    "cities": "city",
}
_CONTACT_SIGNAL_LABELS = {
    "contact": "телефон/email",
    "need": "потребность",
    "event": "событие",
    "company": "компания",
    "city": "город",
}


def _contact_signal_filter_values(raw: str) -> List[str]:
    values: List[str] = []
    for part in str(raw or "").replace(";", ",").split(","):
        normalized = _CONTACT_SIGNAL_FILTER_ALIASES.get(part.strip().lower())
        if normalized and normalized not in values:
            values.append(normalized)
    return values


def _contact_signal_text(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in [
        "display_name",
        "sender_name",
        "sender_username",
        "latest_lead",
        "latest_message_text",
        "latest_message_preview",
        "why_now",
        "best_product_hint",
        "missing_qualification",
        "first_message_suggestion",
        "product_offer_suggestion",
    ]:
        value = row.get(key)
        if value:
            parts.append(str(value))
    for key in ["leads", "source_selectors", "qualified_template_ids"]:
        values = row.get(key)
        if isinstance(values, list):
            parts.extend(str(item) for item in values if item)
    return "\n".join(parts)


def _contact_signal_flags(row: Dict[str, Any]) -> Dict[str, Any]:
    text = _contact_signal_text(row)
    phones = _crm_extract_phones(text)
    emails = _crm_extract_emails(text)
    companies = _crm_extract_companies(text)
    city = _crm_extract_city(text)
    pain_hits: List[str] = []
    for keywords in _XFILES_CONTACT_PAIN_KEYWORDS.values():
        pain_hits.extend(_xfiles_keyword_hits(text, list(keywords)))
    need_hits = _xfiles_keyword_hits(text, _XFILES_BUYING_SIGNAL_KEYWORDS)
    event_hits = _match_event_keywords(text, _get_event_keywords())
    has_need = (
        bool(need_hits or pain_hits)
        or int(row.get("intent_score") or 0) >= 45
        or int(row.get("deal_score") or 0) >= 45
        or str(row.get("lead_temperature") or "") in {"hot", "warm"}
    )
    flags = {
        "has_phone": bool(phones),
        "has_email": bool(emails),
        "has_contact_data": bool(phones or emails),
        "has_need": bool(has_need),
        "has_event": bool(event_hits),
        "has_company": bool(companies),
        "has_city": bool(city),
    }
    tags = [
        label
        for key, label in _CONTACT_SIGNAL_LABELS.items()
        if (
            (key == "contact" and flags["has_contact_data"])
            or (key == "need" and flags["has_need"])
            or (key == "event" and flags["has_event"])
            or (key == "company" and flags["has_company"])
            or (key == "city" and flags["has_city"])
        )
    ]
    flags["signal_tags"] = tags
    return flags


def _decorate_contact_summary_with_signals(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(row)
    summary.update(_contact_signal_flags(summary))
    return summary


def _contact_key_strategy(contact_key: str) -> str:
    value = str(contact_key or "")
    if value.startswith("id:"):
        return "telegram.sender.id"
    if value.startswith("username:"):
        return "telegram.sender.username"
    if value.startswith("name:"):
        return "telegram.sender.name"
    return "unknown"


def _decorate_contact_summary_with_provenance(row: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(row)
    leads = [str(item) for item in list(summary.get("leads") or []) if str(item)]
    selectors = [str(item) for item in list(summary.get("source_selectors") or []) if str(item)]
    summary["provenance"] = {
        "contact_key": {
            "value": str(summary.get("contact_key") or ""),
            "strategy": _contact_key_strategy(str(summary.get("contact_key") or "")),
        },
        "sources": [
            {"lead": lead, "source_selector": selectors[index] if index < len(selectors) else None}
            for index, lead in enumerate(leads)
        ],
        "latest_message": {
            "lead": summary.get("latest_lead"),
            "date_utc": summary.get("last_message_at"),
            "text_source": "telegram.message.text" if summary.get("latest_message_text") else None,
        },
    }
    return summary


def _filter_telegram_contacts_by_signals(
    items: List[TelegramContactDTO],
    signal_filter: str = "",
) -> List[TelegramContactDTO]:
    filters = _contact_signal_filter_values(signal_filter)
    if not filters:
        return items

    def has_signal(row: TelegramContactDTO, signal: str) -> bool:
        if signal == "contact":
            return bool(row.has_contact_data or row.has_phone or row.has_email)
        return bool(getattr(row, f"has_{signal}", False))

    return [
        row
        for row in items
        if all(has_signal(row, signal) for signal in filters)
    ]


def _contact_messages_for_qualification(contact_key: str, limit: int = 200) -> List[TelegramContactMessageDTO]:
    target = str(contact_key or "").strip()
    if not target:
        return []
    rows: List[Dict[str, Any]]
    if _duckdb_contacts_ready():
        rows = _duckdb_load_contact_message_rows(target, limit=max(1, int(limit or 1)))
    else:
        rows = []
        for item in _iter_contact_message_cache(target):
            rows.append({key: item.get(key) for key in TelegramContactMessageDTO.__fields__.keys()})
            if len(rows) >= max(1, int(limit or 1)):
                break
    messages: List[TelegramContactMessageDTO] = []
    for row in rows:
        try:
            messages.append(TelegramContactMessageDTO(**row))
        except Exception:
            continue
    messages.sort(key=lambda entry: (str(entry.date_utc or ""), int(entry.message_id or 0)))
    return messages


def _build_contact_qualification_context(contact_key: str, messages: List[TelegramContactMessageDTO]) -> str:
    lines: List[str] = []
    budget = 52000
    used = 0
    for message in messages:
        text = str(message.text or "").strip()
        if not text:
            continue
        sender = message.sender_username or message.sender_name or message.sender_id or contact_key
        line = (
            f"[{message.date_utc}] чат={message.lead}; автор={sender}; "
            f"message_id={message.message_id}\n{text[:3000]}"
        )
        if used + len(line) > budget:
            break
        lines.append(line)
        used += len(line)
    return "\n\n---\n\n".join(lines)


def _contact_messages_fingerprint(messages: List[TelegramContactMessageDTO]) -> str:
    parts: List[Dict[str, Any]] = []
    for message in messages:
        parts.append(
            {
                "lead": message.lead,
                "message_id": message.message_id,
                "date_utc": message.date_utc,
                "text_hash": hashlib.sha256(str(message.text or "").encode("utf-8")).hexdigest(),
            }
        )
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _contact_latest_message_at(messages: List[TelegramContactMessageDTO]) -> Optional[str]:
    latest = ""
    for message in messages:
        value = str(message.date_utc or "")
        if value > latest:
            latest = value
    return latest or None


def _stable_json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _estimate_llm_tokens(value: Any) -> int:
    text = str(value or "")
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _openrouter_payload_prompt_text(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for message in payload.get("messages") or []:
        if isinstance(message, dict):
            parts.append(str(message.get("content") or ""))
    return "\n\n".join(parts)


def _estimate_openrouter_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    normalized_model = str(model or "").strip().lower()
    if not normalized_model or normalized_model.endswith(":free") or ":free" in normalized_model:
        return 0.0
    input_cost = (max(0, input_tokens) / 1000.0) * 0.00015
    output_cost = (max(0, output_tokens) / 1000.0) * 0.0006
    return round(input_cost + output_cost, 6)


def _openrouter_usage_estimate(
    response_payload: Optional[Dict[str, Any]],
    request_payload: Dict[str, Any],
    result_text: str,
) -> Dict[str, int]:
    usage = response_payload.get("usage") if isinstance(response_payload, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    prompt_text = _openrouter_payload_prompt_text(request_payload)

    def _token_count(*names: str, fallback: int) -> int:
        for name in names:
            try:
                value = int(usage.get(name))
            except (TypeError, ValueError):
                continue
            if value >= 0:
                return value
        return fallback

    input_tokens = _token_count(
        "prompt_tokens",
        "input_tokens",
        fallback=_estimate_llm_tokens(prompt_text),
    )
    output_tokens = _token_count(
        "completion_tokens",
        "output_tokens",
        fallback=_estimate_llm_tokens(result_text),
    )
    total_tokens = _token_count(
        "total_tokens",
        fallback=input_tokens + output_tokens,
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _xfiles_llm_audit_items() -> List[Dict[str, Any]]:
    current = telegram_sync.state.get(XFILES_LLM_AUDIT_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items = [item for item in items if isinstance(item, dict)]
    current["items"] = normalized_items
    telegram_sync.state[XFILES_LLM_AUDIT_STATE_KEY] = current
    return normalized_items


def _xfiles_llm_audit_summary() -> Dict[str, Any]:
    items = _xfiles_llm_audit_items()
    ready_items = [item for item in items if str(item.get("status") or "") == "ready"]
    total_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    total_duration = 0.0
    by_kind: Dict[str, int] = {}
    for item in ready_items:
        try:
            total_cost += float(item.get("cost_estimate_usd") or 0.0)
        except (TypeError, ValueError):
            pass
        for field_name, target in [
            ("input_tokens_estimate", "input"),
            ("output_tokens_estimate", "output"),
            ("total_tokens_estimate", "total"),
        ]:
            try:
                value = int(item.get(field_name) or 0)
            except (TypeError, ValueError):
                value = 0
            if target == "input":
                input_tokens += value
            elif target == "output":
                output_tokens += value
            else:
                total_tokens += value
        try:
            total_duration += float(item.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            pass
        kind = str(item.get("kind") or "unknown")
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "requests_total": len(items),
        "requests_ready": len(ready_items),
        "requests_error": len(items) - len(ready_items),
        "cost_estimate_usd": round(total_cost, 6),
        "input_tokens_estimate": input_tokens,
        "output_tokens_estimate": output_tokens,
        "total_tokens_estimate": total_tokens,
        "avg_duration_sec": round(total_duration / max(1, len(ready_items)), 3),
        "by_kind": by_kind,
    }




def _openrouter_headers(api_key: str) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "http://localhost:8001",
        "X-Title": PROJECT_NAME,
    }


_LLM_TRANSIENT_STATUS_CODES = {502, 503, 504}


def _post_json_with_transient_retries(
    url: str,
    *,
    json_payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    label: str = "LLM",
    attempts: int = 3,
) -> requests.Response:
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=json_payload,
                timeout=timeout if timeout is not None else _openrouter_timeout_sec(),
            )
            status_code = int(getattr(response, "status_code", 200) or 200)
            if status_code in _LLM_TRANSIENT_STATUS_CODES and attempt < attempts:
                delay = min(2.0 * attempt, 6.0)
                _append_runtime_log(
                    "llm",
                    f"{label}: HTTP {status_code}, повтор {attempt + 1}/{attempts} через {delay:.0f}с",
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
            last_exc = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            retryable_status = status_code in _LLM_TRANSIENT_STATUS_CODES
            retryable_network = isinstance(exc, (requests.Timeout, requests.ConnectionError))
            if (retryable_status or retryable_network) and attempt < attempts:
                delay = min(2.0 * attempt, 6.0)
                reason = f"HTTP {status_code}" if status_code else exc.__class__.__name__
                _append_runtime_log(
                    "llm",
                    f"{label}: {reason}, повтор {attempt + 1}/{attempts} через {delay:.0f}с",
                )
                time.sleep(delay)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError(f"{label}: LLM request failed")


def _sanitize_openrouter_payload_for_pii(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _openrouter_allow_pii_enabled():
        return payload
    sanitized = dict(payload)
    messages: List[Dict[str, Any]] = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict):
            continue
        safe_message = dict(message)
        if "content" in safe_message:
            safe_message["content"] = _mask_pii_text(safe_message.get("content"))
        messages.append(safe_message)
    sanitized["messages"] = messages
    return sanitized






def _sync_legacy_payme_outputs() -> None:
    PAYME_OUT_DIR.mkdir(parents=True, exist_ok=True)

    for legacy_dir in LEGACY_PAYME_OUT_DIRS:
        if not legacy_dir.exists():
            continue

        for legacy_jsonl in legacy_dir.glob("*.jsonl"):
            target_jsonl = PAYME_OUT_DIR / legacy_jsonl.name
            if target_jsonl.exists():
                continue

            shutil.copy2(legacy_jsonl, target_jsonl)

            stem = legacy_jsonl.stem
            legacy_html = legacy_dir / f"{stem}-llm.html"
            target_html = PAYME_OUT_DIR / legacy_html.name
            if legacy_html.exists() and not target_html.exists():
                shutil.copy2(legacy_html, target_html)

            legacy_media_dir = legacy_dir / stem
            target_media_dir = PAYME_OUT_DIR / stem
            if legacy_media_dir.exists() and legacy_media_dir.is_dir() and not target_media_dir.exists():
                shutil.copytree(legacy_media_dir, target_media_dir)


def _normalize_source_selector(selector: str) -> str:
    value = str(selector or "").strip()
    if not value:
        raise ValueError("selector is empty")
    if value.startswith("@"):
        value = value[1:]
    try:
        return str(int(value))
    except ValueError:
        return value.lower()


def _selector_identity(value: Union[str, int]) -> str:
    from app.services.telegram_sources_runtime import _selector_to_lead_name

    return _selector_to_lead_name(telegram_sync._parse_line(str(value).strip()))


DEFAULT_EVENT_KEYWORDS = [
    "мероприят",
    "вебинар",
    "конферен",
    "форум",
    "митап",
    "meetup",
    "event",
    "мастер-класс",
    "мастеркласс",
    "воркшоп",
]


def _normalize_event_keywords(values: List[str]) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for value in values or []:
        for chunk in re.split(r"[\n,;]+", str(value or "")):
            item = chunk.strip().lower()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
    return normalized


def _get_event_keywords_state() -> Dict[str, Any]:
    current = telegram_sync.state.get("_event_keywords")
    if not isinstance(current, dict):
        current = {}
    current.setdefault("keywords", list(DEFAULT_EVENT_KEYWORDS))
    telegram_sync.state["_event_keywords"] = current
    return current


def _get_known_selectors_state() -> Dict[str, str]:
    current = telegram_sync.state.get("_known_selectors")
    if not isinstance(current, dict):
        current = {}
    normalized: Dict[str, str] = {}
    for key, value in current.items():
        lead_name = str(key or "").strip().lower()
        selector = str(value or "").strip()
        if not lead_name or not selector:
            continue
        normalized[lead_name] = selector
    telegram_sync.state["_known_selectors"] = normalized
    return normalized


def _remember_selector(selector: Union[str, int]) -> None:
    normalized = _normalize_source_selector(str(selector))
    lead_name = _selector_identity(normalized)
    mapping = _get_known_selectors_state()
    mapping[lead_name] = normalized
    telegram_sync.state["_known_selectors"] = mapping


def _import_dialog_settings_state() -> Dict[str, Dict[str, int]]:
    current = telegram_sync.state.get("_import_dialog_settings")
    if not isinstance(current, dict):
        current = {}
    normalized: Dict[str, Dict[str, int]] = {}
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    for key, value in current.items():
        if not isinstance(value, dict):
            continue
        try:
            normalized_key = _selector_identity(str(key))
        except Exception:
            normalized_key = str(key or "").strip().lower()
        if not normalized_key:
            continue
        try:
            history_months = int(value.get("import_history_months") or value.get("history_months") or 1)
        except Exception:
            history_months = 1
        try:
            message_limit = int(value.get("import_message_limit") or value.get("message_limit") or 1000)
        except Exception:
            message_limit = 1000
        normalized[normalized_key] = {
            "import_history_months": 0 if max_history == 0 or history_months == 0 else max(1, min(max_history, history_months)),
            "import_message_limit": 0 if max_messages == 0 or message_limit == 0 else max(1, min(max_messages, message_limit)),
        }
    telegram_sync.state["_import_dialog_settings"] = normalized
    return normalized


def _effective_import_limits_for_selector(selector: Union[str, int]) -> Dict[str, int]:
    settings = _get_app_settings()
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    try:
        key = _selector_identity(str(selector))
    except Exception:
        key = str(selector or "").strip().lower()
    stored = _import_dialog_settings_state().get(key, {})
    try:
        default_history = int(settings.get("import_default_history_months") or 1)
    except Exception:
        default_history = 1
    try:
        default_messages = int(settings.get("import_default_message_limit") or 1000)
    except Exception:
        default_messages = 1000
    try:
        history_months = int(stored.get("import_history_months") or default_history)
    except Exception:
        history_months = default_history
    try:
        message_limit = int(stored.get("import_message_limit") or default_messages)
    except Exception:
        message_limit = default_messages
    return {
        "import_history_months": 0 if max_history == 0 or history_months == 0 else max(1, min(max_history, history_months)),
        "import_message_limit": 0 if max_messages == 0 or message_limit == 0 else max(1, min(max_messages, message_limit)),
        "import_max_history_months": max_history,
        "import_max_message_limit": max_messages,
    }


def _set_import_limits_for_selector(
    selector: Union[str, int],
    *,
    import_history_months: int,
    import_message_limit: int,
) -> Dict[str, int]:
    try:
        normalized = _normalize_source_selector(str(selector))
        key = _selector_identity(normalized)
    except Exception:
        normalized = str(selector or "").strip()
        key = normalized.lower()
    if not key:
        raise HTTPException(status_code=400, detail="Не указан selector")
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    requested_history = int(import_history_months or 0)
    requested_messages = int(import_message_limit or 0)
    payload = {
        "import_history_months": 0 if max_history == 0 or requested_history == 0 else max(1, min(max_history, requested_history)),
        "import_message_limit": 0 if max_messages == 0 or requested_messages == 0 else max(1, min(max_messages, requested_messages)),
    }
    state = _import_dialog_settings_state()
    state[key] = payload
    telegram_sync.state["_import_dialog_settings"] = state
    _remember_selector(normalized)
    telegram_sync.save_state()
    return {
        **payload,
        "import_max_history_months": max_history,
        "import_max_message_limit": max_messages,
    }


def _bulk_set_import_limits_for_selectors(
    selectors: List[str],
    *,
    import_history_months: int,
    import_message_limit: int,
) -> List[str]:
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    requested_history = int(import_history_months or 0)
    requested_messages = int(import_message_limit or 0)
    payload = {
        "import_history_months": 0 if max_history == 0 or requested_history == 0 else max(1, min(max_history, requested_history)),
        "import_message_limit": 0 if max_messages == 0 or requested_messages == 0 else max(1, min(max_messages, requested_messages)),
    }
    state = _import_dialog_settings_state()
    known_selectors = _get_known_selectors_state()
    updated: List[str] = []
    for selector in selectors:
        try:
            normalized = _normalize_source_selector(str(selector))
            key = _selector_identity(normalized)
        except Exception:
            normalized = str(selector or "").strip()
            key = normalized.lower()
        if not key:
            continue
        state[key] = dict(payload)
        known_selectors[key] = normalized
        updated.append(str(normalized))
    telegram_sync.state["_import_dialog_settings"] = state
    telegram_sync.state["_known_selectors"] = known_selectors
    return updated


def _enable_unlimited_import_for_all_selected_sources() -> Dict[str, Any]:
    settings = _get_app_settings()
    settings.update(
        {
            "telegram_unlimited_import_enabled": True,
            "local_import_limits_enabled": True,
            "local_import_max_history_months": 0,
            "local_import_max_message_limit": 0,
            "import_default_history_months": 0,
            "import_default_message_limit": 0,
            "local_telegram_source_limit_enabled": True,
            "local_telegram_source_limit": 0,
        }
    )
    _save_app_settings(settings)
    selectors = _source_selectors_as_strings()
    updated = _bulk_set_import_limits_for_selectors(
        selectors,
        import_history_months=0,
        import_message_limit=0,
    )
    telegram_sync.save_state()
    return {
        "ok": True,
        "telegram_unlimited_import_enabled": True,
        "updated_sources_count": len(updated),
        "updated_selectors": updated,
        "import_history_months": 0,
        "import_message_limit": 0,
    }


def _apply_import_limits_for_all_selected_sources(
    *,
    import_history_months: int,
    import_message_limit: int,
    unlimited: bool = False,
) -> Dict[str, Any]:
    history_months = 0 if unlimited else max(1, int(import_history_months or 1))
    message_limit = 0 if unlimited else max(1, int(import_message_limit or 1000))
    settings = _get_app_settings()
    settings.update(
        {
            "telegram_unlimited_import_enabled": bool(unlimited),
            "local_import_limits_enabled": True,
            "local_import_max_history_months": history_months,
            "local_import_max_message_limit": message_limit,
            "import_default_history_months": history_months,
            "import_default_message_limit": message_limit,
            **(
                {
                    "local_telegram_source_limit_enabled": True,
                    "local_telegram_source_limit": 0,
                }
                if unlimited
                else {}
            ),
        }
    )
    _save_app_settings(settings)
    selectors = _source_selectors_as_strings()
    updated = _bulk_set_import_limits_for_selectors(
        selectors,
        import_history_months=history_months,
        import_message_limit=message_limit,
    )
    telegram_sync.save_state()
    telegram_sync.request_source_reload()
    return {
        "ok": True,
        "updated_sources_count": len(updated),
        "updated_selectors": updated,
        "telegram_unlimited_import_enabled": bool(unlimited),
        "import_history_months": history_months,
        "import_message_limit": message_limit,
    }


def _source_identity_candidates(selector: Union[str, int]) -> set[str]:
    raw = str(selector or "").strip()
    candidates: set[str] = set()
    for value in {raw, raw.lstrip("@")}:
        value = str(value or "").strip()
        if not value:
            continue
        lowered = value.lower()
        candidates.add(lowered)
        if lowered.endswith(".jsonl"):
            candidates.add(Path(lowered).stem)
        try:
            candidates.add(_selector_identity(value).lower())
        except Exception:
            pass
        try:
            candidates.add(_normalize_source_selector(value).lower())
        except Exception:
            pass
    return {item for item in candidates if item}


def _source_row_matches_identities(row: Dict[str, Any], identities: set[str]) -> bool:
    if not identities:
        return False
    for field in [
        "lead",
        "source_selector",
        "source_chat",
        "chat_username",
        "chat_title",
        "channel",
        "source",
        "file_name",
        "source_jsonl",
    ]:
        value = row.get(field)
        if value is None:
            continue
        text = str(value or "").strip().lower().lstrip("@")
        if not text:
            continue
        variants = {text, Path(text).stem if text.endswith(".jsonl") else text}
        if variants & identities:
            return True
    return False


def _purge_analysis_cache_for_source(kind: str, identities: set[str]) -> int:
    try:
        path = _analysis_cache_path(kind)  # type: ignore[arg-type]
        if not path.exists():
            return 0
        rows = _load_analysis_cache_rows(kind)  # type: ignore[arg-type]
        kept = [row for row in rows if not _source_row_matches_identities(row, identities)]
        removed = len(rows) - len(kept)
        if removed:
            _save_analysis_cache_rows(kind, kept)  # type: ignore[arg-type]
        return removed
    except Exception as exc:
        logger.warning("source purge cache %s failed: %s", kind, exc)
        return 0


def _purge_contacts_messages_cache_for_source(identities: set[str]) -> int:
    path = _contacts_messages_cache_path()
    if not path.exists():
        return 0
    removed = 0
    tmp = path.with_suffix(".tmp")
    with path.open("r", encoding="utf-8", errors="replace") as src, tmp.open("w", encoding="utf-8") as dst:
        for line in src:
            try:
                row = json.loads(line)
            except Exception:
                dst.write(line)
                continue
            if isinstance(row, dict) and _source_row_matches_identities(row, identities):
                removed += 1
                continue
            dst.write(line)
    tmp.replace(path)
    return removed


def _purge_outreach_fallback_for_source(identities: set[str]) -> int:
    state = _outreach_state_fallback()
    rows = list(state.get("crm_fields") or [])
    kept = [row for row in rows if not isinstance(row, dict) or not _source_row_matches_identities(row, identities)]
    removed = len(rows) - len(kept)
    if removed:
        state["crm_fields"] = kept
        telegram_sync.save_state()
    return removed


def _duckdb_delete_source_rows(table: str, identities: set[str]) -> int:
    if duckdb is None or not DUCKDB_PATH.exists() or not identities:
        return 0
    _duckdb_init_schema_sync()
    conn = _duckdb_connect()
    try:
        try:
            columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]
        except Exception:
            return 0
        candidate_columns = [
            col
            for col in [
                "lead",
                "source_selector",
                "source_chat",
                "chat_username",
                "chat_title",
                "channel",
                "source",
                "source_jsonl",
            ]
            if col in columns
        ]
        if not candidate_columns:
            return 0
        before = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        where_parts: List[str] = []
        params: List[Any] = []
        id_values = sorted(identities)
        placeholders = ", ".join(["?"] * len(id_values))
        for col in candidate_columns:
            where_parts.append(f"lower(regexp_replace(coalesce(CAST({col} AS VARCHAR), ''), '^@', '')) IN ({placeholders})")
            params.extend(id_values)
            if col == "source_jsonl":
                like_parts: List[str] = []
                for identity in id_values:
                    like_parts.append(f"lower(coalesce(CAST({col} AS VARCHAR), '')) LIKE ?")
                    params.append(f"%/{identity}.jsonl")
                    like_parts.append(f"lower(coalesce(CAST({col} AS VARCHAR), '')) LIKE ?")
                    params.append(f"%{identity}.jsonl")
                where_parts.append("(" + " OR ".join(like_parts) + ")")
        conn.execute(f"DELETE FROM {table} WHERE {' OR '.join(where_parts)}", params)
        after = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return max(0, before - after)
    except Exception as exc:
        logger.warning("source purge duckdb %s failed: %s", table, exc)
        return 0
    finally:
        conn.close()


def _purge_source_files(identities: set[str]) -> int:
    removed = 0
    for identity in sorted(identities):
        if not identity or "/" in identity or "\\" in identity or identity in {".", ".."}:
            continue
        for path in [
            PAYME_OUT_DIR / f"{identity}.jsonl",
            PAYME_OUT_DIR / f"{identity}-llm.html",
            PAYME_OUT_DIR / f"{identity}-tokens.txt",
            PAYME_OUT_DIR / f"{identity}-tokens.json",
            PAYME_OUT_DIR / f"{identity}-tokens-calculated.txt",
        ]:
            try:
                if path.exists() and path.is_file():
                    path.unlink()
                    removed += 1
            except Exception as exc:
                logger.warning("source purge file %s failed: %s", path, exc)
        media_dir = PAYME_OUT_DIR / identity
        try:
            if media_dir.exists() and media_dir.is_dir():
                shutil.rmtree(media_dir)
                removed += 1
        except Exception as exc:
            logger.warning("source purge dir %s failed: %s", media_dir, exc)
    return removed


def _purge_removed_source_data(selector: Union[str, int]) -> Dict[str, Any]:
    identities = _source_identity_candidates(selector)
    result: Dict[str, Any] = {
        "selector": str(selector or ""),
        "identities": sorted(identities),
        "cache_rows": {},
        "duckdb_rows": {},
        "contact_message_rows": 0,
        "outreach_fallback_rows": 0,
        "files": 0,
        "total_removed": 0,
    }
    for kind in ["crm", "events", "contacts", "routes"]:
        removed = _purge_analysis_cache_for_source(kind, identities)
        result["cache_rows"][kind] = removed
        result["total_removed"] += removed
    removed_contacts_cache = _purge_contacts_messages_cache_for_source(identities)
    result["contact_message_rows"] = removed_contacts_cache
    result["total_removed"] += removed_contacts_cache
    removed_outreach_fallback = _purge_outreach_fallback_for_source(identities)
    result["outreach_fallback_rows"] = removed_outreach_fallback
    result["total_removed"] += removed_outreach_fallback
    for table in ["messages_raw", "crm_contacts", "event_messages", "outreach_crm_fields"]:
        removed = _duckdb_delete_source_rows(table, identities)
        result["duckdb_rows"][table] = removed
        result["total_removed"] += removed
    removed_files = _purge_source_files(identities)
    result["files"] = removed_files
    result["total_removed"] += removed_files
    for prefix in [
        "leads",
        "grid",
        "dashboard",
        "events",
        "event",
        "calendar",
        "crm",
        "contacts",
        "outreach",
        "media",
        "routes",
        "jur",
    ]:
        _api_snapshot_cache_clear_prefix(prefix)
    telegram_sync.state.setdefault("_purged_sources", {})[str(selector or "")] = {
        "at": _utc_now().isoformat(),
        "result": result,
    }
    telegram_sync.save_state()
    return result


def _normalize_event_delete_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _event_delete_key(source: Any, text: Any) -> str:
    candidates = sorted(_source_identity_candidates(str(source or "")))
    source_key = candidates[0] if candidates else str(source or "").strip().lower()
    payload = f"{source_key}\0{_normalize_event_delete_text(text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_row_delete_key(row: Dict[str, Any]) -> str:
    source = row.get("lead") or row.get("source_selector") or row.get("source_chat") or ""
    return _event_delete_key(source, row.get("text"))


def _event_deleted_keys_state() -> Dict[str, Dict[str, Any]]:
    state = _analysis_state("events")
    deleted = state.get("deleted_event_keys")
    if not isinstance(deleted, dict):
        deleted = {}
        state["deleted_event_keys"] = deleted
    return deleted


def _event_row_is_deleted(row: Dict[str, Any]) -> bool:
    return _event_row_delete_key(row) in _event_deleted_keys_state()


def _filter_deleted_event_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if not _event_row_is_deleted(row)]


def _delete_matching_event_rows_from_duckdb(delete_key: str) -> int:
    if duckdb is None or not DUCKDB_PATH.exists():
        return 0
    _duckdb_init_schema_sync()
    conn = _duckdb_connect()
    try:
        try:
            rows = conn.execute(
                "SELECT row_key, lead, source_selector, message_id, date_utc_raw, text FROM event_messages"
            ).fetchall()
        except Exception:
            return 0
        keys: List[str] = []
        for row in rows:
            row_payload = {
                "lead": str(row[1] or ""),
                "source_selector": str(row[2] or "") or None,
                "message_id": int(row[3] or 0),
                "date_utc": str(row[4] or ""),
                "text": str(row[5] or ""),
            }
            if _event_row_delete_key(row_payload) == delete_key:
                keys.append(str(row[0] or ""))
        for row_key in keys:
            conn.execute("DELETE FROM event_messages WHERE row_key = ?", [row_key])
        return len(keys)
    finally:
        conn.close()


def _delete_event_message(payload: EventMessageDeletePayload) -> Dict[str, Any]:
    source = payload.lead or payload.source_selector or ""
    text = payload.text or ""
    if not source or not _normalize_event_delete_text(text):
        raise HTTPException(status_code=400, detail="Нужно передать источник и текст мероприятия")
    delete_key = _event_delete_key(source, text)
    deleted = _event_deleted_keys_state()
    deleted[delete_key] = {
        "lead": payload.lead,
        "source_selector": payload.source_selector,
        "message_id": payload.message_id,
        "text_preview": _normalize_event_delete_text(text)[:240],
        "deleted_at": _utc_now().isoformat(),
    }
    cache_removed = 0
    if _analysis_cache_path("events").exists():
        rows = _load_analysis_cache_rows("events")
        kept = [row for row in rows if _event_row_delete_key(row) != delete_key]
        cache_removed = len(rows) - len(kept)
        if cache_removed:
            _save_analysis_cache_rows("events", kept)
    duckdb_removed = _delete_matching_event_rows_from_duckdb(delete_key)
    telegram_sync.save_state()
    for prefix in ["events", "event", "calendar", "dashboard"]:
        _api_snapshot_cache_clear_prefix(prefix)
    return {
        "removed_count": max(cache_removed + duckdb_removed, 1),
        "cache_removed": cache_removed,
        "duckdb_removed": duckdb_removed,
    }


def _forget_selector(lead: str) -> None:
    target = str(lead or "").strip().lower()
    if not target:
        return
    mapping = _get_known_selectors_state()
    if target in mapping:
        mapping.pop(target, None)
        telegram_sync.state["_known_selectors"] = mapping


def _get_event_keywords() -> List[str]:
    current = _get_event_keywords_state()
    keywords = _normalize_event_keywords(list(current.get("keywords") or []))
    if not keywords:
        keywords = list(DEFAULT_EVENT_KEYWORDS)
    current["keywords"] = keywords
    return keywords


def _set_event_keywords(values: List[str]) -> List[str]:
    keywords = _normalize_event_keywords(values)
    if not keywords:
        keywords = list(DEFAULT_EVENT_KEYWORDS)
    current = _get_event_keywords_state()
    current["keywords"] = keywords
    telegram_sync.state["_event_keywords"] = current
    telegram_sync.save_state()
    return keywords


def _remove_import_sync_selector_by_identity(target_identity: str) -> bool:
    config = telegram_sync.get_import_sync_state()
    raw_selectors = list(config.get("selectors") or [])
    filtered: List[str] = []
    changed = False
    for raw_selector in raw_selectors:
        try:
            normalized = _normalize_source_selector(str(raw_selector))
        except ValueError:
            changed = True
            continue
        if _selector_identity(normalized) == target_identity:
            changed = True
            continue
        filtered.append(normalized)

    if changed:
        config["selectors"] = filtered
        config["updated_at"] = _utc_now().isoformat()
        telegram_sync.state["_import_sync"] = config
    return changed


def _lead_related_stems(lead: str) -> List[str]:
    target = str(lead or "").strip().lower()
    stems: List[str] = []
    for directory in [PAYME_OUT_DIR, *LEGACY_PAYME_OUT_DIRS]:
        if not directory.exists():
            continue
        for path in directory.glob("*.jsonl"):
            if path.stem.lower() == target and path.stem not in stems:
                stems.append(path.stem)
    if not stems and target:
        stems.append(target)
    return stems


def _drop_lead_state(lead: str) -> None:
    target = str(lead or "").strip().lower()
    if not target:
        return
    for key in list(telegram_sync.state.keys()):
        if str(key).startswith("_"):
            continue
        if str(key).lower() == target:
            telegram_sync.state.pop(key, None)


def _delete_lead_artifacts(lead: str) -> None:
    artifact_suffixes = [
        ".jsonl",
        "-llm.html",
        "-tokens.txt",
        "-tokens.json",
        "-tokens-calculated.txt",
    ]

    for stem in _lead_related_stems(lead):
        for directory in [PAYME_OUT_DIR, *LEGACY_PAYME_OUT_DIRS]:
            if not directory.exists():
                continue
            for suffix in artifact_suffixes:
                path = directory / f"{stem}{suffix}"
                if path.exists():
                    path.unlink(missing_ok=True)
            media_dir = directory / stem
            if media_dir.exists() and media_dir.is_dir():
                shutil.rmtree(media_dir, ignore_errors=True)
        _drop_lead_state(stem)
        _forget_selector(stem)


def _match_event_keywords(text: str, keywords: List[str]) -> List[str]:
    haystack = str(text or "").strip().lower()
    if not haystack:
        return []
    return [keyword for keyword in keywords if keyword in haystack]


def _normalize_llm_event_date(value: Any) -> Optional[str]:
    raw = str(value or "").strip()
    if not raw or raw.lower() in {"null", "none", "нет", "unknown", "не указано"}:
        return None
    match = re.search(r"\b(20\d{2}|19\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])\b", raw)
    if not match:
        return None
    candidate = match.group(0)
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def _extract_json_object_from_text(value: str) -> Dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}




def _routes_row_key(row: Dict[str, Any]) -> str:
    return str(row.get("row_hash") or f"{row.get('lead') or row.get('source_jsonl') or ''}:{row.get('message_id') or ''}").strip()


def _normalize_route_address(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    text = re.sub(r"^(г\.?\s*)?москва\s*,?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*,\s*", ", ", text)
    return text.strip(" ,")


def _route_address_key(value: Any) -> str:
    normalized = _normalize_route_address(value).lower()
    normalized = normalized.replace("ё", "е")
    normalized = re.sub(r"\b(город|г\.|москва|мск)\b", "", normalized)
    normalized = re.sub(r"[^0-9a-zа-я]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _routes_cache_rows() -> List[Dict[str, Any]]:
    return _load_analysis_cache_rows(_ROUTES_ANALYSIS_KIND)  # type: ignore[arg-type]


def _save_routes_cache_rows(rows: List[Dict[str, Any]]) -> None:
    _save_analysis_cache_rows(_ROUTES_ANALYSIS_KIND, rows)  # type: ignore[arg-type]


def _duckdb_load_moscow_route_rows(limit: int = 50000) -> List[Dict[str, Any]]:
    if duckdb is None or not DUCKDB_PATH.exists():
        return []
    conn = _duckdb_connect_readonly()
    try:
        raw_rows = conn.execute(
            """
            SELECT
                row_hash,
                source_jsonl,
                message_id,
                date_utc_raw,
                text,
                sender_username,
                sender_name,
                chat_username,
                chat_title
            FROM messages_raw
            WHERE lower(coalesce(text, '')) LIKE '%москва%'
            ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
            LIMIT ?
            """,
            [max(1, int(limit or 1))],
        ).fetchall()
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    selector_map = _managed_selector_map()
    for row in raw_rows:
        source_jsonl = str(row[1] or "")
        lead = Path(source_jsonl).stem if source_jsonl else ""
        items.append(
            {
                "row_hash": str(row[0] or ""),
                "lead": lead,
                "source_selector": selector_map.get(lead.lower()) or str(row[7] or ""),
                "message_id": int(row[2] or 0),
                "date_utc": str(row[3] or ""),
                "text": str(row[4] or ""),
                "sender_username": str(row[5] or ""),
                "sender_name": str(row[6] or ""),
                "chat_username": str(row[7] or ""),
                "chat_title": str(row[8] or ""),
            }
        )
    return items




def _routes_address_directory(rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    items = rows if rows is not None else _routes_cache_rows()
    addresses: Dict[str, Dict[str, Any]] = {}
    for row in items:
        address = _normalize_route_address(row.get("address"))
        address_key = str(row.get("address_key") or _route_address_key(address)).strip()
        if not address or not address_key:
            continue
        current = addresses.setdefault(
            address_key,
            {
                "address_key": address_key,
                "address": address,
                "messages_count": 0,
                "leads": set(),
                "first_seen_at": None,
                "last_seen_at": None,
                "lat": row.get("lat"),
                "lon": row.get("lon"),
                "examples": [],
            },
        )
        current["messages_count"] = int(current.get("messages_count") or 0) + 1
        if row.get("lead"):
            current["leads"].add(str(row.get("lead")))
        date_utc = str(row.get("date_utc") or "")
        if date_utc:
            current["first_seen_at"] = min(filter(None, [current.get("first_seen_at"), date_utc])) if current.get("first_seen_at") else date_utc
            current["last_seen_at"] = max(filter(None, [current.get("last_seen_at"), date_utc])) if current.get("last_seen_at") else date_utc
        if row.get("lat") is not None and row.get("lon") is not None:
            current["lat"] = row.get("lat")
            current["lon"] = row.get("lon")
        if len(current["examples"]) < 3:
            current["examples"].append(
                {
                    "lead": row.get("lead"),
                    "message_id": row.get("message_id"),
                    "date_utc": row.get("date_utc"),
                    "text": str(row.get("text") or "")[:500],
                }
            )
    result: List[Dict[str, Any]] = []
    for item in addresses.values():
        item["leads"] = sorted(item.get("leads") or [])
        result.append(item)
    result.sort(key=lambda item: (int(item.get("messages_count") or 0), str(item.get("last_seen_at") or "")), reverse=True)
    return result


def _routes_status_payload() -> Dict[str, Any]:
    state = _analysis_state(_ROUTES_ANALYSIS_KIND)  # type: ignore[arg-type]
    rows = _routes_cache_rows()
    addresses = _routes_address_directory(rows)
    gps_points = sum(1 for item in addresses if item.get("lat") is not None and item.get("lon") is not None)
    total_moscow = int(state.get("moscow_messages_total") or len(rows) or 0)
    return {
        "kind": "routes",
        "running": bool(state.get("running", False)),
        "cache_ready": bool(rows) or bool(state.get("last_refresh_at")),
        "total_rows": len(rows),
        "moscow_messages_total": total_moscow,
        "addresses_found": len(addresses),
        "gps_points": gps_points,
        "progress_current": int(state.get("progress_current", 0) or 0),
        "progress_total": int(state.get("progress_total", 0) or total_moscow or 0),
        "progress_percent": float(state.get("progress_percent", 0.0) or 0.0),
        "progress_label": state.get("progress_label"),
        "current_item": state.get("current_item"),
        "progress_log": [str(item) for item in (state.get("progress_log") or []) if str(item or "").strip()][:10],
        "last_refresh_at": state.get("last_refresh_at"),
        "last_error": state.get("last_error"),
        "next_refresh_at": state.get("next_refresh_at"),
        "llm_batch_size": _ROUTES_LLM_BATCH_SIZE,
        "openrouter_model": state.get("routes_openrouter_model") or _get_app_settings().get("openrouter_model"),
    }




def _schedule_routes_refresh(
    force_full: bool = False,
    max_llm: Optional[int] = None,
    model_override: Optional[str] = None,
) -> bool:
    global _routes_refresh_task
    with _routes_refresh_lock:
        if _routes_refresh_task and not _routes_refresh_task.done():
            return False
        loop = asyncio.get_running_loop()
        _routes_refresh_task = loop.create_task(
            asyncio.to_thread(_refresh_routes_cache_sync, force_full, max_llm, model_override)
        )
        return True


def _openrouter_event_date_message_days() -> int:
    try:
        return int(_get_app_settings().get("openrouter_event_date_message_days", 30) or 30)
    except (TypeError, ValueError):
        return 30


def _event_date_message_cutoff() -> datetime:
    days = max(1, min(_openrouter_event_date_message_days(), 3650))
    return _utc_now() - timedelta(days=days)


def _parse_event_message_dt(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_date_message_in_window(row: Dict[str, Any]) -> bool:
    message_dt = _parse_event_message_dt(row.get("date_utc") or row.get("date_utc_raw"))
    if message_dt is None:
        return False
    return message_dt >= _event_date_message_cutoff()


def _event_date_needs_extraction(row: Dict[str, Any]) -> bool:
    text = str(row.get("text") or "").strip()
    if len(text) < 12:
        return False
    if not _event_date_message_in_window(row):
        return False
    if str(row.get("event_date") or "").strip():
        return False
    if str(row.get("event_date_source") or "").strip():
        return False
    return True


def _event_date_count_rows_from_cache() -> Dict[str, int]:
    rows = _load_analysis_cache_rows("events") if _analysis_cache_path("events").exists() else []
    total = 0
    processed = 0
    found = 0
    for row in rows:
        if not isinstance(row, dict) or not _event_date_needs_text(row):
            continue
        if not _event_date_message_in_window(row):
            continue
        total += 1
        if str(row.get("event_date") or "").strip():
            found += 1
            processed += 1
        elif str(row.get("event_date_source") or "").strip():
            processed += 1
    return {"total": total, "processed": processed, "found": found}


def _event_date_needs_text(row: Dict[str, Any]) -> bool:
    return len(str(row.get("text") or "").strip()) >= 12


def _event_date_count_rows_sync() -> Dict[str, int]:
    if duckdb is not None and DUCKDB_PATH.exists() and _duckdb_events_ready():
        conn = _duckdb_connect_readonly()
        try:
            keyword_hash = _keywords_hash(_get_event_keywords())
            cutoff = _event_date_message_cutoff()
            row = conn.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE length(trim(coalesce(text, ''))) >= 12) AS total,
                    COUNT(*) FILTER (
                        WHERE length(trim(coalesce(text, ''))) >= 12
                          AND (
                            event_date IS NOT NULL
                            OR length(trim(coalesce(event_date_source, ''))) > 0
                          )
                    ) AS processed,
                    COUNT(*) FILTER (
                        WHERE length(trim(coalesce(text, ''))) >= 12
                          AND event_date IS NOT NULL
                    ) AS found
                FROM event_messages
                WHERE keyword_hash = ?
                  AND try_cast(date_utc_raw AS TIMESTAMPTZ) >= ?
                """,
                [keyword_hash, cutoff],
            ).fetchone()
            return {
                "total": int(row[0] or 0),
                "processed": int(row[1] or 0),
                "found": int(row[2] or 0),
            }
        except Exception:
            return _event_date_count_rows_from_cache()
        finally:
            conn.close()
    return _event_date_count_rows_from_cache()


def _event_date_pending_rows_sync(limit: int = 8) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 8), 25))
    if duckdb is not None and DUCKDB_PATH.exists() and _duckdb_events_ready():
        conn = _duckdb_connect_readonly()
        try:
            keyword_hash = _keywords_hash(_get_event_keywords())
            cutoff = _event_date_message_cutoff()
            raw_rows = conn.execute(
                """
                SELECT
                    lead, source_selector, message_id, date_utc_raw, text,
                    sender_username, sender_name, matched_keywords_json,
                    event_date, event_date_confidence, event_date_source
                FROM event_messages
                WHERE keyword_hash = ?
                  AND try_cast(date_utc_raw AS TIMESTAMPTZ) >= ?
                  AND length(trim(coalesce(text, ''))) >= 12
                  AND coalesce(event_date, '') = ''
                  AND length(trim(coalesce(event_date_source, ''))) = 0
                ORDER BY date_utc_raw DESC, message_id DESC
                LIMIT ?
                """,
                [keyword_hash, cutoff, safe_limit],
            ).fetchall()
        except Exception:
            raw_rows = []
        finally:
            conn.close()

        rows: List[Dict[str, Any]] = []
        for row in raw_rows:
            try:
                rows.append(
                    EventMessageDTO(
                        lead=str(row[0] or ""),
                        source_selector=str(row[1] or "") or None,
                        message_id=int(row[2] or 0),
                        date_utc=str(row[3] or ""),
                        text=str(row[4] or ""),
                        sender_username=str(row[5] or "") or None,
                        sender_name=str(row[6] or "") or None,
                        matched_keywords=list(json.loads(str(row[7] or "[]"))),
                        event_date=str(row[8] or "") or None,
                        event_date_confidence=float(row[9]) if row[9] is not None else None,
                        event_date_source=str(row[10] or "") or None,
                    ).model_dump()
                )
            except Exception:
                continue
        if rows:
            return rows

    rows = _load_analysis_cache_rows("events") if _analysis_cache_path("events").exists() else []
    return [
        dict(row)
        for row in rows
        if isinstance(row, dict) and _event_date_needs_extraction(row)
    ][:safe_limit]


def _event_date_status_snapshot() -> Dict[str, Any]:
    counts = _event_date_count_rows_sync()
    total = int(counts.get("total", 0) or 0)
    processed = int(counts.get("processed", 0) or 0)
    found = int(counts.get("found", 0) or 0)
    pending = max(0, total - processed)
    with _event_date_extraction_lock:
        running = bool(_event_date_extraction_running)
        runtime = dict(_event_date_extraction_runtime)

    rate_per_min = float(runtime.get("rate_per_min", 0.0) or 0.0)
    started_raw = runtime.get("started_at")
    if running and started_raw:
        try:
            started = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
            elapsed = max(1.0, (_utc_now() - started).total_seconds())
            rate_per_min = float(runtime.get("processed", 0) or 0) / elapsed * 60.0
        except Exception:
            pass

    percent = (processed / total * 100.0) if total else 0.0
    return {
        "running": running,
        "total": total,
        "processed": processed,
        "found": found,
        "pending": pending,
        "percent": round(percent, 1),
        "rate_per_min": round(max(0.0, rate_per_min), 2),
        "started_at": runtime.get("started_at"),
        "updated_at": runtime.get("updated_at"),
        "last_error": runtime.get("last_error"),
    }


def _update_event_date_result_sync(row_key: str, result: Dict[str, Any]) -> None:
    event_date = _normalize_llm_event_date(result.get("event_date"))
    event_date_confidence = result.get("event_date_confidence")
    try:
        event_date_confidence = float(event_date_confidence) if event_date_confidence is not None else None
    except (TypeError, ValueError):
        event_date_confidence = None
    event_date_source = str(result.get("event_date_source") or ("openrouter" if event_date else "openrouter:none")).strip()
    updated_at = _utc_now()

    if duckdb is not None and DUCKDB_PATH.exists():
        conn = _duckdb_connect()
        try:
            conn.execute(
                """
                UPDATE event_messages
                SET event_date = ?,
                    event_date_confidence = ?,
                    event_date_source = ?,
                    event_date_updated_at = ?
                WHERE row_key = ?
                """,
                [event_date, event_date_confidence, event_date_source, updated_at, row_key],
            )
        finally:
            conn.close()

    cache_path = _analysis_cache_path("events")
    if cache_path.exists():
        rows = _load_analysis_cache_rows("events")
        changed = False
        for row in rows:
            if _event_row_key(row) != row_key:
                continue
            row["event_date"] = event_date
            row["event_date_confidence"] = event_date_confidence
            row["event_date_source"] = event_date_source
            changed = True
            break
        if changed:
            _save_analysis_cache_rows("events", rows)


def _enrich_event_dates_sync(rows: List[Dict[str, Any]], max_rows: int = 8) -> Dict[str, Any]:
    global _event_date_extraction_running
    with _event_date_extraction_lock:
        if _event_date_extraction_running:
            return {"processed": 0, "errors": 0, "skipped": "already_running"}
        _event_date_extraction_running = True
        now_iso = _utc_now().isoformat()
        _event_date_extraction_runtime.update(
            {
                "started_at": now_iso,
                "updated_at": now_iso,
                "processed": 0,
                "found": 0,
                "errors": 0,
                "last_error": None,
                "rate_per_min": 0.0,
            }
        )

    candidates = [dict(row) for row in rows if isinstance(row, dict) and _event_date_needs_extraction(row)]
    processed = 0
    found = 0
    errors = 0
    try:
        state = _analysis_state("events")
        if not candidates:
            return {"processed": 0, "errors": 0}
        _append_runtime_log("events", f"LLM дата мероприятия: поставлено в очередь {min(len(candidates), max_rows)} сообщений")
        for row in candidates[:max(1, int(max_rows or 1))]:
            row_key = _event_row_key(row)
            try:
                result = _call_openrouter_event_date_sync(row)
                _update_event_date_result_sync(row_key, result)
                processed += 1
                if result.get("event_date"):
                    found += 1
                    _append_runtime_log("events", f"LLM дата мероприятия: {row_key} -> {result.get('event_date')}")
            except Exception as exc:
                errors += 1
                with _event_date_extraction_lock:
                    _event_date_extraction_runtime["last_error"] = str(exc)
                _append_runtime_log("events", f"LLM дата мероприятия ошибка {row_key}: {exc}")
            finally:
                with _event_date_extraction_lock:
                    elapsed = max(1.0, (_utc_now() - datetime.fromisoformat(str(_event_date_extraction_runtime["started_at"]))).total_seconds())
                    _event_date_extraction_runtime.update(
                        {
                            "updated_at": _utc_now().isoformat(),
                            "processed": processed,
                            "found": found,
                            "errors": errors,
                            "rate_per_min": processed / elapsed * 60.0,
                        }
                    )
        state["event_date_last_processed"] = processed
        state["event_date_last_found"] = found
        state["event_date_last_errors"] = errors
        state["event_date_last_rate_per_min"] = float(_event_date_extraction_runtime.get("rate_per_min", 0.0) or 0.0)
        state["last_refresh_at"] = _utc_now().isoformat()
        telegram_sync.save_state()
        return {"processed": processed, "found": found, "errors": errors}
    finally:
        with _event_date_extraction_lock:
            _event_date_extraction_running = False
            _event_date_extraction_runtime["updated_at"] = _utc_now().isoformat()


async def _event_date_extraction_async(rows: List[Dict[str, Any]]) -> None:
    try:
        await asyncio.to_thread(_enrich_event_dates_sync, rows)
    finally:
        global _event_date_extraction_task
        _event_date_extraction_task = None


def _schedule_event_date_extraction(rows: List[Dict[str, Any]], background_tasks: Optional[BackgroundTasks] = None) -> bool:
    global _event_date_extraction_task
    candidates = [row for row in rows if isinstance(row, dict) and _event_date_needs_extraction(row)]
    if not candidates:
        return False
    with _event_date_extraction_lock:
        if _event_date_extraction_running:
            return False
    if background_tasks is not None:
        background_tasks.add_task(_enrich_event_dates_sync, candidates)
        return True
    task = _event_date_extraction_task
    if task is not None and not task.done():
        return False
    try:
        _event_date_extraction_task = asyncio.create_task(_event_date_extraction_async(candidates))
        return True
    except RuntimeError:
        _event_date_extraction_task = None
        return False


def _schedule_event_date_pending_batch(background_tasks: Optional[BackgroundTasks] = None, max_rows: int = 8) -> bool:
    with _event_date_extraction_lock:
        if _event_date_extraction_running:
            return False
    rows = _event_date_pending_rows_sync(max_rows)
    if not rows:
        return False
    return _schedule_event_date_extraction(rows, background_tasks=background_tasks)


def _collect_event_messages(limit: int = 500) -> List[EventMessageDTO]:
    _ensure_dir_exists()
    keywords = _get_event_keywords()
    source_map = _source_selector_map()
    events_found: List[EventMessageDTO] = []

    for jf in sorted(PAYME_OUT_DIR.glob("*.jsonl")):
        lead_name = jf.stem
        source_selector = source_map.get(lead_name.lower())
        for rec in _iter_jsonl(jf):
            msg = rec.get("message", {})
            matched = _match_event_keywords(msg.get("text") or "", keywords)
            if not matched:
                continue
            date_utc = str(msg.get("date_utc") or "").strip()
            if not date_utc:
                continue
            sender = rec.get("sender", {})
            events_found.append(
                EventMessageDTO(
                    lead=lead_name,
                    source_selector=source_selector,
                    message_id=int(msg.get("id") or 0),
                    date_utc=date_utc,
                    text=str(msg.get("text") or ""),
                    sender_username=sender.get("username"),
                    sender_name=sender.get("name"),
                    matched_keywords=matched,
                )
            )

    events_found.sort(key=lambda item: item.date_utc, reverse=True)
    return events_found[: max(1, limit)]


def _crm_row_key(row: Dict[str, Any]) -> str:
    return f"{row.get('lead') or ''}:{int(row.get('message_id') or 0)}"


def _crm_field_provenance_entry(
    field: str,
    source: str,
    detail: Optional[str] = None,
) -> str:
    base = str(source or "").strip()
    if not base:
        base = "unknown"
    detail_value = str(detail or "").strip()
    if detail_value:
        return f"{field}:{base}:{detail_value}"
    return f"{field}:{base}"


def _crm_add_field_provenance(
    provenance: Dict[str, List[str]],
    field: str,
    source: str,
    detail: Optional[str] = None,
) -> None:
    key = str(field or "").strip()
    if not key:
        return
    entry = _crm_field_provenance_entry(key, source, detail)
    values = list(provenance.get(key) or [])
    if entry not in values:
        values.append(entry)
    provenance[key] = values


def _crm_field_provenance_from_sources(
    *,
    sender_name_candidate: Optional[Dict[str, Any]],
    text_name_candidate: Optional[Dict[str, Any]],
    job_title: Optional[str],
    companies: List[str],
    phones: List[str],
    emails: List[str],
    city: Optional[str],
) -> Dict[str, List[str]]:
    provenance: Dict[str, List[str]] = {}
    if sender_name_candidate:
        _crm_add_field_provenance(provenance, "fio", "telegram.sender.name")
    if text_name_candidate:
        _crm_add_field_provenance(provenance, "fio", "telegram.message.text")
    if job_title:
        _crm_add_field_provenance(provenance, "job_title", "telegram.message.text")
    if companies:
        _crm_add_field_provenance(provenance, "company", "telegram.message.text")
    if phones:
        _crm_add_field_provenance(provenance, "phone", "telegram.message.text")
    if emails:
        _crm_add_field_provenance(provenance, "email", "telegram.message.text")
    if city:
        _crm_add_field_provenance(provenance, "city", "telegram.message.text")
    return provenance


def _event_row_key(row: Dict[str, Any]) -> str:
    return f"{row.get('lead') or ''}:{int(row.get('message_id') or 0)}"


def _merge_event_date_fields(row: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(previous, dict):
        return row
    for field in ("event_date", "event_date_confidence", "event_date_source"):
        value = previous.get(field)
        if value not in (None, "") and row.get(field) in (None, ""):
            row[field] = value
    return row


def _contacts_row_key(row: Dict[str, Any]) -> str:
    return str(row.get("contact_key") or "")


def _contacts_compact_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _contacts_display_name(sender_name: Optional[str], sender_username: Optional[str], sender_id: Optional[int]) -> str:
    if _contacts_compact_text(sender_name):
        return _contacts_compact_text(sender_name)
    if _contacts_compact_text(sender_username):
        return f"@{_contacts_compact_text(sender_username).lstrip('@')}"
    if sender_id is not None:
        return f"id:{sender_id}"
    return "Неизвестный контакт"


def _contacts_contact_key(sender_id: Optional[int], sender_username: Optional[str], sender_name: Optional[str]) -> Optional[str]:
    if sender_id is not None:
        return f"id:{int(sender_id)}"
    username = _contacts_compact_text(sender_username).lstrip("@").lower()
    if username:
        return f"username:{username}"
    name = _contacts_compact_text(sender_name).lower()
    if name:
        return f"name:{name}"
    return None


def _contacts_extract_message_from_record(
    lead_name: str,
    source_selector: Optional[str],
    rec: Dict[str, Any],
) -> Optional[TelegramContactMessageDTO]:
    msg = rec.get("message", {})
    sender = rec.get("sender", {})
    message_id = int(msg.get("id") or 0)
    date_utc = str(msg.get("date_utc") or "").strip()
    if message_id <= 0 or not date_utc:
        return None
    sender_id_raw = sender.get("id")
    try:
        sender_id = int(sender_id_raw) if sender_id_raw is not None else None
    except Exception:
        sender_id = None
    sender_username = _contacts_compact_text(sender.get("username")) or None
    sender_name = _contacts_compact_text(sender.get("name")) or None
    contact_key = _contacts_contact_key(sender_id, sender_username, sender_name)
    if not contact_key:
        return None
    return TelegramContactMessageDTO(
        lead=lead_name,
        source_selector=source_selector,
        message_id=message_id,
        date_utc=date_utc,
        text=str(msg.get("text") or ""),
        sender_id=sender_id,
        sender_username=sender_username,
        sender_name=sender_name,
        has_media=bool(msg.get("has_media")),
    )


def _contacts_messages_cache_path() -> Path:
    _ensure_cache_dir_exists()
    return CACHE_DIR / "contacts_messages.jsonl"


def _iter_contact_message_cache(contact_key: Optional[str] = None):
    path = _contacts_messages_cache_path()
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            try:
                row = json.loads(line)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if contact_key and str(row.get("contact_key") or "") != contact_key:
                continue
            yield row


def _contacts_load_summary_rows() -> Dict[str, Dict[str, Any]]:
    contacts_by_key: Dict[str, Dict[str, Any]] = {}
    for row in _load_analysis_cache_rows("contacts"):
        if not isinstance(row, dict):
            continue
        contact_key = _contacts_row_key(row)
        if not contact_key:
            continue
        contact = dict(row)
        contact["related_messages"] = []
        contact.setdefault("leads", [])
        contact.setdefault("source_selectors", [])
        contacts_by_key[contact_key] = contact
    return contacts_by_key


def _contacts_update_summary(contacts_by_key: Dict[str, Dict[str, Any]], message: TelegramContactMessageDTO) -> None:
    row = message.dict()
    contact_key = _contacts_contact_key(row.get("sender_id"), row.get("sender_username"), row.get("sender_name"))
    if not contact_key:
        return
    contact = contacts_by_key.get(contact_key)
    if not isinstance(contact, dict):
        contact = TelegramContactDTO(
            contact_key=contact_key,
            sender_id=row.get("sender_id"),
            sender_username=row.get("sender_username"),
            sender_name=row.get("sender_name"),
            display_name=_contacts_display_name(row.get("sender_name"), row.get("sender_username"), row.get("sender_id")),
            related_messages=[],
        ).dict()
        contacts_by_key[contact_key] = contact

    if not contact.get("sender_name") and row.get("sender_name"):
        contact["sender_name"] = row.get("sender_name")
    if not contact.get("sender_username") and row.get("sender_username"):
        contact["sender_username"] = row.get("sender_username")
    if contact.get("sender_id") is None and row.get("sender_id") is not None:
        contact["sender_id"] = row.get("sender_id")

    contact["display_name"] = _contacts_display_name(
        contact.get("sender_name"),
        contact.get("sender_username"),
        contact.get("sender_id"),
    )
    contact["total_messages"] = int(contact.get("total_messages") or 0) + 1
    contact["related_messages_count"] = int(contact.get("related_messages_count") or 0) + 1

    lead = str(row.get("lead") or "")
    source_selector = str(row.get("source_selector") or "")
    leads = set(str(item) for item in contact.get("leads") or [] if str(item))
    selectors = set(str(item) for item in contact.get("source_selectors") or [] if str(item))
    if lead:
        leads.add(lead)
    if source_selector:
        selectors.add(source_selector)
    contact["leads"] = sorted(leads)
    contact["source_selectors"] = sorted(selectors)

    date_utc = str(row.get("date_utc") or "")
    if date_utc:
        first_message_at = str(contact.get("first_message_at") or "")
        last_message_at = str(contact.get("last_message_at") or "")
        if not first_message_at or date_utc < first_message_at:
            contact["first_message_at"] = date_utc
        if not last_message_at or date_utc >= last_message_at:
            contact["last_message_at"] = date_utc
            contact["latest_lead"] = lead or contact.get("latest_lead")
            latest_text = str(row.get("text") or "").strip()
            contact["latest_message_text"] = latest_text or None
            contact["latest_message_preview"] = _contacts_compact_text(latest_text)[:280] or None


def _duckdb_contacts_ready() -> bool:
    status = _duckdb_status_snapshot()
    return bool(duckdb is not None and status.get("cache_ready") and DUCKDB_PATH.exists())


def _duckdb_source_jsonl_to_lead_name(source_jsonl: str) -> str:
    try:
        return Path(str(source_jsonl or "")).stem
    except Exception:
        return str(source_jsonl or "")


def _duckdb_contact_key_sql() -> str:
    return """
        CASE
            WHEN sender_id IS NOT NULL THEN 'id:' || CAST(sender_id AS VARCHAR)
            WHEN sender_username IS NOT NULL AND trim(sender_username) <> '' THEN 'username:' || lower(trim(sender_username))
            WHEN sender_name IS NOT NULL AND trim(sender_name) <> '' THEN 'name:' || lower(trim(sender_name))
            ELSE NULL
        END
    """






def _duckdb_crm_ready() -> bool:
    if not _duckdb_contacts_ready():
        return False
    crm_state = _analysis_state("crm")
    if crm_state.get("duckdb_ready"):
        return True
    try:
        conn = _duckdb_connect_readonly()
        try:
            row = conn.execute("SELECT COUNT(*) FROM crm_contacts").fetchone()
            return bool(int(row[0] or 0) > 0)
        finally:
            conn.close()
    except Exception:
        return False


def _duckdb_events_ready() -> bool:
    if not _duckdb_contacts_ready():
        return False
    events_state = _analysis_state("events")
    if events_state.get("duckdb_ready"):
        return True
    try:
        conn = _duckdb_connect_readonly()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM event_messages WHERE keyword_hash = ?",
                [_keywords_hash(_get_event_keywords())],
            ).fetchone()
            return bool(int(row[0] or 0) > 0)
        finally:
            conn.close()
    except Exception:
        return False


def _duckdb_iter_messages_raw_for_crm():
    if not _duckdb_contacts_ready():
        return
    conn = _duckdb_connect_readonly()
    try:
        rows = conn.execute(
            """
            SELECT source_jsonl, message_id, date_utc_raw, text, sender_username, sender_name
            FROM messages_raw
            ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
            """
        ).fetchall()
    finally:
        conn.close()
    selector_map = _managed_selector_map()
    for row in rows:
        lead_name = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
        yield {
            "lead": lead_name,
            "source_selector": selector_map.get(str(lead_name).lower()),
            "record": {
                "sender": {
                    "username": str(row[4] or "") or None,
                    "name": str(row[5] or "") or None,
                },
                "message": {
                    "id": int(row[1] or 0),
                    "date_utc": str(row[2] or ""),
                    "text": str(row[3] or ""),
                },
            },
        }


def _duckdb_crm_row_payload(row: CrmContactDTO, row_key: Optional[str] = None) -> tuple[Any, ...]:
    data = row.model_dump()
    return (
        row_key or _crm_row_key(data),
        row.lead,
        row.source_selector,
        int(row.message_id or 0),
        row.date_utc,
        row.text,
        row.sender_username,
        row.sender_name,
        row.full_name,
        row.first_name,
        row.last_name,
        row.patronymic,
        int(row.name_components_count or 0),
        row.job_title,
        json.dumps(row.companies, ensure_ascii=False),
        json.dumps(row.phones, ensure_ascii=False),
        json.dumps(row.emails, ensure_ascii=False),
        row.city,
        json.dumps(row.match_sources, ensure_ascii=False),
        json.dumps(row.field_provenance, ensure_ascii=False),
        _utc_now(),
    )


def _duckdb_rebuild_crm_contacts_sync() -> List[Dict[str, Any]]:
    if not _duckdb_contacts_ready():
        return []
    _duckdb_init_schema_sync()
    raw_items = list(_duckdb_iter_messages_raw_for_crm() or [])
    rows: List[Dict[str, Any]] = []
    batches: List[List[tuple[Any, ...]]] = []
    batch: List[tuple[Any, ...]] = []
    for item in raw_items:
        lead_name = str(item.get("lead") or "")
        source_selector = item.get("source_selector")
        rec = item.get("record") if isinstance(item.get("record"), dict) else {}
        crm_row = _crm_extract_contact_from_record(lead_name, source_selector, rec)
        if not crm_row:
            continue
        batch.append(_duckdb_crm_row_payload(crm_row))
        rows.append(crm_row.model_dump())
        if len(batch) >= 1000:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)

    conn = _duckdb_connect()
    try:
        conn.execute(
            """
            DELETE FROM crm_contacts
            WHERE lower(coalesce(match_sources_json, '')) NOT LIKE '%"media"%'
            """
        )
        for batch in batches:
            conn.executemany(
                """
                INSERT OR REPLACE INTO crm_contacts (
                    row_key, lead, source_selector, message_id, date_utc_raw, text,
                    sender_username, sender_name, full_name, first_name, last_name, patronymic,
                    name_components_count, job_title, companies_json, phones_json, emails_json,
                    city, match_sources_json, field_provenance_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
    finally:
        conn.close()
    rows.sort(key=lambda item: (str(item.get("date_utc") or ""), int(item.get("message_id") or 0)), reverse=True)
    return rows


def _cleanup_crm_telemost_false_phones_sync() -> Dict[str, Any]:
    if duckdb is None or not DUCKDB_PATH.exists():
        return {"checked": 0, "changed": 0, "examples": []}

    conn = _duckdb_connect()
    try:
        try:
            raw_rows = conn.execute(
                """
                SELECT lead, message_id, date_utc_raw, text, phones_json, match_sources_json
                FROM crm_contacts
                WHERE lower(coalesce(text, '')) LIKE '%telemost.yandex.%'
                  AND coalesce(phones_json, '[]') <> '[]'
                """
            ).fetchall()
        except Exception:
            return {"checked": 0, "changed": 0, "examples": []}

        changed = 0
        examples: List[Dict[str, Any]] = []
        for lead, message_id, date_utc, text, phones_json, match_sources_json in raw_rows:
            phones = list(json.loads(str(phones_json or "[]")))
            clean_phones = _crm_filter_phones_for_text(phones, text)
            if clean_phones == phones:
                continue
            match_sources = list(json.loads(str(match_sources_json or "[]")))
            if not clean_phones:
                match_sources = [source for source in match_sources if source != "phone"]
            conn.execute(
                """
                UPDATE crm_contacts
                SET phones_json = ?, match_sources_json = ?
                WHERE lead = ? AND message_id = ? AND date_utc_raw = ?
                """,
                [
                    json.dumps(clean_phones, ensure_ascii=False),
                    json.dumps(match_sources, ensure_ascii=False),
                    str(lead or ""),
                    int(message_id or 0),
                    str(date_utc or ""),
                ],
            )
            changed += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "lead": str(lead or ""),
                        "message_id": int(message_id or 0),
                        "before": phones,
                        "after": clean_phones,
                    }
                )
    finally:
        conn.close()

    return {"checked": len(raw_rows), "changed": changed, "examples": examples}






def _duckdb_search_available() -> bool:
    status = _duckdb_status_snapshot()
    return bool(duckdb is not None and status.get("cache_ready") and DUCKDB_PATH.exists())




def _duckdb_row_to_search_message(row: Any, selector_map: Dict[str, str]) -> Dict[str, Any]:
    lead_name = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
    phones = _crm_filter_phones_for_text(list(json.loads(str(row[12] or "[]"))), str(row[3] or ""))
    match_sources = list(json.loads(str(row[15] or "[]")))
    if not phones:
        match_sources = [source for source in match_sources if source != "phone"]
    return SearchMessageDTO(
        lead=lead_name,
        source_selector=selector_map.get(str(lead_name).lower()),
        message_id=int(row[1] or 0),
        date_utc=str(row[2] or ""),
        text=str(row[3] or ""),
        sender_username=str(row[4] or "") or None,
        sender_name=str(row[5] or "") or None,
        full_name=str(row[6] or "") or None,
        first_name=str(row[7] or "") or None,
        last_name=str(row[8] or "") or None,
        patronymic=str(row[9] or "") or None,
        job_title=str(row[10] or "") or None,
        companies=list(json.loads(str(row[11] or "[]"))),
        phones=phones,
        emails=list(json.loads(str(row[13] or "[]"))),
        city=str(row[14] or "") or None,
        match_sources=match_sources,
    ).model_dump()




def _build_search_context_blocks(items: List[Dict[str, Any]]) -> List[str]:
    blocks: List[str] = []
    for item in items:
        row = SearchMessageDTO(**item)
        meta: List[str] = [f"chat={row.lead}", f"date={row.date_utc}"]
        if row.sender_username:
            meta.append(f"username=@{row.sender_username.lstrip('@')}")
        if row.sender_name:
            meta.append(f"sender={row.sender_name}")
        if row.full_name:
            meta.append(f"full_name={row.full_name}")
        if row.job_title:
            meta.append(f"title={row.job_title}")
        if row.companies:
            meta.append(f"companies={', '.join(row.companies)}")
        if row.phones:
            meta.append(f"phones={', '.join(row.phones)}")
        if row.emails:
            meta.append(f"emails={', '.join(row.emails)}")
        if row.city:
            meta.append(f"city={row.city}")
        blocks.append(f"[{'; '.join(meta)}]\n{row.text}")
    return blocks










def _source_selectors_as_strings() -> List[str]:
    from app.services.telegram_sources_runtime import _load_source_selectors_for_ui

    result: List[str] = []
    for item in _load_source_selectors_for_ui():
        result.append(str(item))
    return result


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
    "time",
    "uuid",
    "datetime",
    "timedelta",
    "timezone",
    "wraps",
    "Path",
    "Any",
    "Dict",
    "List",
    "Literal",
    "Optional",
    "Set",
    "Union",
    "requests",
    "HTTPException",
    "_with_legacy_globals",
    "_XFILES_CONTACT_TOPIC_KEYWORDS",
    "_XFILES_CONTACT_PAIN_KEYWORDS",
    "_XFILES_BUYING_SIGNAL_KEYWORDS",
    "_XFILES_OBJECTION_KEYWORDS",
    "_XFILES_ABILITY_KEYWORDS",
    "_xfiles_keyword_hits",
    "_xfiles_product_hint_from_catalog",
    "_XFILES_LEAD_TEMPERATURE_LABELS",
    "_xfiles_contact_temperature",
    "_xfiles_score_explanation",
    "_xfiles_why_now",
    "_xfiles_apply_contact_signal_summary",
    "_xfiles_assistant_short_text",
    "_xfiles_deal_assistant_messages",
    "_xfiles_objection_reply",
    "_xfiles_contract_metrics_sync",
    "_xfiles_contract_templates",
    "_xfiles_contract_templates_page_sync",
    "_xfiles_deal_contract_kit_sync",
    "_xfiles_deal_negotiation_brief_sync",
    "_xfiles_contracts_state",
    "_xfiles_contract_status_for_deal",
    "_xfiles_set_contract_status",
    "_xfiles_has_email",
    "_xfiles_has_inn",
    "_xfiles_has_signer_role",
    "_xfiles_has_deadline",
    "_xfiles_jur_matches_for_deal",
    "_xfiles_contract_checklist",
    "_xfiles_contract_missing_fields",
    "_xfiles_deal_price_text",
    "_xfiles_short_proposal",
    "_xfiles_proposal_document",
    "_xfiles_contract_duration_metrics",
    "_xfiles_event_date_from_row",
    "_xfiles_event_topic",
    "_xfiles_event_contact_key",
    "_xfiles_event_sales_windows",
    "_xfiles_pick_next_event_window",
    "_xfiles_event_product_offer",
    "_XFILES_NEED_SIGNAL_DEFINITIONS",
    "_XFILES_NEED_SOURCE_LABELS",
    "_xfiles_need_search_keywords",
    "_xfiles_need_detect_tags",
    "_xfiles_need_pick_sentence",
    "_xfiles_need_extract_budget",
    "_xfiles_need_extract_deadline",
    "_xfiles_need_source_label",
    "_xfiles_need_first_touch",
    "_xfiles_need_probability",
    "_xfiles_need_estimated_value_from_budget",
    "_xfiles_need_deal_payload",
    "_xfiles_need_is_strong_enough_for_auto_deal",
    "_xfiles_auto_create_need_deal_drafts",
    "_xfiles_need_signal_id",
    "_xfiles_need_signals_from_duckdb",
    "_xfiles_need_signals_from_enreach",
    "_xfiles_deal_from_outreach_item",
    "_expand_existing_outreach_values_sync",
    "_filter_telegram_contacts",
    "_contact_source_rows_for_filters",
    "_build_contact_chat_filter_options",
    "_filter_telegram_contact_messages",
    "CONTACT_QUALIFICATIONS_STATE_KEY",
    "CONTACT_EXCLUSIONS_STATE_KEY",
    "_contact_qualifications_state",
    "_contact_exclusions_state",
    "_contact_do_not_contact_summary",
    "_set_contact_do_not_contact",
    "_contact_qualification_summary",
    "_decorate_contact_summary_with_qualifications",
    "_filter_telegram_contacts_by_qualification",
    "_filter_telegram_contacts_by_temperature",
    "_CONTACT_SIGNAL_FILTER_ALIASES",
    "_CONTACT_SIGNAL_LABELS",
    "_contact_signal_filter_values",
    "_contact_signal_text",
    "_contact_signal_flags",
    "_decorate_contact_summary_with_signals",
    "_contact_key_strategy",
    "_decorate_contact_summary_with_provenance",
    "_filter_telegram_contacts_by_signals",
    "_contact_messages_for_qualification",
    "_build_contact_qualification_context",
    "_contact_messages_fingerprint",
    "_contact_latest_message_at",
    "_stable_json_hash",
    "_estimate_llm_tokens",
    "_openrouter_payload_prompt_text",
    "_estimate_openrouter_cost_usd",
    "_openrouter_usage_estimate",
    "_xfiles_llm_audit_items",
    "_xfiles_llm_audit_summary",
    "_openrouter_headers",
    "_LLM_TRANSIENT_STATUS_CODES",
    "_post_json_with_transient_retries",
    "_sanitize_openrouter_payload_for_pii",
    "_sync_legacy_payme_outputs",
    "_normalize_source_selector",
    "_selector_identity",
    "DEFAULT_EVENT_KEYWORDS",
    "_normalize_event_keywords",
    "_get_event_keywords_state",
    "_get_known_selectors_state",
    "_remember_selector",
    "_import_dialog_settings_state",
    "_effective_import_limits_for_selector",
    "_set_import_limits_for_selector",
    "_enable_unlimited_import_for_all_selected_sources",
    "_apply_import_limits_for_all_selected_sources",
    "_source_identity_candidates",
    "_source_row_matches_identities",
    "_purge_analysis_cache_for_source",
    "_purge_contacts_messages_cache_for_source",
    "_purge_outreach_fallback_for_source",
    "_duckdb_delete_source_rows",
    "_purge_source_files",
    "_purge_removed_source_data",
    "_normalize_event_delete_text",
    "_event_delete_key",
    "_event_row_delete_key",
    "_event_deleted_keys_state",
    "_event_row_is_deleted",
    "_filter_deleted_event_rows",
    "_delete_matching_event_rows_from_duckdb",
    "_delete_event_message",
    "_forget_selector",
    "_get_event_keywords",
    "_set_event_keywords",
    "_remove_import_sync_selector_by_identity",
    "_lead_related_stems",
    "_drop_lead_state",
    "_delete_lead_artifacts",
    "_match_event_keywords",
    "_normalize_llm_event_date",
    "_extract_json_object_from_text",
    "_routes_row_key",
    "_normalize_route_address",
    "_route_address_key",
    "_routes_cache_rows",
    "_save_routes_cache_rows",
    "_duckdb_load_moscow_route_rows",
    "_routes_address_directory",
    "_routes_status_payload",
    "_schedule_routes_refresh",
    "_openrouter_event_date_message_days",
    "_event_date_message_cutoff",
    "_parse_event_message_dt",
    "_event_date_message_in_window",
    "_event_date_needs_extraction",
    "_event_date_count_rows_from_cache",
    "_event_date_needs_text",
    "_event_date_count_rows_sync",
    "_event_date_pending_rows_sync",
    "_event_date_status_snapshot",
    "_update_event_date_result_sync",
    "_enrich_event_dates_sync",
    "_event_date_extraction_async",
    "_schedule_event_date_extraction",
    "_schedule_event_date_pending_batch",
    "_collect_event_messages",
    "_crm_row_key",
    "_crm_field_provenance_entry",
    "_crm_add_field_provenance",
    "_crm_field_provenance_from_sources",
    "_event_row_key",
    "_merge_event_date_fields",
    "_contacts_row_key",
    "_contacts_compact_text",
    "_contacts_display_name",
    "_contacts_contact_key",
    "_contacts_extract_message_from_record",
    "_contacts_messages_cache_path",
    "_iter_contact_message_cache",
    "_contacts_load_summary_rows",
    "_contacts_update_summary",
    "_duckdb_contacts_ready",
    "_duckdb_source_jsonl_to_lead_name",
    "_duckdb_contact_key_sql",
    "_duckdb_crm_ready",
    "_duckdb_events_ready",
    "_duckdb_iter_messages_raw_for_crm",
    "_duckdb_crm_row_payload",
    "_duckdb_rebuild_crm_contacts_sync",
    "_cleanup_crm_telemost_false_phones_sync",
    "_duckdb_search_available",
    "_duckdb_row_to_search_message",
    "_build_search_context_blocks",
    "_source_selectors_as_strings",
)
