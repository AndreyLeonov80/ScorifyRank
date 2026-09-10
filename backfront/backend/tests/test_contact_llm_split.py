from __future__ import annotations

from app.services import contact_llm_runtime
from app.services.contact_llm import signals


def test_contact_signal_helpers_are_split_and_reexported() -> None:
    assert contact_llm_runtime._XFILES_BUYING_SIGNAL_KEYWORDS is signals._XFILES_BUYING_SIGNAL_KEYWORDS
    assert contact_llm_runtime._xfiles_keyword_hits("Нужен подрядчик", ["нужен", "нет"]) == ["нужен"]
    temperature = contact_llm_runtime._xfiles_contact_temperature(
        {"deal_score": 80, "intent_score": 60, "fit_score": 70, "ability_to_pay_score": 55},
        total_messages=10,
    )
    assert temperature["key"] == "hot"
    assert "80/100" in contact_llm_runtime._xfiles_score_explanation(
        {"deal_score": 80, "intent_score": 60, "fit_score": 70, "urgency_score": 40, "ability_to_pay_score": 55},
        temperature,
    )
