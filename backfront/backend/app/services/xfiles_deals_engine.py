"""X-Files deal calculation helpers extracted from the legacy backend."""

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

from app.services.deals_helpers.audit import estimate_llm_cost_metrics
from app.services.deals_helpers.builders import build_daily_plan_bucket, build_plan_item
from app.services.deals_helpers.repository import load_deal_items, postgres_status_message, postgres_waiting
from app.services.deals_helpers.scoring import deal_attention_hours, deal_priority, deal_profit, deal_profit_per_hour, epoch_utc

_POSTGRES_WAITING_CONTRACT_MESSAGE = "PostgreSQL подключается или временно недоступен"

def _xfiles_deals_status_sync() -> XFilesDealsStatusDTO:
    items = load_deal_items(_xfiles_load_deals, limit=20000)
    active_stages = {"idea", "lead", "qualified", "proposal", "negotiation", "contract"}
    qualified_stages = {"qualified", "proposal", "negotiation", "contract", "won"}
    now = _utc_now()
    day_cutoff = now - timedelta(days=1)
    active_items = [item for item in items if item.stage in active_stages]
    expected_value = round(sum(float(item.expected_value or 0.0) for item in items), 2)
    expected_profit = round(sum(float(item.expected_profit or 0.0) for item in items), 2)
    pipeline_value = round(sum(float(item.expected_value or 0.0) for item in active_items), 2)
    pipeline_profit = round(sum(float(item.expected_profit or 0.0) for item in active_items), 2)
    average_margin = round(
        sum(float(item.margin or 1.0) for item in active_items) / len(active_items),
        4,
    ) if active_items else 1.0
    margin_products = len(_xfiles_load_product_margins())
    sla_green = sum(1 for item in items if item.sla_status == "green")
    sla_yellow = sum(1 for item in items if item.sla_status == "yellow")
    sla_red = sum(1 for item in items if item.sla_status == "red")
    qualified_active = sum(1 for item in active_items if item.stage in qualified_stages)
    next_action_ready = sum(1 for item in active_items if str(item.next_action or "").strip())
    next_action_missing = max(0, len(active_items) - next_action_ready)
    new_signals_today = 0
    qualified_leads_today = 0
    next_action_minutes: List[float] = []
    attention_minutes = 0.0
    for item in active_items:
        created_dt = _xfiles_parse_optional_dt(item.created_at)
        updated_dt = _xfiles_parse_optional_dt(item.updated_at)
        fresh_dt = updated_dt or created_dt
        if created_dt and created_dt >= day_cutoff:
            new_signals_today += 1
        if item.stage in qualified_stages and fresh_dt and fresh_dt >= day_cutoff:
            qualified_leads_today += 1
        if item.next_action and created_dt and updated_dt and updated_dt >= created_dt:
            next_action_minutes.append(min(30 * 24 * 60, (updated_dt - created_dt).total_seconds() / 60.0))
        if item.sla_status == "red":
            attention_minutes += 8.0
        elif item.sla_status == "yellow":
            attention_minutes += 5.0
        else:
            attention_minutes += 3.0
    attention_minutes += next_action_missing * 6.0
    pipeline_attention_hours = round(attention_minutes / 60.0, 2) if active_items else 0.0
    pipeline_profit_per_attention_hour = (
        round(pipeline_profit / pipeline_attention_hours, 2)
        if pipeline_attention_hours > 0
        else 0.0
    )
    avg_time_to_next_action_minutes = (
        round(sum(next_action_minutes) / len(next_action_minutes), 1)
        if next_action_minutes
        else 0.0
    )
    stage_counts = {stage: 0 for stage in _XFILES_STAGE_ORDER}
    for item in items:
        stage_counts[item.stage] = stage_counts.get(item.stage, 0) + 1

    def stages_count(*stages: str) -> int:
        return int(sum(stage_counts.get(stage, 0) for stage in stages))

    funnel_defs = [
        ("signal", "Сигнал", len(items)),
        ("qualification", "Квалификация", stages_count("qualified", "proposal", "negotiation", "contract", "won")),
        ("message", "Сообщение", stages_count("proposal", "negotiation", "contract", "won")),
        ("response", "Ответ", stages_count("negotiation", "contract", "won")),
        ("meeting", "Встреча", stages_count("negotiation", "contract", "won")),
        ("proposal", "КП", stages_count("proposal", "negotiation", "contract", "won")),
        ("contract", "Договор", stages_count("contract", "won")),
        ("payment", "Оплата", stages_count("won")),
    ]
    conversion_funnel: List[XFilesFunnelStepDTO] = []
    previous_count: Optional[int] = None
    worst_drop_label: Optional[str] = None
    worst_drop_percent = 0.0
    for key, label, count in funnel_defs:
        if previous_count is None:
            conversion_percent = 100.0 if count > 0 else 0.0
        elif previous_count <= 0:
            conversion_percent = 0.0
        else:
            conversion_percent = round((count / previous_count) * 100.0, 1)
            drop_percent = 100.0 - conversion_percent
            if previous_count >= 5 and drop_percent > worst_drop_percent:
                worst_drop_percent = drop_percent
                worst_drop_label = label
        tone: Literal["green", "yellow", "red"]
        if key == "signal":
            tone = "green" if count > 0 else "yellow"
        elif conversion_percent >= 50:
            tone = "green"
        elif conversion_percent >= 20:
            tone = "yellow"
        else:
            tone = "red"
        conversion_funnel.append(
            XFilesFunnelStepDTO(
                key=key,
                label=label,
                count=int(count),
                conversion_percent=conversion_percent,
                tone=tone,
            )
        )
        previous_count = count

    qualified_count = stages_count("qualified", "proposal", "negotiation", "contract", "won")
    message_stage_count = stages_count("proposal", "negotiation", "contract", "won")
    response_stage_count = stages_count("negotiation", "contract", "won")
    reply_rate_percent = round((response_stage_count / message_stage_count) * 100.0, 1) if message_stage_count > 0 else 0.0
    lead_signals_per_hour = round(new_signals_today / 24.0, 2)
    qualifications_per_hour = round(qualified_leads_today / 24.0, 2)
    next_actions_per_hour = round(next_action_ready / 24.0, 2)
    meetings_per_week = stages_count("negotiation", "contract", "won")
    epoch = epoch_utc()

    def deal_dt(value: Any) -> datetime:
        parsed = _xfiles_parse_optional_dt(value)
        return parsed or epoch

    llm_audit_summary = _xfiles_llm_audit_summary()
    llm_costs = estimate_llm_cost_metrics(
        items_count=len(items),
        qualified_count=qualified_count,
        audit_summary=llm_audit_summary,
    )
    audited_llm_requests = int(llm_costs["audited_llm_requests"])
    estimated_llm_input_tokens = int(llm_costs["estimated_llm_input_tokens"])
    estimated_llm_output_tokens = int(llm_costs["estimated_llm_output_tokens"])
    openrouter_spend_usd = float(llm_costs["openrouter_spend_usd"])
    llm_cost_per_deal_usd = float(llm_costs["llm_cost_per_deal_usd"])
    cost_per_qualified_lead_usd = float(llm_costs["cost_per_qualified_lead_usd"])
    llm_cost_signal = str(llm_costs["llm_cost_signal"])
    source_buckets: Dict[str, Dict[str, Any]] = {}
    for item in items:
        source_key = str(item.source_chat or item.source or item.contact_key or "unknown").strip() or "unknown"
        bucket = source_buckets.setdefault(
            source_key,
            {
                "source": source_key,
                "total": 0,
                "active": 0,
                "qualified": 0,
                "won": 0,
                "expected_value": 0.0,
                "expected_profit": 0.0,
                "estimated_llm_cost_usd": 0.0,
                "score_sum": 0,
                "last_activity_at": None,
            },
        )
        bucket["total"] += 1
        if item.stage in active_stages:
            bucket["active"] += 1
        if item.stage in qualified_stages:
            bucket["qualified"] += 1
        if item.stage == "won":
            bucket["won"] += 1
        bucket["expected_value"] += float(item.expected_value or 0.0)
        bucket["expected_profit"] += float(item.expected_profit or 0.0)
        bucket["estimated_llm_cost_usd"] += llm_cost_per_deal_usd
        bucket["score_sum"] += int(item.score or 0)
        item_activity = item.updated_at or item.created_at
        if item_activity and (
            not bucket.get("last_activity_at")
            or deal_dt(item_activity) > deal_dt(bucket.get("last_activity_at"))
        ):
            bucket["last_activity_at"] = item_activity

    source_roi: List[Dict[str, Any]] = []
    source_group_recommendations: List[Dict[str, Any]] = []
    for source_key, bucket in source_buckets.items():
        total_source_deals = int(bucket.get("total") or 0)
        source_profit = round(float(bucket.get("expected_profit") or 0.0), 2)
        source_cost = round(float(bucket.get("estimated_llm_cost_usd") or 0.0), 4)
        source_qualified = int(bucket.get("qualified") or 0)
        source_cost_per_qualified = round(source_cost / max(1, source_qualified), 4)
        source_profit_per_cost = round(source_profit / source_cost, 2) if source_cost > 0 else 0.0
        avg_score = round(float(bucket.get("score_sum") or 0) / max(1, total_source_deals), 1)
        group_fields = _lead_scan_group_fields(source_key, source_key)
        current_group = str(group_fields.get("scan_group") or "C")
        current_group_label = str(group_fields.get("scan_group_label") or current_group)
        recommended_group = current_group
        recommendation = "watch"
        reason = "Нужно больше сделок для уверенной оценки источника."
        if source_qualified >= 2 and source_profit > 0 and avg_score >= 50:
            recommended_group = "A" if source_profit_per_cost >= 500 else "B"
            recommendation = "promote"
            reason = "Источник уже даёт квалифицированные сделки и положительный expected profit."
        elif total_source_deals >= 5 and source_qualified == 0 and source_profit <= 0:
            recommended_group = "D"
            recommendation = "deprioritize"
            reason = "Источник создаёт затраты на анализ, но пока не даёт квалифицированных сделок."
        elif total_source_deals >= 3 and source_cost_per_qualified >= 2.0 and source_profit <= 0:
            recommended_group = "C"
            recommendation = "slow_down"
            reason = "Стоимость квалификации выглядит высокой относительно результата."
        row = {
            "source": source_key,
            "current_group": current_group,
            "current_group_label": current_group_label,
            "recommended_group": recommended_group,
            "recommendation": recommendation,
            "reason": reason,
            "total_deals": total_source_deals,
            "active_deals": int(bucket.get("active") or 0),
            "qualified_deals": source_qualified,
            "won_deals": int(bucket.get("won") or 0),
            "expected_value": round(float(bucket.get("expected_value") or 0.0), 2),
            "expected_profit": source_profit,
            "estimated_llm_cost_usd": source_cost,
            "cost_per_qualified_lead_usd": source_cost_per_qualified,
            "profit_per_llm_dollar": source_profit_per_cost,
            "avg_score": avg_score,
            "last_activity_at": bucket.get("last_activity_at"),
        }
        source_roi.append(row)
        if recommendation in {"promote", "deprioritize", "slow_down"} and recommended_group != current_group:
            source_group_recommendations.append(row)
    source_roi.sort(
        key=lambda row: (
            float(row.get("expected_profit") or 0.0),
            int(row.get("qualified_deals") or 0),
            float(row.get("profit_per_llm_dollar") or 0.0),
        ),
        reverse=True,
    )
    source_group_recommendations.sort(
        key=lambda row: (
            0 if row.get("recommendation") == "deprioritize" else 1,
            float(row.get("expected_profit") or 0.0),
            int(row.get("qualified_deals") or 0),
        ),
        reverse=True,
    )
    cost_metrics = {
        "openrouter_spend_usd": openrouter_spend_usd,
        "openrouter_spend_estimated": True,
        "openrouter_audited_requests": audited_llm_requests,
        "openrouter_audited_ready": int(llm_audit_summary.get("requests_ready") or 0),
        "openrouter_audited_errors": int(llm_audit_summary.get("requests_error") or 0),
        "openrouter_avg_duration_sec": float(llm_audit_summary.get("avg_duration_sec") or 0.0),
        "openrouter_by_kind": llm_audit_summary.get("by_kind") or {},
        "estimated_llm_input_tokens": estimated_llm_input_tokens,
        "estimated_llm_output_tokens": estimated_llm_output_tokens,
        "estimated_llm_total_tokens": estimated_llm_input_tokens + estimated_llm_output_tokens,
        "llm_cost_per_deal_usd": llm_cost_per_deal_usd,
        "ocr_spend_usd": 0.0,
        "backend_attention_hours": pipeline_attention_hours,
        "cost_per_qualified_lead_usd": cost_per_qualified_lead_usd,
        "llm_cost_per_qualified_lead_usd": cost_per_qualified_lead_usd,
        "llm_cost_signal": llm_cost_signal,
        "source_roi_count": len(source_roi),
        "source_group_recommendations_count": len(source_group_recommendations),
        "note": "MVP: LLM spend считается по audit-log запросов и оценке токенов; фактический billing-log подключается отдельной задачей.",
    }
    speed_metrics = {
        "lead_signals_per_hour": lead_signals_per_hour,
        "qualifications_per_hour": qualifications_per_hour,
        "next_actions_per_hour": next_actions_per_hour,
        "meetings_per_week": meetings_per_week,
        "reply_rate_percent": reply_rate_percent,
    }
    bottlenecks: List[XFilesDashboardInsightDTO] = []
    recommended_actions: List[XFilesDashboardInsightDTO] = []
    if len(items) > 0 and qualified_count / max(1, len(items)) < 0.12:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="yellow",
                title="Мало квалификаций",
                metric=f"{qualified_count} из {len(items)} сделок",
                action="Запустить массовую квалификацию контактов и обновить шаблоны fit/intent.",
            )
        )
    if sla_red > 0:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="red",
                title="Просроченные follow-up",
                metric=f"{sla_red} сделок красные по SLA",
                action="Разобрать очередь красных сделок и назначить next action на сегодня.",
            )
        )
    if next_action_missing > 0:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="red" if next_action_missing >= 5 else "yellow",
                title="Нет следующего действия",
                metric=f"{next_action_missing} активных сделок без next action",
                action="Заполнить next action: написать, уточнить боль, назначить встречу или подготовить КП.",
            )
        )
    if worst_drop_label and worst_drop_percent >= 50:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="yellow",
                title=f"Провал воронки: {worst_drop_label}",
                metric=f"потеря {round(worst_drop_percent, 1)}%",
                action="Посмотреть предыдущий этап и усилить шаблон сообщения или критерии квалификации.",
            )
        )
    if message_stage_count >= 5 and reply_rate_percent < 20:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="red",
                title="Плохой reply rate",
                metric=f"{reply_rate_percent}% ответов",
                action="Обновить шаблон первого сообщения и проверить, не слишком холодные ли источники.",
            )
        )
    if llm_cost_signal == "red":
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="red",
                title="Дорогая LLM-квалификация",
                metric=f"${cost_per_qualified_lead_usd}/qualified lead",
                action="Поставить слабые источники в D/архив и запускать LLM только на источниках с результатом.",
            )
        )
    elif llm_cost_signal == "yellow":
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="yellow",
                title="Стоимость LLM растёт",
                metric=f"${cost_per_qualified_lead_usd}/qualified lead",
                action="Сузить массовую квалификацию и проверить источники с высоким cost/lead.",
            )
        )
    weak_sources = [row for row in source_group_recommendations if row.get("recommendation") in {"deprioritize", "slow_down"}]
    strong_sources = [row for row in source_group_recommendations if row.get("recommendation") == "promote"]
    if weak_sources:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="yellow",
                title="Есть слабые источники",
                metric=f"{len(weak_sources)} источников",
                action=f"Понизить частоту для {weak_sources[0].get('source')}: нет квалифицированных сделок при затратах на анализ.",
            )
        )
    if strong_sources:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="green",
                title="Есть источники для ускорения",
                metric=f"{len(strong_sources)} источников",
                action=f"Проверить перевод {strong_sources[0].get('source')} в группу {strong_sources[0].get('recommended_group')}.",
            )
        )
    if not bottlenecks:
        bottlenecks.append(
            XFilesDashboardInsightDTO(
                tone="green",
                title="Критичных узких мест не видно",
                metric="SLA и next action выглядят рабочими",
                action="Продолжать пополнять pipeline и проверять качество новых сигналов.",
            )
        )

    def deal_priority_key(item: XFilesDealDTO) -> tuple:
        return deal_priority(item, deal_dt)

    def plan_item(item: XFilesDealDTO, action: str) -> Dict[str, Any]:
        return build_plan_item(
            item,
            action,
            attention_hours=deal_attention_hours,
            profit_per_hour=deal_profit_per_hour,
        )

    def build_plan_bucket(
        key: str,
        label: str,
        target: int,
        candidates: List[XFilesDealDTO],
        action: str,
    ) -> XFilesDailyPlanBucketDTO:
        return build_daily_plan_bucket(
            XFilesDailyPlanBucketDTO,
            key=key,
            label=label,
            target=target,
            candidates=candidates,
            action=action,
            plan_item=plan_item,
        )

    top_active = sorted(active_items, key=deal_priority_key, reverse=True)
    priority_tasks = [
        plan_item(item, "Сделать первым: максимум expected profit")
        for item in top_active[:10]
    ]
    quick_money_candidates = [
        item
        for item in active_items
        if deal_profit(item) > 0
        and int(item.score or 0) >= 60
        and (
            item.stage in {"qualified", "proposal", "negotiation", "contract"}
            or item.sla_status in {"red", "yellow"}
            or bool(str(item.next_action or "").strip())
        )
    ]
    quick_money_deals = [
        plan_item(item, "Быстрые деньги: короткий цикл и высокий intent")
        for item in sorted(
            quick_money_candidates,
            key=lambda row: (deal_profit_per_hour(row), deal_profit(row), int(row.score or 0)),
            reverse=True,
        )[:5]
    ]
    active_values = sorted(float(item.expected_value or 0.0) for item in active_items if float(item.expected_value or 0.0) > 0)
    strategic_threshold = 0.0
    if active_values:
        strategic_threshold = max(300000.0, active_values[int((len(active_values) - 1) * 0.75)])
    strategic_candidates = [
        item
        for item in active_items
        if float(item.expected_value or 0.0) >= strategic_threshold > 0
        and item.stage in {"idea", "lead", "qualified", "proposal", "negotiation", "contract"}
    ]
    strategic_deals = [
        plan_item(item, "Стратегическая сделка: высокий чек, длинный цикл")
        for item in sorted(
            strategic_candidates,
            key=lambda row: (float(row.expected_value or 0.0), deal_profit(row), int(row.score or 0)),
            reverse=True,
        )[:5]
    ]
    money_actions: List[XFilesDashboardInsightDTO] = []
    if quick_money_deals:
        best = quick_money_deals[0]
        money_actions.append(
            XFilesDashboardInsightDTO(
                tone="green",
                title="Быстрые деньги",
                metric=f"{len(quick_money_deals)} сделок",
                action=f"Начать с “{best.get('title') or 'сделки'}”: {best.get('profit_per_user_hour') or 0} ₽/ч внимания.",
            )
        )
    if strategic_deals:
        best = strategic_deals[0]
        money_actions.append(
            XFilesDashboardInsightDTO(
                tone="yellow",
                title="Стратегические сделки",
                metric=f"{len(strategic_deals)} сделок",
                action=f"Выделить отдельный трек для “{best.get('title') or 'сделки'}”: чек {round(float(best.get('expected_value') or 0.0))} ₽.",
            )
        )
    recommended_actions = [*money_actions, *bottlenecks][:3]
    due_candidates = [
        item
        for item in active_items
        if item.sla_status in {"red", "yellow"}
        or (item.next_action_at and deal_dt(item.next_action_at) <= now)
        or str(item.next_action or "").strip()
    ]
    due_candidates = sorted(
        due_candidates,
        key=lambda item: (
            0 if item.sla_status == "red" else 1 if item.sla_status == "yellow" else 2,
            deal_dt(item.next_action_at).timestamp() if item.next_action_at else deal_dt(item.updated_at).timestamp(),
            -deal_profit(item),
        ),
    )
    follow_up_candidates = due_candidates + top_active
    proposal_candidates = sorted(
        [item for item in active_items if item.stage in {"qualified", "proposal"}] + top_active,
        key=deal_priority_key,
        reverse=True,
    )
    contract_candidates = sorted(
        [item for item in active_items if item.stage in {"negotiation", "contract"}] + top_active,
        key=deal_priority_key,
        reverse=True,
    )
    daily_plan = [
        build_plan_bucket("contacts", "10 контактов", 10, top_active, "Написать сегодня"),
        build_plan_bucket("follow_up", "5 follow-up", 5, follow_up_candidates, "Сделать follow-up"),
        build_plan_bucket("proposal", "3 КП", 3, proposal_candidates, "Подготовить КП"),
        build_plan_bucket("contract", "1 договор", 1, contract_candidates, "Довести до договора"),
    ]
    daily_plan_summary = " · ".join(
        f"{bucket.label}: {bucket.count}/{bucket.target}"
        for bucket in daily_plan
    )
    postgresql_available = _xfiles_postgres_storage_available()
    storage = "postgresql" if postgresql_available else "state"
    postgresql_waiting = postgres_waiting(
        postgres_dsn=POSTGRES_DSN,
        psycopg_module=psycopg,
        postgresql_available=postgresql_available,
    )
    message = postgres_status_message(
        postgres_dsn=POSTGRES_DSN,
        psycopg_module=psycopg,
        postgresql_available=postgresql_available,
        migration_error=_postgres_state_deals_migration_last_error,
    )
    return XFilesDealsStatusDTO(
        storage=storage,  # type: ignore[arg-type]
        postgresql_configured=bool(POSTGRES_DSN),
        postgresql_available=postgresql_available,
        postgresql_waiting=postgresql_waiting,
        total=len(items),
        active=len(active_items),
        won=sum(1 for item in items if item.stage == "won"),
        lost=sum(1 for item in items if item.stage == "lost"),
        overdue=sla_red,
        due_soon=sla_yellow,
        sla_green=sla_green,
        sla_yellow=sla_yellow,
        sla_red=sla_red,
        expected_value=expected_value,
        expected_profit=expected_profit,
        pipeline_value=pipeline_value,
        pipeline_profit=pipeline_profit,
        average_margin=average_margin,
        margin_products=margin_products,
        pipeline_attention_hours=pipeline_attention_hours,
        pipeline_profit_per_attention_hour=pipeline_profit_per_attention_hour,
        qualified_leads_today=qualified_leads_today,
        qualified_leads_per_day=float(qualified_leads_today),
        avg_time_to_next_action_minutes=avg_time_to_next_action_minutes,
        next_action_ready=next_action_ready,
        next_action_missing=next_action_missing,
        new_signals_today=new_signals_today,
        qualified_active=qualified_active,
        stale_actions=sla_red,
        conversion_funnel=conversion_funnel,
        conversion_bottleneck=worst_drop_label,
        cost_metrics=cost_metrics,
        speed_metrics=speed_metrics,
        bottlenecks=bottlenecks,
        recommended_actions=recommended_actions,
        daily_plan=daily_plan,
        daily_plan_summary=daily_plan_summary,
        priority_tasks=priority_tasks,
        quick_money_deals=quick_money_deals,
        strategic_deals=strategic_deals,
        source_roi=source_roi[:25],
        source_group_recommendations=source_group_recommendations[:25],
        profit_per_user_hour=pipeline_profit_per_attention_hour,
        message=message,
        last_error=_postgres_last_error or _postgres_state_deals_migration_last_error,
    )


