"""Chat analysis routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import analysis as analysis_schemas
from app.services import analysis as analysis_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/leads/{lead}/analysis/stats", response_model=analysis_schemas.ChatTokenStatsDTO)
def api_payme_lead_analysis_stats(lead: str):
    return analysis_service.api_payme_lead_analysis_stats(lead)


@router.get("/api/payme/leads/{lead}/analysis/history", response_model=analysis_schemas.ChatAnalysisHistoryDTO)
def api_payme_lead_analysis_history(lead: str):
    return analysis_service.api_payme_lead_analysis_history(lead)


@router.post("/api/payme/leads/{lead}/analysis/run", response_model=analysis_schemas.ChatAnalysisRunDTO)
async def api_payme_lead_analysis_run(lead: str, payload: analysis_schemas.ChatAnalysisPayload):
    return await analysis_service.api_payme_lead_analysis_run(lead, payload)


@router.post("/api/payme/llm-run")
async def api_payme_llm_run(payload: analysis_schemas.LlmRunPayload):
    return await analysis_service.api_payme_llm_run(payload)
