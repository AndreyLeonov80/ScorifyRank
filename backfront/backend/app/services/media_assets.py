"""Media and OCR asset helpers extracted from the legacy backend."""

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

def _call_ocr_service_sync(image_path: Path, force: bool = False) -> Optional[Path]:
    service_url = _ocr_service_url()
    if not service_url:
        raise RuntimeError("OCR service URL is empty. Set it in Settings or PAYME_OCR_SERVICE_URL.")
    relative_path = _ocr_relative_image_path(image_path)
    txt_path = _ocr_text_path_for_image(image_path)
    upload_supported = True

    try:
        with image_path.open("rb") as image_file:
            response = requests.post(
                f"{service_url}/ocr/upload",
                data={
                    "relative_path": relative_path,
                    "force": str(bool(force)).lower(),
                },
                files={
                    "file": (image_path.name, image_file, "application/octet-stream"),
                },
                timeout=OCR_REQUEST_TIMEOUT_SEC,
            )
        if response.status_code in {404, 405}:
            upload_supported = False
        else:
            response.raise_for_status()
            payload = response.json()
            if "text" in payload:
                txt_path.write_text(str(payload.get("text") or ""), encoding="utf-8")
                return txt_path
            txt_relative_path = str(payload.get("text_relative_path") or "").strip()
            if txt_relative_path:
                return (PAYME_OUT_DIR / txt_relative_path).resolve()
            return txt_path
    except requests.Timeout as exc:
        raise RuntimeError(f"OCR service upload timed out after {OCR_REQUEST_TIMEOUT_SEC:g}s: {exc}") from exc
    except requests.HTTPError as exc:
        raise RuntimeError(f"OCR service upload failed: HTTP {response.status_code} {response.text[:240]}") from exc
    except requests.RequestException as exc:
        raise RuntimeError(f"OCR service upload failed: {exc}") from exc

    if not upload_supported and not image_path.exists():
        raise RuntimeError("OCR upload endpoint is unsupported and local shared media file is unavailable.")
    response = requests.post(
        f"{service_url}/ocr/file",
        json={
            "relative_path": relative_path,
            "force": bool(force),
        },
        timeout=OCR_REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()
    payload = response.json()
    txt_relative_path = str(payload.get("text_relative_path") or "").strip()
    if txt_relative_path:
        return (PAYME_OUT_DIR / txt_relative_path).resolve()
    return txt_path


def _image_ocr_progress_log(message: str) -> None:
    timestamp = _utc_now().strftime("%Y-%m-%d %H:%M:%S")
    current_log = _image_ocr_status.get("progress_log")
    if not isinstance(current_log, list):
        current_log = []
    _image_ocr_status["progress_log"] = [f"{timestamp} {str(message or '').strip()}"] + current_log[:19]


def _build_media_status() -> "MediaStatusDTO":
    image_files = _iter_media_image_files()
    total_images = len(image_files)
    images_bytes = 0
    for image_path in image_files:
        try:
            images_bytes += int(image_path.stat().st_size)
        except OSError:
            continue
    pending_count = _count_pending_image_ocr_files()
    processed_count = int(_image_ocr_status.get("processed_count", 0) or 0)
    error_count = int(_image_ocr_status.get("error_count", 0) or 0)
    crm_rows_created = int(_image_ocr_status.get("crm_rows_created", 0) or 0)
    deleted_images = int(_image_ocr_status.get("deleted_images", 0) or 0)
    progress_total = int(_image_ocr_status.get("progress_total", 0) or 0)
    progress_current = int(_image_ocr_status.get("progress_current", 0) or 0)
    progress_percent = float(_image_ocr_status.get("progress_percent", 0.0) or 0.0)
    running = bool(_image_ocr_status.get("running", False))
    ocr_setting_enabled = _media_ocr_images_enabled()
    ocr_available = _ocr_is_enabled()
    selected_leads = _get_media_selected_leads()
    enabled = ocr_setting_enabled and len(selected_leads) > 0
    media_backfill = _media_backfill_summary(selected_leads)
    media_backfill_running = bool(media_backfill.get("running"))
    running = running or media_backfill_running
    stale_reason = None
    if not ocr_setting_enabled:
        stale_reason = "OCR изображений выключен в настройках."
    elif not ocr_available:
        stale_reason = "OCR backend недоступен. Поднимите gramlead-ocr или включите локальный fallback."
    elif enabled and pending_count > 0 and not running:
        stale_reason = "Есть изображения без OCR. Запустите распознавание или дождитесь фоновой обработки."

    if running and progress_total <= 0:
        progress_total = max(1, pending_count + processed_count)
        progress_current = min(progress_total, max(0, processed_count))
        progress_percent = round((progress_current / progress_total) * 100.0, 2) if progress_total > 0 else 0.0

    progress_label = "OCR отключён"
    if not ocr_setting_enabled:
        progress_label = "OCR изображений выключен"
    elif media_backfill_running and not bool(_image_ocr_status.get("running", False)):
        progress_label = "Идёт скачивание изображений из Telegram"
        if progress_total <= 0:
            progress_current = int(media_backfill.get("checked", 0) or 0)
            progress_total = max(progress_current + 1, 1)
            progress_percent = min(99.0, round((progress_current / progress_total) * 100.0, 2))
    elif bool(_image_ocr_status.get("running", False)):
        progress_label = "Идёт распознавание изображений"
    elif pending_count > 0:
        progress_label = "Есть изображения без OCR"
    elif total_images > 0:
        progress_label = "OCR-кеш готов"
    elif enabled and int(media_backfill.get("downloaded", 0) or 0) > 0:
        progress_label = (
            "Изображения скачаны, OCR обработал и удалил файлы"
            if _media_ocr_delete_images_enabled()
            else "Изображения скачаны, OCR обработал, файлы сохранены"
        )
    elif enabled and int(media_backfill.get("done_count", 0) or 0) > 0:
        progress_label = "История media проверена: изображений не найдено"
    elif enabled and int(media_backfill.get("waiting_count", 0) or 0) > 0:
        progress_label = "Жду подключение Telegram-чата для media"
    else:
        progress_label = "Изображений пока нет"

    if (
        enabled
        and not running
        and progress_total <= 0
        and int(media_backfill.get("done_count", 0) or 0) > 0
        and int(media_backfill.get("checked", 0) or 0) > 0
    ):
        progress_current = int(media_backfill.get("checked", 0) or 0)
        progress_total = progress_current
        progress_percent = 100.0

    progress_log = [str(item) for item in (_image_ocr_status.get("progress_log") or []) if str(item or "").strip()]
    if enabled:
        lead_status_lines = [
            f"{str(item.get('lead') or '').strip()}: {str(item.get('status_label') or '').strip()} · проверено {int(item.get('checked', 0) or 0)} · скачано {int(item.get('downloaded', 0) or 0)}"
            for item in (media_backfill.get("lead_rows") or [])[:8]
            if str(item.get("lead") or "").strip()
        ]
        progress_log = [
            f"Media: выбрано чатов {len(selected_leads)}, активно {int(media_backfill.get('active_count', 0) or 0)}, проверено сообщений {int(media_backfill.get('checked', 0) or 0)}, скачано изображений {int(media_backfill.get('downloaded', 0) or 0)}.",
            *lead_status_lines,
            *progress_log,
        ]
        active_leads = [str(item) for item in media_backfill.get("active_leads") or [] if str(item or "").strip()]
        waiting_leads = [str(item) for item in media_backfill.get("waiting_leads") or [] if str(item or "").strip()]
        if active_leads:
            progress_log.insert(1, f"Скачивание media активно: {', '.join(active_leads[:5])}.")
        if waiting_leads:
            progress_log.insert(1, f"Жду Telegram entity для media: {', '.join(waiting_leads[:5])}.")

    return MediaStatusDTO(
        enabled=enabled,
        interval_sec=int(MEDIA_OCR_LOOP_INTERVAL_SEC),
        running=running,
        cache_ready=total_images > 0 or processed_count > 0 or crm_rows_created > 0,
        total_rows=total_images,
        ocr_enabled=ocr_setting_enabled,
        ocr_available=ocr_available,
        ocr_mode=_ocr_mode(),
        ocr_service_url=_ocr_service_url(),
        pending_count=pending_count,
        processed_count=processed_count,
        error_count=error_count,
        crm_rows_created=crm_rows_created,
        deleted_images=deleted_images,
        images_bytes=images_bytes,
        progress_current=progress_current,
        progress_total=progress_total,
        progress_percent=progress_percent,
        progress_label=progress_label,
        current_item=_image_ocr_status.get("current_item") or str(media_backfill.get("current_lead") or "") or None,
        progress_started_at=_image_ocr_status.get("last_started_at"),
        progress_log=progress_log,
        selected_leads_count=len(selected_leads),
        media_backfill_running=media_backfill_running,
        media_backfill_checked=int(media_backfill.get("checked", 0) or 0),
        media_backfill_downloaded=int(media_backfill.get("downloaded", 0) or 0),
        media_backfill_done_count=int(media_backfill.get("done_count", 0) or 0),
        media_backfill_active_count=int(media_backfill.get("active_count", 0) or 0),
        media_backfill_waiting_count=int(media_backfill.get("waiting_count", 0) or 0),
        media_backfill_leads=[dict(item) for item in (media_backfill.get("lead_rows") or [])],
        last_refresh_at=_image_ocr_status.get("last_finished_at"),
        last_error=_image_ocr_status.get("last_error"),
        next_refresh_at=None,
        stale_reason=stale_reason,
    )


def _media_backfill_summary(selected_leads: Optional[List[str]] = None) -> Dict[str, Any]:
    leads = selected_leads if selected_leads is not None else _get_media_selected_leads()
    tasks = getattr(telegram_sync, "_chat_media_backfill_tasks", {}) or {}
    checked = 0
    downloaded = 0
    done_count = 0
    active_leads: List[str] = []
    waiting_leads: List[str] = []
    lead_rows: List[Dict[str, Any]] = []

    for lead in leads:
        lead_key = _normalize_media_lead(lead)
        if not lead_key:
            continue
        chat_state = telegram_sync.get_chat_state(lead_key)
        lead_checked = int(chat_state.get("media_backfill_items_checked", 0) or 0)
        lead_downloaded = int(chat_state.get("media_backfill_images_downloaded", 0) or 0)
        lead_done = bool(chat_state.get("media_backfill_done"))
        checked += lead_checked
        downloaded += lead_downloaded
        if lead_done:
            done_count += 1

        task = tasks.get(lead_key)
        lead_running = bool(task is not None and not task.done())
        lead_waiting = False
        if lead_running:
            active_leads.append(lead_key)
        elif lead_key not in telegram_sync.entities_by_chat_key and not lead_done:
            lead_waiting = True
            waiting_leads.append(lead_key)

        if lead_running:
            status_label = "Идёт обработка media"
        elif lead_waiting:
            status_label = "Жду подключение Telegram-чата"
        elif lead_done and lead_downloaded > 0:
            status_label = (
                f"Готово: скачано {lead_downloaded}, OCR обработал и удалил файлы"
                if _media_ocr_delete_images_enabled()
                else f"Готово: скачано {lead_downloaded}, OCR обработал, файлы сохранены"
            )
        elif lead_done:
            status_label = "Готово: изображений не найдено"
        elif lead_checked > 0 or lead_downloaded > 0:
            status_label = "Проверка остановлена, можно переобработать"
        else:
            status_label = "Ожидает проверки"

        lead_rows.append({
            "lead": lead_key,
            "checked": lead_checked,
            "downloaded": lead_downloaded,
            "done": lead_done,
            "running": lead_running,
            "waiting": lead_waiting,
            "status_label": status_label,
            "started_at": chat_state.get("media_backfill_started_at"),
            "updated_at": chat_state.get("media_backfill_updated_at"),
            "completed_at": chat_state.get("media_backfill_completed_at"),
        })

    return {
        "selected_count": len(leads),
        "running": bool(active_leads),
        "checked": checked,
        "downloaded": downloaded,
        "done_count": done_count,
        "active_count": len(active_leads),
        "waiting_count": len(waiting_leads),
        "active_leads": active_leads,
        "waiting_leads": waiting_leads,
        "lead_rows": lead_rows,
        "current_lead": active_leads[0] if active_leads else (waiting_leads[0] if waiting_leads else ""),
    }


def _is_media_enabled_for_chat(chat_key: str) -> bool:
    if not _media_ocr_images_enabled():
        return False
    return _normalize_media_lead(chat_key) in set(_get_media_selected_leads())


def _find_media_record_for_image_sync(image_path: Path) -> Dict[str, Any]:
    lead_name = image_path.parent.parent.name
    message_id = _media_image_message_id(image_path)
    source_selector = _managed_selector_map().get(lead_name.lower())

    if duckdb is not None and DUCKDB_PATH.exists():
        try:
            conn = _duckdb_connect_readonly()
            try:
                row = conn.execute(
                    """
                    SELECT chat_id, chat_username, chat_title, sender_id, sender_username,
                           sender_name, message_id, text, date_utc_raw, reply_to_msg_id,
                           has_media, media_path
                    FROM messages_raw
                    WHERE message_id = ?
                      AND (
                        lower(source_jsonl) = lower(?)
                        OR lower(source_jsonl) LIKE lower(?)
                      )
                    ORDER BY coalesce(date_utc_raw, '') DESC
                    LIMIT 1
                    """,
                    [message_id, f"{lead_name}.jsonl", f"%/{lead_name}.jsonl"],
                ).fetchone()
            finally:
                conn.close()
            if row:
                return {
                    "chat": {
                        "id": _duckdb_optional_int(row[0]),
                        "username": str(row[1] or "") or source_selector or lead_name,
                        "title": str(row[2] or "") or lead_name,
                    },
                    "sender": {
                        "id": _duckdb_optional_int(row[3]),
                        "username": str(row[4] or "") or None,
                        "name": str(row[5] or "") or None,
                    },
                    "message": {
                        "id": int(row[6] or message_id),
                        "text": str(row[7] or ""),
                        "date_utc": str(row[8] or ""),
                        "reply_to_msg_id": _duckdb_optional_int(row[9]),
                        "has_media": bool(row[10]),
                        "media_path": str(row[11] or "") or "/" + _path_to_app_relative(image_path).lstrip("/"),
                    },
                }
        except Exception as exc:
            _image_ocr_progress_log(f"DuckDB lookup для media не удался: {exc}")

    jsonl_path = PAYME_OUT_DIR / f"{lead_name}.jsonl"
    if jsonl_path.exists():
        for rec in _iter_jsonl(jsonl_path):
            msg = rec.get("message", {}) if isinstance(rec, dict) else {}
            try:
                if int(msg.get("id") or 0) != message_id:
                    continue
            except (TypeError, ValueError):
                continue
            return rec

    try:
        modified_at = datetime.fromtimestamp(image_path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        modified_at = _utc_now().isoformat()
    return {
        "chat": {"id": None, "username": source_selector or lead_name, "title": lead_name},
        "sender": {"id": None, "username": None, "name": None},
        "message": {
            "id": message_id,
            "text": "",
            "date_utc": modified_at,
            "reply_to_msg_id": None,
            "has_media": True,
            "media_path": "/" + _path_to_app_relative(image_path).lstrip("/"),
        },
    }


def _ensure_pending_image_ocr_task(force: bool = False) -> bool:
    global _image_ocr_task
    if not _media_ocr_images_enabled():
        _image_ocr_status["available"] = False
        _image_ocr_status["mode"] = _ocr_mode()
        _image_ocr_status["last_error"] = "OCR изображений выключен в настройках."
        _image_ocr_progress_log(_image_ocr_status["last_error"])
        return False
    if not _ocr_is_enabled():
        _image_ocr_status["available"] = False
        _image_ocr_status["mode"] = _ocr_mode()
        _image_ocr_status["last_error"] = "OCR backend недоступен. Отдельный сервис gramlead-ocr не запущен."
        _image_ocr_progress_log(_image_ocr_status["last_error"])
        return False
    if _image_ocr_task and not _image_ocr_task.done():
        return False
    _image_ocr_task = asyncio.create_task(_run_pending_image_ocr(force=force))
    return True


def _list_image_assets(limit: int = 1000, include_ocr_preview: bool = False) -> List[ImageAssetDTO]:
    assets: List[ImageAssetDTO] = []
    seen_text_paths: set[Path] = set()
    image_paths = _iter_media_image_files()
    for image_path in image_paths:
        lead = image_path.parent.parent.name
        txt_path = _ocr_text_path_for_image(image_path)
        recognized = txt_path.exists()
        if recognized:
            seen_text_paths.add(txt_path.resolve())
        ocr_preview = None
        if recognized and include_ocr_preview:
            try:
                ocr_preview = _image_preview_text(txt_path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                ocr_preview = None

        try:
            modified_at = datetime.fromtimestamp(image_path.stat().st_mtime, tz=timezone.utc).isoformat()
            size_bytes = int(image_path.stat().st_size)
        except OSError:
            modified_at = None
            size_bytes = 0

        assets.append(
            ImageAssetDTO(
                lead=lead,
                file_name=image_path.name,
                media_path="/" + _path_to_app_relative(image_path).lstrip("/"),
                text_path="/" + _path_to_app_relative(txt_path).lstrip("/") if recognized else None,
                image_exists=True,
                recognized=recognized,
                ocr_preview=ocr_preview,
                modified_at=modified_at,
                size_bytes=size_bytes,
            )
        )

    for txt_path in _iter_media_text_files():
        if txt_path.resolve() in seen_text_paths:
            continue
        lead = txt_path.parent.parent.name
        ocr_preview = None
        if include_ocr_preview:
            try:
                ocr_preview = _image_preview_text(txt_path.read_text(encoding="utf-8", errors="replace"))
            except Exception:
                ocr_preview = None

        try:
            modified_at = datetime.fromtimestamp(txt_path.stat().st_mtime, tz=timezone.utc).isoformat()
            size_bytes = int(txt_path.stat().st_size)
        except OSError:
            modified_at = None
            size_bytes = 0

        assets.append(
            ImageAssetDTO(
                lead=lead,
                file_name=txt_path.name,
                media_path="/" + _path_to_app_relative(txt_path).lstrip("/"),
                text_path="/" + _path_to_app_relative(txt_path).lstrip("/"),
                image_exists=False,
                recognized=True,
                ocr_preview=ocr_preview,
                modified_at=modified_at,
                size_bytes=size_bytes,
            )
        )

    assets.sort(key=lambda item: item.modified_at or "", reverse=True)
    return assets[: max(limit, 1)]


__all__ = [
    "refresh_legacy_globals",
    "_build_media_status",
    "_call_ocr_service_sync",
    "_ensure_pending_image_ocr_task",
    "_find_media_record_for_image_sync",
    "_image_ocr_progress_log",
    "_is_media_enabled_for_chat",
    "_list_image_assets",
    "_media_backfill_summary",
]
