"""Job progress routes used by dashboard and long-running frontend popups."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas import jobs as jobs_schemas
from app.services import jobs as jobs_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/jobs", response_model=jobs_schemas.JobsPageDTO)
def api_payme_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    type: Optional[str] = Query(default=None),
):
    return jobs_service.list_jobs(page=page, page_size=page_size, status=status, job_type=type)


@router.post("/api/payme/jobs", response_model=jobs_schemas.JobCreateDTO)
def api_payme_jobs_create(payload: jobs_schemas.JobCreatePayload):
    return jobs_service.enqueue_job(payload)


@router.post("/api/payme/analysis/run", response_model=jobs_schemas.JobCreateDTO)
def api_payme_analysis_run_as_job(payload: jobs_schemas.JobCreatePayload):
    if not payload.type:
        payload.type = "llm_analysis"
    return jobs_service.enqueue_job(payload)


@router.get("/api/payme/jobs/{job_id}", response_model=jobs_schemas.JobProgressDTO)
def api_payme_job(job_id: str):
    return jobs_service.get_job(job_id)


@router.get("/api/payme/jobs/{job_id}/events", response_model=jobs_schemas.JobEventsPageDTO)
def api_payme_job_events(
    job_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    return jobs_service.list_events(job_id=job_id, page=page, page_size=page_size)


@router.post("/api/payme/jobs/{job_id}/cancel", response_model=jobs_schemas.JobCancelDTO)
def api_payme_job_cancel(job_id: str):
    return jobs_service.cancel_job(job_id)
