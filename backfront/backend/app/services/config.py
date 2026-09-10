"""Settings and auth services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

async def api_payme_auth_api_credentials(payload: TelegramApiCredentialsPayload):
    settings = _get_app_settings()
    settings["telegram_api_id"] = payload.api_id
    settings["telegram_api_hash"] = payload.api_hash
    settings = _save_app_settings(settings)
    api_id, api_hash = _resolve_telegram_api_credentials(settings)
    if not api_id or not api_hash:
        raise HTTPException(status_code=400, detail="Введите корректные Telegram api_id и api_hash")

    await telegram_sync.apply_api_credentials(api_id, api_hash)
    return TelegramAuthActionDTO(
        ok=True,
        message="Telegram api_id/api_hash сохранены. Теперь можно авторизоваться по телефону.",
        status=await _runtime_status(),
    )

async def api_payme_auth_code(payload: TelegramAuthCodePayload):
    try:
        message = await telegram_sync.submit_web_auth_code(payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram auth code failed: {exc}") from exc

    return TelegramAuthActionDTO(ok=True, message=message, status=await _runtime_status())

async def api_payme_auth_logout():
    try:
        await telegram_sync._reset_client(drop_session=True)
        telegram_sync._clear_auth_progress()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram logout failed: {exc}") from exc

    return TelegramAuthActionDTO(
        ok=True,
        message="Telegram-сессия удалена. Введите номер телефона для новой авторизации.",
        status=await _runtime_status(),
    )

async def api_payme_auth_password(payload: TelegramAuthPasswordPayload):
    try:
        message = await telegram_sync.submit_web_auth_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram auth password failed: {exc}") from exc

    return TelegramAuthActionDTO(ok=True, message=message, status=await _runtime_status())

async def api_payme_auth_phone(payload: TelegramAuthPhonePayload):
    try:
        _save_app_settings({"telegram_phone": payload.phone})
        message = await telegram_sync.start_web_auth(payload.phone, reset_session=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram auth start failed: {exc}") from exc

    return TelegramAuthActionDTO(ok=True, message=message, status=await _runtime_status())

async def api_payme_auth_phone_resend(payload: TelegramAuthPhoneResendPayload):
    try:
        _save_app_settings({"telegram_phone": payload.phone})
        message = await telegram_sync.start_web_auth(
            payload.phone,
            force_sms=bool(payload.force_sms),
            reset_session=bool(payload.reset_session),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram auth resend failed: {exc}") from exc

    return TelegramAuthActionDTO(ok=True, message=message, status=await _runtime_status())

async def api_payme_auth_reauthorize():
    try:
        await telegram_sync._reset_client(drop_session=True)
        telegram_sync._clear_auth_progress()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Telegram auth reset failed: {exc}") from exc

    return TelegramAuthActionDTO(
        ok=True,
        message="Сохраненная Telegram-сессия сброшена. Введите номер телефона для новой авторизации.",
        status=await _runtime_status(),
    )

async def api_payme_openrouter_models(
    query: str = Query(default=""),
    include_paid: bool = Query(default=False),
):
    return await asyncio.to_thread(_list_openrouter_models_sync, query, include_paid)

def api_payme_settings():
    return AppSettingsDTO(**_get_app_settings(), message="Настройки загружены")

async def api_payme_settings_save(payload: AppSettingsPayload):
    settings = _save_app_settings(payload.model_dump(exclude_unset=True))
    if settings.get("telegram_unlimited_import_enabled"):
        _enable_unlimited_import_for_all_selected_sources()
        settings = _get_app_settings()
    api_id, api_hash = _resolve_telegram_api_credentials(settings)
    await telegram_sync.apply_api_credentials(api_id, api_hash)
    if settings.get("ocr_images_enabled") and _iter_media_image_files():
        _ensure_pending_image_ocr_task(force=False)
    return AppSettingsDTO(**settings, message="Настройки сохранены")

def api_payme_settings_enable_unlimited_import():
    result = _enable_unlimited_import_for_all_selected_sources()
    _invalidate_import_limit_dependent_caches()
    _ensure_telegram_sync_job_after_import_limits("settings-unlimited-import")
    settings = _get_app_settings()
    return {
        **result,
        "settings": AppSettingsDTO(
            **settings,
            message=(
                "Безлимитная загрузка включена: все импортированные источники "
                "получили 0 мес. / 0 сообщений как режим без ограничений."
            ),
        ).model_dump(),
    }

def _ensure_telegram_sync_job_after_import_limits(reason: str) -> None:
    try:
        from app.services import jobs as jobs_service

        jobs_service.ensure_telegram_sync_job(reason=reason)
    except Exception as exc:
        try:
            _append_runtime_log("telegram-sync", f"Не удалось запустить Telegram sync после изменения лимитов: {exc}")
        except Exception:
            pass


def _invalidate_import_limit_dependent_caches() -> None:
    try:
        _api_snapshot_cache_clear_prefix("leads:")
        _api_snapshot_cache_clear_prefix("dashboard_summary:")
    except Exception:
        pass
    try:
        _lead_snapshot_cache["items"] = None
        _lead_snapshot_cache["updated_at"] = 0.0
    except Exception:
        pass


def api_payme_settings_apply_import_limits_all(payload: dict):
    unlimited = bool((payload or {}).get("unlimited", False))
    try:
        history_months = int((payload or {}).get("import_history_months", 1) or 0)
    except (TypeError, ValueError):
        history_months = 1
    try:
        message_limit = int((payload or {}).get("import_message_limit", 1000) or 0)
    except (TypeError, ValueError):
        message_limit = 1000
    result = _apply_import_limits_for_all_selected_sources(
        import_history_months=history_months,
        import_message_limit=message_limit,
        unlimited=unlimited,
    )
    _invalidate_import_limit_dependent_caches()
    _ensure_telegram_sync_job_after_import_limits("import-limits-all")
    settings = _get_app_settings()
    return {
        **result,
        "message": (
            "Безлимитные лимиты применены ко всем источникам, Telegram sync запущен"
            if unlimited
            else "Лимиты применены ко всем источникам, Telegram sync запущен"
        ),
        "settings": AppSettingsDTO(**settings, message="Настройки лимитов импорта обновлены").model_dump(),
    }

async def api_payme_system_reset_data():
    current = _build_data_reset_status()
    if current.get("running"):
        return current
    _update_data_reset_status(
        running=True,
        progress_percent=1,
        progress_label="Начинаю сброс производных данных",
        last_error="",
    )
    try:
        await asyncio.to_thread(_reset_runtime_data_preserving_settings_sync)
        _schedule_duckdb_sync(force_full=True)
        _update_data_reset_status(
            running=False,
            progress_percent=100,
            progress_label="Готово: данные сброшены, DuckDB переиндексируется заново",
            last_error="",
        )
    except Exception as exc:
        _update_data_reset_status(
            running=False,
            progress_label="Ошибка сброса данных",
            last_error=str(exc),
        )
    return _build_data_reset_status()

def api_payme_system_reset_data_status():
    return _build_data_reset_status()