def _xfiles_template_model_benchmarks(limit: int = 25) -> List[XFilesTemplateModelBenchmarkDTO]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for item in _xfiles_llm_audit_items():
        if not isinstance(item, dict):
            continue
        input_ids = item.get("input_ids") if isinstance(item.get("input_ids"), dict) else {}
        kind = str(item.get("kind") or "unknown").strip() or "unknown"
        model = str(item.get("model") or "unknown").strip() or "unknown"
        template_id = str(input_ids.get("template_id") or item.get("template_id") or kind or "default").strip() or "default"
        prompt_hash = str(item.get("prompt_hash") or "").strip()
        key = f"{kind}:{model}:{template_id}"
        bucket = buckets.setdefault(
            key,
            {
                "key": key,
                "kind": kind,
                "model": model,
                "template_id": template_id,
                "prompt_hash": prompt_hash,
                "requests": 0,
                "ready": 0,
                "errors": 0,
                "duration": 0.0,
                "cost": 0.0,
            },
        )
        bucket["requests"] += 1
        if prompt_hash and not bucket.get("prompt_hash"):
            bucket["prompt_hash"] = prompt_hash
        status = str(item.get("status") or "").strip()
        if status == "ready":
            bucket["ready"] += 1
        else:
            bucket["errors"] += 1
        try:
            bucket["duration"] += float(item.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            bucket["cost"] += float(item.get("cost_estimate_usd") or 0.0)
        except (TypeError, ValueError):
            pass

    rows: List[XFilesTemplateModelBenchmarkDTO] = []
    for bucket in buckets.values():
        requests_count = int(bucket.get("requests") or 0)
        ready_count = int(bucket.get("ready") or 0)
        errors_count = int(bucket.get("errors") or 0)
        total_cost = round(float(bucket.get("cost") or 0.0), 6)
        avg_duration = round(float(bucket.get("duration") or 0.0) / max(1, ready_count), 3)
        success_rate = round((ready_count / max(1, requests_count)) * 100.0, 1)
        avg_cost = round(total_cost / max(1, requests_count), 6)
        cost_per_ready = round(total_cost / max(1, ready_count), 6)
        duration_penalty = min(35, int(avg_duration * 2))
        cost_penalty = min(30, int(cost_per_ready * 1000))
        error_penalty = min(40, errors_count * 12)
        quality_score = max(0, min(100, int(success_rate) - duration_penalty - cost_penalty - error_penalty))
        if quality_score >= 75:
            recommendation = "keep"
            reason = "Шаблон/модель выглядят стабильными по успеху, скорости и стоимости."
        elif errors_count > 0 or quality_score < 45:
            recommendation = "replace_or_tune"
            reason = "Есть ошибки, высокая стоимость или низкая скорость: лучше заменить модель или доработать промт."
        else:
            recommendation = "ab_test"
            reason = "Можно оставить в тесте и сравнить с альтернативным промтом или моделью."
        rows.append(
            XFilesTemplateModelBenchmarkDTO(
                key=str(bucket.get("key") or ""),
                kind=str(bucket.get("kind") or "unknown"),
                template_id=str(bucket.get("template_id") or "default"),
                model=str(bucket.get("model") or "unknown"),
                prompt_hash=str(bucket.get("prompt_hash") or ""),
                requests=requests_count,
                ready=ready_count,
                errors=errors_count,
                success_rate_percent=success_rate,
                avg_duration_sec=avg_duration,
                cost_estimate_usd=total_cost,
                avg_cost_usd=avg_cost,
                cost_per_ready_usd=cost_per_ready,
                quality_proxy_score=quality_score,
                recommendation=recommendation,
                reason=reason,
            )
        )
    rows.sort(
        key=lambda item: (
            item.recommendation == "replace_or_tune",
            item.quality_proxy_score,
            -item.cost_per_ready_usd,
            item.ready,
        ),
        reverse=True,
    )
    return rows[: max(1, int(limit or 1))]


def _xfiles_deal_opportunities_sync(limit: int = 20) -> XFilesDealOpportunitiesDTO:
    normalized_limit = max(1, min(int(limit or 20), 100))
    active_stages = {"idea", "lead", "qualified", "proposal", "negotiation", "contract"}
    items: List[XFilesDealOpportunityDTO] = []
    for deal in load_deal_items(_xfiles_load_deals, limit=20000):
        if deal.stage not in active_stages:
            continue
        money = _xfiles_opportunity_money(deal)
        attention_hours = _xfiles_opportunity_attention_hours(deal)
        profit_per_hour = round(money / max(0.1, attention_hours), 2)
        urgency_score = _xfiles_opportunity_urgency_score(deal)
        priority_score = min(
            100,
            int(deal.score or 0)
            + min(35, int(profit_per_hour / 25000))
            + min(25, int(money / 100000))
            + min(25, int(urgency_score / 4)),
        )
        who = (
            deal.contact_name
            or deal.company
            or deal.contact_key
            or deal.source_chat
            or deal.source
            or deal.title
        )
        why_bits = []
        if money > 0:
            why_bits.append(f"expected profit {money:g} ₽")
        if profit_per_hour > 0:
            why_bits.append(f"{profit_per_hour:g} ₽/час внимания")
        if deal.sla_status in {"red", "yellow"}:
            why_bits.append(f"SLA {deal.sla_status}")
        if deal.stage in {"qualified", "proposal", "negotiation", "contract"}:
            why_bits.append(f"этап {_XFILES_STAGE_LABELS.get(deal.stage, deal.stage)}")
        items.append(
            XFilesDealOpportunityDTO(
                id=deal.id,
                opportunity_type="deal",
                priority_score=priority_score,
                title=deal.title,
                stage=deal.stage,
                stage_label=_XFILES_STAGE_LABELS.get(deal.stage, deal.stage),
                score=int(deal.score or 0),
                expected_value=float(deal.expected_value or 0.0),
                expected_profit=money,
                probability=float(deal.probability or 0.0),
                margin=float(deal.margin or 1.0),
                attention_hours=attention_hours,
                profit_per_user_hour=profit_per_hour,
                urgency_score=urgency_score,
                who=str(who or ""),
                contact_key=deal.contact_key,
                contact_name=deal.contact_name,
                company=deal.company,
                source=deal.source,
                source_chat=deal.source_chat,
                source_message_id=deal.source_message_id,
                source_date=deal.updated_at or deal.created_at,
                need=deal.need or "",
                offer=deal.product_match or "",
                when_to_write=_xfiles_opportunity_when_to_write(deal, urgency_score),
                next_action=deal.next_action or "",
                next_action_at=deal.next_action_at,
                first_message=_xfiles_opportunity_first_message(deal),
                why_now=" · ".join(why_bits) or "есть сигнал, но нужно дозаполнить экономику и следующий шаг",
                has_deal=True,
                created_at=deal.created_at,
                updated_at=deal.updated_at,
            )
        )
    items.sort(
        key=lambda item: (
            item.priority_score,
            item.profit_per_user_hour,
            item.expected_profit,
            item.urgency_score,
            item.score,
            item.updated_at or item.created_at or "",
        ),
        reverse=True,
    )
    for index, item in enumerate(items[:normalized_limit], start=1):
        item.rank = index
    return XFilesDealOpportunitiesDTO(
        items=items[:normalized_limit],
        total=len(items),
        generated_at=_utc_now().isoformat(),
        message=(
            "Лучшие сделочные возможности готовы из кеша сделок: кто, потребность, оффер, "
            "когда писать и какое действие быстрее двигает деньги."
        ),
    )


def _xfiles_function_impacts(status: XFilesDealsStatusDTO) -> List[XFilesFunctionImpactDTO]:
    cost_metrics = status.cost_metrics if isinstance(status.cost_metrics, dict) else {}
    speed_metrics = status.speed_metrics if isinstance(status.speed_metrics, dict) else {}
    openrouter_spend = float(cost_metrics.get("openrouter_spend_usd") or 0.0)
    cost_per_qualified = float(cost_metrics.get("cost_per_qualified_lead_usd") or 0.0)
    source_recommendations = int(cost_metrics.get("source_group_recommendations_count") or len(status.source_group_recommendations or []))
    qualified_today = float(status.qualified_leads_per_day or 0.0)
    next_action_ready = int(status.next_action_ready or 0)
    reply_rate = float(speed_metrics.get("reply_rate_percent") or 0.0)
    pipeline_profit = float(status.pipeline_profit or 0.0)
    profit_per_hour = float(status.profit_per_user_hour or 0.0)
    impacts = [
        XFilesFunctionImpactDTO(
            key="deal_profit_engine",
            label="Сделки / profit engine",
            value_type="money",
            metric="pipeline profit / час внимания",
            current_value=round(profit_per_hour, 2),
            unit="руб/час",
            earned_money=round(pipeline_profit, 2),
            recommendation="Сначала открывать сделки с максимальным expected profit per user hour.",
            source="deals/status",
        ),
        XFilesFunctionImpactDTO(
            key="contact_qualification",
            label="Квалификация контактов",
            value_type="time",
            metric="квалифицированных лидов в день",
            current_value=round(qualified_today, 2),
            unit="лидов/день",
            saved_time_minutes=round(qualified_today * 12.0, 1),
            speed_gain="Меньше ручного чтения истории контакта перед первым касанием.",
            recommendation="Держать фокус на контактах с intent/fit, а не на всём потоке сообщений.",
            source="contacts + LLM qualification",
        ),
        XFilesFunctionImpactDTO(
            key="crm_enrichment",
            label="CRM-распознавание",
            value_type="time",
            metric="готовых next action",
            current_value=float(next_action_ready),
            unit="действий",
            saved_time_minutes=round(max(0, next_action_ready) * 3.0, 1),
            speed_gain="ФИО, телефоны, компании и города попадают в рабочую очередь без ручного копирования.",
            recommendation="Дозаполнять next action у сделок, где CRM уже нашёл контактные данные.",
            source="crm/enReach",
        ),
        XFilesFunctionImpactDTO(
            key="outreach_conversion",
            label="enReach / outReach",
            value_type="speed",
            metric="reply rate",
            current_value=round(reply_rate, 1),
            unit="%",
            speed_gain="Шаблоны первого сообщения сокращают путь от сигнала до диалога.",
            recommendation="A/B тестировать шаблоны, если reply rate ниже 20%.",
            source="outreach sequences",
        ),
        XFilesFunctionImpactDTO(
            key="source_roi",
            label="ROI источников",
            value_type="risk",
            metric="источников с рекомендацией по группе",
            current_value=float(source_recommendations),
            unit="источников",
            risk_reduction="Слабые источники можно переводить в D/архив и не тратить Telegram/LLM лимиты.",
            recommendation="Повышать частоту только для источников, которые дают qualified/won и expected profit.",
            source="source ROI",
        ),
        XFilesFunctionImpactDTO(
            key="llm_cost_guard",
            label="Контроль стоимости LLM",
            value_type="money",
            metric="cost / qualified lead",
            current_value=round(cost_per_qualified, 4),
            unit="USD",
            earned_money=round(max(0.0, pipeline_profit - openrouter_spend), 2),
            risk_reduction="Дорогие модели и слабые промты видны до того, как они съедят маржу.",
            recommendation="Менять модель/промт, если cost per qualified lead растёт без роста pipeline profit.",
            source="OpenRouter audit",
        ),
    ]
    return impacts


def _xfiles_contact_signal_profile(
    decorated: Dict[str, Any],
    messages: Optional[List[TelegramContactMessageDTO]] = None,
    existing_deal: Optional[XFilesDealDTO] = None,
    days_since: Optional[int] = None,
) -> Dict[str, Any]:
    total_messages = max(0, int(decorated.get("total_messages") or decorated.get("related_messages_count") or 0))
    qualification_count = max(0, int(decorated.get("qualification_count") or 0))
    message_texts = [str(getattr(message, "text", "") or "").strip() for message in (messages or [])]
    latest_text = str(decorated.get("latest_message_text") or decorated.get("latest_message_preview") or "").strip()
    combined_text = "\n".join([latest_text, *message_texts]).strip()
    if len(combined_text) > 60000:
        combined_text = combined_text[:60000]

    topics = [
        label
        for label, keywords in _XFILES_CONTACT_TOPIC_KEYWORDS.items()
        if _xfiles_keyword_hits(combined_text, keywords)
    ]
    pains = [
        label
        for label, keywords in _XFILES_CONTACT_PAIN_KEYWORDS.items()
        if _xfiles_keyword_hits(combined_text, keywords)
    ]
    buying_signals = _xfiles_keyword_hits(combined_text, _XFILES_BUYING_SIGNAL_KEYWORDS)
    objections = _xfiles_keyword_hits(combined_text, _XFILES_OBJECTION_KEYWORDS)
    ability_hits = _xfiles_keyword_hits(combined_text, _XFILES_ABILITY_KEYWORDS)
    product_candidates = _xfiles_product_match_candidates(combined_text, limit=2)
    catalog_product_hint = _xfiles_product_hint_from_catalog(combined_text)
    product_match_score = int(product_candidates[0].get("score") or 0) if product_candidates else 0
    offer_recommendation = str(product_candidates[0].get("recommendation") or "") if product_candidates else ""
    has_money_context = bool(re.search(r"(?:\d[\d\s]{2,})(?:\s?(?:₽|руб|тыс|млн|k|m))", combined_text, re.IGNORECASE))

    fit_score = 18
    fit_score += min(28, total_messages // 4)
    fit_score += min(18, len(topics) * 6)
    fit_score += 10 if decorated.get("sender_username") else 0
    fit_score += 10 if len(decorated.get("leads") or []) >= 2 else 0
    fit_score += 12 if qualification_count else 0
    fit_score += 12 if catalog_product_hint else 0

    intent_score = 18
    intent_score += min(38, len(buying_signals) * 7)
    intent_score += min(18, len(pains) * 6)
    intent_score += 10 if qualification_count else 0
    intent_score -= min(12, len(objections) * 4)

    urgency_score = 20
    if days_since is not None:
        if days_since <= 1:
            urgency_score += 34
        elif days_since <= 7:
            urgency_score += 24
        elif days_since <= 30:
            urgency_score += 14
        elif days_since <= 90:
            urgency_score += 6
    urgency_score += min(26, len(_xfiles_keyword_hits(combined_text, ["срочно", "сегодня", "завтра", "дедлайн", "до конца", "сейчас", "быстро"])) * 8)

    ability_to_pay_score = 18
    ability_to_pay_score += min(34, len(ability_hits) * 6)
    ability_to_pay_score += 18 if has_money_context else 0
    ability_to_pay_score += 10 if any(topic in topics for topic in ["финансы/инвестиции", "продажи/лиды"]) else 0
    ability_to_pay_score += min(12, total_messages // 20)

    fit_score = max(0, min(100, fit_score))
    intent_score = max(0, min(100, intent_score))
    urgency_score = max(0, min(100, urgency_score))
    ability_to_pay_score = max(0, min(100, ability_to_pay_score))
    deal_score = int(round(100 * ((fit_score / 100) * (intent_score / 100) * (urgency_score / 100) * (ability_to_pay_score / 100)) ** 0.25))
    if existing_deal and existing_deal.stage not in {"won", "lost"}:
        deal_score = max(0, deal_score - 8)

    if catalog_product_hint:
        best_product_hint = catalog_product_hint
    elif "продажи/лиды" in topics:
        best_product_hint = "X-Files/enReach: лидогенерация, квалификация и сделочный контур"
    elif "AI/автоматизация" in topics:
        best_product_hint = "AI-интеграция или автоматизация CRM/операций"
    elif "мероприятия/нетворк" in topics:
        best_product_hint = "пакет подготовки встреч, outreach и follow-up вокруг события"
    elif "финансы/инвестиции" in topics:
        best_product_hint = "аналитика, structured deal research или автоматизация финансовых данных"
    else:
        best_product_hint = "диагностика потребности и короткая консультация"

    missing_parts: List[str] = []
    if not qualification_count:
        missing_parts.append("LLM-квалификация")
    if not buying_signals:
        missing_parts.append("явный buying intent")
    if not ability_hits and not has_money_context:
        missing_parts.append("сигнал платёжеспособности")
    if not topics:
        missing_parts.append("понятная тема интереса")
    missing_qualification = ", ".join(missing_parts) if missing_parts else "данных достаточно для первого касания"

    card_parts = [
        f"Темы: {', '.join(topics) if topics else 'не выделены'}",
        f"Боли: {', '.join(pains) if pains else 'не выделены'}",
        f"Покупательские сигналы: {', '.join(buying_signals[:6]) if buying_signals else 'нет явных'}",
        f"Возражения: {', '.join(objections[:4]) if objections else 'не найдены'}",
        f"Лучший продукт: {best_product_hint}",
        f"Не хватает: {missing_qualification}",
    ]
    return {
        "fit_score": fit_score,
        "intent_score": intent_score,
        "urgency_score": urgency_score,
        "ability_to_pay_score": ability_to_pay_score,
        "deal_score": deal_score,
        "topics": topics,
        "pains": pains,
        "buying_signals": buying_signals[:8],
        "objections": objections[:6],
        "best_product_hint": best_product_hint,
        "product_match_score": product_match_score,
        "offer_recommendation": offer_recommendation,
        "missing_qualification": missing_qualification,
        "qualification_card": " · ".join(card_parts),
    }


def _xfiles_contact_recommendation(
    row: Dict[str, Any],
    existing_deal: Optional[XFilesDealDTO],
    messages: Optional[List[TelegramContactMessageDTO]] = None,
) -> XFilesDailyContactDTO:
    decorated = _decorate_contact_summary_with_qualifications(row)
    total_messages = max(0, int(decorated.get("total_messages") or decorated.get("related_messages_count") or 0))
    qualification_count = max(0, int(decorated.get("qualification_count") or 0))
    last_dt = _xfiles_parse_optional_dt(decorated.get("last_message_at"))
    days_since = None
    if last_dt:
        days_since = max(0, int((_utc_now() - last_dt).total_seconds() // 86400))

    profile = _xfiles_contact_signal_profile(
        decorated,
        messages=messages,
        existing_deal=existing_deal,
        days_since=days_since,
    )
    score = int(profile.get("deal_score") or 0)
    temperature = _xfiles_contact_temperature(
        profile,
        total_messages=total_messages,
        qualification_count=qualification_count,
    )
    score_explanation = _xfiles_score_explanation(profile, temperature)
    why_now = _xfiles_why_now(profile, days_since, existing_deal=existing_deal)

    reasons: List[str] = []
    if profile.get("topics"):
        reasons.append("темы: " + ", ".join(profile.get("topics") or []))
    if profile.get("buying_signals"):
        reasons.append("intent: " + ", ".join((profile.get("buying_signals") or [])[:3]))
    if qualification_count:
        reasons.append(f"есть {qualification_count} LLM-анализ")
    if total_messages:
        reasons.append(f"{total_messages} сообщений")
    if days_since is not None:
        if days_since == 0:
            reasons.append("писал сегодня")
        elif days_since == 1:
            reasons.append("писал вчера")
        else:
            reasons.append(f"последняя активность {days_since} дн. назад")
    if existing_deal and existing_deal.stage not in {"won", "lost"}:
        reasons.append(f"уже есть сделка: {existing_deal.stage}")
    if not reasons:
        reasons.append("есть история сообщений в базе")

    display_name = str(decorated.get("display_name") or decorated.get("sender_name") or decorated.get("sender_username") or decorated.get("contact_key") or "").strip()
    latest_lead = str(decorated.get("latest_lead") or "").strip()
    first_name = display_name.split()[0] if display_name else "Здравствуйте"
    next_action = (
        "Открыть готовую квалификацию, выбрать оффер и отправить первое касание"
        if qualification_count
        else "Квалифицировать контакт и подготовить первое касание"
    )
    if existing_deal and existing_deal.stage not in {"won", "lost"}:
        next_action = f"Вернуться к сделке “{existing_deal.title}” и обновить следующий шаг"
    first_message = (
        f"{first_name}, добрый день. Увидел ваш контекст"
        f"{f' в {latest_lead}' if latest_lead else ''}; кажется, у нас может быть полезная точка для разговора. "
        f"Вижу возможную тему: {profile.get('best_product_hint') or 'диагностика потребности'}. "
        "Можно задам один короткий уточняющий вопрос?"
    )

    return XFilesDailyContactDTO(
        contact_key=str(decorated.get("contact_key") or "").strip(),
        display_name=display_name,
        sender_username=str(decorated.get("sender_username") or "").strip() or None,
        latest_lead=latest_lead or None,
        total_messages=total_messages,
        qualification_count=qualification_count,
        first_message_at=str(decorated.get("first_message_at") or "") or None,
        last_message_at=str(decorated.get("last_message_at") or "") or None,
        latest_message_preview=_xfiles_clean_text(decorated.get("latest_message_preview") or decorated.get("latest_message_text") or "", 900),
        fit_score=int(profile.get("fit_score") or 0),
        intent_score=int(profile.get("intent_score") or 0),
        urgency_score=int(profile.get("urgency_score") or 0),
        ability_to_pay_score=int(profile.get("ability_to_pay_score") or 0),
        deal_score=score,
        why="; ".join(reasons),
        qualification_card=str(profile.get("qualification_card") or ""),
        topics=[str(item) for item in (profile.get("topics") or [])],
        pains=[str(item) for item in (profile.get("pains") or [])],
        buying_signals=[str(item) for item in (profile.get("buying_signals") or [])],
        objections=[str(item) for item in (profile.get("objections") or [])],
        best_product_hint=str(profile.get("best_product_hint") or ""),
        product_match_score=int(profile.get("product_match_score") or 0),
        offer_recommendation=str(profile.get("offer_recommendation") or ""),
        missing_qualification=str(profile.get("missing_qualification") or ""),
        lead_temperature=temperature["key"],
        lead_temperature_label=temperature["label"],
        score_explanation=score_explanation,
        why_now=why_now,
        next_action=next_action,
        first_message=first_message,
        has_deal=bool(existing_deal),
        deal_id=existing_deal.id if existing_deal else None,
        deal_title=existing_deal.title if existing_deal else None,
    )


def _xfiles_deal_assistant_sync(deal_id: str) -> XFilesDealAssistantDTO:
    deal = _xfiles_get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    messages = _xfiles_deal_assistant_messages(deal, limit=80)
    message_texts = [
        _xfiles_assistant_short_text(message.text, 900)
        for message in messages
        if _xfiles_assistant_short_text(message.text, 900)
    ]
    latest_message = message_texts[-1] if message_texts else _xfiles_assistant_short_text(deal.need or deal.notes or "", 900)
    display_name = _xfiles_assistant_short_text(deal.contact_name or deal.contact_key or deal.company or "Контакт", 240)
    source_chat = _xfiles_assistant_short_text(deal.source_chat or "", 180)
    decorated = {
        "contact_key": deal.contact_key or "",
        "display_name": display_name,
        "sender_username": "",
        "latest_lead": source_chat,
        "total_messages": len(messages),
        "related_messages_count": len(messages),
        "latest_message_text": latest_message,
        "latest_message_preview": latest_message,
        "leads": [source_chat] if source_chat else [],
    }
    profile = _xfiles_contact_signal_profile(
        decorated,
        messages=messages,
        existing_deal=deal,
        days_since=None,
    )
    temperature = _xfiles_contact_temperature(profile, total_messages=len(messages), qualification_count=0)
    score_explanation = _xfiles_score_explanation(profile, temperature)
    product_hint = _xfiles_assistant_short_text(deal.product_match or profile.get("best_product_hint") or "", 500)
    topics = [str(item) for item in (profile.get("topics") or [])][:6]
    pains = [str(item) for item in (profile.get("pains") or [])][:6]
    buying_signals = [str(item) for item in (profile.get("buying_signals") or [])][:6]
    objections_raw = [str(item) for item in (profile.get("objections") or [])][:5]
    if not objections_raw:
        objections_raw = ["нет времени", "непонятен бюджет", "неочевидна ценность"]

    first_name = display_name.split()[0] if display_name and display_name != "Контакт" else "Добрый день"
    next_best = (
        f"{first_name}, добрый день. По вашему контексту вижу тему: {product_hint or 'диагностика задачи'}. "
        f"Правильно понимаю, что сейчас важнее всего {pains[0] if pains else 'быстро понять, где есть экономия времени или денег'}? "
        "Если да, предложу короткий следующий шаг без большой подготовки."
    )
    missing = str(profile.get("missing_qualification") or "")
    qualification_questions = [
        "Какой результат будет считаться успешным через 2-4 недели?",
        "Кто кроме вас влияет на решение и бюджет?",
        "Есть ли дедлайн, событие или причина сделать это сейчас?",
        "Что уже пробовали и почему это не сработало?",
        "Какой минимальный пилот был бы безопасен для старта?",
    ]
    if "сигнал платёжеспособности" not in missing:
        qualification_questions.append("Какой диапазон бюджета уже комфортен для пилота?")
    if "явный buying intent" not in missing:
        qualification_questions.append("Вы сейчас скорее исследуете тему или уже выбираете решение?")

    call_agenda = [
        "1. За 2 минуты подтвердить контекст и текущую задачу контакта.",
        "2. Уточнить цель, дедлайн, критерии успеха и кто принимает решение.",
        f"3. Проверить fit продукта: {product_hint or 'диагностика / пилот X-Files'}",
        "4. Обсудить самый маленький безопасный следующий шаг.",
        "5. Зафиксировать next action, срок и ответственного.",
    ]
    compact_history = message_texts[-10:]
    if not compact_history:
        compact_history = [
            _xfiles_assistant_short_text(deal.need or "Потребность пока не описана", 900),
            _xfiles_assistant_short_text(deal.notes or "", 900),
        ]
    ten_bullets = [
        f"{idx + 1}. {text}"
        for idx, text in enumerate([item for item in compact_history if item][:10])
    ]
    five_minute_brief = [
        f"Контакт: {display_name}{f' · {deal.company}' if deal.company else ''}",
        f"Стадия: {_XFILES_STAGE_LABELS.get(str(deal.stage), str(deal.stage))}; текущий score {deal.score}/100.",
        f"Что обсуждал: {', '.join(topics) if topics else (_xfiles_assistant_short_text(deal.need, 240) or 'темы пока слабые')}.",
        f"Что может хотеть: {', '.join(pains or buying_signals) if (pains or buying_signals) else 'нужно добрать квалификацию'}.",
        f"Что предложить: {product_hint or 'короткую диагностику и пилот'}",
        f"Следующий шаг: {deal.next_action or 'задать один квалифицирующий вопрос'}",
    ]
    do_not_write = [
        "Не обещать результат, который не подтверждён данными переписки.",
        "Не начинать с длинной презентации продукта; сначала один вопрос по ситуации.",
        "Не давить на бюджет, если он не упоминался явно.",
        "Не спорить с возражениями; фиксировать критерии и предлагать маленький пилот.",
    ]
    if not message_texts:
        do_not_write.append("Не писать персонализированный outreach без проверки истории сообщений: по сделке мало исходных данных.")

    recommended_score = max(int(deal.score or 0), int(profile.get("deal_score") or 0))
    recommended_score = max(0, min(100, recommended_score))
    recommended_next_action = (
        f"Отправить next best message и проверить: {qualification_questions[0]}"
        if recommended_score >= 45
        else "Собрать больше контекста перед активным outreach: уточнить задачу, бюджет и дедлайн"
    )

    return XFilesDealAssistantDTO(
        deal_id=deal.id,
        generated_at=_utc_now().isoformat(),
        contact_summary=score_explanation,
        who=f"{display_name}{f' · {deal.company}' if deal.company else ''}{f' · {source_chat}' if source_chat else ''}",
        discussed=topics or [_xfiles_assistant_short_text(deal.need or "темы пока не выделены", 300)],
        wants=pains or buying_signals or ["нужно добрать явную потребность"],
        can_buy=product_hint or "короткая диагностика / пилот, пока fit не подтверждён",
        next_best_message=next_best,
        objections=[
            {"objection": objection, "reply": _xfiles_objection_reply(objection, product_hint)}
            for objection in objections_raw
        ],
        qualification_questions=qualification_questions[:8],
        call_agenda=call_agenda,
        five_minute_brief=five_minute_brief,
        ten_bullets=ten_bullets[:10],
        do_not_write=do_not_write,
        recommended_score=recommended_score,
        recommended_next_action=recommended_next_action,
        source_messages=len(messages),
    )


def _xfiles_event_sales_plan_sync(limit: int = 10) -> XFilesEventSalesPlanDTO:
    normalized_limit = max(1, min(int(limit or 10), 50))
    source_limit = max(250, normalized_limit * 80)
    event_rows = [row for row in _analysis_rows("events", limit=source_limit) if isinstance(row, dict)]
    route_rows = [row for row in _routes_cache_rows() if isinstance(row, dict)]
    route_addresses = _routes_address_directory(route_rows)
    route_by_lead: Dict[str, Dict[str, Any]] = {}
    for row in route_rows:
        lead_key = _xfiles_norm_identity(row.get("lead") or row.get("source_jsonl"))
        if not lead_key or not _normalize_route_address(row.get("address")):
            continue
        previous = route_by_lead.get(lead_key)
        if not previous or str(row.get("date_utc") or "") > str(previous.get("date_utc") or ""):
            route_by_lead[lead_key] = row

    deals_by_message: Dict[tuple[str, str], XFilesDealDTO] = {}
    for deal in _xfiles_load_deals(limit=20000):
        source_chat = _xfiles_norm_identity(deal.source_chat)
        message_id = _xfiles_norm_identity(deal.source_message_id)
        if source_chat and message_id:
            deals_by_message[(source_chat, message_id)] = deal

    buckets: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    for row in event_rows:
        lead = str(row.get("lead") or "").strip()
        topic = _xfiles_event_topic(row)
        event_dt = _xfiles_event_date_from_row(row)
        bucket_key = (
            lead,
            event_dt.date().isoformat() if event_dt else str(row.get("date_utc") or "")[:10],
            topic.split(",")[0].strip().lower(),
        )
        bucket = buckets.setdefault(bucket_key, {"senders": set(), "count": 0})
        sender = _xfiles_event_contact_key(row)
        if sender:
            bucket["senders"].add(sender)
        bucket["count"] = int(bucket.get("count") or 0) + 1

    def event_sort_key(row: Dict[str, Any]) -> tuple:
        event_dt = _xfiles_event_date_from_row(row)
        message_dt = _xfiles_parse_optional_dt(row.get("date_utc"))
        has_date = 1 if str(row.get("event_date") or "").strip() else 0
        return (has_date, event_dt.timestamp() if event_dt else 0.0, message_dt.timestamp() if message_dt else 0.0)

    sorted_events = sorted(event_rows, key=event_sort_key, reverse=True)
    items: List[XFilesEventSalesPlanItemDTO] = []
    events_with_dates = 0
    events_with_routes = 0
    group_outreach_candidates = 0
    seen: set[str] = set()
    for row in sorted_events:
        row_id = _event_row_key(row)
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        text = _outreach_compact_text(row.get("text") or "")
        if not text:
            continue
        lead = str(row.get("lead") or "").strip()
        event_dt = _xfiles_event_date_from_row(row)
        message_dt = _xfiles_parse_optional_dt(row.get("date_utc"))
        if str(row.get("event_date") or "").strip():
            events_with_dates += 1
        route = route_by_lead.get(_xfiles_norm_identity(lead), {})
        route_address = _normalize_route_address(route.get("address")) if route else ""
        if route_address:
            events_with_routes += 1
        topic = _xfiles_event_topic(row)
        bucket_key = (
            lead,
            event_dt.date().isoformat() if event_dt else str(row.get("date_utc") or "")[:10],
            topic.split(",")[0].strip().lower(),
        )
        bucket = buckets.get(bucket_key, {})
        bucket_senders = sorted(str(item) for item in (bucket.get("senders") or []) if str(item).strip())
        related_contacts_count = len(bucket_senders)
        if related_contacts_count >= 3:
            group_outreach_candidates += 1
        contact_key = _xfiles_event_contact_key(row)
        who_to_write = contact_key or lead or "контакт события"
        windows = _xfiles_event_sales_windows(event_dt, message_dt)
        next_window = _xfiles_pick_next_event_window(windows)
        product = _xfiles_event_product_offer(text)
        score = min(
            100,
            28
            + (18 if event_dt else 0)
            + (14 if route_address else 0)
            + min(18, related_contacts_count * 4)
            + min(22, int(product.get("score") or 0) // 3),
        )
        existing_deal = deals_by_message.get((_xfiles_norm_identity(lead), str(row.get("message_id") or "").lower()))
        participants = bucket_senders[:6] if bucket_senders else [who_to_write]
        group_plan = (
            f"Собрать групповой follow-up для {related_contacts_count} контактов вокруг темы “{topic}”. "
            "Сначала личное сообщение организатору/автору, затем общий outreach по участникам."
            if related_contacts_count >= 3
            else None
        )
        next_action = next_window.action if next_window else "Написать по событийному поводу"
        if route_address:
            next_action = f"{next_action}. Проверить офлайн-встречу: {route_address}"
        items.append(
            XFilesEventSalesPlanItemDTO(
                id=row_id,
                lead=lead,
                source_selector=row.get("source_selector"),
                message_id=int(row.get("message_id") or 0),
                event_date=str(row.get("event_date") or (event_dt.date().isoformat() if event_dt else "")) or None,
                message_date=str(row.get("date_utc") or "") or None,
                place=route_address,
                topic=topic,
                participants=participants,
                who_to_write=who_to_write,
                contact_key=contact_key,
                sender_username=row.get("sender_username"),
                sender_name=row.get("sender_name"),
                matched_keywords=[str(item) for item in (row.get("matched_keywords") or []) if str(item).strip()],
                message=text,
                message_preview=_xfiles_clean_text(text, 360) or "",
                offer=str(product.get("offer") or ""),
                product_match=str(product.get("product_match") or ""),
                score=score,
                probability=max(float(product.get("probability") or 0.2), 0.35 if score >= 65 else 0.25),
                margin=_xfiles_clean_margin(product.get("margin"), 1.0),
                sales_window_label=next_window.label if next_window else "",
                next_action_at=next_window.action_at if next_window else None,
                next_action=next_action,
                sales_windows=windows,
                route_address=route_address or None,
                route_address_key=str(route.get("address_key") or _route_address_key(route_address) or "") or None,
                related_contacts_count=related_contacts_count,
                group_outreach_plan=group_plan,
                has_deal=bool(existing_deal),
                deal_id=existing_deal.id if existing_deal else None,
                deal_title=existing_deal.title if existing_deal else None,
            )
        )
        if len(items) >= normalized_limit:
            break

    event_leads = {_xfiles_norm_identity(row.get("lead")) for row in event_rows if row.get("lead")}
    event_senders_by_lead: Dict[str, set[str]] = {}
    event_dates_by_lead: Dict[str, List[str]] = {}
    for row in event_rows:
        lead_key = _xfiles_norm_identity(row.get("lead"))
        if not lead_key:
            continue
        sender = _xfiles_event_contact_key(row)
        if sender:
            event_senders_by_lead.setdefault(lead_key, set()).add(sender)
        event_dt = _xfiles_event_date_from_row(row)
        if event_dt:
            event_dates_by_lead.setdefault(lead_key, []).append(event_dt.date().isoformat())

    meeting_days: List[XFilesRouteMeetingDayDTO] = []
    for address in route_addresses[: normalized_limit]:
        leads = [str(lead) for lead in (address.get("leads") or []) if str(lead).strip()]
        related_leads = [_xfiles_norm_identity(lead) for lead in leads]
        events_count = sum(1 for lead in related_leads if lead in event_leads)
        contacts_count = len(set().union(*(event_senders_by_lead.get(lead, set()) for lead in related_leads))) if related_leads else 0
        suggested_dates = sorted(
            date
            for lead in related_leads
            for date in event_dates_by_lead.get(lead, [])
            if date
        )
        meeting_days.append(
            XFilesRouteMeetingDayDTO(
                address_key=str(address.get("address_key") or ""),
                address=str(address.get("address") or ""),
                messages_count=int(address.get("messages_count") or 0),
                leads_count=len(leads),
                events_count=events_count,
                contacts_count=contacts_count,
                gps_ready=address.get("lat") is not None and address.get("lon") is not None,
                lat=address.get("lat"),
                lon=address.get("lon"),
                suggested_day=suggested_dates[0] if suggested_dates else (_utc_now() + timedelta(days=1)).date().isoformat(),
                action=(
                    f"Собрать день встреч: {len(leads)} источников рядом, "
                    f"{contacts_count} контактов из событий, {int(address.get('messages_count') or 0)} сообщений для подготовки."
                ),
                examples=list(address.get("examples") or [])[:3],
            )
        )

    return XFilesEventSalesPlanDTO(
        items=items,
        meeting_days=meeting_days,
        total_events=len(event_rows),
        events_with_dates=events_with_dates,
        events_with_routes=events_with_routes,
        group_outreach_candidates=group_outreach_candidates,
        generated_at=_utc_now().isoformat(),
    )


def _xfiles_daily_contacts_sync(limit: int = 10, lead_temperature: str = "all") -> XFilesDailyContactsDTO:
    normalized_limit = max(1, min(int(limit or 10), 50))
    normalized_temperature = str(lead_temperature or "all").strip()
    source_limit = max(200, min(50000, normalized_limit * 120))
    if _duckdb_contacts_ready():
        source_rows = _duckdb_load_contact_rows(limit=source_limit)
    else:
        source_rows = _analysis_rows("contacts", limit=source_limit)

    deals_by_contact = _xfiles_existing_deals_by_contact()
    items: List[XFilesDailyContactDTO] = []
    rows_by_contact: Dict[str, Dict[str, Any]] = {}
    for row in source_rows:
        if not isinstance(row, dict):
            continue
        contact_key = str(row.get("contact_key") or "").strip()
        if not contact_key:
            continue
        rows_by_contact.setdefault(_xfiles_norm_identity(contact_key), row)
        item = _xfiles_contact_recommendation(row, deals_by_contact.get(_xfiles_norm_identity(contact_key)))
        if item.deal_score <= 0:
            continue
        items.append(item)

    def sort_key(row: XFilesDailyContactDTO) -> tuple:
        last_dt = _xfiles_parse_optional_dt(row.last_message_at)
        last_ts = last_dt.timestamp() if last_dt else 0.0
        return (int(row.has_deal), -int(row.deal_score or 0), -last_ts, -int(row.total_messages or 0))

    items.sort(key=sort_key)
    enrich_keys = [
        _xfiles_norm_identity(item.contact_key)
        for item in items[: max(normalized_limit * 2, 20)]
        if _xfiles_norm_identity(item.contact_key)
    ]
    enriched_items: Dict[str, XFilesDailyContactDTO] = {}
    for contact_key in enrich_keys:
        row = rows_by_contact.get(contact_key)
        if not row:
            continue
        messages = _contact_messages_for_qualification(str(row.get("contact_key") or ""), limit=80)
        enriched = _xfiles_contact_recommendation(row, deals_by_contact.get(contact_key), messages=messages)
        if enriched.deal_score > 0:
            enriched_items[contact_key] = enriched
    if enriched_items:
        items = [
            enriched_items.get(_xfiles_norm_identity(item.contact_key), item)
            for item in items
        ]
        items.sort(key=sort_key)
    if normalized_temperature and normalized_temperature != "all":
        items = [
            item
            for item in items
            if str(item.lead_temperature or "") == normalized_temperature
        ]
    return XFilesDailyContactsDTO(
        items=items[:normalized_limit],
        total=len(items),
        generated_at=_utc_now().isoformat(),
    )


def _xfiles_need_signal_from_parts(
    *,
    source: str,
    source_label: Optional[str],
    lead: Optional[str],
    source_selector: Optional[str],
    message_id: Optional[int],
    date_utc: Optional[str],
    text: str,
    sender_id: Optional[int] = None,
    sender_username: Optional[str] = None,
    sender_name: Optional[str] = None,
    company: Optional[str] = None,
    existing_deals_by_contact: Optional[Dict[str, XFilesDealDTO]] = None,
) -> Optional[XFilesNeedSignalDTO]:
    compact_text = _outreach_compact_text(text)
    if len(compact_text) < 8:
        return None
    tags, tag_labels, score = _xfiles_need_detect_tags(compact_text)
    if not tags:
        return None

    contact_key = _contacts_contact_key(sender_id, sender_username, sender_name) or (
        f"source:{_xfiles_norm_identity(lead)}" if lead else ""
    )
    contact_name = _contacts_display_name(sender_name, sender_username, sender_id) if contact_key else ""
    pain_labels = [
        label
        for label, keywords in _XFILES_CONTACT_PAIN_KEYWORDS.items()
        if _xfiles_keyword_hits(compact_text, keywords)
    ]
    buying_hits = _xfiles_keyword_hits(compact_text, _XFILES_BUYING_SIGNAL_KEYWORDS)
    objections = _xfiles_keyword_hits(compact_text, _XFILES_OBJECTION_KEYWORDS)
    role_hits = _xfiles_keyword_hits(" ".join([compact_text, contact_name]), _XFILES_ABILITY_KEYWORDS)
    product_candidates = _xfiles_product_match_candidates(" ".join([compact_text, contact_name, str(company or "")]), limit=2)
    best_product = product_candidates[0] if product_candidates else None
    product = str(best_product.get("name") or "") if best_product else _xfiles_product_hint_from_catalog(compact_text)
    if not product:
        if "event" in tags:
            product = "событийный outreach и подготовка встреч"
        elif "contractor" in tags or "service_purchase" in tags:
            product = "подбор решения / подрядчика и быстрый диагностический созвон"
        elif "hiring" in tags:
            product = "поиск и квалификация подрядчиков или кандидатов"
        else:
            product = "быстрая диагностика потребности"
    need = _xfiles_need_pick_sentence(compact_text, tags)
    budget = _xfiles_need_extract_budget(compact_text)
    deadline = _xfiles_need_extract_deadline(compact_text)
    if budget:
        score = min(100, score + 8)
    if deadline:
        score = min(100, score + 8)
    urgency_label = "горячий" if score >= 72 else "тёплый" if score >= 48 else "наблюдать"
    product_match_score = int(best_product.get("score") or 0) if best_product else 0
    product_match_probability = float(best_product.get("probability") or 0.0) if best_product else 0.0
    product_expected_value_hint = float(best_product.get("expected_value_hint") or 0.0) if best_product else 0.0
    product_expected_profit_rank = float(best_product.get("expected_profit_rank") or 0.0) if best_product else 0.0
    product_margin = _xfiles_clean_margin(best_product.get("margin") if best_product else None, 1.0)
    offer_recommendation = str(best_product.get("recommendation") or "") if best_product else ""
    alternative_product = str(product_candidates[1].get("name") or "") if len(product_candidates) > 1 else ""
    do_not_sell_reason = str(best_product.get("do_not_sell_reason") or "") if best_product else ""
    pitch = _xfiles_product_pitch(best_product, need, contact_name) if best_product else _xfiles_need_first_touch(contact_name, str(lead or ""), need, product)
    existing_deal = None
    if existing_deals_by_contact and contact_key:
        existing_deal = existing_deals_by_contact.get(_xfiles_norm_identity(contact_key))

    stable_key = _xfiles_operational_stable_key(
        "need",
        {
            "source": source,
            "lead": lead,
            "message_id": message_id,
            "contact_key": contact_key,
            "need": need or compact_text,
        },
    )
    return XFilesNeedSignalDTO(
        id=_xfiles_need_signal_id(source, str(lead or ""), message_id, contact_key, compact_text),
        stable_key=stable_key,
        source=source,
        source_label=_xfiles_need_source_label(source, source_label),
        lead=str(lead or "").strip() or None,
        source_selector=str(source_selector or "").strip() or None,
        contact_key=contact_key or None,
        contact_name=contact_name,
        company=_xfiles_clean_text(company, 500),
        sender_username=str(sender_username or "").strip() or None,
        message_id=message_id,
        date_utc=str(date_utc or "").strip() or None,
        text=_xfiles_clean_text(compact_text, 6000) or "",
        need=need,
        pain=", ".join(pain_labels[:4]),
        task=", ".join(tag_labels[:4]),
        budget=budget,
        deadline=deadline,
        role=", ".join(role_hits[:4]),
        buying_context=", ".join(buying_hits[:5]),
        objection=", ".join(objections[:4]),
        tags=tags,
        tag_labels=tag_labels,
        urgency_label=urgency_label,
        product_match=product,
        product_match_score=product_match_score,
        product_match_probability=product_match_probability,
        product_expected_value_hint=product_expected_value_hint,
        product_expected_profit_rank=product_expected_profit_rank,
        product_margin=product_margin,
        alternative_product=alternative_product,
        offer_recommendation=offer_recommendation,
        do_not_sell_reason=do_not_sell_reason,
        pitch=pitch,
        first_touch=pitch,
        score=score,
        has_deal=bool(existing_deal),
        deal_id=existing_deal.id if existing_deal else None,
        deal_title=existing_deal.title if existing_deal else None,
    )


def _xfiles_need_signals_page_sync(
    *,
    page: int = 1,
    page_size: int = 5,
    query: str = "",
    tag: str = "all",
    source: str = "all",
    limit: int = 3000,
) -> XFilesNeedSignalsPageDTO:
    normalized_limit = max(100, min(10000, int(limit or 3000)))
    existing_deals = _xfiles_existing_deals_by_contact()
    raw_items = [
        *_xfiles_need_signals_from_duckdb(normalized_limit, existing_deals),
        *_xfiles_need_signals_from_enreach(min(3000, normalized_limit), existing_deals),
    ]

    seen: set[str] = set()
    deduped: List[XFilesNeedSignalDTO] = []
    for item in raw_items:
        item.stable_key = item.stable_key or _xfiles_need_stable_key(item)
        dedupe_key = item.stable_key or "|".join(
            [
                _xfiles_norm_identity(item.contact_key),
                ",".join(item.tags[:2]),
                _outreach_compact_text(item.need or item.text).lower()[:220],
            ]
        )
        if not dedupe_key.strip("|") or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(item)

    auto_created_deals = _xfiles_auto_create_need_deal_drafts(deduped, existing_deals)

    normalized_query = str(query or "").strip().lower()
    normalized_tag = str(tag or "all").strip()
    normalized_source = str(source or "all").strip()
    filtered: List[XFilesNeedSignalDTO] = []
    for item in deduped:
        if normalized_tag and normalized_tag != "all" and normalized_tag not in item.tags:
            continue
        if normalized_source and normalized_source != "all" and item.source != normalized_source:
            continue
        if normalized_query:
            hay = " ".join(
                [
                    item.contact_name,
                    item.sender_username or "",
                    item.lead or "",
                    item.source_selector or "",
                    item.company or "",
                    item.need,
                    item.text,
                    item.product_match,
                    " ".join(item.tag_labels),
                ]
            ).lower()
            if normalized_query not in hay:
                continue
        filtered.append(item)

    def sort_key(item: XFilesNeedSignalDTO) -> tuple:
        parsed = _xfiles_parse_optional_dt(item.date_utc)
        ts = parsed.timestamp() if parsed else 0.0
        return (-int(item.score or 0), -ts)

    filtered.sort(key=sort_key)
    page_data = _paginate_items(filtered, page=page, page_size=page_size)
    return XFilesNeedSignalsPageDTO(
        **page_data,
        generated_at=_utc_now().isoformat(),
        auto_created_deals=auto_created_deals,
    )


__all__ = [
    "refresh_legacy_globals",
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
]
