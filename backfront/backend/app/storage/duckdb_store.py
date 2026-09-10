"""DuckDB storage helpers extracted from the legacy backend."""

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

from app.storage.duckdb.connection import ensure_duckdb_available
from app.storage.duckdb.ingest import bootstrap_required, source_file_stats
from app.storage.duckdb.maintenance import indexes_ready_after_bootstrap
from app.storage.duckdb.schema import DUCKDB_EXPORT_TABLES, init_schema

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


def _duckdb_export_parquet_sync() -> List[str]:
    ensure_duckdb_available(duckdb)
    _duckdb_init_schema_sync()
    _ensure_parquet_dir_exists()
    conn = _duckdb_connect()
    exported: List[str] = []
    try:
        for table_name, file_name in DUCKDB_EXPORT_TABLES.items():
            target = (PARQUET_DIR / file_name).resolve()
            conn.execute(
                f"COPY (SELECT * FROM {table_name}) TO {_duckdb_sql_string_literal(str(target))} (FORMAT 'parquet', COMPRESSION 'zstd')",
            )
            exported.append(_path_to_app_relative(target))

        contacts_target = (PARQUET_DIR / "contacts_summary.parquet").resolve()
        conn.execute(
            f"""
            COPY (
                WITH base AS (
                    SELECT
                        {_duckdb_contact_key_sql()} AS contact_key,
                        source_jsonl,
                        sender_id,
                        sender_username,
                        sender_name,
                        text,
                        date_utc,
                        date_utc_raw
                    FROM messages_raw
                )
                SELECT
                    contact_key,
                    max(sender_id) AS sender_id,
                    max(sender_username) AS sender_username,
                    max(sender_name) AS sender_name,
                    count(*) AS total_messages,
                    min(date_utc_raw) AS first_message_at,
                    max(date_utc_raw) AS last_message_at,
                    arg_max(source_jsonl, coalesce(date_utc_raw, '')) AS latest_source_jsonl,
                    arg_max(text, coalesce(date_utc_raw, '')) AS latest_message_preview
                FROM base
                WHERE contact_key IS NOT NULL
                GROUP BY contact_key
            ) TO {_duckdb_sql_string_literal(str(contacts_target))} (FORMAT 'parquet', COMPRESSION 'zstd')
            """,
        )
        exported.append(_path_to_app_relative(contacts_target))
    finally:
        conn.close()
    return exported


def _duckdb_init_schema_sync() -> None:
    conn = _duckdb_connect()
    try:
        init_schema(conn)
        _duckdb_refresh_file_registry_stats_sync(conn)
    finally:
        conn.close()


def _duckdb_refresh_file_registry_stats_sync(conn: Any) -> Dict[str, int]:
    try:
        conn.execute(
            """
            UPDATE file_registry
            SET source_key = regexp_replace(coalesce(nullif(file_name, ''), split_part(source_jsonl, '/', -1)), '\\.jsonl$', '')
            WHERE source_key IS NULL OR trim(source_key) = ''
            """
        )
        conn.execute(
            """
            UPDATE messages_raw
            SET source_key = regexp_replace(split_part(source_jsonl, '/', -1), '\\.jsonl$', '')
            WHERE source_key IS NULL OR trim(source_key) = ''
            """
        )
        conn.execute(
            """
            UPDATE file_registry
            SET
                records_count_jsonl = coalesce(records_count, 0),
                records_count_duckdb = coalesce((
                    SELECT count(*)
                    FROM messages_raw
                    WHERE messages_raw.source_key = file_registry.source_key
                ), 0),
                lag_rows = greatest(
                    coalesce(records_count, 0) - coalesce((
                        SELECT count(*)
                        FROM messages_raw
                        WHERE messages_raw.source_key = file_registry.source_key
                    ), 0),
                    0
                )
            """
        )
        row = conn.execute(
            """
            SELECT
                coalesce(sum(records_count_jsonl), 0),
                coalesce(sum(records_count_duckdb), 0),
                coalesce(sum(lag_rows), 0)
            FROM file_registry
            """
        ).fetchone()
        return {
            "jsonl_rows_total": int((row[0] if row else 0) or 0),
            "duckdb_rows_total": int((row[1] if row else 0) or 0),
            "lag_rows_total": int((row[2] if row else 0) or 0),
        }
    except Exception as exc:
        _duckdb_append_log(f"DuckDB stats refresh skipped: {exc}")
        return {"jsonl_rows_total": 0, "duckdb_rows_total": 0, "lag_rows_total": 0}


def _duckdb_refresh_read_snapshot_sync(conn: Any) -> bool:
    try:
        if not DUCKDB_PATH.exists():
            return False
        conn.execute("CHECKPOINT")
        _ensure_duckdb_dir_exists()
        target = DUCKDB_READ_PATH
        tmp_target = target.with_name(f"{target.name}.tmp")
        shutil.copy2(DUCKDB_PATH, tmp_target)
        os.replace(tmp_target, target)
        stat = target.stat()
        _duckdb_update_status(
            read_snapshot_path=str(target),
            read_snapshot_exists=True,
            read_snapshot_mtime=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        )
        return True
    except Exception as exc:
        _duckdb_append_log(f"DuckDB read snapshot skipped: {exc}")
        return False


def _duckdb_stage_jsonl_to_parquet_sync(path: Path, stat: os.stat_result, source_jsonl: str, file_mtime_sec: float) -> Path:
    ensure_duckdb_available(duckdb)
    if _duckdb_file_looks_like_parquet(path):
        return path.resolve()
    if _duckdb_jsonl_has_parquet_payload(path):
        raise RuntimeError(f"{path.name} has .jsonl extension but contains parquet payload")
    target = _duckdb_stage_parquet_path(path, stat)
    if target.exists():
        if _duckdb_stage_parquet_is_valid_sync(target):
            _duckdb_cleanup_stage_sidecars_sync(path, keep_path=target)
            return target
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
    conn = _duckdb_connect()
    try:
        conn.execute(
            f"""
            COPY (
                WITH src AS (
                    SELECT
                        row_number() OVER () AS row_num,
                        json
                    FROM read_json_objects(?, format='newline_delimited', ignore_errors=true)
                    WHERE json IS NOT NULL
                ),
                parsed AS (
                    SELECT
                        row_num,
                        json,
                        TRY_CAST(json_extract_string(json, '$.chat.id') AS BIGINT) AS chat_id,
                        nullif(json_extract_string(json, '$.chat.username'), '') AS chat_username,
                        nullif(json_extract_string(json, '$.chat.title'), '') AS chat_title,
                        TRY_CAST(json_extract_string(json, '$.sender.id') AS BIGINT) AS sender_id,
                        nullif(json_extract_string(json, '$.sender.username'), '') AS sender_username,
                        nullif(json_extract_string(json, '$.sender.name'), '') AS sender_name,
                        TRY_CAST(json_extract_string(json, '$.message.id') AS BIGINT) AS message_id,
                        coalesce(json_extract_string(json, '$.message.text'), '') AS text,
                        TRY_CAST(json_extract_string(json, '$.message.date_utc') AS TIMESTAMPTZ) AS date_utc,
                        nullif(json_extract_string(json, '$.message.date_utc'), '') AS date_utc_raw,
                        TRY_CAST(json_extract_string(json, '$.message.reply_to_msg_id') AS BIGINT) AS reply_to_msg_id,
                        coalesce(TRY_CAST(json_extract(json, '$.message.has_media') AS BOOLEAN), false) AS has_media,
                        nullif(json_extract_string(json, '$.message.media_path'), '') AS media_path
                    FROM src
                )
                SELECT
                    CASE
                        WHEN message_id IS NOT NULL THEN md5(
                            'telegram-message\n' || ? || '\n' ||
                            coalesce(CAST(chat_id AS VARCHAR), chat_username, chat_title, '') || '\n' ||
                            CAST(message_id AS VARCHAR)
                        )
                        ELSE md5(
                            'telegram-line\n' || ? || '\n' ||
                            CAST(row_num AS VARCHAR) || '\n' ||
                            coalesce(date_utc_raw, '') || '\n' ||
                            coalesce(CAST(sender_id AS VARCHAR), '') || '\n' ||
                            coalesce(text, '')
                        )
                    END AS row_hash,
                    ? AS source_jsonl,
                    regexp_replace(split_part(?, '/', -1), '\\.jsonl$', '') AS source_key,
                    CAST(row_num AS BIGINT) AS source_offset,
                    chat_id,
                    chat_username,
                    chat_title,
                    sender_id,
                    sender_username,
                    sender_name,
                    message_id,
                    text,
                    date_utc,
                    date_utc_raw,
                    reply_to_msg_id,
                    has_media,
                    media_path,
                    ? AS file_mtime_sec,
                    current_timestamp AS ingested_at
                FROM parsed
            ) TO {_duckdb_sql_string_literal(str(target))} (FORMAT 'parquet', COMPRESSION 'zstd')
            """,
            [str(path), source_jsonl, source_jsonl, source_jsonl, source_jsonl, float(file_mtime_sec or 0.0)],
        )
    finally:
        conn.close()
    if not _duckdb_stage_parquet_is_valid_sync(target):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"Invalid parquet sidecar schema for {path.name}")
    _duckdb_cleanup_stage_sidecars_sync(path, keep_path=target)
    return target


