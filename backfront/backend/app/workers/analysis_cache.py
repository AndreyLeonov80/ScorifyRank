"""Analysis cache workers extracted from the legacy backend."""

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

def _analysis_cache_path(kind: AnalysisKind) -> Path:
    _ensure_cache_dir_exists()
    return CACHE_DIR / f"{kind}_cache.json"


def _analysis_state(kind: AnalysisKind) -> Dict[str, Any]:
    root = _analysis_state_root()
    current = root.get(kind)
    if not isinstance(current, dict):
        current = {}
        root[kind] = current
    current.setdefault("enabled", True)
    current.setdefault("interval_sec", _ANALYSIS_AUTO_REFRESH_DEFAULT_SEC)
    current.setdefault("running", False)
    current.setdefault("total_rows", 0)
    current.setdefault("last_refresh_at", None)
    current.setdefault("last_error", None)
    current.setdefault("source_offsets", {})
    current.setdefault("next_refresh_at", None)
    current.setdefault("last_keywords_hash", None)
    current.setdefault("progress_current", 0)
    current.setdefault("progress_total", 0)
    current.setdefault("progress_percent", 0.0)
    current.setdefault("progress_label", None)
    current.setdefault("current_item", None)
    current.setdefault("progress_started_at", None)
    current.setdefault("progress_log", [])
    return current


def _load_analysis_cache_rows_limited(kind: AnalysisKind, limit: int) -> List[Dict[str, Any]]:
    safe_limit = max(0, int(limit or 0))
    if safe_limit <= 0:
        return []
    path = _analysis_cache_path(kind)
    if not path.exists():
        return []

    decoder = json.JSONDecoder()
    rows: List[Dict[str, Any]] = []
    buffer = ""
    eof = False
    array_started = False

    try:
        with path.open("r", encoding="utf-8", errors="replace") as file:
            while len(rows) < safe_limit:
                if not eof and len(buffer) < 131072:
                    chunk = file.read(131072)
                    if chunk:
                        buffer += chunk
                    else:
                        eof = True

                buffer = buffer.lstrip()
                if not array_started:
                    if buffer.startswith("["):
                        buffer = buffer[1:]
                        array_started = True
                    elif buffer.startswith("{"):
                        # Backward-compatible with jsonl-like cache files.
                        array_started = True
                    elif eof:
                        break
                    else:
                        continue

                buffer = buffer.lstrip()
                if buffer.startswith("]"):
                    break
                if buffer.startswith(","):
                    buffer = buffer[1:]
                    continue
                if not buffer:
                    if eof:
                        break
                    continue

                try:
                    item, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if eof:
                        break
                    chunk = file.read(131072)
                    if chunk:
                        buffer += chunk
                    else:
                        eof = True
                    continue

                if isinstance(item, dict):
                    rows.append(item)
                buffer = buffer[end:]
    except Exception:
        return []

    return rows


