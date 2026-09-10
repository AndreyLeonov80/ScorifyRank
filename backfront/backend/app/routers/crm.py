"""CRM HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.schemas import crm as crm_schemas
from app.services import crm as crm_service
from app.services.crm_exports import amocrm as amocrm_service
from app.services.crm_exports import bitrix24 as bitrix24_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/crm/status", response_model=crm_schemas.AnalysisStatusDTO)
def api_payme_crm_status():
    return crm_service.api_payme_crm_status()


@router.post("/api/payme/crm/refresh", response_model=crm_schemas.AnalysisActionDTO)
async def api_payme_crm_refresh():
    return await crm_service.api_payme_crm_refresh()


@router.post("/api/payme/crm/config", response_model=crm_schemas.AnalysisActionDTO)
def api_payme_crm_config(payload: crm_schemas.AnalysisConfigPayload):
    return crm_service.api_payme_crm_config(payload)


@router.get("/api/payme/crm/contacts", response_model=crm_schemas.CrmContactsPageDTO)
def api_payme_crm_contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=1000, ge=1, le=5000),
    lead: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    only_name: bool = Query(default=False),
    only_phone: bool = Query(default=False),
    only_email: bool = Query(default=False),
    only_company: bool = Query(default=False),
    only_city: bool = Query(default=False),
    only_title: bool = Query(default=False),
):
    return crm_service.api_payme_crm_contacts(
        page=page,
        page_size=page_size,
        limit=limit,
        lead=lead,
        query=query,
        only_name=only_name,
        only_phone=only_phone,
        only_email=only_email,
        only_company=only_company,
        only_city=only_city,
        only_title=only_title,
    )


@router.post("/api/payme/crm/cleanup-telemost-phones")
async def api_payme_crm_cleanup_telemost_phones():
    return await crm_service.api_payme_crm_cleanup_telemost_phones()


@router.get("/api/payme/exports/bitrix24/settings")
def api_payme_exports_bitrix24_settings():
    return bitrix24_service.get_settings()


@router.post("/api/payme/exports/bitrix24/settings")
def api_payme_exports_bitrix24_save_settings(payload: bitrix24_service.Bitrix24ConnectionPayload):
    return bitrix24_service.save_settings(payload)


@router.post("/api/payme/exports/bitrix24/test")
def api_payme_exports_bitrix24_test():
    return bitrix24_service.test_connection()


@router.post("/api/payme/exports/bitrix24/setup")
def api_payme_exports_bitrix24_setup(payload: Optional[Dict[str, Any]] = None):
    return bitrix24_service.setup_custom_fields(dry_run=bool((payload or {}).get("dry_run")))


@router.post("/api/payme/exports/bitrix24/dry-run")
def api_payme_exports_bitrix24_dry_run(payload: Optional[bitrix24_service.Bitrix24RunPayload] = None):
    return bitrix24_service.dry_run(payload)


@router.post("/api/payme/exports/bitrix24/run")
def api_payme_exports_bitrix24_run(payload: bitrix24_service.Bitrix24RunPayload):
    return bitrix24_service.run_export(payload)


@router.post("/api/payme/exports/bitrix24/cancel")
def api_payme_exports_bitrix24_cancel(payload: Dict[str, Any]):
    return bitrix24_service.cancel_job(str(payload.get("job_id") or ""))


@router.get("/api/payme/exports/bitrix24/jobs")
def api_payme_exports_bitrix24_jobs():
    return bitrix24_service.list_jobs()


@router.get("/api/payme/exports/bitrix24/jobs/{job_id}")
def api_payme_exports_bitrix24_job(job_id: str):
    return bitrix24_service.get_job(job_id)


@router.get("/api/payme/exports/bitrix24/mappings")
def api_payme_exports_bitrix24_mappings():
    return bitrix24_service.list_mappings()


@router.get("/api/payme/exports/amocrm/settings")
def api_payme_exports_amocrm_settings():
    return amocrm_service.get_settings()


@router.post("/api/payme/exports/amocrm/settings")
def api_payme_exports_amocrm_save_settings(payload: amocrm_service.AmoCrmConnectionPayload):
    return amocrm_service.save_settings(payload)


@router.post("/api/payme/exports/amocrm/test")
def api_payme_exports_amocrm_test():
    return amocrm_service.test_connection()


@router.post("/api/payme/exports/amocrm/setup")
def api_payme_exports_amocrm_setup(payload: Optional[Dict[str, Any]] = None):
    return amocrm_service.setup_custom_fields(dry_run=bool((payload or {}).get("dry_run")))


@router.post("/api/payme/exports/amocrm/dry-run")
def api_payme_exports_amocrm_dry_run(payload: Optional[amocrm_service.AmoCrmRunPayload] = None):
    return amocrm_service.dry_run(payload)


@router.post("/api/payme/exports/amocrm/run")
def api_payme_exports_amocrm_run(payload: amocrm_service.AmoCrmRunPayload):
    return amocrm_service.run_export(payload)


@router.post("/api/payme/exports/amocrm/cancel")
def api_payme_exports_amocrm_cancel(payload: Dict[str, Any]):
    return amocrm_service.cancel_job(str(payload.get("job_id") or ""))


@router.get("/api/payme/exports/amocrm/jobs")
def api_payme_exports_amocrm_jobs():
    return amocrm_service.list_jobs()


@router.get("/api/payme/exports/amocrm/jobs/{job_id}")
def api_payme_exports_amocrm_job(job_id: str):
    return amocrm_service.get_job(job_id)


@router.get("/api/payme/exports/amocrm/mappings")
def api_payme_exports_amocrm_mappings():
    return amocrm_service.list_mappings()