def _duckdb_ingest_sync(force_full: bool = False) -> Dict[str, int]:
    ensure_duckdb_available(duckdb)

    _duckdb_init_schema_sync()
    initial_counts = _duckdb_counts_sync()
    bootstrap_mode = bootstrap_required(initial_counts, force_full=force_full)
    sync_mode = "bootstrap" if bootstrap_mode else "incremental"
    file_stats = source_file_stats(_duckdb_source_files())
    source_files_total = len(file_stats)
    bytes_total = sum(max(0, int(stat.st_size or 0)) for _, stat in file_stats)
    _duckdb_update_status(
        source_files_total=source_files_total,
        progress_total=source_files_total,
        progress_current=0,
        progress_percent=0.0,
        progress_label="Подготовка DuckDB",
        current_item=None,
        last_error=None,
        stale_reason=None,
        bytes_total=bytes_total,
        bytes_processed=0,
        rows_ingested_in_run=0,
        last_deduplicated_rows=0,
        rows_per_sec=0.0,
        mb_per_sec=0.0,
        average_batch_size=0.0,
        current_file_rows_per_sec=0.0,
        current_file_mb_per_sec=0.0,
        sync_mode=sync_mode,
        current_phase="scan",
        indexes_ready=not bootstrap_mode,
        parquet_stage_enabled=_DUCKDB_PARQUET_STAGING_ENABLED,
        parquet_stage_used=False,
        parquet_stage_files=0,
        corrupt_jsonl_files=0,
        corrupt_jsonl_examples=[],
        last_file_name=None,
        last_file_duration_sec=0.0,
        last_file_rows=0,
    )

    conn = _duckdb_connect()
    total_inserted = 0
    bytes_processed_completed = 0
    run_started_monotonic = time.monotonic()
    total_batch_rows = 0
    total_batch_flushes = 0
    parquet_stage_files = 0
    changed_source_files = 0
    corrupt_jsonl_files = 0
    corrupt_jsonl_examples: List[str] = []
    try:
        _duckdb_append_log(f"DuckDB sync mode: {sync_mode}")
        for index, (path, stat) in enumerate(file_stats, start=1):
            source_jsonl = _path_to_app_relative(path)
            file_started_monotonic = time.monotonic()
            _duckdb_update_status(
                progress_current=index - 1,
                progress_total=source_files_total,
                progress_percent=round(((index - 1) / source_files_total) * 100.0, 2) if source_files_total else 100.0,
                progress_label="Догрузка JSONL в DuckDB",
                current_item=path.stem,
                current_phase="raw_ingest",
            )
            _duckdb_append_log(f"Проверяю {path.name}")

            previous_row = conn.execute(
                """
                SELECT size_bytes, ingested_offset, records_count, parquet_path, parquet_size_bytes, parquet_mtime_sec
                FROM file_registry
                WHERE source_jsonl = ?
                """,
                [source_jsonl],
            ).fetchone()

            prev_offset = int(previous_row[1] or 0) if previous_row else 0
            prev_records_count = int(previous_row[2] or 0) if previous_row else 0
            prev_parquet_path = str(previous_row[3] or "") if previous_row else ""
            prev_parquet_size = int(previous_row[4] or 0) if previous_row else 0
            prev_parquet_mtime = float(previous_row[5] or 0.0) if previous_row else 0.0
            file_size = int(stat.st_size)
            file_mtime_sec = float(stat.st_mtime)

            if _duckdb_jsonl_has_parquet_payload(path):
                corrupt_jsonl_files += 1
                if len(corrupt_jsonl_examples) < 5:
                    corrupt_jsonl_examples.append(path.name)
                message = (
                    f"{path.name}: пропуск — файл имеет расширение .jsonl, но внутри parquet payload. "
                    "Оставляю текущий кеш DuckDB; первоисточник нужно заново выгрузить из Telegram."
                )
                _duckdb_append_log(message)
                if corrupt_jsonl_files <= 5:
                    _append_runtime_log("duckdb", message)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO file_registry (
                        source_jsonl, source_key, file_name, size_bytes, mtime_sec, ingested_offset, records_count,
                        parquet_path, parquet_size_bytes, parquet_mtime_sec, last_ingested_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        source_jsonl,
                        _duckdb_source_key(source_jsonl),
                        path.name,
                        file_size,
                        file_mtime_sec,
                        file_size,
                        prev_records_count,
                        prev_parquet_path or None,
                        prev_parquet_size or None,
                        prev_parquet_mtime or None,
                        _utc_now(),
                    ],
                )
                bytes_processed_completed += max(0, file_size)
                elapsed_sec = max(0.001, time.monotonic() - run_started_monotonic)
                file_elapsed_sec = max(0.001, time.monotonic() - file_started_monotonic)
                _duckdb_update_status(
                    progress_current=index,
                    progress_total=source_files_total,
                    progress_percent=round((index / source_files_total) * 100.0, 2) if source_files_total else 100.0,
                    progress_label="Пропущен повреждённый JSONL",
                    current_item=path.stem,
                    current_phase="source_warning",
                    bytes_processed=bytes_processed_completed,
                    rows_ingested_in_run=total_inserted,
                    rows_per_sec=round(total_inserted / elapsed_sec, 2),
                    mb_per_sec=round((bytes_processed_completed / 1024 / 1024) / elapsed_sec, 3),
                    current_file_rows_per_sec=0.0,
                    current_file_mb_per_sec=round((file_size / 1024 / 1024) / file_elapsed_sec, 3),
                    corrupt_jsonl_files=corrupt_jsonl_files,
                    corrupt_jsonl_examples=corrupt_jsonl_examples,
                    last_file_name=path.name,
                    last_file_duration_sec=round(file_elapsed_sec, 3),
                    last_file_rows=0,
                )
                continue

            reset_file = bool(force_full or (previous_row and file_size < prev_offset))
            if reset_file:
                conn.execute("DELETE FROM messages_raw WHERE source_jsonl = ?", [source_jsonl])
                prev_offset = 0
                prev_records_count = 0
                _duckdb_append_log(f"Перестраиваю {path.name} с нуля")

            inserted_for_file = 0
            last_offset = prev_offset
            used_parquet_stage = False
            parquet_path_value: Optional[str] = None
            parquet_size_bytes_value: Optional[int] = None
            parquet_mtime_sec_value: Optional[float] = None
            if _duckdb_should_use_parquet_stage(path, stat, bootstrap_mode, prev_offset=prev_offset, reset_file=reset_file):
                _duckdb_update_status(
                    current_phase="parquet_stage",
                    progress_label="Подготовка Parquet staging",
                    current_item=f"{path.stem} · staging parquet",
                )
                try:
                    stage_started_monotonic = time.monotonic()
                    parquet_path = _duckdb_stage_parquet_path(path, stat)
                    parquet_reused = bool(
                        prev_parquet_path
                        and prev_parquet_size > 0
                        and abs(prev_parquet_mtime - file_mtime_sec) < 0.0001
                        and Path(prev_parquet_path).exists()
                        and Path(prev_parquet_path).resolve() == parquet_path.resolve()
                    )
                    parquet_path = _duckdb_stage_jsonl_to_parquet_sync(path, stat, source_jsonl, file_mtime_sec)
                    stage_elapsed_sec = max(0.001, time.monotonic() - stage_started_monotonic)
                    parquet_stat = parquet_path.stat()
                    parquet_path_value = str(parquet_path)
                    parquet_size_bytes_value = int(parquet_stat.st_size)
                    parquet_mtime_sec_value = float(parquet_stat.st_mtime)
                    append_bytes = max(0, file_size - max(0, int(prev_offset or 0)))
                    _duckdb_append_log(
                        f"{path.name}: parquet staging {'reuse' if parquet_reused else 'build'} за {round(stage_elapsed_sec, 2)}с -> {parquet_path.name} · append {round(append_bytes / 1024 / 1024, 2)} MB"
                    )
                    _duckdb_update_status(
                        current_phase="parquet_load",
                        progress_label="Загрузка staging parquet в DuckDB",
                        current_item=f"{path.stem} · parquet load",
                        parquet_stage_used=True,
                        parquet_stage_files=parquet_stage_files + 1,
                    )
                    inserted_for_file = int(conn.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(parquet_path)]).fetchone()[0] or 0)
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO messages_raw (
                            row_hash, source_jsonl, source_key, source_offset, chat_id, chat_username, chat_title,
                            sender_id, sender_username, sender_name, message_id, text, date_utc,
                            date_utc_raw, reply_to_msg_id, has_media, media_path, file_mtime_sec, ingested_at
                        )
                        SELECT
                            row_hash,
                            source_jsonl,
                            regexp_replace(split_part(source_jsonl, '/', -1), '\\.jsonl$', '') AS source_key,
                            source_offset,
                            chat_id,
                            chat_username,
                            chat_title,
                            sender_id, sender_username, sender_name, message_id, text, date_utc,
                            date_utc_raw, reply_to_msg_id, has_media, media_path, file_mtime_sec, ingested_at
                        FROM (
                            SELECT
                                *,
                                row_number() OVER (
                                    PARTITION BY row_hash
                                    ORDER BY source_offset DESC, ingested_at DESC
                                ) AS rn
                            FROM read_parquet(?)
                        )
                        WHERE rn = 1
                        """,
                        [str(parquet_path)],
                    )
                    used_parquet_stage = True
                    parquet_stage_files += 1
                    total_batch_rows += inserted_for_file
                    total_batch_flushes += 1
                    last_offset = file_size
                except Exception as exc:
                    _duckdb_append_log(f"{path.name}: parquet staging fallback -> {exc}")
                    _append_runtime_log("duckdb", f"parquet staging fallback for {path.name}: {exc}")
                    parquet_path_value = None
                    parquet_size_bytes_value = None
                    parquet_mtime_sec_value = None
            elif prev_parquet_path:
                _duckdb_cleanup_stage_sidecars_sync(path)

            if not used_parquet_stage:
                batch: List[tuple[Any, ...]] = []
                last_progress_emit_at = time.monotonic()
                last_log_emit_at = last_progress_emit_at
                last_logged_rows = 0
                for source_offset, current_offset, record in _iter_jsonl_records_with_offsets(path, offset=prev_offset):
                    batch.append(_duckdb_row_from_record(source_jsonl, file_mtime_sec, source_offset, record))
                    inserted_for_file += 1
                    last_offset = max(last_offset, int(current_offset))
                    if len(batch) >= _DUCKDB_BATCH_SIZE:
                        total_batch_rows += len(batch)
                        total_batch_flushes += 1
                        _duckdb_update_status(
                            current_phase="db_write",
                            current_item=f"{path.stem} · flush {len(batch)} строк в DuckDB",
                        )
                        _duckdb_flush_message_batch_sync(conn, batch)
                        batch = []
                    now_monotonic = time.monotonic()
                    file_fraction = 1.0
                    file_percent = 100.0
                    if file_size > 0:
                        file_fraction = min(1.0, max(float(current_offset) / float(file_size), 0.0))
                        file_percent = round(file_fraction * 100.0, 1)
                    should_emit_progress = (
                        inserted_for_file == 1
                        or inserted_for_file % 5000 == 0
                        or (now_monotonic - last_progress_emit_at) >= _DUCKDB_PROGRESS_EMIT_SEC
                    )
                    if should_emit_progress:
                        overall_fraction = 1.0 if source_files_total <= 0 else min(
                            1.0,
                            max(((index - 1) + file_fraction) / float(source_files_total), 0.0),
                        )
                        bytes_processed = bytes_processed_completed + max(0, int(current_offset or 0))
                        elapsed_sec = max(0.001, now_monotonic - run_started_monotonic)
                        file_elapsed_sec = max(0.001, now_monotonic - file_started_monotonic)
                        rows_ingested_in_run = total_inserted + inserted_for_file
                        _duckdb_update_status(
                            progress_current=index - 1,
                            progress_total=source_files_total,
                            progress_percent=round(overall_fraction * 100.0, 2),
                            progress_label="Догрузка JSONL в DuckDB",
                            current_item=f"{path.stem} · {file_percent}% файла · {inserted_for_file} строк",
                            bytes_processed=bytes_processed,
                            rows_ingested_in_run=rows_ingested_in_run,
                            rows_per_sec=round(rows_ingested_in_run / elapsed_sec, 2),
                            mb_per_sec=round((bytes_processed / 1024 / 1024) / elapsed_sec, 3),
                            average_batch_size=round(total_batch_rows / total_batch_flushes, 2) if total_batch_flushes else 0.0,
                            current_file_rows_per_sec=round(inserted_for_file / file_elapsed_sec, 2),
                            current_file_mb_per_sec=round((max(0, int(current_offset or 0)) / 1024 / 1024) / file_elapsed_sec, 3),
                        )
                        last_progress_emit_at = now_monotonic
                    should_emit_log = (
                        inserted_for_file == 1
                        or inserted_for_file - last_logged_rows >= 10000
                        or (now_monotonic - last_log_emit_at) >= _DUCKDB_LOG_EMIT_SEC
                    )
                    if should_emit_log:
                        _duckdb_append_log(f"{path.name}: {inserted_for_file} строк, {file_percent}% файла")
                        last_log_emit_at = now_monotonic
                        last_logged_rows = inserted_for_file
                if batch:
                    total_batch_rows += len(batch)
                    total_batch_flushes += 1
                    _duckdb_update_status(
                        current_phase="db_write",
                        current_item=f"{path.stem} · финальный flush {len(batch)} строк в DuckDB",
                    )
                    _duckdb_flush_message_batch_sync(conn, batch)

            final_offset = file_size if file_size >= last_offset else last_offset
            records_count = prev_records_count + inserted_for_file if not reset_file else inserted_for_file
            conn.execute(
                """
                INSERT OR REPLACE INTO file_registry (
                    source_jsonl, source_key, file_name, size_bytes, mtime_sec, ingested_offset, records_count,
                    parquet_path, parquet_size_bytes, parquet_mtime_sec, last_ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    source_jsonl,
                    _duckdb_source_key(source_jsonl),
                    path.name,
                    file_size,
                    file_mtime_sec,
                    final_offset,
                    records_count,
                    parquet_path_value,
                    parquet_size_bytes_value,
                    parquet_mtime_sec_value,
                    _utc_now(),
                ],
            )

            total_inserted += inserted_for_file
            if inserted_for_file > 0 or reset_file:
                changed_source_files += 1
            bytes_processed_completed += max(0, file_size)
            elapsed_sec = max(0.001, time.monotonic() - run_started_monotonic)
            file_elapsed_sec = max(0.001, time.monotonic() - file_started_monotonic)
            _duckdb_update_status(
                progress_current=index,
                progress_total=source_files_total,
                progress_percent=round((index / source_files_total) * 100.0, 2) if source_files_total else 100.0,
                bytes_processed=bytes_processed_completed,
                rows_ingested_in_run=total_inserted,
                rows_per_sec=round(total_inserted / elapsed_sec, 2),
                mb_per_sec=round((bytes_processed_completed / 1024 / 1024) / elapsed_sec, 3),
                average_batch_size=round(total_batch_rows / total_batch_flushes, 2) if total_batch_flushes else 0.0,
                current_file_rows_per_sec=round(inserted_for_file / file_elapsed_sec, 2),
                current_file_mb_per_sec=round((file_size / 1024 / 1024) / file_elapsed_sec, 3),
                parquet_stage_used=bool(parquet_stage_files > 0),
                parquet_stage_files=parquet_stage_files,
                last_file_name=path.name,
                last_file_duration_sec=round(file_elapsed_sec, 3),
                last_file_rows=inserted_for_file,
            )
            _duckdb_append_log(
                f"{path.name} завершён: {inserted_for_file} строк за {round(file_elapsed_sec, 2)}с · {round(inserted_for_file / file_elapsed_sec, 2)} rows/sec"
            )

        if bootstrap_mode and _DUCKDB_DEFER_HEAVY_INDEXES:
            _duckdb_update_status(
                progress_label="Построение индексов DuckDB",
                current_item="Индексы и оптимизация чтения",
                current_phase="index_build",
            )
            _duckdb_append_log("Строю heavy indexes после bootstrap")
            _duckdb_ensure_indexes_sync(include_heavy=True)
        elif not _DUCKDB_DEFER_HEAVY_INDEXES:
            _duckdb_update_status(
                progress_label="Проверка индексов DuckDB",
                current_item="Индексы работают inline",
                current_phase="index_check",
            )
            _duckdb_ensure_indexes_sync(include_heavy=True)
        elif not bootstrap_mode:
            _duckdb_update_status(current_phase="finalize")

        duplicates_removed = _duckdb_deduplicate_messages_sync(conn)
        if duplicates_removed:
            _duckdb_append_log(f"DuckDB dedupe: удалено дублей сообщений {duplicates_removed}")
            _append_runtime_log("duckdb", f"dedupe removed {duplicates_removed} duplicate message rows")

        lag_counts = _duckdb_refresh_file_registry_stats_sync(conn)
        _duckdb_refresh_read_snapshot_sync(conn)
        counts = _duckdb_counts_sync()
        counts.update(lag_counts)
        counts["rows_ingested_in_run"] = total_inserted
        counts["source_files_total"] = source_files_total
        counts["source_files_changed"] = changed_source_files
        now_iso = _utc_now().isoformat()
        elapsed_sec = max(0.001, time.monotonic() - run_started_monotonic)
        indexes_ready = indexes_ready_after_bootstrap(
            defer_heavy_indexes=_DUCKDB_DEFER_HEAVY_INDEXES,
            bootstrap_mode=bootstrap_mode,
            status_snapshot=_duckdb_status_snapshot(),
        )
        _duckdb_update_status(
            cache_ready=counts["message_rows"] > 0 or counts["tracked_files"] > 0,
            tracked_files=counts["tracked_files"],
            file_registry_rows=counts["file_registry_rows"],
            message_rows=counts["message_rows"],
            jsonl_rows_total=counts.get("jsonl_rows_total", 0),
            duckdb_rows_total=counts.get("duckdb_rows_total", counts["message_rows"]),
            lag_rows_total=counts.get("lag_rows_total", 0),
            duplicate_message_rows=counts["duplicate_message_rows"],
            last_deduplicated_rows=duplicates_removed,
            source_files_indexed=counts["source_files_indexed"],
            progress_current=source_files_total,
            progress_total=source_files_total,
            progress_percent=100.0 if source_files_total > 0 else 0.0,
            progress_label="DuckDB готов",
            current_item=None,
            last_refresh_at=now_iso,
            last_error=None,
            stale_reason=None if counts["message_rows"] > 0 else "DuckDB ещё не проиндексировал сообщения",
            bytes_processed=bytes_processed_completed,
            rows_ingested_in_run=total_inserted,
            rows_per_sec=round(total_inserted / elapsed_sec, 2),
            mb_per_sec=round((bytes_processed_completed / 1024 / 1024) / elapsed_sec, 3),
            average_batch_size=round(total_batch_rows / total_batch_flushes, 2) if total_batch_flushes else 0.0,
            current_file_rows_per_sec=0.0,
            current_file_mb_per_sec=0.0,
            current_phase="idle",
            indexes_ready=indexes_ready,
            parquet_stage_used=bool(parquet_stage_files > 0),
            parquet_stage_files=parquet_stage_files,
            corrupt_jsonl_files=corrupt_jsonl_files,
            corrupt_jsonl_examples=corrupt_jsonl_examples,
        )
        _duckdb_append_log(
            f"DuckDB обновлён: файлов {counts['tracked_files']}, сообщений {counts['message_rows']}, новых строк {total_inserted}, скорость {round(total_inserted / elapsed_sec, 2)} rows/sec"
        )
        return counts
    finally:
        conn.close()