def _build_analysis_status(kind: AnalysisKind) -> AnalysisStatusDTO:
    state = _analysis_state(kind)
    cache_ready = _analysis_cache_ready_fast(kind)
    stale_reason: Optional[str] = None
    if kind == "events":
        current_hash = _keywords_hash(_get_event_keywords())
        if state.get("last_keywords_hash") not in (None, current_hash) or state.get("last_keywords_hash") == "__stale__":
            stale_reason = "Ключевые слова изменились, кеш мероприятий ждёт обновления."
    event_date_status = _event_date_status_snapshot() if kind == "events" else {}
    return AnalysisStatusDTO(
        kind=kind,
        enabled=bool(state.get("enabled", True)),
        interval_sec=int(state.get("interval_sec") or _ANALYSIS_AUTO_REFRESH_DEFAULT_SEC),
        running=bool(state.get("running", False)),
        cache_ready=cache_ready,
        total_rows=int(state.get("total_rows", 0) or 0),
        progress_current=int(state.get("progress_current", 0) or 0),
        progress_total=int(state.get("progress_total", 0) or 0),
        progress_percent=float(state.get("progress_percent", 0.0) or 0.0),
        progress_label=state.get("progress_label"),
        current_item=state.get("current_item"),
        progress_started_at=state.get("progress_started_at"),
        progress_log=[str(item) for item in (state.get("progress_log") or []) if str(item or "").strip()],
        last_refresh_at=state.get("last_refresh_at"),
        last_error=state.get("last_error"),
        next_refresh_at=_analysis_next_refresh_at(kind),
        stale_reason=stale_reason,
        event_date_running=bool(event_date_status.get("running", False)),
        event_date_total=int(event_date_status.get("total", 0) or 0),
        event_date_processed=int(event_date_status.get("processed", 0) or 0),
        event_date_found=int(event_date_status.get("found", 0) or 0),
        event_date_pending=int(event_date_status.get("pending", 0) or 0),
        event_date_percent=float(event_date_status.get("percent", 0.0) or 0.0),
        event_date_rate_per_min=float(event_date_status.get("rate_per_min", 0.0) or 0.0),
        event_date_started_at=event_date_status.get("started_at"),
        event_date_updated_at=event_date_status.get("updated_at"),
        event_date_last_error=event_date_status.get("last_error"),
    )


def _refresh_routes_cache_sync(
    force_full: bool = False,
    max_llm: Optional[int] = None,
    model_override: Optional[str] = None,
) -> Dict[str, Any]:
    state = _analysis_state(_ROUTES_ANALYSIS_KIND)  # type: ignore[arg-type]
    started_at = _utc_now().isoformat()
    _analysis_set_progress(
        _ROUTES_ANALYSIS_KIND,  # type: ignore[arg-type]
        current=0,
        total=0,
        label="Ищу сообщения со словом Москва",
        current_item="DuckDB messages_raw",
        started_at=started_at,
        append_log="Запущен анализ маршрутов: поиск сообщений со словом Москва",
    )
    state["running"] = True
    state["last_error"] = None
    telegram_sync.save_state()

    processed_llm = 0
    errors = 0
    try:
        source_rows = _duckdb_load_moscow_route_rows(limit=200000)
        existing = {} if force_full else {_routes_row_key(row): dict(row) for row in _routes_cache_rows() if isinstance(row, dict)}
        total = len(source_rows)
        state["moscow_messages_total"] = total
        llm_limit = max(1, int(max_llm if max_llm is not None else _ROUTES_LLM_BATCH_SIZE))
        routes_model = _normalize_openrouter_model_id(model_override or _get_app_settings().get("openrouter_model"))
        state["routes_openrouter_model"] = routes_model
        rows_by_key: Dict[str, Dict[str, Any]] = {}
        _analysis_set_progress(
            _ROUTES_ANALYSIS_KIND,  # type: ignore[arg-type]
            current=0,
            total=total,
            label="Определяю адреса через OpenRouter",
            append_log=f"Найдено сообщений с Москва: {total}. Модель: {routes_model}. LLM-лимит за проход: {llm_limit}",
        )
        for index, row in enumerate(source_rows, start=1):
            row_key = _routes_row_key(row)
            cached = existing.get(row_key)
            if cached and not force_full:
                rows_by_key[row_key] = {**row, **cached}
                _analysis_set_progress(_ROUTES_ANALYSIS_KIND, current=index, total=total, current_item=row.get("lead"), save=False)  # type: ignore[arg-type]
                continue

            item = {
                **row,
                "row_key": row_key,
                "address": None,
                "address_key": None,
                "confidence": 0.0,
                "address_source": "pending",
                "address_reason": "",
                "lat": None,
                "lon": None,
                "updated_at": _utc_now().isoformat(),
            }
            if processed_llm < llm_limit:
                try:
                    result = _call_openrouter_route_address_sync(row, model_override=routes_model)
                    item.update(
                        {
                            "address": result.get("address"),
                            "address_key": result.get("address_key"),
                            "confidence": result.get("confidence"),
                            "address_source": result.get("source"),
                            "address_reason": result.get("reason"),
                            "lat": result.get("lat"),
                            "lon": result.get("lon"),
                            "updated_at": _utc_now().isoformat(),
                        }
                    )
                    processed_llm += 1
                    if item.get("address"):
                        _analysis_progress_log(_ROUTES_ANALYSIS_KIND, f"{row.get('lead')}: найден адрес {item.get('address')}")  # type: ignore[arg-type]
                except Exception as exc:
                    errors += 1
                    item["address_source"] = "openrouter:error"
                    item["address_reason"] = str(exc)
                    _analysis_progress_log(_ROUTES_ANALYSIS_KIND, f"{row.get('lead')}: ошибка OpenRouter {exc}")  # type: ignore[arg-type]
            rows_by_key[row_key] = item
            _analysis_set_progress(
                _ROUTES_ANALYSIS_KIND,  # type: ignore[arg-type]
                current=index,
                total=total,
                current_item=row.get("lead"),
                save=index % 20 == 0,
            )

        rows = sorted(rows_by_key.values(), key=lambda item: (str(item.get("date_utc") or ""), int(item.get("message_id") or 0)), reverse=True)
        _save_routes_cache_rows(rows)
        addresses = _routes_address_directory(rows)
        state["running"] = False
        state["total_rows"] = len(rows)
        state["addresses_found"] = len(addresses)
        state["gps_points"] = sum(1 for item in addresses if item.get("lat") is not None and item.get("lon") is not None)
        state["last_refresh_at"] = _utc_now().isoformat()
        state["last_error"] = None if not errors else f"Ошибок OpenRouter: {errors}"
        _analysis_set_progress(
            _ROUTES_ANALYSIS_KIND,  # type: ignore[arg-type]
            current=total,
            total=total,
            label="Маршруты готовы",
            current_item=None,
            append_log=f"Маршруты готовы: адресов {len(addresses)}, обработано LLM {processed_llm}, ошибок {errors}",
        )
        telegram_sync.save_state()
        return {"rows": len(rows), "addresses": len(addresses), "processed_llm": processed_llm, "errors": errors}
    except Exception as exc:
        state["running"] = False
        state["last_error"] = str(exc)
        _analysis_set_progress(
            _ROUTES_ANALYSIS_KIND,  # type: ignore[arg-type]
            label="Ошибка анализа маршрутов",
            append_log=f"Ошибка анализа маршрутов: {exc}",
        )
        telegram_sync.save_state()
        raise


