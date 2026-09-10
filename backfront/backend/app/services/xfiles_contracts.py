"""X-Files contract helpers extracted from the legacy backend."""

from __future__ import annotations

import sys


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime")
    legacy_back = sys.modules.get("back")
    for source in (runtime, legacy_back):
        if source is None:
            continue
        for name, value in vars(source).items():
            if not name.startswith("__") and name != "refresh_legacy_globals":
                globals()[name] = value


refresh_legacy_globals()

def _xfiles_deal_negotiation_brief_sync(deal_id: str) -> XFilesNegotiationBriefDTO:
    deal = _xfiles_get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    assistant = _xfiles_deal_assistant_sync(deal_id)
    first_question = assistant.qualification_questions[0] if assistant.qualification_questions else "уточнить критерий успеха"
    first_reply = assistant.objections[0].get("reply", "") if assistant.objections else ""
    product = _xfiles_assistant_short_text(deal.product_match or assistant.can_buy, 220) or "короткий пилот"
    strategy = [
        "Начать с контекста контакта, а не с презентации продукта.",
        f"Проверить главный критерий покупки: {first_question}",
        f"Упаковать предложение как маленький безопасный шаг: {product}.",
        "Закрыть разговор конкретным next action, датой и ответственным.",
    ]
    if first_reply:
        strategy.append(f"Если появится возражение, отвечать коротко: {first_reply}")
    return XFilesNegotiationBriefDTO(
        deal_id=deal.id,
        generated_at=_utc_now().isoformat(),
        title=deal.title,
        stage=deal.stage,
        recommended_score=assistant.recommended_score,
        source_messages=assistant.source_messages,
        brief=assistant.five_minute_brief,
        strategy=strategy,
        next_best_message=assistant.next_best_message,
        objection_replies=assistant.objections,
        qualification_questions=assistant.qualification_questions,
        call_agenda=assistant.call_agenda,
        do_not_write=assistant.do_not_write,
    )


def _xfiles_contract_templates() -> List[XFilesContractTemplateDTO]:
    # These are intentionally deterministic defaults: the user can close a deal
    # even when no external document generator is configured yet.
    defaults = [
        {
            "id": "proposal_one_screen",
            "kind": "proposal",
            "title": "КП в 1 экран",
            "description": "Короткое предложение: контекст, решение, результат, цена и следующий шаг.",
            "body": "Контекст → Решение → Ожидаемый результат → Стоимость → Следующий шаг",
        },
        {
            "id": "contract_service",
            "kind": "contract",
            "title": "Договор оказания услуг",
            "description": "Базовый договор для пилота, внедрения или консультационного проекта.",
            "body": "Стороны, предмет, сроки, стоимость, порядок оплаты, приёмка, конфиденциальность.",
        },
        {
            "id": "invoice_basic",
            "kind": "invoice",
            "title": "Счёт",
            "description": "Минимальный счёт на оплату после согласования КП.",
            "body": "Получатель, плательщик, основание, сумма, НДС/без НДС, срок оплаты.",
        },
        {
            "id": "appendix_scope",
            "kind": "appendix",
            "title": "Приложение с объёмом работ",
            "description": "Фиксирует deliverables, критерии готовности и границы работ.",
            "body": "Цели, работы, исключения, сроки, формат результата, ответственные.",
        },
        {
            "id": "nda_simple",
            "kind": "nda",
            "title": "NDA",
            "description": "Короткое соглашение о конфиденциальности для обмена чувствительными данными.",
            "body": "Конфиденциальная информация, срок, ограничения раскрытия, ответственность.",
        },
    ]
    state = _xfiles_contracts_state()
    templates = state.get("templates")
    if not isinstance(templates, list) or not templates:
        templates = defaults
        state["templates"] = templates
        telegram_sync.save_state()
    result: List[XFilesContractTemplateDTO] = []
    for raw in templates:
        if not isinstance(raw, dict):
            continue
        try:
            result.append(XFilesContractTemplateDTO(**raw))
        except Exception:
            continue
    return result or [XFilesContractTemplateDTO(**row) for row in defaults]


def _xfiles_contract_templates_page_sync() -> XFilesContractTemplatesPageDTO:
    items = _xfiles_contract_templates()
    return XFilesContractTemplatesPageDTO(
        items=items,
        total=len(items),
        generated_at=_utc_now().isoformat(),
    )


def _xfiles_contract_metrics_sync() -> XFilesContractMetricsDTO:
    deals = _xfiles_load_deals(limit=20000)
    statuses: Dict[str, int] = {
        "needs_data": 0,
        "proposal_ready": 0,
        "sent": 0,
        "negotiation": 0,
        "signed": 0,
        "paid": 0,
    }
    missing_counts: Dict[str, int] = {}
    for deal in deals:
        jur_matches = _xfiles_jur_matches_for_deal(deal, limit=3)
        checklist = _xfiles_contract_checklist(deal, jur_matches)
        missing_fields = _xfiles_contract_missing_fields(checklist)
        status = _xfiles_contract_status_for_deal(deal, missing_fields)
        statuses[status] = int(statuses.get(status, 0)) + 1
        for field in missing_fields:
            missing_counts[field] = int(missing_counts.get(field, 0)) + 1
    missing_fields_top = [
        {"field": field, "count": count}
        for field, count in sorted(missing_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    ready_to_send = int(statuses.get("proposal_ready", 0) + statuses.get("sent", 0) + statuses.get("negotiation", 0))
    signed_or_paid = int(statuses.get("signed", 0) + statuses.get("paid", 0))
    return XFilesContractMetricsDTO(
        generated_at=_utc_now().isoformat(),
        deals_total=len(deals),
        statuses=statuses,
        missing_fields_top=missing_fields_top,
        duration_metrics=_xfiles_contract_duration_metrics(),
        ready_to_send=ready_to_send,
        signed_or_paid=signed_or_paid,
        message="Contract metrics показывают готовность КП/договора, узкие места по данным и скорость переходов между этапами.",
    )


def _xfiles_deal_contract_kit_sync(deal_id: str) -> XFilesDealContractKitDTO:
    deal = _xfiles_get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
    jur_matches = _xfiles_jur_matches_for_deal(deal)
    checklist = _xfiles_contract_checklist(deal, jur_matches)
    missing_fields = _xfiles_contract_missing_fields(checklist)
    status = _xfiles_contract_status_for_deal(deal, missing_fields)
    return XFilesDealContractKitDTO(
        deal_id=deal.id,
        generated_at=_utc_now().isoformat(),
        contract_status=status,
        short_proposal=_xfiles_short_proposal(deal, missing_fields),
        proposal_document=_xfiles_proposal_document(deal, checklist, jur_matches),
        checklist=checklist,
        missing_fields=missing_fields,
        templates=_xfiles_contract_templates(),
        jur_matches=jur_matches,
        metrics=_xfiles_contract_duration_metrics(),
    )


__all__ = [
    "refresh_legacy_globals",
    "_xfiles_contract_metrics_sync",
    "_xfiles_contract_templates",
    "_xfiles_contract_templates_page_sync",
    "_xfiles_deal_contract_kit_sync",
    "_xfiles_deal_negotiation_brief_sync",
]