def _duckdb_load_contact_rows(limit: int = 50000) -> List[Dict[str, Any]]:
    if not _duckdb_contacts_ready():
        return []
    selector_map = _managed_selector_map()
    conn = _duckdb_connect_readonly()
    try:
        sql = f"""
            WITH base AS (
                SELECT
                    {_duckdb_contact_key_sql()} AS contact_key,
                    source_jsonl,
                    sender_id,
                    sender_username,
                    sender_name,
                    text,
                    date_utc,
                    date_utc_raw,
                    message_id
                FROM messages_raw
            )
            SELECT
                contact_key,
                max(sender_id) AS sender_id,
                max(sender_username) AS sender_username,
                max(sender_name) AS sender_name,
                count(*) AS total_messages,
                min(date_utc_raw) AS first_message_at,
                max(date_utc_raw) AS last_message_at,
                arg_max(source_jsonl, coalesce(date_utc_raw, '')) AS latest_source_jsonl,
                arg_max(text, coalesce(date_utc_raw, '')) AS latest_message_preview,
                string_agg(DISTINCT source_jsonl, '||') AS source_jsonl_list
            FROM base
            WHERE contact_key IS NOT NULL
            GROUP BY contact_key
            ORDER BY max(coalesce(date_utc_raw, '')) DESC, count(*) DESC
            LIMIT ?
        """
        raw_rows = conn.execute(sql, [max(1, int(limit or 1))]).fetchall()
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    for row in raw_rows:
        contact_key = str(row[0] or "").strip()
        if not contact_key:
            continue
        sender_id = _duckdb_optional_int(row[1])
        sender_username = _contacts_compact_text(row[2]) or None
        sender_name = _contacts_compact_text(row[3]) or None
        latest_source_jsonl = str(row[7] or "")
        latest_lead = _duckdb_source_jsonl_to_lead_name(latest_source_jsonl)
        source_jsonl_list = str(row[9] or "")
        lead_names = [
            _duckdb_source_jsonl_to_lead_name(item)
            for item in source_jsonl_list.split("||")
            if str(item or "").strip()
        ]
        unique_leads: List[str] = []
        seen_leads: set[str] = set()
        for lead_name in lead_names:
            normalized = str(lead_name or "").strip()
            if not normalized or normalized in seen_leads:
                continue
            seen_leads.add(normalized)
            unique_leads.append(normalized)
        source_selectors: List[str] = []
        seen_selectors: set[str] = set()
        for lead_name in unique_leads:
            selector = selector_map.get(str(lead_name).lower())
            if not selector or selector in seen_selectors:
                continue
            seen_selectors.add(selector)
            source_selectors.append(selector)
        preview = _contacts_compact_text(str(row[8] or ""))[:280] or None
        latest_message_text = str(row[8] or "").strip() or None
        items.append(
            TelegramContactDTO(
                contact_key=contact_key,
                sender_id=sender_id,
                sender_username=sender_username,
                sender_name=sender_name,
                display_name=_contacts_display_name(sender_name, sender_username, sender_id),
                total_messages=int(row[4] or 0),
                first_message_at=str(row[5] or "") or None,
                last_message_at=str(row[6] or "") or None,
                latest_lead=latest_lead or None,
                latest_message_preview=preview,
                latest_message_text=latest_message_text,
                related_messages_count=int(row[4] or 0),
                leads=unique_leads,
                source_selectors=source_selectors,
                related_messages=[],
            ).model_dump()
        )
    return items


