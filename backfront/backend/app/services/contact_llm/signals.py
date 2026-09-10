"""Contact signal constants and pure scoring helpers."""

from __future__ import annotations

from typing import Any, Dict, List


_XFILES_CONTACT_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "продажи/лиды": ["продаж", "лид", "клиент", "воронк", "outreach", "crm", "заявк"],
    "AI/автоматизация": ["ai", "ии", "llm", "gpt", "бот", "автоматизац", "интеграц", "нейро"],
    "финансы/инвестиции": ["финанс", "инвест", "мсфо", "налог", "бюджет", "выручк", "маржин"],
    "мероприятия/нетворк": ["мероприят", "вебинар", "конференц", "митап", "нетворк", "встреч"],
    "найм/команда": ["ваканс", "наним", "команд", "резюме", "сотрудник", "hr"],
}
_XFILES_CONTACT_PAIN_KEYWORDS: Dict[str, List[str]] = {
    "ручной труд/время": ["вручную", "долго", "времени", "устал", "рутин", "не успева"],
    "ищет решение/подрядчика": ["нужен", "ищу", "кто может", "порекомендуйте", "подрядчик", "сервис"],
    "стоимость/бюджет": ["бюджет", "цена", "дорого", "оплат", "руб", "стоимость"],
    "сложно внедрять": ["сложно", "проблем", "не работает", "ошибк", "завис", "непонятно"],
}
_XFILES_BUYING_SIGNAL_KEYWORDS = [
    "ищу",
    "нужен",
    "нужно",
    "надо",
    "купить",
    "заказать",
    "порекомендуйте",
    "кто может",
    "сколько стоит",
    "бюджет",
    "срочно",
    "подрядчик",
    "решение",
]
_XFILES_OBJECTION_KEYWORDS = [
    "дорого",
    "нет бюджета",
    "не готов",
    "позже",
    "сомневаюсь",
    "не понимаю",
    "не подходит",
]
_XFILES_ABILITY_KEYWORDS = [
    "директор",
    "основатель",
    "ceo",
    "cfo",
    "owner",
    "продюсер",
    "маркетолог",
    "руководитель",
    "бизнес",
    "компания",
    "выручка",
    "бюджет",
    "инвест",
    "договор",
]
_XFILES_LEAD_TEMPERATURE_LABELS = {
    "hot": "Горячий",
    "warm": "Тёплый",
    "cold": "Холодный",
    "not_fit": "Не подходит",
    "needs_data": "Нужно больше данных",
}


def _xfiles_keyword_hits(text: str, keywords: List[str]) -> List[str]:
    normalized = str(text or "").lower()
    hits: List[str] = []
    for keyword in keywords:
        raw = str(keyword or "").strip().lower()
        if raw and raw in normalized and raw not in hits:
            hits.append(raw)
    return hits


def _xfiles_contact_temperature(
    profile: Dict[str, Any],
    total_messages: int = 0,
    qualification_count: int = 0,
) -> Dict[str, str]:
    score = int(profile.get("deal_score") or 0)
    intent = int(profile.get("intent_score") or 0)
    fit = int(profile.get("fit_score") or 0)
    ability = int(profile.get("ability_to_pay_score") or 0)
    topics = profile.get("topics") or []
    buying_signals = profile.get("buying_signals") or []
    missing = str(profile.get("missing_qualification") or "")
    if total_messages < 3 and not topics and not buying_signals and qualification_count <= 0:
        key = "needs_data"
    elif "явный buying intent" in missing and qualification_count <= 0 and not buying_signals:
        key = "needs_data"
    elif fit < 28 or (score < 25 and intent < 30 and ability < 30):
        key = "not_fit"
    elif score >= 70 and intent >= 50:
        key = "hot"
    elif score >= 45:
        key = "warm"
    else:
        key = "cold"
    return {"key": key, "label": _XFILES_LEAD_TEMPERATURE_LABELS.get(key, key)}


def _xfiles_score_explanation(profile: Dict[str, Any], temperature: Dict[str, str]) -> str:
    score = int(profile.get("deal_score") or 0)
    fit = int(profile.get("fit_score") or 0)
    intent = int(profile.get("intent_score") or 0)
    urgency = int(profile.get("urgency_score") or 0)
    ability = int(profile.get("ability_to_pay_score") or 0)
    strongest = max(
        [("fit", fit), ("intent", intent), ("urgency", urgency), ("ability-to-pay", ability)],
        key=lambda item: item[1],
    )
    weakest = min(
        [("fit", fit), ("intent", intent), ("urgency", urgency), ("ability-to-pay", ability)],
        key=lambda item: item[1],
    )
    return (
        f"{temperature.get('label') or 'Лид'}: {score}/100. "
        f"Сильнее всего: {strongest[0]} {strongest[1]}/100; "
        f"слабее всего: {weakest[0]} {weakest[1]}/100. "
        f"Разбивка: fit {fit}, intent {intent}, urgency {urgency}, pay {ability}."
    )


__all__ = [
    "_XFILES_CONTACT_TOPIC_KEYWORDS",
    "_XFILES_CONTACT_PAIN_KEYWORDS",
    "_XFILES_BUYING_SIGNAL_KEYWORDS",
    "_XFILES_OBJECTION_KEYWORDS",
    "_XFILES_ABILITY_KEYWORDS",
    "_XFILES_LEAD_TEMPERATURE_LABELS",
    "_xfiles_keyword_hits",
    "_xfiles_contact_temperature",
    "_xfiles_score_explanation",
]
