"""Telegram source, dialog cache, source policy, and lightweight lead helpers."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Union

from fastapi import HTTPException
from app.core.telethon_compat import FloodWaitError, PeerFloodError, TelegramClient, TelegramMessage, UserPrivacyRestrictedError
from app.schemas.compat_models import TelegramDialogDTO

_SELECTOR_LOOKUP_CACHE_TTL_SEC = 1.0
_selector_lookup_cache: Dict[str, Any] = {"updated_at": 0.0, "maps": None}


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime") or sys.modules.get("back")
    if runtime is None:
        return
    for name, value in vars(runtime).items():
        if not name.startswith("__") and name != "refresh_legacy_globals":
            globals()[name] = value


def _sync_runtime_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime") or sys.modules.get("back")
    if runtime is None:
        return
    for name in (
        "_telegram_dialogs_cache",
        "_telegram_dialogs_refresh_task",
        "_dialog_meta_cache",
        "_lead_snapshot_cache",
        "_lead_snapshot_refresh_task",
    ):
        if name in globals():
            setattr(runtime, name, globals()[name])


def _with_legacy_globals(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        refresh_legacy_globals()
        result = func(*args, **kwargs)
        _sync_runtime_globals()
        return result

    return wrapper


def _with_legacy_globals_async(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        refresh_legacy_globals()
        result = await func(*args, **kwargs)
        _sync_runtime_globals()
        return result

    return wrapper


refresh_legacy_globals()

def _source_selectors_state_list() -> List[str]:
    sync = globals().get("telegram_sync")
    if sync is not None and not getattr(sync, "state", None):
        try:
            sync.state = sync.load_state()
        except Exception:
            pass
    state = getattr(sync, "state", {}) if sync is not None else {}
    if not isinstance(state, dict):
        return []
    raw_items = state.get(SOURCE_SELECTORS_STATE_KEY)
    if not isinstance(raw_items, list):
        raw_items = []

    unique_selectors: List[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        try:
            normalized = _normalize_source_selector(raw)
        except Exception:
            continue
        identity = _selector_identity(normalized)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique_selectors.append(normalized)

    if raw_items != unique_selectors:
        state[SOURCE_SELECTORS_STATE_KEY] = unique_selectors
        if sync is not None:
            try:
                sync.save_state()
            except Exception:
                pass
    return unique_selectors


async def _refresh_analysis_cache_async(kind: AnalysisKind, force_full: bool = False) -> None:
    state = _analysis_state(kind)
    state["running"] = True
    state["last_error"] = None
    state["progress_started_at"] = _utc_now().isoformat()
    if duckdb is not None and _DUCKDB_SYNC_ENABLED and (force_full or _duckdb_due()):
        _schedule_duckdb_sync(force_full=force_full)
    if kind != "contacts":
        state["progress_current"] = 0
        state["progress_total"] = 0
        state["progress_percent"] = 0.0
        state["progress_label"] = "Подготовка"
        state["current_item"] = None
        state["progress_log"] = []
    telegram_sync.save_state()
    try:
        if kind == "crm":
            await asyncio.to_thread(_refresh_crm_cache_sync, force_full)
        elif kind == "contacts":
            await asyncio.to_thread(_refresh_contacts_cache_sync, force_full)
        else:
            await asyncio.to_thread(_refresh_event_cache_sync, force_full)
    except Exception as exc:
        state["last_error"] = str(exc)
        telegram_sync.save_state()
        raise
    finally:
        state["running"] = False
        state["next_refresh_at"] = _analysis_next_refresh_at(kind)
        if state.get("last_error"):
            state["progress_label"] = "Ошибка"
        elif kind == "contacts":
            state["progress_current"] = int(state.get("progress_total") or state.get("progress_current") or 0)
            total_value = int(state.get("progress_total") or 0)
            state["progress_percent"] = 100.0 if total_value > 0 else float(state.get("progress_percent") or 0.0)
            state["progress_label"] = "Готово"
        telegram_sync.save_state()
        _analysis_refresh_tasks[kind] = None






async def _analysis_autorefresh_loop() -> None:
    kind_menu = {"crm": "crm", "events": "events", "contacts": "contacts"}
    while True:
        try:
            for kind in _ANALYSIS_KINDS:
                menu_key = kind_menu.get(str(kind))
                if menu_key and not _xfiles_is_menu_allowed(menu_key):
                    continue
                if _analysis_due(kind):
                    _schedule_analysis_refresh(kind)
            await asyncio.sleep(_ANALYSIS_LOOP_SLEEP_SEC)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[analysis-cache] scheduler error: {exc!r}")
            await asyncio.sleep(_ANALYSIS_LOOP_SLEEP_SEC)


def _write_source_selectors(selectors: List[str]) -> None:
    unique_selectors: List[str] = []
    seen: set[str] = set()
    for selector in selectors:
        normalized = _normalize_source_selector(selector)
        identity = _selector_identity(normalized)
        if identity in seen:
            continue
        seen.add(identity)
        unique_selectors.append(normalized)

    telegram_sync.state[SOURCE_SELECTORS_STATE_KEY] = unique_selectors
    telegram_sync.save_state()

def _load_source_selectors_for_ui() -> List[Union[str, int]]:
    return [telegram_sync._parse_line(item) for item in _source_selectors_state_list()]


def _dialog_chat_type(dialog: Any, entity: Any) -> Literal["channel", "group", "private", "bot"]:
    if bool(getattr(entity, "bot", False)):
        return "bot"
    if bool(getattr(dialog, "is_group", False)) or bool(getattr(entity, "megagroup", False)):
        return "group"
    if bool(getattr(dialog, "is_channel", False)) or bool(getattr(entity, "broadcast", False)):
        return "channel"
    return "private"


def _dialog_selector(entity: Any) -> str:
    username = getattr(entity, "username", None)
    if username:
        return str(username).lower()
    return str(int(getattr(entity, "id")))


def _dialog_title(dialog: Any, entity: Any) -> str:
    if getattr(dialog, "name", None):
        return str(dialog.name)
    if getattr(entity, "title", None):
        return str(entity.title)

    first_name = getattr(entity, "first_name", None) or ""
    last_name = getattr(entity, "last_name", None) or ""
    full_name = (first_name + " " + last_name).strip()
    if full_name:
        return full_name

    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    return str(getattr(entity, "id", "unknown"))


def _dialog_preview(dialog: Any) -> tuple[Optional[str], Optional[str], Optional[str]]:
    message = getattr(dialog, "message", None)
    if not message:
        return None, None, None

    last_date_utc: Optional[str] = None
    if getattr(message, "date", None):
        last_date_utc = message.date.astimezone(timezone.utc).isoformat()

    text = getattr(message, "message", None) or ""
    if text:
        return last_date_utc, text[:160], text

    if getattr(message, "media", None) is not None:
        return last_date_utc, "[media]", "[media]"

    return last_date_utc, None, None


_DIALOG_META_CACHE_TTL_SECONDS = 60.0
_dialog_meta_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "items": {},
}


def _build_dialog_meta_catalog(dialogs: List[TelegramDialogDTO]) -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for dialog in dialogs:
        meta = {
            "chat_type": dialog.chat_type,
            "is_archived": bool(dialog.is_archived),
        }
        keys = {
            _selector_to_lead_name(dialog.selector),
            _selector_to_lead_name(int(dialog.id)),
        }
        if dialog.username:
            keys.add(_selector_to_lead_name(dialog.username))
        for lead_name in keys:
            if lead_name:
                catalog[lead_name] = meta
    return catalog


def _entity_chat_type(entity: Any) -> str:
    if bool(getattr(entity, "bot", False)):
        return "bot"
    if bool(getattr(entity, "broadcast", False)):
        return "channel"
    if bool(getattr(entity, "megagroup", False)) or bool(getattr(entity, "gigagroup", False)):
        return "group"
    if getattr(entity, "title", None):
        return "group"
    return "private"


def _runtime_entity_meta_catalog() -> Dict[str, Dict[str, Any]]:
    catalog: Dict[str, Dict[str, Any]] = {}
    for chat_key, entity in list(telegram_sync.entities_by_chat_key.items()):
        meta = {
            "chat_type": _entity_chat_type(entity),
            "is_archived": False,
        }
        keys = {_selector_to_lead_name(chat_key)}
        username = getattr(entity, "username", None)
        if username:
            keys.add(_selector_to_lead_name(username))
        entity_id = getattr(entity, "id", None)
        if entity_id is not None:
            keys.add(_selector_to_lead_name(int(entity_id)))
        for lead_name in keys:
            if lead_name:
                catalog[lead_name] = meta
    return catalog


def _cached_dialog_meta_catalog() -> Dict[str, Dict[str, Any]]:
    cached_items = _dialog_meta_cache.get("items")
    if isinstance(cached_items, dict) and cached_items:
        return dict(cached_items)

    runtime_catalog = _runtime_entity_meta_catalog()
    if runtime_catalog:
        return dict(runtime_catalog)

    cached_dialogs = _telegram_dialogs_cache.get("items")
    if isinstance(cached_dialogs, list) and cached_dialogs:
        try:
            catalog = _build_dialog_meta_catalog(cached_dialogs)
        except Exception:
            return {}
        _dialog_meta_cache["items"] = catalog
        _dialog_meta_cache["expires_at"] = time.monotonic() + _DIALOG_META_CACHE_TTL_SECONDS
        return dict(catalog)
    return {}


def _is_private_only_leads_filter(
    *,
    query: str,
    show_channels: bool,
    show_groups: bool,
    show_private: bool,
    show_bots: bool,
    show_archived: bool,
) -> bool:
    return (
        not str(query or "").strip()
        and bool(show_private)
        and not bool(show_channels)
        and not bool(show_groups)
        and not bool(show_bots)
        and not bool(show_archived)
    )


async def _list_telegram_dialogs() -> List[TelegramDialogDTO]:
    session_file = _telegram_session_file_path()
    if not session_file.exists():
        raise HTTPException(status_code=400, detail="Telegram не авторизован")
    if telegram_sync.is_sync_paused():
        status = telegram_sync.get_sync_control_status()
        raise HTTPException(
            status_code=429,
            detail=f"Telegram sync приостановлен: {status.get('reason') or 'manual'}",
        )
    if telegram_sync._is_global_flood_wait_active("dialogs list"):
        status = telegram_sync.get_global_flood_wait_status()
        raise HTTPException(
            status_code=429,
            detail=f"Telegram cooldown активен до {status.get('can_fetch_after') or status.get('until')}",
        )
    if telegram_sync._is_operation_cooldown_active("dialogs", "dialogs list"):
        status = telegram_sync.get_rate_limit_status()
        cooldown = (status.get("operation_cooldowns") or {}).get("dialogs") or {}
        raise HTTPException(
            status_code=429,
            detail=f"Telegram dialogs cooldown активен до {cooldown.get('can_fetch_after') or cooldown.get('retry_after')}",
        )

    temp_session_dir = APP_DIR / ".tmp"
    temp_session_dir.mkdir(parents=True, exist_ok=True)
    temp_session_base = temp_session_dir / f"telegram-dialogs-{uuid.uuid4().hex}"
    temp_session_file = temp_session_base.with_suffix(".session")
    temp_session_journal = temp_session_file.with_name(f"{temp_session_file.name}-journal")
    source_journal = session_file.with_name(f"{session_file.name}-journal")

    try:
        shutil.copy2(session_file, temp_session_file)
        if source_journal.exists():
            shutil.copy2(source_journal, temp_session_journal)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Не удалось подготовить временную Telegram-сессию: {exc}") from exc

    dialogs_client: Optional[TelegramClient] = None
    added_identities = {_selector_identity(item) for item in _source_selectors_as_strings()}
    dialogs: List[TelegramDialogDTO] = []

    await telegram_sync._sleep_operation_cooldown("dialogs", "dialogs list")
    await telegram_sync._dialogs_lock.acquire()
    try:
        api_id, api_hash = _require_telegram_api_credentials()
        dialogs_client = TelegramClient(str(temp_session_base), api_id, api_hash)
        await dialogs_client.connect()

        is_authorized = await dialogs_client.is_user_authorized()
        if not is_authorized:
            raise HTTPException(status_code=400, detail="Telegram не авторизован")

        async for dialog in dialogs_client.iter_dialogs(ignore_migrated=True):
            entity = getattr(dialog, "entity", None)
            if entity is None:
                continue
            if bool(getattr(entity, "is_self", False)):
                continue

            selector = _dialog_selector(entity)
            last_date_utc, last_text_preview, last_text_full = _dialog_preview(dialog)
            import_limits = _effective_import_limits_for_selector(selector)
            dialogs.append(
                TelegramDialogDTO(
                    id=int(getattr(entity, "id")),
                    title=_dialog_title(dialog, entity),
                    username=getattr(entity, "username", None),
                    selector=selector,
                    chat_type=_dialog_chat_type(dialog, entity),
                    is_archived=bool(getattr(dialog, "folder_id", 0)),
                    is_already_added=_selector_identity(selector) in added_identities,
                    unread_count=int(getattr(dialog, "unread_count", 0) or 0),
                    last_date_utc=last_date_utc,
                    last_text_preview=last_text_preview,
                    last_text_full=last_text_full,
                    import_history_months=import_limits["import_history_months"],
                    import_message_limit=import_limits["import_message_limit"],
                    import_max_history_months=import_limits["import_max_history_months"],
                    import_max_message_limit=import_limits["import_max_message_limit"],
                )
            )
    except HTTPException:
        raise
    except FloodWaitError as exc:
        telegram_sync._activate_global_flood_wait(exc, "dialogs list")
        raise HTTPException(status_code=429, detail=f"Telegram FloodWait: ждать {telegram_sync._flood_wait_seconds(exc)} секунд") from exc
    except (PeerFloodError, UserPrivacyRestrictedError) as exc:
        telegram_sync._mark_telegram_risk_blocked(exc, "dialogs list")
        raise HTTPException(status_code=429, detail=f"Telegram ограничил список диалогов: {type(exc).__name__}") from exc
    except Exception as exc:
        if telegram_sync._is_transient_telegram_rate_limit(exc):
            telegram_sync._register_telegram_transient_limit(exc, "dialogs list", operation="dialogs")
            raise HTTPException(status_code=429, detail=f"Telegram dialogs cooldown: {exc}") from exc
        raise HTTPException(status_code=500, detail=f"Не удалось получить список диалогов Telegram: {exc}") from exc
    finally:
        try:
            telegram_sync._dialogs_lock.release()
        except ValueError:
            pass
        if dialogs_client is not None:
            try:
                await dialogs_client.disconnect()
            except Exception:
                pass
        temp_session_file.unlink(missing_ok=True)
        temp_session_journal.unlink(missing_ok=True)

    dialogs.sort(
        key=lambda item: (
            item.is_archived,
            item.is_already_added,
            -(item.unread_count or 0),
            item.last_date_utc or "",
            item.title.lower(),
        ),
        reverse=False,
    )
    dialogs.sort(
        key=lambda item: (
            1 if item.last_date_utc else 0,
            item.last_date_utc or "",
        ),
        reverse=True,
    )
    dialogs.sort(key=lambda item: (item.is_archived, item.is_already_added))
    return dialogs


def _store_telegram_dialogs_cache(items: List[TelegramDialogDTO]) -> None:
    _telegram_dialogs_cache["items"] = list(items)
    _telegram_dialogs_cache["updated_at"] = _utc_now().isoformat()
    _telegram_dialogs_cache["expires_at"] = time.monotonic() + _TELEGRAM_DIALOGS_CACHE_TTL_SECONDS
    _telegram_dialogs_cache["last_error"] = None
    _write_telegram_dialogs_disk_cache(items)


def _telegram_dialogs_disk_cache_path() -> Path:
    cache_dir = globals().get("CACHE_DIR")
    if not isinstance(cache_dir, Path):
        app_dir = globals().get("APP_DIR")
        cache_dir = Path(app_dir) / "cache" if app_dir else Path(".")
    return Path(cache_dir) / "telegram_dialogs_cache.json"


def _telegram_dialog_to_cache_payload(dialog: TelegramDialogDTO) -> Dict[str, Any]:
    if hasattr(dialog, "model_dump"):
        return dialog.model_dump()
    return dialog.dict()


def _telegram_dialog_from_cache_payload(payload: Any) -> Optional[TelegramDialogDTO]:
    if not isinstance(payload, dict):
        return None
    try:
        return TelegramDialogDTO(**payload)
    except Exception:
        return None


def _write_telegram_dialogs_disk_cache(items: List[TelegramDialogDTO]) -> None:
    try:
        path = _telegram_dialogs_disk_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "updated_at": _utc_now().isoformat(),
            "items": [_telegram_dialog_to_cache_payload(item) for item in items],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_telegram_dialogs_disk_cache() -> List[TelegramDialogDTO]:
    try:
        path = _telegram_dialogs_disk_cache_path()
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(raw_items, list):
            return []
        items = [
            item
            for item in (_telegram_dialog_from_cache_payload(raw) for raw in raw_items)
            if item is not None
        ]
        if items:
            _telegram_dialogs_cache["items"] = list(items)
            _telegram_dialogs_cache["updated_at"] = str(payload.get("updated_at") or "")
            _telegram_dialogs_cache["expires_at"] = time.monotonic() + _TELEGRAM_DIALOGS_CACHE_TTL_SECONDS
            _telegram_dialogs_cache["last_error"] = None
        return items
    except Exception:
        return []


def _dialog_identity_values(dialog: TelegramDialogDTO) -> set[str]:
    values = {
        _selector_identity(dialog.selector),
        _selector_identity(dialog.username or ""),
        _selector_identity(dialog.title or ""),
        _selector_identity(str(dialog.id or "")),
    }
    return {value for value in values if value}


def _effective_import_limits_from_cached_state(
    selector: Union[str, int],
    *,
    settings: Dict[str, Any],
    import_settings: Dict[str, Dict[str, int]],
    max_history: int,
    max_messages: int,
) -> Dict[str, int]:
    try:
        key = _selector_identity(str(selector))
    except Exception:
        key = str(selector or "").strip().lower()
    stored = import_settings.get(key, {})
    try:
        default_history = int(settings.get("import_default_history_months") or 1)
    except Exception:
        default_history = 1
    try:
        default_messages = int(settings.get("import_default_message_limit") or 1000)
    except Exception:
        default_messages = 1000
    try:
        history_months = int(stored.get("import_history_months") or default_history)
    except Exception:
        history_months = default_history
    try:
        message_limit = int(stored.get("import_message_limit") or default_messages)
    except Exception:
        message_limit = default_messages
    return {
        "import_history_months": 0 if max_history == 0 or history_months == 0 else max(1, min(max_history, history_months)),
        "import_message_limit": 0 if max_messages == 0 or message_limit == 0 else max(1, min(max_messages, message_limit)),
        "import_max_history_months": max_history,
        "import_max_message_limit": max_messages,
    }


def _source_selector_fallback_dialog(
    selector: str,
    *,
    import_limits: Optional[Dict[str, int]] = None,
) -> Optional[TelegramDialogDTO]:
    try:
        normalized = _normalize_source_selector(selector)
    except Exception:
        return None
    clean = normalized.lstrip("@").strip()
    if not clean:
        return None
    limits = import_limits or _effective_import_limits_for_selector(normalized)
    digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
    synthetic_id = int(digest[:12], 16)
    waiting_text = "Добавлен в источники, ожидает обновления кэша Telegram."
    return TelegramDialogDTO(
        id=synthetic_id,
        title=clean,
        username=None if normalized.isdigit() else clean,
        selector=normalized,
        chat_type="group",
        is_archived=False,
        is_already_added=True,
        unread_count=0,
        last_date_utc=None,
        last_text_preview=waiting_text,
        last_text_full=waiting_text,
        **limits,
    )


def _merge_added_source_selectors_into_dialogs(
    dialogs: List[TelegramDialogDTO],
    *,
    include_missing_added: bool = True,
) -> List[TelegramDialogDTO]:
    result = list(dialogs)
    raw_selectors = _source_selectors_as_strings()
    selector_by_identity: Dict[str, str] = {}
    for raw_selector in raw_selectors:
        identity = _selector_identity(raw_selector)
        if not identity:
            continue
        selector_by_identity.setdefault(identity, str(raw_selector))
    source_identities = set(selector_by_identity.keys())
    known: set[str] = set()
    for dialog in result:
        dialog_identities = _dialog_identity_values(dialog)
        dialog.is_already_added = bool(dialog_identities.intersection(source_identities))
        known.update(dialog_identities)
    if not include_missing_added:
        return result

    settings = _get_app_settings()
    max_history = _xfiles_import_history_months_max()
    max_messages = _xfiles_import_message_limit_max()
    import_settings = _import_dialog_settings_state()
    for selector in source_identities:
        identity = _selector_identity(selector)
        if not identity or identity in known:
            continue
        raw_selector = selector_by_identity.get(identity, selector)
        limits = _effective_import_limits_from_cached_state(
            raw_selector,
            settings=settings,
            import_settings=import_settings,
            max_history=max_history,
            max_messages=max_messages,
        )
        fallback = _source_selector_fallback_dialog(raw_selector, import_limits=limits)
        if fallback is not None:
            result.append(fallback)
            known.update(_dialog_identity_values(fallback))
    return result


def _mark_telegram_dialogs_cache_added(selectors: Iterable[str]) -> None:
    added_identities = {
        _selector_identity(selector)
        for selector in selectors
        if str(selector or "").strip()
    }
    if not added_identities:
        return

    cached_dialogs = _telegram_dialogs_cache.get("items")
    if not isinstance(cached_dialogs, list) or not cached_dialogs:
        return

    changed = False
    for dialog in cached_dialogs:
        if not isinstance(dialog, TelegramDialogDTO):
            continue
        dialog_identities = {
            _selector_identity(dialog.selector),
            _selector_identity(str(dialog.id)),
        }
        if dialog.username:
            dialog_identities.add(_selector_identity(dialog.username))
        if dialog_identities & added_identities and not dialog.is_already_added:
            dialog.is_already_added = True
            changed = True

    if changed:
        _telegram_dialogs_cache["updated_at"] = _utc_now().isoformat()
        _telegram_dialogs_cache["last_error"] = None


def _mark_telegram_dialogs_cache_removed(selectors: Iterable[str]) -> None:
    removed_identities = {
        _selector_identity(selector)
        for selector in selectors
        if str(selector or "").strip()
    }
    if not removed_identities:
        return

    cached_dialogs = _telegram_dialogs_cache.get("items")
    if not isinstance(cached_dialogs, list) or not cached_dialogs:
        return

    changed = False
    for dialog in cached_dialogs:
        if not isinstance(dialog, TelegramDialogDTO):
            continue
        dialog_identities = {
            _selector_identity(dialog.selector),
            _selector_identity(str(dialog.id)),
        }
        if dialog.username:
            dialog_identities.add(_selector_identity(dialog.username))
        if dialog_identities & removed_identities and dialog.is_already_added:
            dialog.is_already_added = False
            changed = True

    if changed:
        _telegram_dialogs_cache["updated_at"] = _utc_now().isoformat()
        _telegram_dialogs_cache["last_error"] = None


async def _refresh_telegram_dialogs_cache_async() -> None:
    global _telegram_dialogs_refresh_task
    try:
        items = await _list_telegram_dialogs()
        _store_telegram_dialogs_cache(items)
    except Exception as exc:
        _telegram_dialogs_cache["last_error"] = str(exc)
        raise
    finally:
        _telegram_dialogs_refresh_task = None


def _schedule_telegram_dialogs_refresh() -> bool:
    global _telegram_dialogs_refresh_task
    if _telegram_dialogs_refresh_task is not None and not _telegram_dialogs_refresh_task.done():
        return False
    try:
        _telegram_dialogs_refresh_task = asyncio.create_task(_refresh_telegram_dialogs_cache_async())
    except RuntimeError:
        _telegram_dialogs_refresh_task = None
        return False
    return True


async def _get_telegram_dialogs_for_api(force_refresh: bool = False) -> List[TelegramDialogDTO]:
    now = time.monotonic()
    cached_items = _telegram_dialogs_cache.get("items")
    cached_expires_at = float(_telegram_dialogs_cache.get("expires_at") or 0.0)

    if (
        isinstance(cached_items, list)
        and now < cached_expires_at
    ):
        return list(cached_items)

    if isinstance(cached_items, list) and not force_refresh:
        return list(cached_items)

    if not force_refresh:
        disk_items = _load_telegram_dialogs_disk_cache()
        if disk_items:
            _schedule_telegram_dialogs_refresh()
            return list(disk_items)

    if _telegram_dialogs_refresh_task is not None and not _telegram_dialogs_refresh_task.done():
        if not force_refresh:
            return []
        try:
            await asyncio.wait_for(
                asyncio.shield(_telegram_dialogs_refresh_task),
                timeout=_TELEGRAM_DIALOGS_REQUEST_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=504,
                detail="Telegram отвечает слишком долго. Обновление списка продолжается в фоне, попробуйте ещё раз через несколько секунд.",
            ) from exc

        cached_items = _telegram_dialogs_cache.get("items")
        return list(cached_items or [])

    if not force_refresh:
        _schedule_telegram_dialogs_refresh()
        return []

    try:
        items = await asyncio.wait_for(
            _list_telegram_dialogs(),
            timeout=_TELEGRAM_DIALOGS_REQUEST_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError as exc:
        _schedule_telegram_dialogs_refresh()
        raise HTTPException(
            status_code=504,
            detail="Telegram отвечает слишком долго. Обновление списка продолжается в фоне, попробуйте ещё раз через несколько секунд.",
        ) from exc

    _store_telegram_dialogs_cache(items)
    return list(items)


async def _get_dialog_meta_catalog(force: bool = False) -> Dict[str, Dict[str, Any]]:
    now = time.monotonic()
    cached_items = _dialog_meta_cache.get("items")
    cached_expires_at = float(_dialog_meta_cache.get("expires_at") or 0.0)
    if not force and cached_items and now < cached_expires_at:
        return dict(cached_items)

    try:
        if not telegram_sync.client.is_connected():
            return dict(cached_items or {})
    except Exception:
        return dict(cached_items or {})

    try:
        is_authorized = await telegram_sync.client.is_user_authorized()
    except Exception:
        return dict(cached_items or {})

    if not is_authorized:
        return dict(cached_items or {})

    try:
        dialogs = await _list_telegram_dialogs()
    except HTTPException:
        return dict(cached_items or {})
    except Exception:
        return dict(cached_items or {})

    _store_telegram_dialogs_cache(dialogs)
    catalog = _build_dialog_meta_catalog(dialogs)
    _dialog_meta_cache["items"] = catalog
    _dialog_meta_cache["expires_at"] = now + _DIALOG_META_CACHE_TTL_SECONDS
    return dict(catalog)


def _image_preview_text(value: Optional[str], max_len: int = 220) -> Optional[str]:
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text




def _parse_iso_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _compute_import_sync_status() -> ImportSyncStatusDTO:
    config = telegram_sync.get_import_sync_state()
    enabled = bool(config.get("enabled"))
    raw_selectors: List[str] = []
    seen_selector_identities: set[str] = set()
    for item in _source_selectors_as_strings():
        raw_selector = str(item).strip()
        if not raw_selector:
            continue
        try:
            identity = _selector_identity(raw_selector)
        except Exception:
            identity = raw_selector.lower()
        if not identity or identity in seen_selector_identities:
            continue
        seen_selector_identities.add(identity)
        raw_selectors.append(raw_selector)

    if not enabled or not raw_selectors:
        return ImportSyncStatusDTO(
            enabled=False,
            message="Режим синхронизации всех данных из Import выключен",
            started_at=config.get("started_at"),
            updated_at=config.get("updated_at"),
        )

    total_dialogs = len(raw_selectors)
    completed_dialogs = 0
    active_dialogs = 0
    pending_dialogs = 0
    processed_units = 0
    total_units = 0
    last_updated_dt = _parse_iso_ts(config.get("updated_at")) or _parse_iso_ts(config.get("started_at")) or _utc_now()

    for raw_selector in raw_selectors:
        selector = telegram_sync._parse_line(raw_selector)
        selector_key = telegram_sync._selector_key(selector)
        chat_key = telegram_sync._selector_to_chat_key.get(selector_key)

        if not chat_key:
            task = telegram_sync._chat_setup_tasks.get(selector_key)
            if task and not task.done():
                active_dialogs += 1
            else:
                pending_dialogs += 1
            total_units += 1
            continue

        chat_state = telegram_sync.get_chat_state(chat_key)
        latest_id = int(chat_state.get("backfill_latest_id", 0) or chat_state.get("max_saved_id", 0) or 0)
        offset_id = int(chat_state.get("backfill_offset_id", 0) or 0)
        backfill_done = bool(chat_state.get("backfill_done"))

        updated_dt = (
            _parse_iso_ts(chat_state.get("backfill_updated_at"))
            or _parse_iso_ts(chat_state.get("backfill_completed_at"))
            or _parse_iso_ts(chat_state.get("backfill_started_at"))
        )
        if updated_dt and updated_dt > last_updated_dt:
            last_updated_dt = updated_dt

        if latest_id > 0:
            total_units += latest_id
        else:
            total_units += 1

        if backfill_done:
            completed_dialogs += 1
            processed_units += latest_id if latest_id > 0 else 1
            continue

        if chat_key in telegram_sync._chat_backfill_tasks and not telegram_sync._chat_backfill_tasks[chat_key].done():
            active_dialogs += 1
        elif selector_key in telegram_sync._chat_setup_tasks and not telegram_sync._chat_setup_tasks[selector_key].done():
            active_dialogs += 1
        else:
            pending_dialogs += 1

        if latest_id > 0 and offset_id > 0:
            processed_units += max(0, min(latest_id, latest_id - offset_id))

    progress_percent = 0.0
    if total_units > 0:
        progress_percent = max(0.0, min(100.0, (processed_units / total_units) * 100.0))

    eta_seconds: Optional[int] = None
    started_dt = _parse_iso_ts(config.get("started_at"))
    if started_dt and processed_units > 0 and total_units > processed_units:
        elapsed = max((_utc_now() - started_dt).total_seconds(), 1.0)
        rate = processed_units / elapsed
        if rate > 0:
            eta_seconds = int((total_units - processed_units) / rate)

    message = f"Синхронизировано {completed_dialogs} из {total_dialogs} диалогов"
    if completed_dialogs >= total_dialogs and total_dialogs > 0:
        message = f"Синхронизация завершена: {completed_dialogs} из {total_dialogs}"

    return ImportSyncStatusDTO(
        enabled=True,
        total_dialogs=total_dialogs,
        completed_dialogs=completed_dialogs,
        active_dialogs=active_dialogs,
        pending_dialogs=pending_dialogs,
        progress_percent=round(progress_percent, 2),
        processed_units=int(processed_units),
        total_units=int(total_units),
        eta_seconds=eta_seconds,
        started_at=config.get("started_at"),
        updated_at=last_updated_dt.isoformat() if last_updated_dt else config.get("updated_at"),
        message=message,
    )

def _selector_to_lead_name(selector: Union[str, int]) -> str:
    if isinstance(selector, int):
        return f"id_{selector}"

    value = str(selector).strip()
    if value.startswith("@"):
        value = value[1:]
    return value.lower()


def _build_selector_lookup_maps() -> Dict[str, Dict[str, str]]:
    source: Dict[str, str] = {}
    for selector in _load_source_selectors_for_ui():
        lead_name = _selector_to_lead_name(selector)
        source[lead_name] = str(selector)

    import_sync: Dict[str, str] = {}
    for selector in telegram_sync.get_import_sync_selectors():
        lead_name = _selector_to_lead_name(selector)
        import_sync[lead_name] = str(selector)

    managed = dict(source)
    for lead_name, selector in import_sync.items():
        managed.setdefault(lead_name, selector)
    for lead_name, selector in _get_known_selectors_state().items():
        managed.setdefault(lead_name, selector)

    return {"source": source, "import_sync": import_sync, "managed": managed}


def _selector_lookup_maps() -> Dict[str, Dict[str, str]]:
    now = time.monotonic()
    cached = _selector_lookup_cache.get("maps")
    if isinstance(cached, dict) and (now - float(_selector_lookup_cache.get("updated_at") or 0.0)) <= _SELECTOR_LOOKUP_CACHE_TTL_SEC:
        return {name: dict(value) for name, value in cached.items()}
    maps = _build_selector_lookup_maps()
    _selector_lookup_cache["maps"] = {name: dict(value) for name, value in maps.items()}
    _selector_lookup_cache["updated_at"] = now
    return maps


def _invalidate_selector_lookup_cache() -> None:
    _selector_lookup_cache["maps"] = None
    _selector_lookup_cache["updated_at"] = 0.0


def _source_selector_map() -> Dict[str, str]:
    return _selector_lookup_maps()["source"]


def _import_sync_selector_map() -> Dict[str, str]:
    return _selector_lookup_maps()["import_sync"]


def _managed_selector_map() -> Dict[str, str]:
    return _selector_lookup_maps()["managed"]

def _lead_exists_in_source(lead: str) -> bool:
    return lead.lower() in _managed_selector_map()


def _duckdb_leads_ready() -> bool:
    status = _duckdb_status_snapshot()
    return bool(duckdb is not None and status.get("cache_ready") and DUCKDB_PATH.exists())


def _duckdb_normalize_preview_text(value: Any) -> Optional[str]:
    text = str(value or "").replace("\r", "\n").strip()
    if not text:
        return None
    return text[:160]


def _duckdb_list_source_rows_for_lead(lead: str) -> List[tuple[str, str]]:
    target = str(lead or "").strip().lower()
    if not target or not _duckdb_leads_ready():
        return []
    conn = _duckdb_connect_readonly()
    try:
        raw_rows = conn.execute("SELECT source_jsonl, file_name FROM file_registry").fetchall()
    finally:
        conn.close()

    rows: List[tuple[str, str]] = []
    for source_jsonl, file_name in raw_rows:
        file_value = str(file_name or "")
        derived_name = _selector_to_lead_name(Path(file_value or str(source_jsonl or "")).stem)
        if derived_name == target:
            rows.append((str(source_jsonl or ""), file_value))
    return rows


def _telegram_chat_state_for_lead(lead_name: str, source_selector: Optional[str] = None) -> Dict[str, Any]:
    sync = globals().get("telegram_sync")
    state = getattr(sync, "state", {}) if sync is not None else {}
    if not isinstance(state, dict):
        return {}

    candidate_keys: List[str] = []
    for value in (lead_name, source_selector):
        normalized = str(value or "").strip()
        if not normalized:
            continue
        candidate_keys.extend([normalized, normalized.lower()])
        try:
            selector_key = sync._selector_key(normalized) if sync is not None else normalized.lower()
        except Exception:
            selector_key = normalized.lower()
        candidate_keys.append(selector_key)

        selector_cache = state.get(TELEGRAM_SELECTOR_CACHE_STATE_KEY)
        if isinstance(selector_cache, dict):
            cache_entry = selector_cache.get(selector_key)
            if isinstance(cache_entry, dict):
                chat_key = str(cache_entry.get("chat_key") or "").strip()
                if chat_key:
                    candidate_keys.extend([chat_key, chat_key.lower()])

    for key in candidate_keys:
        entry = state.get(key)
        if isinstance(entry, dict) and (
            "telegram_status" in entry
            or "retry_after" in entry
            or "last_sync_at" in entry
            or "last_error" in entry
        ):
            return entry
    return {}


def _lead_dto_telegram_fields(lead_name: str, source_selector: Optional[str] = None) -> Dict[str, Optional[str]]:
    chat_state = _telegram_chat_state_for_lead(lead_name, source_selector)
    status = str(chat_state.get("telegram_status") or "").strip() or None
    return {
        "telegram_status": status,
        "retry_after": str(chat_state.get("retry_after") or "").strip() or None,
        "last_sync_at": str(chat_state.get("last_sync_at") or chat_state.get("last_seen_at") or "").strip() or None,
        "last_error": str(chat_state.get("last_error") or "").strip() or None,
    }


def _lead_scan_group_fields(lead_name: str, source_selector: Optional[str] = None) -> Dict[str, Any]:
    settings = _get_app_settings()
    groups = _coerce_telegram_scan_groups(settings.get("telegram_scan_groups"))
    assignments = _coerce_telegram_scan_group_assignments(
        settings.get("telegram_scan_group_assignments"),
        groups,
    )
    groups_by_id = {
        _normalize_scan_group_id(item.get("id")): item
        for item in groups
        if isinstance(item, dict)
    }

    candidate_keys = [
        _normalize_scan_group_assignment_key(lead_name),
        _normalize_scan_group_assignment_key(source_selector),
    ]
    try:
        if source_selector:
            candidate_keys.append(_selector_identity(source_selector))
    except Exception:
        pass
    candidate_keys = [key for key in candidate_keys if key]

    group_id = "C"
    for key in candidate_keys:
        assigned = assignments.get(key)
        if assigned:
            group_id = assigned
            break
    if group_id not in groups_by_id:
        group_id = "C" if "C" in groups_by_id else next(iter(groups_by_id.keys()), "C")

    group = groups_by_id.get(group_id, {})
    return {
        "scan_group": group_id,
        "scan_group_label": str(group.get("label") or group_id),
        "scan_group_frequency": str(group.get("frequency") or ""),
        "scan_group_interval_minutes": int(group.get("interval_minutes") or 0) or None,
    }


_SOURCE_POLICY_MODES = {"own", "allowed", "public", "unknown", "blocked"}


def _normalize_source_policy_mode(value: Any) -> str:
    mode = str(value or "unknown").strip().lower()
    return mode if mode in _SOURCE_POLICY_MODES else "unknown"


def _source_policy_candidate_keys(lead_name: str, source_selector: Optional[str] = None) -> List[str]:
    keys: List[str] = []
    for value in (lead_name, source_selector):
        normalized = str(value or "").strip()
        if not normalized:
            continue
        assignment_key = _normalize_scan_group_assignment_key(normalized)
        if assignment_key:
            keys.append(assignment_key)
        try:
            selector_key = _selector_identity(normalized)
            if selector_key:
                keys.append(selector_key)
        except Exception:
            pass
    deduped: List[str] = []
    seen: set[str] = set()
    for key in keys:
        if key and key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def _source_policy_state() -> Dict[str, Any]:
    sync = globals().get("telegram_sync")
    state = getattr(sync, "state", None)
    if not isinstance(state, dict):
        return {"items": {}}
    current = state.get(TELEGRAM_SOURCE_POLICY_STATE_KEY)
    if not isinstance(current, dict):
        current = {}
    items = current.get("items")
    if not isinstance(items, dict):
        items = {}
    current["items"] = items
    state[TELEGRAM_SOURCE_POLICY_STATE_KEY] = current
    return current


def _coerce_source_policy_item(
    selector_key: str,
    raw: Optional[Dict[str, Any]],
    *,
    lead_name: str,
    source_selector: Optional[str],
) -> SourcePolicyDTO:
    raw = raw if isinstance(raw, dict) else {}
    mode = _normalize_source_policy_mode(raw.get("mode"))
    selector = str(raw.get("selector") or source_selector or "").strip() or None
    lead = str(raw.get("lead") or lead_name or selector_key).strip() or selector_key
    return SourcePolicyDTO(
        selector_key=selector_key,
        lead=_selector_to_lead_name(lead),
        selector=selector,
        mode=mode,
        scan_allowed=mode != "blocked",
        reason=str(raw.get("reason") or "").strip(),
        updated_at=str(raw.get("updated_at") or "").strip() or None,
        source=str(raw.get("source") or "manual").strip() or "manual",
    )


def _source_policy_for_lead(lead_name: str, source_selector: Optional[str] = None) -> SourcePolicyDTO:
    candidate_keys = _source_policy_candidate_keys(lead_name, source_selector)
    fallback_key = candidate_keys[0] if candidate_keys else _selector_to_lead_name(lead_name or source_selector or "unknown")
    items = _source_policy_state().get("items", {})
    for key in candidate_keys:
        raw = items.get(key)
        if isinstance(raw, dict):
            return _coerce_source_policy_item(
                key,
                raw,
                lead_name=lead_name,
                source_selector=source_selector,
            )
    return _coerce_source_policy_item(
        fallback_key,
        None,
        lead_name=lead_name,
        source_selector=source_selector,
    )


def _set_source_policy(
    lead_name: str,
    source_selector: Optional[str],
    mode: str,
    reason: Optional[str] = None,
    *,
    source: str = "manual",
) -> SourcePolicyDTO:
    normalized_mode = _normalize_source_policy_mode(mode)
    candidate_keys = _source_policy_candidate_keys(lead_name, source_selector)
    if not candidate_keys:
        candidate_keys = [_selector_to_lead_name(lead_name or source_selector or "unknown")]
    lead_value = _selector_to_lead_name(lead_name or source_selector or candidate_keys[0])
    selector_value = str(source_selector or "").strip() or None
    payload = {
        "lead": lead_value,
        "selector": selector_value,
        "mode": normalized_mode,
        "reason": str(reason or "").strip(),
        "updated_at": _utc_now().isoformat(),
        "source": str(source or "manual").strip() or "manual",
    }
    items = _source_policy_state().setdefault("items", {})
    for key in candidate_keys:
        if key:
            items[key] = dict(payload)

    sync = globals().get("telegram_sync")
    if sync is not None:
        sync.save_state()
    _api_snapshot_cache_clear_prefix("leads:")
    _lead_snapshot_cache["items"] = None
    return _coerce_source_policy_item(
        candidate_keys[0],
        payload,
        lead_name=lead_value,
        source_selector=selector_value,
    )


def _source_policy_all() -> List[SourcePolicyDTO]:
    items = _source_policy_state().get("items", {})
    policies: List[SourcePolicyDTO] = []
    seen: set[tuple[str, str, str]] = set()
    for key, raw in sorted(items.items(), key=lambda item: str(item[0]).lower()):
        if not isinstance(raw, dict):
            continue
        policy = _coerce_source_policy_item(
            str(key),
            raw,
            lead_name=str(raw.get("lead") or key),
            source_selector=str(raw.get("selector") or "").strip() or None,
        )
        dedupe_key = (policy.lead, policy.selector or "", policy.mode)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        policies.append(policy)
    return policies


def _lead_source_policy_fields(lead_name: str, source_selector: Optional[str] = None) -> Dict[str, Any]:
    policy = _source_policy_for_lead(lead_name, source_selector)
    return {
        "source_policy_mode": policy.mode,
        "source_scan_allowed": policy.scan_allowed,
        "source_policy_reason": policy.reason or None,
    }


def _duckdb_detect_role_from_values(
    chat_id: Any,
    chat_username: Optional[str],
    sender_id: Any,
    sender_username: Optional[str],
) -> str:
    try:
        if sender_id is not None and chat_id is not None and int(sender_id) == int(chat_id):
            return "assistant"
    except Exception:
        pass
    if sender_username and chat_username and str(sender_username).strip().lower() == str(chat_username).strip().lower():
        return "assistant"
    return "user"








def _latest_message_window(messages: List[MessageDTO], offset: int = 0, limit: int = 200) -> List[MessageDTO]:
    if not limit or int(limit) <= 0:
        return messages[max(0, int(offset or 0)) :]
    safe_limit = max(1, int(limit))
    safe_offset = max(0, int(offset or 0))
    end = max(0, len(messages) - safe_offset)
    start = max(0, end - safe_limit)
    return messages[start:end]


def _message_has_visible_content(message: MessageDTO) -> bool:
    return bool(str(message.text or "").strip() or str(message.media_path or "").strip())

def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                # Пропускаем битые строки
                continue

def _detect_role(rec: Dict[str, Any]) -> str:
    """
    Heuristics:
    - если sender.id == chat.id или sender.username == chat.username -> assistant
    - иначе user
    """
    try:
        chat = rec.get("chat", {})
        sender = rec.get("sender", {})
        if sender.get("id") == chat.get("id") or (
            sender.get("username") and sender.get("username") == chat.get("username")
        ):
            return "assistant"
        return "user"
    except Exception:
        return "user"

def _get_lead_file_summary(jf: Path) -> Dict[str, Any]:
    cache_key = str(jf.resolve())
    try:
        stat = jf.stat()
    except OSError:
        return {
            "count": 0,
            "last_date_utc": None,
            "last_text_preview": None,
            "last_text_full": None,
            "size": 0,
            "mtime_ns": 0,
        }

    size = int(stat.st_size)
    mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
    if _duckdb_file_has_parquet_magic(jf):
        summary = {
            "count": 0,
            "last_date_utc": None,
            "last_text_preview": "[parquet payload в .jsonl]",
            "last_text_full": "[parquet payload в .jsonl]",
            "size": size,
            "mtime_ns": mtime_ns,
        }
        _lead_file_summary_cache[cache_key] = summary
        return summary

    cached = _lead_file_summary_cache.get(cache_key)

    full_rescan = not cached or size < int(cached.get("size", 0))
    count = int(cached.get("count", 0)) if cached and not full_rescan else 0
    last_dt = cached.get("last_date_utc") if cached and not full_rescan else None
    last_text = (cached.get("last_text_full") or cached.get("last_text_preview")) if cached and not full_rescan else None
    offset = 0 if full_rescan else int(cached.get("size", 0))

    with jf.open("r", encoding="utf-8", errors="ignore") as f:
        if offset > 0:
            f.seek(offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            msg = rec.get("message", {})
            count += 1
            dt = msg.get("date_utc")
            if dt and (last_dt is None or dt > last_dt):
                last_dt = dt
                last_text = msg.get("text") or ""

    summary = {
        "count": count,
        "last_date_utc": last_dt,
        "last_text_preview": str(last_text or "")[:160] or None,
        "last_text_full": last_text,
        "size": size,
        "mtime_ns": mtime_ns,
    }
    _lead_file_summary_cache[cache_key] = summary
    return summary


def _lead_import_limit_context() -> Dict[str, Any]:
    try:
        settings = _get_app_settings()
    except Exception:
        settings = {}
    try:
        import_settings = _import_dialog_settings_state()
    except Exception:
        import_settings = {}
    try:
        max_history = _xfiles_import_history_months_max()
    except Exception:
        max_history = 1
    try:
        max_messages = _xfiles_import_message_limit_max()
    except Exception:
        max_messages = 1000
    return {
        "settings": settings if isinstance(settings, dict) else {},
        "import_settings": import_settings if isinstance(import_settings, dict) else {},
        "max_history": int(max_history or 0),
        "max_messages": int(max_messages or 0),
    }


def _lead_import_limit_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except Exception:
        return default


def _lead_import_limit_fields(selector: Union[str, int], context: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    context = context or _lead_import_limit_context()
    settings = context.get("settings") if isinstance(context.get("settings"), dict) else {}
    import_settings = context.get("import_settings") if isinstance(context.get("import_settings"), dict) else {}
    max_history = _lead_import_limit_int(context.get("max_history"), 1)
    max_messages = _lead_import_limit_int(context.get("max_messages"), 1000)
    try:
        key = _selector_identity(str(selector))
    except Exception:
        key = str(selector or "").strip().lower()
    stored = import_settings.get(key, {}) if isinstance(import_settings, dict) else {}
    if not isinstance(stored, dict):
        stored = {}
    default_history = _lead_import_limit_int(settings.get("import_default_history_months"), 1)
    default_messages = _lead_import_limit_int(settings.get("import_default_message_limit"), 1000)
    history_months = _lead_import_limit_int(stored.get("import_history_months"), default_history)
    message_limit = _lead_import_limit_int(stored.get("import_message_limit"), default_messages)
    return {
        "import_history_months": 0 if max_history == 0 or history_months == 0 else max(1, min(max_history, history_months)),
        "import_message_limit": 0 if max_messages == 0 or message_limit == 0 else max(1, min(max_messages, message_limit)),
        "import_max_history_months": max_history,
        "import_max_message_limit": max_messages,
    }


def _build_lightweight_leads(dialog_meta_catalog: Optional[Dict[str, Dict[str, Any]]] = None) -> List[LeadDTO]:
    if _duckdb_leads_ready():
        return _duckdb_load_lead_rows(dialog_meta_catalog=dialog_meta_catalog)
    _ensure_dir_exists()
    leads_by_name: Dict[str, LeadDTO] = {}
    source_map = _source_selector_map()
    import_sync_map = _import_sync_selector_map()
    managed_map = _managed_selector_map()
    dialog_meta_catalog = dialog_meta_catalog or {}
    import_limit_context = _lead_import_limit_context()

    for jf in sorted(PAYME_OUT_DIR.glob("*.jsonl")):
        name = jf.stem
        cached_summary = _get_lead_file_summary(jf)
        in_source = name.lower() in source_map
        in_import_sync = name.lower() in import_sync_map
        dialog_meta = dialog_meta_catalog.get(name.lower(), {})
        source_selector = managed_map.get(name.lower())
        leads_by_name[name.lower()] = LeadDTO(
            name=name,
            file=jf.name,
            count=int(cached_summary.get("count", 0) or 0),
            last_date_utc=cached_summary.get("last_date_utc"),
            last_text_preview=cached_summary.get("last_text_preview"),
            last_text_full=cached_summary.get("last_text_full") or cached_summary.get("last_text_preview"),
            in_source=in_source,
            has_jsonl=True,
            sync_status="active" if (in_source or in_import_sync) else "archived",
            source_selector=source_selector,
            chat_type=dialog_meta.get("chat_type", "group"),
            is_archived=bool(dialog_meta.get("is_archived", False)),
            **_lead_dto_telegram_fields(name.lower(), source_selector),
            **_lead_scan_group_fields(name.lower(), source_selector),
            **_lead_import_limit_fields(source_selector or name, import_limit_context),
            **_lead_source_policy_fields(name.lower(), source_selector),
        )

    for lead_name, source_selector in managed_map.items():
        if lead_name in leads_by_name:
            continue
        dialog_meta = dialog_meta_catalog.get(lead_name, {})
        leads_by_name[lead_name] = LeadDTO(
            name=lead_name,
            file=f"{lead_name}.jsonl",
            count=0,
            last_date_utc=None,
            last_text_preview=None,
            last_text_full=None,
            in_source=lead_name in source_map,
            has_jsonl=False,
            sync_status="pending",
            source_selector=source_selector,
            chat_type=dialog_meta.get("chat_type", "group"),
            is_archived=bool(dialog_meta.get("is_archived", False)),
            **_lead_dto_telegram_fields(lead_name, source_selector),
            **_lead_scan_group_fields(lead_name, source_selector),
            **_lead_import_limit_fields(source_selector or lead_name, import_limit_context),
            **_lead_source_policy_fields(lead_name, source_selector),
        )

    return sorted(
        leads_by_name.values(),
        key=lambda lead: (
            0 if lead.in_source else 1,
            -(lead.count or 0),
            lead.name.lower(),
        ),
    )


def _list_leads(dialog_meta_catalog: Optional[Dict[str, Dict[str, Any]]] = None) -> List[LeadDTO]:
    if _duckdb_leads_ready():
        return _duckdb_load_lead_rows(dialog_meta_catalog=dialog_meta_catalog)
    _ensure_dir_exists()
    leads_by_name: Dict[str, LeadDTO] = {}
    source_map = _source_selector_map()
    import_sync_map = _import_sync_selector_map()
    managed_map = _managed_selector_map()
    dialog_meta_catalog = dialog_meta_catalog or {}
    import_limit_context = _lead_import_limit_context()

    for jf in sorted(PAYME_OUT_DIR.glob("*.jsonl")):
        name = jf.stem
        summary = _get_lead_file_summary(jf)

        in_source = name.lower() in source_map
        in_import_sync = name.lower() in import_sync_map
        dialog_meta = dialog_meta_catalog.get(name.lower(), {})
        source_selector = managed_map.get(name.lower())
        leads_by_name[name.lower()] = LeadDTO(
            name=name,
            file=jf.name,
            count=int(summary.get("count", 0) or 0),
            last_date_utc=summary.get("last_date_utc"),
            last_text_preview=summary.get("last_text_preview"),
            last_text_full=summary.get("last_text_full") or summary.get("last_text_preview"),
            in_source=in_source,
            has_jsonl=True,
            sync_status="active" if (in_source or in_import_sync) else "archived",
            source_selector=source_selector,
            chat_type=dialog_meta.get("chat_type", "group"),
            is_archived=bool(dialog_meta.get("is_archived", False)),
            **_lead_dto_telegram_fields(name.lower(), source_selector),
            **_lead_scan_group_fields(name.lower(), source_selector),
            **_lead_import_limit_fields(source_selector or name, import_limit_context),
            **_lead_source_policy_fields(name.lower(), source_selector),
        )

    for lead_name, source_selector in managed_map.items():
        if lead_name in leads_by_name:
            continue
        dialog_meta = dialog_meta_catalog.get(lead_name, {})
        leads_by_name[lead_name] = LeadDTO(
            name=lead_name,
            file=f"{lead_name}.jsonl",
            count=0,
            last_date_utc=None,
            last_text_preview=None,
            last_text_full=None,
            in_source=lead_name in source_map,
            has_jsonl=False,
            sync_status="pending",
            source_selector=source_selector,
            chat_type=dialog_meta.get("chat_type", "group"),
            is_archived=bool(dialog_meta.get("is_archived", False)),
            **_lead_dto_telegram_fields(lead_name, source_selector),
            **_lead_scan_group_fields(lead_name, source_selector),
            **_lead_import_limit_fields(source_selector or lead_name, import_limit_context),
            **_lead_source_policy_fields(lead_name, source_selector),
        )

    return sorted(
        leads_by_name.values(),
        key=lambda lead: (
            0 if lead.in_source else 1,
            -(lead.count or 0),
            lead.name.lower(),
        ),
    )


async def _refresh_lead_snapshot_async(force_dialog_meta: bool = False) -> None:
    global _lead_snapshot_refresh_task
    try:
        dialog_meta_catalog = await _get_dialog_meta_catalog(force=force_dialog_meta)
        items = await asyncio.to_thread(_list_leads, dialog_meta_catalog)
        _lead_snapshot_cache["items"] = items
        _lead_snapshot_cache["updated_at"] = time.monotonic()
    finally:
        _lead_snapshot_refresh_task = None


def _schedule_lead_snapshot_refresh(force_dialog_meta: bool = False) -> None:
    global _lead_snapshot_refresh_task
    if _lead_snapshot_refresh_task is not None and not _lead_snapshot_refresh_task.done():
        return
    try:
        _lead_snapshot_refresh_task = asyncio.create_task(_refresh_lead_snapshot_async(force_dialog_meta))
    except RuntimeError:
        _lead_snapshot_refresh_task = None

def _read_messages(lead: str, offset: int = 0, limit: int = 200) -> List[MessageDTO]:
    if _duckdb_leads_ready():
        return _duckdb_load_lead_messages(lead, offset=offset, limit=limit)
    _ensure_dir_exists()
    jf = PAYME_OUT_DIR / f"{lead}.jsonl"
    if not jf.exists():
        # попробуем нечувствительно к регистру
        matches = [p for p in PAYME_OUT_DIR.glob("*.jsonl") if p.stem.lower() == lead.lower()]
        if matches:
            jf = matches[0]
        elif _lead_exists_in_source(lead):
            return []
        else:
            raise HTTPException(status_code=404, detail=f"Lead '{lead}' not found")

    messages_by_id: Dict[int, MessageDTO] = {}
    for rec in _iter_jsonl(jf):
        msg = rec.get("message", {})
        sender = rec.get("sender", {})
        role = _detect_role(rec)
        message = MessageDTO(
            id=int(msg.get("id")),
            role=role,
            text=msg.get("text") or "",
            date_utc=msg.get("date_utc") or "",
            reply_to_msg_id=msg.get("reply_to_msg_id"),
            has_media=bool(msg.get("has_media")),
            media_path=msg.get("media_path"),
            sender_username=sender.get("username"),
            sender_name=sender.get("name"),
        )
        if _message_has_visible_content(message):
            messages_by_id[message.id] = message

    # сортируем по дате на всякий случай
    all_msgs = list(messages_by_id.values())
    all_msgs.sort(key=lambda m: m.date_utc)

    return _latest_message_window(all_msgs, offset=offset, limit=limit)


for _name, _value in list(globals().items()):
    if _name.startswith("_") and callable(_value) and _name not in {
        "_sync_runtime_globals",
        "_with_legacy_globals",
        "_with_legacy_globals_async",
    }:
        if getattr(_value, "__code__", None) and bool(getattr(_value.__code__, "co_flags", 0) & 0x80):
            globals()[_name] = _with_legacy_globals_async(_value)
        else:
            globals()[_name] = _with_legacy_globals(_value)

__all__ = (
    "_source_selectors_state_list",
    "_refresh_analysis_cache_async",
    "_analysis_autorefresh_loop",
    "_write_source_selectors",
    "_load_source_selectors_for_ui",
    "_dialog_chat_type",
    "_dialog_selector",
    "_dialog_title",
    "_dialog_preview",
    "_DIALOG_META_CACHE_TTL_SECONDS",
    "_dialog_meta_cache",
    "_build_dialog_meta_catalog",
    "_entity_chat_type",
    "_runtime_entity_meta_catalog",
    "_cached_dialog_meta_catalog",
    "_is_private_only_leads_filter",
    "_list_telegram_dialogs",
    "_store_telegram_dialogs_cache",
    "_telegram_dialogs_disk_cache_path",
    "_write_telegram_dialogs_disk_cache",
    "_load_telegram_dialogs_disk_cache",
    "_merge_added_source_selectors_into_dialogs",
    "_mark_telegram_dialogs_cache_added",
    "_mark_telegram_dialogs_cache_removed",
    "_refresh_telegram_dialogs_cache_async",
    "_schedule_telegram_dialogs_refresh",
    "_get_telegram_dialogs_for_api",
    "_get_dialog_meta_catalog",
    "_image_preview_text",
    "_parse_iso_ts",
    "_compute_import_sync_status",
    "_selector_to_lead_name",
    "_source_selector_map",
    "_import_sync_selector_map",
    "_managed_selector_map",
    "_lead_exists_in_source",
    "_duckdb_leads_ready",
    "_duckdb_normalize_preview_text",
    "_duckdb_list_source_rows_for_lead",
    "_telegram_chat_state_for_lead",
    "_lead_dto_telegram_fields",
    "_lead_scan_group_fields",
    "_SOURCE_POLICY_MODES",
    "_normalize_source_policy_mode",
    "_source_policy_candidate_keys",
    "_source_policy_state",
    "_coerce_source_policy_item",
    "_source_policy_for_lead",
    "_set_source_policy",
    "_source_policy_all",
    "_lead_source_policy_fields",
    "_duckdb_detect_role_from_values",
    "_latest_message_window",
    "_message_has_visible_content",
    "_iter_jsonl",
    "_detect_role",
    "_get_lead_file_summary",
    "_build_lightweight_leads",
    "_list_leads",
    "_refresh_lead_snapshot_async",
    "_schedule_lead_snapshot_refresh",
    "_read_messages",
)