def _duckdb_load_contact_message_rows(contact_key: str, limit: int = 5000) -> List[Dict[str, Any]]:
    target = str(contact_key or "").strip()
    if not target or not _duckdb_contacts_ready():
        return []
    selector_map = _managed_selector_map()
    conn = _duckdb_connect_readonly()
    try:
        sql = f"""
            WITH base AS (
                SELECT
                    {_duckdb_contact_key_sql()} AS contact_key,
                    source_jsonl,
                    sender_id,
                    sender_username,
                    sender_name,
                    text,
                    date_utc,
                    date_utc_raw,
                    message_id,
                    has_media
                FROM messages_raw
            )
            SELECT
                source_jsonl,
                sender_id,
                sender_username,
                sender_name,
                text,
                date_utc_raw,
                message_id,
                has_media
            FROM base
            WHERE contact_key = ?
            ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
            LIMIT ?
        """
        raw_rows = conn.execute(sql, [target, max(1, int(limit or 1))]).fetchall()
    finally:
        conn.close()

    items: List[Dict[str, Any]] = []
    for row in raw_rows:
        lead_name = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
        source_selector = selector_map.get(str(lead_name).lower())
        items.append(
            TelegramContactMessageDTO(
                lead=lead_name,
                source_selector=source_selector,
                message_id=int(row[6] or 0),
                date_utc=str(row[5] or ""),
                text=str(row[4] or ""),
                sender_id=_duckdb_optional_int(row[1]),
                sender_username=_contacts_compact_text(row[2]) or None,
                sender_name=_contacts_compact_text(row[3]) or None,
                has_media=bool(row[7]),
            ).model_dump()
        )
    return items


