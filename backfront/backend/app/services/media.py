"""Media/image routes extracted from the monolith."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
legacy.refresh_globals(globals(), setdefault=True)

from app.services.media_assets import (
    _build_media_status,
    _call_ocr_service_sync,
    _ensure_pending_image_ocr_task,
    _find_media_record_for_image_sync,
    _image_ocr_progress_log,
    _is_media_enabled_for_chat,
    _list_image_assets,
    _media_backfill_summary,
)

def api_payme_images(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=1000, ge=1, le=5000),
    query: str = Query(default=""),
    lead_filter: str = Query(default=""),
    recognized_only: bool = Query(default=False),
    pending_only: bool = Query(default=False),
):
    normalized_query = str(query or "").strip().lower()
    normalized_lead_filter = str(lead_filter or "").strip().lower()
    items = _list_image_assets(limit=limit, include_ocr_preview=True)
    filtered = _filter_image_assets(
        items,
        query=normalized_query,
        lead_filter=normalized_lead_filter,
        recognized_only=recognized_only,
        pending_only=pending_only,
    )
    return ImageAssetsPageDTO(**_paginate_items(filtered, page=page, page_size=page_size))

def api_payme_image_text(media_path: str = Query(..., min_length=1)):
    image_path = _app_relative_to_abs_path(media_path)
    if image_path.suffix.lower() == ".txt":
        txt_path = image_path
    else:
        txt_path = _ocr_text_path_for_image(image_path)

    if image_path.suffix.lower() != ".txt" and (not image_path.exists() or not _is_supported_image_file(image_path)) and not txt_path.exists():
        raise HTTPException(status_code=404, detail="Изображение или OCR-текст не найден")
    if image_path.suffix.lower() == ".txt" and not txt_path.exists():
        raise HTTPException(status_code=404, detail="OCR-текст не найден")

    recognized = txt_path.exists()
    text = ""
    preview = None
    crm_fields: List[Dict[str, str]] = []
    if recognized:
        try:
            text = txt_path.read_text(encoding="utf-8", errors="replace")
            preview = _image_preview_text(text)
            crm_fields = _media_ocr_crm_fields_from_text(text)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Не удалось прочитать OCR-текст: {exc}") from exc

    return ImageAssetTextDTO(
        media_path="/" + _path_to_app_relative(image_path).lstrip("/"),
        text_path="/" + _path_to_app_relative(txt_path).lstrip("/") if recognized else None,
        recognized=recognized,
        text=text,
        preview=preview,
        crm_fields=crm_fields,
        crm_categories=_crm_unique_list([str(item.get("field_label") or "") for item in crm_fields if item.get("field_label")]),
    )

def api_payme_media_config():
    return MediaConfigDTO(
        ok=True,
        message="Настройки media загружены",
        selected_leads=_get_media_selected_leads(),
    )

def api_payme_media_status():
    return _cached_sync_snapshot("media_status", _build_media_status)

def api_payme_media_add(payload: MediaLeadPayload):
    leads = _get_media_selected_leads()
    target = _normalize_media_lead(payload.lead)
    if not target:
        raise HTTPException(status_code=400, detail="Укажите чат для media")
    if target not in leads:
        leads.append(target)
    selected = _set_media_selected_leads(leads)
    try:
        chat_state = telegram_sync.get_chat_state(target)
        chat_state["media_backfill_done"] = False
        chat_state["media_backfill_offset_id"] = 0
        chat_state["media_backfill_items_checked"] = 0
        chat_state["media_backfill_images_downloaded"] = 0
        chat_state["media_backfill_started_at"] = None
        chat_state["media_backfill_completed_at"] = None
        telegram_sync.save_state()
    except Exception as exc:
        _image_ocr_progress_log(
            f"Media для {target}: не удалось сбросить состояние backfill ({exc}), продолжаю без падения UI."
        )
    _image_ocr_progress_log(
        f"Media включено для {target}. История будет проверена на изображения, новые изображения тоже пойдут в OCR автоматически."
    )
    try:
        entity = telegram_sync.entities_by_chat_key.get(target)
        if entity is not None:
            telegram_sync.start_media_backfill_in_background(entity, target, force=True)
        else:
            _image_ocr_progress_log(f"Media для {target}: жду подключение Telegram-чата, затем начну скачивание изображений.")
    except Exception as exc:
        _image_ocr_progress_log(
            f"Media для {target}: добавлено в список, но backfill не стартовал сразу ({exc}). Фоновый цикл повторит позже."
        )
    try:
        if _count_pending_image_ocr_files() > 0:
            _ensure_pending_image_ocr_task(force=False)
    except Exception as exc:
        _image_ocr_progress_log(f"Media для {target}: OCR-задача будет запущена позже ({exc}).")
    return MediaConfigDTO(
        ok=True,
        message=f"Media включено для '{target}'",
        selected_leads=selected,
    )

def api_payme_media_add_many(payload: MediaLeadsPayload):
    raw_leads = payload.leads or []
    normalized_targets: List[str] = []
    seen_targets = set()
    for raw_lead in raw_leads:
        target = _normalize_media_lead(raw_lead)
        if not target or target in seen_targets:
            continue
        seen_targets.add(target)
        normalized_targets.append(target)

    if not normalized_targets:
        return MediaConfigDTO(
            ok=True,
            message="Нет чатов для включения media",
            selected_leads=_get_media_selected_leads(),
        )

    leads = _get_media_selected_leads()
    existing = set(leads)
    added: List[str] = []
    for target in normalized_targets:
        if target in existing:
            continue
        leads.append(target)
        existing.add(target)
        added.append(target)

    selected = _set_media_selected_leads(leads)
    for target in added:
        try:
            chat_state = telegram_sync.get_chat_state(target)
            chat_state["media_backfill_done"] = False
            chat_state["media_backfill_offset_id"] = 0
            chat_state["media_backfill_items_checked"] = 0
            chat_state["media_backfill_images_downloaded"] = 0
            chat_state["media_backfill_started_at"] = None
            chat_state["media_backfill_completed_at"] = None
        except Exception as exc:
            _image_ocr_progress_log(
                f"Media для {target}: не удалось подготовить состояние backfill ({exc}), фоновый цикл повторит позже."
            )

    try:
        telegram_sync.save_state()
    except Exception as exc:
        _image_ocr_progress_log(f"Media: не удалось сохранить состояние Telegram после массового добавления ({exc}).")

    if added:
        _image_ocr_progress_log(
            f"Media: массово включено {len(added)} чатов. Фоновый OCR loop начнёт обработку по очереди."
        )
    else:
        _image_ocr_progress_log("Media: все выбранные чаты уже были включены.")

    return MediaConfigDTO(
        ok=True,
        message=f"Media включено для чатов: {len(added)}",
        selected_leads=selected,
    )

def api_payme_media_remove(payload: MediaLeadPayload):
    target = _normalize_media_lead(payload.lead)
    selected = _set_media_selected_leads([lead for lead in _get_media_selected_leads() if lead != target])
    _image_ocr_progress_log(f"Media выключено для {target}.")
    return MediaConfigDTO(
        ok=True,
        message=f"Media выключено для '{target}'",
        selected_leads=selected,
    )

def api_payme_media_clear(payload: MediaLeadPayload):
    target = _normalize_media_lead(payload.lead)
    result = _clear_media_for_lead(target)
    return MediaClearDTO(
        ok=True,
        message=f"Media очищено для '{target}'",
        deleted_images=int(result.get("deleted_images", 0)),
        deleted_texts=int(result.get("deleted_texts", 0)),
        selected_leads=_get_media_selected_leads(),
    )

def api_payme_media_clear_all():
    result = _clear_all_media_images()
    return MediaClearDTO(
        ok=True,
        message="Все сохранённые изображения удалены",
        deleted_images=int(result.get("deleted_images", 0)),
        deleted_texts=int(result.get("deleted_texts", 0)),
        selected_leads=_get_media_selected_leads(),
    )

async def api_payme_images_ocr_pending():
    if not _media_ocr_images_enabled():
        _image_ocr_status["available"] = False
        _image_ocr_status["mode"] = _ocr_mode()
        _image_ocr_status["last_error"] = "OCR изображений выключен в настройках."
        return ImageOcrActionDTO(
            ok=False,
            message="OCR изображений выключен в настройках.",
            available=False,
            mode=_ocr_mode(),
            running=False,
            pending_count=_count_pending_image_ocr_files(),
            processed_count=int(_image_ocr_status.get("processed_count", 0) or 0),
            error_count=int(_image_ocr_status.get("error_count", 0) or 0),
            last_started_at=_image_ocr_status.get("last_started_at"),
            last_finished_at=_image_ocr_status.get("last_finished_at"),
            last_error=_image_ocr_status.get("last_error"),
        )
    if not _ocr_is_enabled():
        _image_ocr_status["available"] = False
        _image_ocr_status["mode"] = _ocr_mode()
        _image_ocr_status["last_error"] = "OCR отключён. Поднимите gramlead-ocr отдельно."
        return ImageOcrActionDTO(
            ok=False,
            message="OCR отключён. Поднимите gramlead-ocr отдельно.",
            available=False,
            mode=_ocr_mode(),
            running=False,
            pending_count=_count_pending_image_ocr_files(),
            processed_count=int(_image_ocr_status.get("processed_count", 0) or 0),
            error_count=int(_image_ocr_status.get("error_count", 0) or 0),
            last_started_at=_image_ocr_status.get("last_started_at"),
            last_finished_at=_image_ocr_status.get("last_finished_at"),
            last_error=_image_ocr_status.get("last_error"),
        )
    started = _ensure_pending_image_ocr_task(force=False)
    pending_count = _count_pending_image_ocr_files()
    return ImageOcrActionDTO(
        ok=bool(started or _image_ocr_status.get("running", False)),
        message="Запущено распознавание изображений без .txt" if started else "Распознавание уже выполняется",
        available=bool(_image_ocr_status.get("available", False)),
        mode=str(_image_ocr_status.get("mode", _ocr_mode())),
        running=bool(_image_ocr_status.get("running", False)),
        pending_count=pending_count,
        processed_count=int(_image_ocr_status.get("processed_count", 0) or 0),
        error_count=int(_image_ocr_status.get("error_count", 0) or 0),
        last_started_at=_image_ocr_status.get("last_started_at"),
        last_finished_at=_image_ocr_status.get("last_finished_at"),
        last_error=_image_ocr_status.get("last_error"),
    )
