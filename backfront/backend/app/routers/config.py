"""Settings, auth, and setup HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Query

from app.schemas import config as config_schemas
from app.services import config as config_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/settings", response_model=config_schemas.AppSettingsDTO)
def api_payme_settings():
    return config_service.api_payme_settings()


@router.post("/api/payme/settings", response_model=config_schemas.AppSettingsDTO)
async def api_payme_settings_save(payload: config_schemas.AppSettingsPayload):
    return await config_service.api_payme_settings_save(payload)


@router.post("/api/payme/settings/import/unlimited", response_model=Dict[str, Any])
def api_payme_settings_enable_unlimited_import():
    return config_service.api_payme_settings_enable_unlimited_import()


@router.post("/api/payme/settings/import/limits-all", response_model=Dict[str, Any])
def api_payme_settings_apply_import_limits_all(payload: Dict[str, Any]):
    return config_service.api_payme_settings_apply_import_limits_all(payload)


@router.get("/api/payme/system/reset-data/status")
def api_payme_system_reset_data_status():
    return config_service.api_payme_system_reset_data_status()


@router.post("/api/payme/system/reset-data")
async def api_payme_system_reset_data():
    return await config_service.api_payme_system_reset_data()


@router.get("/api/payme/openrouter/models", response_model=config_schemas.OpenRouterModelsDTO)
async def api_payme_openrouter_models(
    query: str = Query(default=""),
    include_paid: bool = Query(default=False),
):
    return await config_service.api_payme_openrouter_models(query=query, include_paid=include_paid)


@router.post("/api/payme/auth/phone", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_phone(payload: config_schemas.TelegramAuthPhonePayload):
    return await config_service.api_payme_auth_phone(payload)


@router.post("/api/payme/auth/phone/resend", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_phone_resend(payload: config_schemas.TelegramAuthPhoneResendPayload):
    return await config_service.api_payme_auth_phone_resend(payload)


@router.post("/api/payme/auth/api-credentials", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_api_credentials(payload: config_schemas.TelegramApiCredentialsPayload):
    return await config_service.api_payme_auth_api_credentials(payload)


@router.post("/api/payme/auth/code", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_code(payload: config_schemas.TelegramAuthCodePayload):
    return await config_service.api_payme_auth_code(payload)


@router.post("/api/payme/auth/password", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_password(payload: config_schemas.TelegramAuthPasswordPayload):
    return await config_service.api_payme_auth_password(payload)


@router.post("/api/payme/auth/reauthorize", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_reauthorize():
    return await config_service.api_payme_auth_reauthorize()


@router.post("/api/payme/auth/logout", response_model=config_schemas.TelegramAuthActionDTO)
async def api_payme_auth_logout():
    return await config_service.api_payme_auth_logout()