def _duckdb_rebuild_event_messages_sync() -> List[Dict[str, Any]]:
    if not _duckdb_contacts_ready():
        return []
    keywords = _get_event_keywords()
    keyword_hash = _keywords_hash(keywords)
    conn = _duckdb_connect()
    try:
        existing_date_rows = conn.execute(
            """
            SELECT row_key, event_date, event_date_confidence, event_date_source
            FROM event_messages
            WHERE event_date IS NOT NULL OR event_date_source IS NOT NULL
            """
        ).fetchall()
        existing_event_dates: Dict[str, Dict[str, Any]] = {
            str(item[0] or ""): {
                "event_date": str(item[1] or "") or None,
                "event_date_confidence": item[2],
                "event_date_source": str(item[3] or "") or None,
            }
            for item in existing_date_rows
            if str(item[0] or "")
        }
        raw_rows = conn.execute(
            """
            SELECT source_jsonl, message_id, date_utc_raw, text, sender_username, sender_name
            FROM messages_raw
            ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
            """
        ).fetchall()
    finally:
        conn.close()

    rows: List[Dict[str, Any]] = []
    selector_map = _managed_selector_map()
    batches: List[List[tuple[Any, ...]]] = []
    batch: List[tuple[Any, ...]] = []
    for raw in raw_rows:
        lead_name = _duckdb_source_jsonl_to_lead_name(str(raw[0] or ""))
        text = str(raw[3] or "")
        matched_keywords = _match_event_keywords(text, keywords)
        if not matched_keywords:
            continue
        date_utc = str(raw[2] or "").strip()
        if not date_utc:
            continue
        source_selector = selector_map.get(str(lead_name).lower())
        row = EventMessageDTO(
            lead=lead_name,
            source_selector=source_selector,
            message_id=int(raw[1] or 0),
            date_utc=date_utc,
            text=text,
            sender_username=str(raw[4] or "") or None,
            sender_name=str(raw[5] or "") or None,
            matched_keywords=matched_keywords,
        ).model_dump()
        _merge_event_date_fields(row, existing_event_dates.get(_event_row_key(row)))
        rows.append(row)
        batch.append(
            (
                _event_row_key(row),
                keyword_hash,
                row["lead"],
                row.get("source_selector"),
                int(row["message_id"] or 0),
                row["date_utc"],
                row.get("event_date"),
                row.get("event_date_confidence"),
                row.get("event_date_source"),
                _utc_now() if row.get("event_date_source") else None,
                row["text"],
                row.get("sender_username"),
                row.get("sender_name"),
                json.dumps(row.get("matched_keywords") or [], ensure_ascii=False),
                _utc_now(),
            )
        )
        if len(batch) >= 1000:
            batches.append(batch)
            batch = []
    if batch:
        batches.append(batch)

    conn = _duckdb_connect()
    try:
        conn.execute("DELETE FROM event_messages")
        for batch in batches:
            conn.executemany(
                """
                INSERT OR REPLACE INTO event_messages (
                    row_key, keyword_hash, lead, source_selector, message_id, date_utc_raw,
                    event_date, event_date_confidence, event_date_source, event_date_updated_at,
                    text, sender_username, sender_name, matched_keywords_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                batch,
            )
    finally:
        conn.close()
    rows.sort(key=lambda item: str(item.get("date_utc") or ""), reverse=True)
    return rows


def _duckdb_load_event_rows(limit: int = 5000) -> List[Dict[str, Any]]:
    if not _duckdb_contacts_ready():
        return []
    events_table_ready = bool(_analysis_state("events").get("duckdb_ready"))
    conn = _duckdb_connect_readonly()
    try:
        if events_table_ready:
            keyword_hash = _keywords_hash(_get_event_keywords())
            raw_rows = conn.execute(
                """
                SELECT
                    lead, source_selector, message_id, date_utc_raw, text,
                    sender_username, sender_name, matched_keywords_json,
                    event_date, event_date_confidence, event_date_source
                FROM event_messages
                WHERE keyword_hash = ?
                ORDER BY date_utc_raw DESC, message_id DESC
                LIMIT ?
                """,
                [keyword_hash, max(1, int(limit or 1))],
            ).fetchall()
            row_mode = "events"
        else:
            keywords = _get_event_keywords()
            where_parts = ["lower(coalesce(text, '')) LIKE ?" for _ in keywords]
            params = [f"%{keyword.lower()}%" for keyword in keywords]
            raw_rows = conn.execute(
                f"""
                SELECT
                    source_jsonl, message_id, date_utc_raw, text,
                    sender_username, sender_name
                FROM messages_raw
                WHERE {" OR ".join(where_parts) if where_parts else "false"}
                ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
                LIMIT ?
                """,
                [*params, max(1, int(limit or 1)) * 3],
            ).fetchall()
            row_mode = "messages"
    finally:
        conn.close()
    rows: List[Dict[str, Any]] = []
    selector_map = _managed_selector_map()
    for row in raw_rows:
        try:
            if row_mode == "events":
                item = EventMessageDTO(
                    lead=str(row[0] or ""),
                    source_selector=str(row[1] or "") or None,
                    message_id=int(row[2] or 0),
                    date_utc=str(row[3] or ""),
                    text=str(row[4] or ""),
                    sender_username=str(row[5] or "") or None,
                    sender_name=str(row[6] or "") or None,
                    matched_keywords=list(json.loads(str(row[7] or "[]"))),
                    event_date=str(row[8] or "") or None,
                    event_date_confidence=float(row[9]) if row[9] is not None else None,
                    event_date_source=str(row[10] or "") or None,
                ).model_dump()
            else:
                lead_name = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
                text = str(row[3] or "")
                matched_keywords = _match_event_keywords(text, _get_event_keywords())
                if not matched_keywords:
                    continue
                item = EventMessageDTO(
                    lead=lead_name,
                    source_selector=selector_map.get(str(lead_name).lower()),
                    message_id=int(row[1] or 0),
                    date_utc=str(row[2] or ""),
                    text=text,
                    sender_username=str(row[4] or "") or None,
                    sender_name=str(row[5] or "") or None,
                    matched_keywords=matched_keywords,
                ).model_dump()
            rows.append(item)
            if len(rows) >= max(1, int(limit or 1)):
                break
        except Exception:
            continue
    return rows


def _duckdb_search_sql_filters(
    query: str = "",
    lead_filter: str = "",
    author_filter: str = "",
    company_filter: str = "",
    phone_filter: str = "",
    email_filter: str = "",
    city_filter: str = "",
    title_filter: str = "",
    date_from: str = "",
    date_to: str = "",
) -> tuple[str, List[Any]]:
    where: List[str] = []
    params: List[Any] = []

    if query:
        like_value = f"%{query.lower()}%"
        where.append(
            """
            (
                lower(coalesce(m.text, '')) LIKE ?
                OR lower(coalesce(m.sender_username, '')) LIKE ?
                OR lower(coalesce(m.sender_name, '')) LIKE ?
                OR lower(coalesce(c.full_name, '')) LIKE ?
                OR lower(coalesce(c.job_title, '')) LIKE ?
                OR lower(coalesce(c.companies_json, '')) LIKE ?
                OR lower(coalesce(c.phones_json, '')) LIKE ?
                OR lower(coalesce(c.emails_json, '')) LIKE ?
                OR lower(coalesce(c.city, '')) LIKE ?
            )
            """
        )
        params.extend([like_value] * 9)

    if lead_filter:
        where.append("lower(regexp_replace(split_part(m.source_jsonl, '/', -1), '\\\\.jsonl$', '')) LIKE ?")
        params.append(f"%{lead_filter.lower()}%")
    if author_filter:
        where.append(
            "(lower(coalesce(m.sender_username, '')) LIKE ? OR lower(coalesce(m.sender_name, '')) LIKE ? OR lower(coalesce(c.full_name, '')) LIKE ?)"
        )
        params.extend([f"%{author_filter.lower()}%"] * 3)
    if company_filter:
        where.append("lower(coalesce(c.companies_json, '')) LIKE ?")
        params.append(f"%{company_filter.lower()}%")
    if phone_filter:
        where.append("lower(coalesce(c.phones_json, '')) LIKE ?")
        params.append(f"%{phone_filter.lower()}%")
    if email_filter:
        where.append("lower(coalesce(c.emails_json, '')) LIKE ?")
        params.append(f"%{email_filter.lower()}%")
    if city_filter:
        where.append("lower(coalesce(c.city, '')) LIKE ?")
        params.append(f"%{city_filter.lower()}%")
    if title_filter:
        where.append("lower(coalesce(c.job_title, '')) LIKE ?")
        params.append(f"%{title_filter.lower()}%")
    if date_from:
        where.append("substr(coalesce(m.date_utc_raw, ''), 1, 10) >= ?")
        params.append(str(date_from))
    if date_to:
        where.append("substr(coalesce(m.date_utc_raw, ''), 1, 10) <= ?")
        params.append(str(date_to))

    sql_where = f"WHERE {' AND '.join(where)}" if where else ""
    return sql_where, params


def _duckdb_search_messages_page(
    page: int = 1,
    page_size: int = 5,
    limit: int = 5000,
    query: str = "",
    lead_filter: str = "",
    author_filter: str = "",
    company_filter: str = "",
    phone_filter: str = "",
    email_filter: str = "",
    city_filter: str = "",
    title_filter: str = "",
    date_from: str = "",
    date_to: str = "",
) -> Dict[str, Any]:
    if not _duckdb_search_available():
        return _paginate_items([], page=page, page_size=page_size)

    sql_where, params = _duckdb_search_sql_filters(
        query=query,
        lead_filter=lead_filter,
        author_filter=author_filter,
        company_filter=company_filter,
        phone_filter=phone_filter,
        email_filter=email_filter,
        city_filter=city_filter,
        title_filter=title_filter,
        date_from=date_from,
        date_to=date_to,
    )
    selector_map = _managed_selector_map()
    conn = _duckdb_connect_readonly()
    try:
        base_sql = f"""
            FROM messages_raw m
            LEFT JOIN crm_contacts c
              ON m.source_jsonl = c.lead || '.jsonl'
             AND m.message_id = c.message_id
            {sql_where}
        """
        total = int(conn.execute(f"SELECT COUNT(*) {base_sql}", params).fetchone()[0] or 0)
        capped_total = min(total, max(1, int(limit or 1)))
        offset = max(0, (max(1, int(page)) - 1) * max(1, int(page_size)))
        rows = conn.execute(
            f"""
            SELECT
                m.source_jsonl,
                m.message_id,
                m.date_utc_raw,
                m.text,
                m.sender_username,
                m.sender_name,
                c.full_name,
                c.first_name,
                c.last_name,
                c.patronymic,
                c.job_title,
                c.companies_json,
                c.phones_json,
                c.emails_json,
                c.city,
                c.match_sources_json
            {base_sql}
            ORDER BY coalesce(m.date_utc, TIMESTAMPTZ '1970-01-01 00:00:00+00') DESC, m.message_id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, max(1, int(page_size)), offset],
        ).fetchall()
    finally:
        conn.close()
    items = [_duckdb_row_to_search_message(row, selector_map) for row in rows][: max(1, int(limit or 1))]
    page_payload = _paginate_items(items, page=page, page_size=page_size)
    page_payload["total"] = capped_total
    page_payload["total_pages"] = max(1, (capped_total + max(1, int(page_size)) - 1) // max(1, int(page_size)))
    return page_payload


def _duckdb_load_crm_rows(limit: int = 5000) -> List[Dict[str, Any]]:
    if not _duckdb_contacts_ready():
        return []
    _duckdb_init_schema_sync()
    crm_table_ready = bool(_analysis_state("crm").get("duckdb_ready"))
    conn = _duckdb_connect_readonly()
    try:
        if crm_table_ready:
            raw_rows = conn.execute(
                """
                SELECT
                    lead, source_selector, message_id, date_utc_raw, text,
                    sender_username, sender_name, full_name, first_name, last_name, patronymic,
                    name_components_count, job_title, companies_json, phones_json, emails_json,
                    city, match_sources_json, field_provenance_json
                FROM crm_contacts
                ORDER BY date_utc_raw DESC, message_id DESC
                LIMIT ?
                """,
                [max(1, int(limit or 1))],
            ).fetchall()
            row_mode = "crm"
        else:
            raw_rows = conn.execute(
                """
                SELECT
                    source_jsonl, message_id, date_utc_raw, text,
                    sender_username, sender_name
                FROM messages_raw
                ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
                LIMIT ?
                """,
                [max(50, int(limit or 1) * 10)],
            ).fetchall()
            row_mode = "messages"
    finally:
        conn.close()
    rows: List[Dict[str, Any]] = []
    selector_map = _managed_selector_map()
    for row in raw_rows:
        try:
            if row_mode == "crm":
                item = CrmContactDTO(
                    lead=str(row[0] or ""),
                    source_selector=str(row[1] or "") or None,
                    message_id=int(row[2] or 0),
                    date_utc=str(row[3] or ""),
                    text=str(row[4] or ""),
                    sender_username=str(row[5] or "") or None,
                    sender_name=str(row[6] or "") or None,
                    full_name=str(row[7] or "") or None,
                    first_name=str(row[8] or "") or None,
                    last_name=str(row[9] or "") or None,
                    patronymic=str(row[10] or "") or None,
                    name_components_count=int(row[11] or 0),
                    job_title=str(row[12] or "") or None,
                    companies=list(json.loads(str(row[13] or "[]"))),
                    phones=list(json.loads(str(row[14] or "[]"))),
                    emails=list(json.loads(str(row[15] or "[]"))),
                    city=str(row[16] or "") or None,
                    match_sources=list(json.loads(str(row[17] or "[]"))),
                    field_provenance=dict(json.loads(str(row[18] or "{}"))),
                ).model_dump()
                item = _crm_sanitize_contact_payload(item)
            else:
                lead_name = _duckdb_source_jsonl_to_lead_name(str(row[0] or ""))
                item_dto = _crm_extract_contact_from_record(
                    lead_name,
                    selector_map.get(str(lead_name).lower()),
                    {
                        "sender": {
                            "username": str(row[4] or "") or None,
                            "name": str(row[5] or "") or None,
                        },
                        "message": {
                            "id": int(row[1] or 0),
                            "date_utc": str(row[2] or ""),
                            "text": str(row[3] or ""),
                        },
                    },
                )
                if not item_dto:
                    continue
                item = item_dto.model_dump()
            rows.append(item)
            if len(rows) >= max(1, int(limit or 1)):
                break
        except Exception:
            continue
    return rows


def _duckdb_load_lead_registry_rows(dialog_meta_catalog: Optional[Dict[str, Dict[str, Any]]] = None) -> List[LeadDTO]:
    if not _duckdb_leads_ready():
        return []

    source_map = _source_selector_map()
    import_sync_map = _import_sync_selector_map()
    managed_map = _managed_selector_map()
    dialog_meta_catalog = dialog_meta_catalog or {}

    conn = _duckdb_connect_readonly()
    try:
        registry_rows = conn.execute(
            """
            SELECT source_jsonl, file_name, records_count, mtime_sec
            FROM file_registry
            ORDER BY lower(file_name)
            """
        ).fetchall()
    finally:
        conn.close()

    leads_by_name: Dict[str, LeadDTO] = {}
    import_limit_context = _lead_import_limit_context()
    for source_jsonl, file_name, records_count, mtime_sec in registry_rows:
        derived_name = _selector_to_lead_name(Path(str(file_name or source_jsonl or "")).stem)
        if not derived_name:
            continue
        dialog_meta = dialog_meta_catalog.get(derived_name, {})
        in_source = derived_name in source_map
        in_import_sync = derived_name in import_sync_map
        last_date_utc = None
        try:
            if mtime_sec:
                last_date_utc = datetime.fromtimestamp(float(mtime_sec), tz=timezone.utc).isoformat()
        except Exception:
            last_date_utc = None
        source_selector = managed_map.get(derived_name)
        leads_by_name[derived_name] = LeadDTO(
            name=derived_name,
            file=Path(str(file_name or source_jsonl or f"{derived_name}.jsonl")).name,
            count=int(records_count or 0),
            last_date_utc=last_date_utc,
            last_text_preview=None,
            last_text_full=None,
            in_source=in_source,
            has_jsonl=True,
            sync_status="active" if (in_source or in_import_sync) else "archived",
            source_selector=source_selector,
            chat_type=dialog_meta.get("chat_type", "group"),
            is_archived=bool(dialog_meta.get("is_archived", False)),
            **_lead_dto_telegram_fields(derived_name, source_selector),
            **_lead_scan_group_fields(derived_name, source_selector),
            **_lead_import_limit_fields(source_selector or derived_name, import_limit_context),
            **_lead_source_policy_fields(derived_name, source_selector),
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
            1 if lead.in_source else 0,
            lead.last_date_utc or "",
            lead.count or 0,
            lead.name.lower(),
        ),
        reverse=True,
    )


