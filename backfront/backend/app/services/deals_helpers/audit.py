"""LLM audit/cost helpers for X-Files deals."""

from __future__ import annotations

from typing import Any, Dict


def estimate_llm_cost_metrics(
    *,
    items_count: int,
    qualified_count: int,
    audit_summary: Dict[str, Any],
) -> Dict[str, Any]:
    llm_input_tokens_per_deal = 2200
    llm_output_tokens_per_deal = 650
    llm_cost_per_1k_input_tokens_usd = 0.00015
    llm_cost_per_1k_output_tokens_usd = 0.0006
    estimated_llm_input_tokens = items_count * llm_input_tokens_per_deal
    estimated_llm_output_tokens = items_count * llm_output_tokens_per_deal
    audited_llm_requests = int(audit_summary.get("requests_total") or 0)
    if audited_llm_requests > 0:
        estimated_llm_input_tokens = int(audit_summary.get("input_tokens_estimate") or 0)
        estimated_llm_output_tokens = int(audit_summary.get("output_tokens_estimate") or 0)
        openrouter_spend_usd = round(float(audit_summary.get("cost_estimate_usd") or 0.0), 4)
    else:
        openrouter_spend_usd = round(
            (estimated_llm_input_tokens / 1000.0) * llm_cost_per_1k_input_tokens_usd
            + (estimated_llm_output_tokens / 1000.0) * llm_cost_per_1k_output_tokens_usd,
            4,
        )
    llm_cost_per_deal_usd = round(openrouter_spend_usd / max(1, items_count), 4)
    cost_per_qualified_lead_usd = round(openrouter_spend_usd / max(1, qualified_count), 4)
    if qualified_count <= 0 and items_count >= 5:
        llm_cost_signal = "red"
    elif cost_per_qualified_lead_usd >= 2.0:
        llm_cost_signal = "yellow"
    else:
        llm_cost_signal = "ok"
    return {
        "audited_llm_requests": audited_llm_requests,
        "estimated_llm_input_tokens": estimated_llm_input_tokens,
        "estimated_llm_output_tokens": estimated_llm_output_tokens,
        "openrouter_spend_usd": openrouter_spend_usd,
        "llm_cost_per_deal_usd": llm_cost_per_deal_usd,
        "cost_per_qualified_lead_usd": cost_per_qualified_lead_usd,
        "llm_cost_signal": llm_cost_signal,
    }
