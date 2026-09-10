"""Telegram channel/source HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import channels as channels_schemas
from app.schemas import jobs as jobs_schemas
from app.services import channels as channels_service

router = APIRouter(tags=["payme"])


@router.post("/api/payme/source/reload")
async def api_payme_source_reload():
    return await channels_service.api_payme_source_reload()


@router.post("/api/payme/source/add", response_model=channels_schemas.SourceEditDTO)
async def api_payme_source_add(payload: channels_schemas.SourceSelectorPayload):
    return await channels_service.api_payme_source_add(payload)


@router.post("/api/payme/source/remove", response_model=channels_schemas.SourceEditDTO)
async def api_payme_source_remove(payload: channels_schemas.SourceSelectorPayload):
    return await channels_service.api_payme_source_remove(payload)


@router.get("/api/payme/source-policies", response_model=channels_schemas.SourcePolicyPageDTO)
def api_payme_source_policies():
    return channels_service.api_payme_source_policies()


@router.post("/api/payme/source-policy", response_model=channels_schemas.SourcePolicyActionDTO)
async def api_payme_source_policy(payload: channels_schemas.SourcePolicyPayload):
    return await channels_service.api_payme_source_policy(payload)


@router.get("/api/payme/telegram/dialogs", response_model=channels_schemas.TelegramDialogsPageDTO)
async def api_payme_telegram_dialogs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    show_channels: bool = Query(default=True),
    show_groups: bool = Query(default=True),
    show_private: bool = Query(default=True),
    show_bots: bool = Query(default=False),
    show_archived: bool = Query(default=False),
    membership_filter: str = Query(default="all"),
    sort_by: str = Query(default="last_date_desc"),
    force_refresh: bool = Query(default=False),
):
    return await channels_service.api_payme_telegram_dialogs(
        page=page,
        page_size=page_size,
        query=query,
        show_channels=show_channels,
        show_groups=show_groups,
        show_private=show_private,
        show_bots=show_bots,
        show_archived=show_archived,
        membership_filter=membership_filter,
        sort_by=sort_by,
        force_refresh=force_refresh,
    )


@router.post("/api/payme/telegram/dialogs/import", response_model=channels_schemas.TelegramDialogsImportDTO)
async def api_payme_telegram_dialogs_import(payload: channels_schemas.TelegramDialogsImportPayload):
    return await channels_service.api_payme_telegram_dialogs_import(payload)


@router.post("/api/payme/telegram/dialogs/settings", response_model=channels_schemas.TelegramDialogSettingsDTO)
async def api_payme_telegram_dialogs_settings(payload: channels_schemas.TelegramDialogSettingsPayload):
    return await channels_service.api_payme_telegram_dialogs_settings(payload)


@router.post("/api/payme/telegram/dialogs/remove-added", response_model=channels_schemas.TelegramDialogsRemoveAddedDTO)
async def api_payme_telegram_dialogs_remove_added(payload: channels_schemas.TelegramDialogsRemoveAddedPayload):
    return await channels_service.api_payme_telegram_dialogs_remove_added(payload)


@router.get("/api/payme/import-sync/status", response_model=channels_schemas.ImportSyncStatusDTO)
def api_payme_import_sync_status():
    return channels_service.api_payme_import_sync_status()


@router.post("/api/payme/import-sync/enable", response_model=channels_schemas.ImportSyncActionDTO)
async def api_payme_import_sync_enable():
    return await channels_service.api_payme_import_sync_enable()


@router.post("/api/payme/import-sync/disable", response_model=channels_schemas.ImportSyncActionDTO)
async def api_payme_import_sync_disable():
    return await channels_service.api_payme_import_sync_disable()


@router.get("/api/payme/telegram-sync/control")
def api_payme_telegram_sync_control():
    return channels_service.api_payme_telegram_sync_control()


@router.post("/api/payme/telegram-sync/pause")
async def api_payme_telegram_sync_pause(reason: str = Query(default="manual dashboard")):
    return await channels_service.api_payme_telegram_sync_pause(reason=reason)


@router.post("/api/payme/telegram-sync/resume")
async def api_payme_telegram_sync_resume(reason: str = Query(default="manual dashboard")):
    return await channels_service.api_payme_telegram_sync_resume(reason=reason)


@router.get("/api/payme/telegram-sync/job", response_model=jobs_schemas.JobProgressDTO)
def api_payme_telegram_sync_job_status():
    return channels_service.api_payme_telegram_sync_job_status()


@router.post("/api/payme/telegram-sync/run", response_model=jobs_schemas.JobCreateDTO)
def api_payme_telegram_sync_run(reason: str = Query(default="manual")):
    return channels_service.api_payme_telegram_sync_run(reason=reason)
