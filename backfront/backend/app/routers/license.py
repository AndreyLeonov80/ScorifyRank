"""License and tariff HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import license as license_schemas
from app.services import license as license_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/license/status", response_model=license_schemas.XFilesLicenseStatusDTO)
def api_payme_license_status():
    return license_service.api_payme_license_status()


@router.get("/api/payme/tariffs")
def api_payme_tariffs():
    return license_service.api_payme_tariffs()


@router.get("/api/payme/update/status")
def api_payme_update_status():
    return license_service.api_payme_update_status()


@router.post("/api/payme/license/activate", response_model=license_schemas.XFilesLicenseActionDTO)
def api_payme_license_activate(payload: license_schemas.XFilesLicenseActivatePayload):
    return license_service.api_payme_license_activate(payload)


@router.post("/api/payme/license/upgrade", response_model=license_schemas.XFilesLicenseActionDTO)
def api_payme_license_upgrade(payload: license_schemas.XFilesLicenseActivatePayload):
    return license_service.api_payme_license_upgrade(payload)


@router.post("/api/payme/license/renew", response_model=license_schemas.XFilesLicenseActionDTO)
def api_payme_license_renew(payload: license_schemas.XFilesLicenseActivatePayload):
    return license_service.api_payme_license_renew(payload)


@router.post("/api/payme/license/email/import", response_model=license_schemas.XFilesLicenseEmailImportDTO)
def api_payme_license_email_import():
    return license_service.api_payme_license_email_import()


@router.get("/api/payme/license/audit", response_model=list[license_schemas.XFilesLicenseAuditDTO])
def api_payme_license_audit(limit: int = Query(default=50, ge=1, le=500)):
    return license_service.api_payme_license_audit(limit=limit)


@router.get("/api/payme/license/menus", response_model=license_schemas.XFilesLicenseMenusDTO)
def api_payme_license_menus():
    return license_service.api_payme_license_menus()


@router.post("/api/payme/license/menus/check", response_model=license_schemas.XFilesLicenseMenuCheckDTO)
def api_payme_license_menus_check(payload: license_schemas.XFilesLicenseMenuCheckPayload):
    return license_service.api_payme_license_menus_check(payload)