def _refresh_contacts_cache_sync(force_full: bool = False) -> Dict[str, Any]:
    _ensure_dir_exists()
    state = _analysis_state("contacts")
    if _duckdb_contacts_ready():
        rows = _duckdb_load_contact_rows(limit=200000)
        _clear_analysis_cache_rows_file("contacts")
        _clear_contacts_messages_cache_file()
        state["total_rows"] = len(rows)
        state["last_refresh_at"] = _utc_now().isoformat()
        state["last_error"] = None
        _analysis_set_progress(
            "contacts",
            current=len(_duckdb_source_files()),
            total=len(_duckdb_source_files()),
            label="Кеш контактов собран из DuckDB",
            current_item=None,
            append_log=f"DuckDB-индексация контактов готова: контактов {len(rows)}",
            save=False,
        )
        return {"rows": rows, "processed_files": len(_duckdb_source_files()), "mode": "duckdb"}

    source_offsets = state.get("source_offsets") if isinstance(state.get("source_offsets"), dict) else {}
    selector_map = _managed_selector_map()
    files = sorted(PAYME_OUT_DIR.glob("*.jsonl"))
    existing_names = {path.name for path in files}
    messages_cache_path = _contacts_messages_cache_path()
    started_at = state.get("progress_started_at") or _utc_now().isoformat()
    _analysis_set_progress(
        "contacts",
        current=0,
        total=len(files),
        label="Подготовка файлов",
        current_item=None,
        started_at=started_at,
        append_log=f"Старт индексации контактов: файлов в архиве {len(files)}",
    )

    removed_leads = {Path(name).stem for name in list(source_offsets.keys()) if name not in existing_names}
    need_full = bool(force_full or removed_leads)
    file_meta: List[tuple[Path, str, os.stat_result, int]] = []
    if not need_full:
        for jf in files:
            try:
                stat = jf.stat()
            except OSError:
                continue
            previous = source_offsets.get(jf.name) if isinstance(source_offsets, dict) else None
            start_offset = 0
            if isinstance(previous, dict):
                prev_offset = int(previous.get("offset", 0) or 0)
                prev_size = int(previous.get("size", 0) or 0)
                if stat.st_size >= prev_offset and stat.st_size >= prev_size:
                    start_offset = prev_offset
                else:
                    need_full = True
                    break
            file_meta.append((jf, jf.stem, stat, start_offset))

    if need_full:
        source_offsets = {}
        file_meta = []
        for jf in files:
            try:
                stat = jf.stat()
            except OSError:
                continue
            file_meta.append((jf, jf.stem, stat, 0))
        contacts_by_key: Dict[str, Dict[str, Any]] = {}
        tmp_messages = messages_cache_path.with_suffix(".tmp")
        processed_files = 0
        with tmp_messages.open("w", encoding="utf-8") as messages_out:
            for jf, lead_name, stat, start_offset in file_meta:
                source_selector = selector_map.get(lead_name.lower())
                _analysis_set_progress(
                    "contacts",
                    current=processed_files,
                    total=len(file_meta),
                    label="Первичная индексация контактов",
                    current_item=lead_name,
                    append_log=f"Обрабатываю чат {lead_name}",
                    save=False,
                )
                with jf.open("r", encoding="utf-8", errors="replace") as file:
                    file.seek(start_offset)
                    while True:
                        line = file.readline()
                        if not line:
                            break
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(rec, dict):
                            continue
                        message = _contacts_extract_message_from_record(lead_name, source_selector, rec)
                        if not message:
                            continue
                        row = message.dict()
                        row["contact_key"] = _contacts_contact_key(row.get("sender_id"), row.get("sender_username"), row.get("sender_name"))
                        if not row["contact_key"]:
                            continue
                        messages_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        _contacts_update_summary(contacts_by_key, TelegramContactMessageDTO(**{
                            key: row.get(key) for key in TelegramContactMessageDTO.__fields__.keys()
                        }))
                    source_offsets[jf.name] = {
                        "offset": file.tell(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                processed_files += 1
                _analysis_set_progress(
                    "contacts",
                    current=processed_files,
                    total=len(file_meta),
                    label="Первичная индексация контактов",
                    current_item=lead_name,
                    append_log=f"Готово: {lead_name}",
                )
        tmp_messages.replace(messages_cache_path)
    else:
        contacts_by_key = _contacts_load_summary_rows()
        messages_cache_path.parent.mkdir(parents=True, exist_ok=True)
        processed_files = 0
        with messages_cache_path.open("a", encoding="utf-8") as messages_out:
            for jf, lead_name, stat, start_offset in file_meta:
                source_selector = selector_map.get(lead_name.lower())
                _analysis_set_progress(
                    "contacts",
                    current=processed_files,
                    total=len(file_meta),
                    label="Догрузка новых контактов",
                    current_item=lead_name,
                    append_log=f"Проверяю новые сообщения чата {lead_name}",
                    save=False,
                )
                with jf.open("r", encoding="utf-8", errors="replace") as file:
                    file.seek(start_offset)
                    while True:
                        line = file.readline()
                        if not line:
                            break
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        if not isinstance(rec, dict):
                            continue
                        message = _contacts_extract_message_from_record(lead_name, source_selector, rec)
                        if not message:
                            continue
                        row = message.dict()
                        row["contact_key"] = _contacts_contact_key(row.get("sender_id"), row.get("sender_username"), row.get("sender_name"))
                        if not row["contact_key"]:
                            continue
                        messages_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                        _contacts_update_summary(contacts_by_key, TelegramContactMessageDTO(**{
                            key: row.get(key) for key in TelegramContactMessageDTO.__fields__.keys()
                        }))
                    source_offsets[jf.name] = {
                        "offset": file.tell(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                processed_files += 1
                _analysis_set_progress(
                    "contacts",
                    current=processed_files,
                    total=len(file_meta),
                    label="Догрузка новых контактов",
                    current_item=lead_name,
                    save=True,
                )

    rows = sorted(
        contacts_by_key.values(),
        key=lambda item: (str(item.get("last_message_at") or ""), int(item.get("total_messages") or 0)),
        reverse=True,
    )
    _save_analysis_cache_rows("contacts", rows)
    state["source_offsets"] = source_offsets
    state["total_rows"] = len(rows)
    state["last_refresh_at"] = _utc_now().isoformat()
    state["last_error"] = None
    _analysis_set_progress(
        "contacts",
        current=len(file_meta),
        total=len(file_meta),
        label="Кеш контактов собран",
        current_item=None,
        append_log=f"Индексация завершена: контактов {len(rows)}, файлов {len(source_offsets)}",
        save=False,
    )
    telegram_sync.save_state()
    return {"rows": rows, "processed_files": len(source_offsets)}


def _refresh_crm_cache_sync(force_full: bool = False) -> Dict[str, Any]:
    _ensure_dir_exists()
    state = _analysis_state("crm")
    if _duckdb_contacts_ready():
        rows = _duckdb_rebuild_crm_contacts_sync()
        _clear_analysis_cache_rows_file("crm")
        state["total_rows"] = len(rows)
        state["last_refresh_at"] = _utc_now().isoformat()
        state["last_error"] = None
        state["duckdb_ready"] = True
        telegram_sync.save_state()
        return {"rows": rows, "processed_files": len(_duckdb_source_files()), "mode": "duckdb"}

    source_offsets = state.get("source_offsets") if isinstance(state.get("source_offsets"), dict) else {}
    selector_map = _managed_selector_map()
    files = sorted(PAYME_OUT_DIR.glob("*.jsonl"))
    existing_names = {path.name for path in files}

    existing_rows = [] if force_full else _load_analysis_cache_rows("crm")
    rows_by_key: Dict[str, Dict[str, Any]] = {
        _crm_row_key(row): row for row in existing_rows if isinstance(row, dict)
    }
    removed_leads = {Path(name).stem for name in list(source_offsets.keys()) if name not in existing_names}
    if removed_leads:
        rows_by_key = {
            key: row for key, row in rows_by_key.items()
            if str(row.get("lead") or "") not in removed_leads
        }
        source_offsets = {key: value for key, value in source_offsets.items() if key in existing_names}

    reset_leads: set[str] = set()
    if force_full:
        source_offsets = {}

    for jf in files:
        lead_name = jf.stem
        file_key = jf.name
        try:
            stat = jf.stat()
        except OSError:
            continue
        previous = source_offsets.get(file_key) if isinstance(source_offsets, dict) else None
        start_offset = 0
        if isinstance(previous, dict):
            prev_offset = int(previous.get("offset", 0) or 0)
            prev_size = int(previous.get("size", 0) or 0)
            if stat.st_size >= prev_offset and stat.st_size >= prev_size and not force_full:
                start_offset = prev_offset
            else:
                reset_leads.add(lead_name)
                start_offset = 0
        else:
            start_offset = 0

        source_selector = selector_map.get(lead_name.lower())
        with jf.open("r", encoding="utf-8", errors="replace") as file:
            file.seek(max(start_offset, 0))
            while True:
                line = file.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                row = _crm_extract_contact_from_record(lead_name, source_selector, rec)
                if not row:
                    continue
                rows_by_key[_crm_row_key(row.dict())] = row.dict()
            source_offsets[file_key] = {
                "offset": file.tell(),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }

    if reset_leads:
        rows_by_key = {
            key: row for key, row in rows_by_key.items()
            if str(row.get("lead") or "") not in reset_leads
        }
        selector_map = _managed_selector_map()
        for lead_name in reset_leads:
            jf = PAYME_OUT_DIR / f"{lead_name}.jsonl"
            if not jf.exists():
                continue
            source_selector = selector_map.get(lead_name.lower())
            with jf.open("r", encoding="utf-8", errors="replace") as file:
                for line in file:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    row = _crm_extract_contact_from_record(lead_name, source_selector, rec)
                    if not row:
                        continue
                    rows_by_key[_crm_row_key(row.dict())] = row.dict()
                try:
                    stat = jf.stat()
                    source_offsets[jf.name] = {
                        "offset": file.tell(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                except OSError:
                    pass

    rows = sorted(
        rows_by_key.values(),
        key=lambda item: (str(item.get("date_utc") or ""), int(item.get("message_id") or 0)),
        reverse=True,
    )
    _save_analysis_cache_rows("crm", rows)
    state["source_offsets"] = source_offsets
    state["total_rows"] = len(rows)
    state["last_refresh_at"] = _utc_now().isoformat()
    state["last_error"] = None
    telegram_sync.save_state()
    return {"rows": rows, "processed_files": len(source_offsets)}


def _refresh_event_cache_sync(force_full: bool = False) -> Dict[str, Any]:
    _ensure_dir_exists()
    state = _analysis_state("events")
    if _duckdb_contacts_ready():
        rows = _duckdb_rebuild_event_messages_sync()
        current_hash = _keywords_hash(_get_event_keywords())
        _clear_analysis_cache_rows_file("events")
        state["total_rows"] = len(rows)
        state["last_refresh_at"] = _utc_now().isoformat()
        state["last_error"] = None
        state["last_keywords_hash"] = current_hash
        state["duckdb_ready"] = True
        telegram_sync.save_state()
        return {"rows": rows, "processed_files": len(_duckdb_source_files()), "mode": "duckdb"}

    source_offsets = state.get("source_offsets") if isinstance(state.get("source_offsets"), dict) else {}
    keywords = _get_event_keywords()
    current_hash = _keywords_hash(keywords)
    source_map = _source_selector_map()
    files = sorted(PAYME_OUT_DIR.glob("*.jsonl"))
    existing_names = {path.name for path in files}

    need_full = force_full or state.get("last_keywords_hash") not in (None, current_hash)
    existing_rows = [] if need_full else _load_analysis_cache_rows("events")
    rows_by_key: Dict[str, Dict[str, Any]] = {
        _event_row_key(row): row for row in existing_rows if isinstance(row, dict)
    }
    removed_leads = {Path(name).stem for name in list(source_offsets.keys()) if name not in existing_names}
    if removed_leads:
        rows_by_key = {
            key: row for key, row in rows_by_key.items()
            if str(row.get("lead") or "") not in removed_leads
        }
        source_offsets = {key: value for key, value in source_offsets.items() if key in existing_names}
    reset_leads: set[str] = set()
    if need_full:
        source_offsets = {}

    for jf in files:
        lead_name = jf.stem
        file_key = jf.name
        try:
            stat = jf.stat()
        except OSError:
            continue
        previous = source_offsets.get(file_key) if isinstance(source_offsets, dict) else None
        start_offset = 0
        if isinstance(previous, dict):
            prev_offset = int(previous.get("offset", 0) or 0)
            prev_size = int(previous.get("size", 0) or 0)
            if stat.st_size >= prev_offset and stat.st_size >= prev_size and not need_full:
                start_offset = prev_offset
            else:
                reset_leads.add(lead_name)
                start_offset = 0
        else:
            start_offset = 0

        source_selector = source_map.get(lead_name.lower())
        with jf.open("r", encoding="utf-8", errors="replace") as file:
            file.seek(max(start_offset, 0))
            while True:
                line = file.readline()
                if not line:
                    break
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("message", {})
                matched = _match_event_keywords(msg.get("text") or "", keywords)
                if not matched:
                    continue
                date_utc = str(msg.get("date_utc") or "").strip()
                if not date_utc:
                    continue
                sender = rec.get("sender", {})
                row = EventMessageDTO(
                    lead=lead_name,
                    source_selector=source_selector,
                    message_id=int(msg.get("id") or 0),
                    date_utc=date_utc,
                    text=str(msg.get("text") or ""),
                    sender_username=sender.get("username"),
                    sender_name=sender.get("name"),
                    matched_keywords=matched,
                ).dict()
                _merge_event_date_fields(row, rows_by_key.get(_event_row_key(row)))
                rows_by_key[_event_row_key(row)] = row
            source_offsets[file_key] = {
                "offset": file.tell(),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }

    if reset_leads:
        rows_by_key = {
            key: row for key, row in rows_by_key.items()
            if str(row.get("lead") or "") not in reset_leads
        }
        source_map = _source_selector_map()
        for lead_name in reset_leads:
            jf = PAYME_OUT_DIR / f"{lead_name}.jsonl"
            if not jf.exists():
                continue
            source_selector = source_map.get(lead_name.lower())
            with jf.open("r", encoding="utf-8", errors="replace") as file:
                for line in file:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(rec, dict):
                        continue
                    msg = rec.get("message", {})
                    matched = _match_event_keywords(msg.get("text") or "", keywords)
                    if not matched:
                        continue
                    date_utc = str(msg.get("date_utc") or "").strip()
                    if not date_utc:
                        continue
                    sender = rec.get("sender", {})
                    row = EventMessageDTO(
                        lead=lead_name,
                        source_selector=source_selector,
                        message_id=int(msg.get("id") or 0),
                        date_utc=date_utc,
                        text=str(msg.get("text") or ""),
                        sender_username=sender.get("username"),
                        sender_name=sender.get("name"),
                        matched_keywords=matched,
                    ).dict()
                    _merge_event_date_fields(row, rows_by_key.get(_event_row_key(row)))
                    rows_by_key[_event_row_key(row)] = row
                try:
                    stat = jf.stat()
                    source_offsets[jf.name] = {
                        "offset": file.tell(),
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                    }
                except OSError:
                    pass

    rows = sorted(
        rows_by_key.values(),
        key=lambda item: str(item.get("date_utc") or ""),
        reverse=True,
    )
    _save_analysis_cache_rows("events", rows)
    state["source_offsets"] = source_offsets
    state["total_rows"] = len(rows)
    state["last_refresh_at"] = _utc_now().isoformat()
    state["last_error"] = None
    state["last_keywords_hash"] = current_hash
    telegram_sync.save_state()
    return {"rows": rows, "processed_files": len(source_offsets)}


def _schedule_analysis_refresh(kind: AnalysisKind, force_full: bool = False) -> bool:
    task = _analysis_refresh_tasks.get(kind)
    if task is not None and not task.done():
        return False
    try:
        _analysis_refresh_tasks[kind] = asyncio.create_task(_refresh_analysis_cache_async(kind, force_full=force_full))
    except RuntimeError:
        _analysis_refresh_tasks[kind] = None
        return False
    return True


def _analysis_rows(kind: AnalysisKind, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    safe_limit = max(1, int(limit)) if limit is not None else None
    if kind == "contacts":
        rows = _duckdb_load_contact_rows(limit=safe_limit or 200000)
        if rows:
            return rows
    if kind == "crm":
        rows = _duckdb_load_crm_rows(limit=safe_limit or 200000)
        if rows:
            return rows
    if kind == "events":
        rows = _duckdb_load_event_rows(limit=safe_limit or 200000)
        if rows or _duckdb_events_ready():
            return rows
    if safe_limit is not None:
        return _load_analysis_cache_rows_limited(kind, safe_limit)
    return _load_analysis_cache_rows(kind)


__all__ = [
    "refresh_legacy_globals",
    "_analysis_cache_path",
    "_analysis_rows",
    "_analysis_state",
    "_build_analysis_status",
    "_load_analysis_cache_rows_limited",
    "_refresh_contacts_cache_sync",
    "_refresh_crm_cache_sync",
    "_refresh_event_cache_sync",
    "_refresh_routes_cache_sync",
    "_schedule_analysis_refresh",
]