def _duckdb_load_lead_rows(dialog_meta_catalog: Optional[Dict[str, Dict[str, Any]]] = None) -> List[LeadDTO]:
    if not _duckdb_leads_ready():
        return []

    source_map = _source_selector_map()
    import_sync_map = _import_sync_selector_map()
    managed_map = _managed_selector_map()
    dialog_meta_catalog = dialog_meta_catalog or {}
    lead_rows: Dict[str, Dict[str, Any]] = {}

    conn = _duckdb_connect_readonly()
    try:
        aggregated_rows = conn.execute(
            """
            WITH ranked AS (
                SELECT
                    source_jsonl,
                    message_id,
                    text,
                    date_utc_raw,
                    media_path,
                    row_number() OVER (
                        PARTITION BY source_jsonl, message_id
                        ORDER BY source_offset DESC
                    ) AS row_rank
                FROM messages_raw
                WHERE length(trim(coalesce(text, ''))) > 0
                   OR length(trim(coalesce(media_path, ''))) > 0
            )
            SELECT
                source_jsonl,
                COUNT(*) AS message_count,
                arg_max(
                    coalesce(nullif(trim(text), ''), '[media]'),
                    coalesce(date_utc_raw, '')
                ) AS last_text_preview,
                max(coalesce(date_utc_raw, '')) AS last_date_utc_raw
            FROM ranked
            WHERE row_rank = 1
            GROUP BY source_jsonl
            """
        ).fetchall()
        registry_rows = conn.execute(
            """
            SELECT
                source_jsonl,
                file_name
            FROM file_registry
            ORDER BY lower(file_name)
            """
        ).fetchall()
    finally:
        conn.close()

    for source_jsonl, message_count, last_text_preview, last_date_utc_raw in aggregated_rows:
        derived_name = _selector_to_lead_name(_duckdb_source_jsonl_to_lead_name(str(source_jsonl or "")))
        row = lead_rows.setdefault(
            derived_name,
            {
                "file": f"{derived_name}.jsonl",
                "count": 0,
                "last_date_utc": None,
                "last_text_preview": None,
                "last_text_full": None,
                "has_jsonl": False,
            },
        )
        row["count"] = int(row.get("count") or 0) + int(message_count or 0)
        row["has_jsonl"] = True
        candidate_date = str(last_date_utc_raw or "").strip() or None
        current_date = row.get("last_date_utc")
        if candidate_date and (not current_date or candidate_date >= current_date):
            row["last_date_utc"] = candidate_date
            row["last_text_preview"] = _duckdb_normalize_preview_text(last_text_preview)
            row["last_text_full"] = str(last_text_preview or "").strip() or None

    for source_jsonl, file_name in registry_rows:
        derived_name = _selector_to_lead_name(Path(str(file_name or source_jsonl or "")).stem)
        row = lead_rows.setdefault(
            derived_name,
            {
                "file": f"{derived_name}.jsonl",
                "count": 0,
                "last_date_utc": None,
                "last_text_preview": None,
                "last_text_full": None,
                "has_jsonl": False,
            },
        )
        row["file"] = str(file_name or row["file"])
        row["has_jsonl"] = True

    for lead_name, source_selector in managed_map.items():
        lead_rows.setdefault(
            lead_name,
            {
                "file": f"{lead_name}.jsonl",
                "count": 0,
                "last_date_utc": None,
                "last_text_preview": None,
                "last_text_full": None,
                "has_jsonl": False,
            },
        )

    leads_by_name: Dict[str, LeadDTO] = {}
    import_limit_context = _lead_import_limit_context()
    for lead_name, row in lead_rows.items():
        dialog_meta = dialog_meta_catalog.get(lead_name, {})
        in_source = lead_name in source_map
        in_import_sync = lead_name in import_sync_map
        source_selector = managed_map.get(lead_name)
        leads_by_name[lead_name] = LeadDTO(
            name=lead_name,
            file=str(row.get("file") or f"{lead_name}.jsonl"),
            count=int(row.get("count") or 0),
            last_date_utc=row.get("last_date_utc"),
            last_text_preview=row.get("last_text_preview"),
            last_text_full=row.get("last_text_full") or row.get("last_text_preview"),
            in_source=in_source,
            has_jsonl=bool(row.get("has_jsonl")),
            sync_status="active" if (in_source or in_import_sync) else ("archived" if row.get("has_jsonl") else "pending"),
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


def _duckdb_load_lead_messages(lead: str, offset: int = 0, limit: int = 200) -> List[MessageDTO]:
    target = str(lead or "").strip().lower()
    if not target:
        return []

    source_rows = _duckdb_list_source_rows_for_lead(target)
    if not source_rows:
        if _lead_exists_in_source(target):
            return []
        raise HTTPException(status_code=404, detail=f"Lead '{lead}' not found")

    source_jsonls = [item[0] for item in source_rows if item and item[0]]
    if not source_jsonls:
        return []

    placeholders = ", ".join("?" for _ in source_jsonls)
    fields_sql = """
        SELECT
            chat_id,
            chat_username,
            sender_id,
            sender_username,
            sender_name,
            message_id,
            text,
            date_utc_raw,
            reply_to_msg_id,
            has_media,
            media_path
        FROM (
            SELECT
                chat_id,
                chat_username,
                sender_id,
                sender_username,
                sender_name,
                message_id,
                text,
                date_utc,
                date_utc_raw,
                reply_to_msg_id,
                has_media,
                media_path,
                row_number() OVER (
                    PARTITION BY source_jsonl, message_id
                    ORDER BY source_offset DESC
                ) AS row_rank
            FROM messages_raw
    """
    where_sql = (
        f"WHERE source_jsonl IN ({placeholders}) "
        "AND (length(trim(coalesce(text, ''))) > 0 OR length(trim(coalesce(media_path, ''))) > 0)"
    )
    ranked_tail_sql = ") WHERE row_rank = 1"
    params: List[Any] = list(source_jsonls)
    if limit and int(limit) > 0:
        # For chat UI we need the latest window, but still render it oldest -> newest.
        query = f"""
            {fields_sql}
            {where_sql}
            {ranked_tail_sql}
            ORDER BY coalesce(date_utc_raw, '') DESC, message_id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([max(1, int(limit)), max(0, int(offset or 0))])
    else:
        query = f"""
            {fields_sql}
            {where_sql}
            {ranked_tail_sql}
            ORDER BY coalesce(date_utc_raw, '') ASC, message_id ASC
        """

    conn = _duckdb_connect_readonly()
    try:
        raw_rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    if limit and int(limit) > 0:
        raw_rows = list(reversed(raw_rows))
    else:
        raw_rows = raw_rows[max(0, int(offset or 0)) :]

    messages: List[MessageDTO] = []
    for row in raw_rows:
        role = _duckdb_detect_role_from_values(row[0], row[1], row[2], row[3])
        messages.append(
            MessageDTO(
                id=int(row[5] or 0),
                role=role,
                text=str(row[6] or ""),
                date_utc=str(row[7] or ""),
                reply_to_msg_id=_duckdb_optional_int(row[8]),
                has_media=bool(row[9]),
                media_path=str(row[10] or "").strip() or None,
                sender_username=str(row[3] or "").strip() or None,
                sender_name=str(row[4] or "").strip() or None,
            )
        )
    return messages


__all__ = [
    "refresh_legacy_globals",
    "_duckdb_export_parquet_sync",
    "_duckdb_ingest_sync",
    "_duckdb_init_schema_sync",
    "_duckdb_load_contact_message_rows",
    "_duckdb_load_contact_rows",
    "_duckdb_load_crm_rows",
    "_duckdb_load_event_rows",
    "_duckdb_load_lead_messages",
    "_duckdb_load_lead_registry_rows",
    "_duckdb_load_lead_rows",
    "_duckdb_list_source_rows_for_lead",
    "_duckdb_rebuild_event_messages_sync",
    "_duckdb_search_messages_page",
    "_duckdb_search_sql_filters",
    "_duckdb_stage_jsonl_to_parquet_sync",
]
