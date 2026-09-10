"""DuckDB schema and export table definitions."""

from __future__ import annotations

from typing import Any, Dict


DUCKDB_EXPORT_TABLES: Dict[str, str] = {
    "messages_raw": "messages_raw.parquet",
    "file_registry": "file_registry.parquet",
    "crm_contacts": "crm_contacts.parquet",
    "event_messages": "event_messages.parquet",
}


def init_schema(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_registry (
            source_jsonl VARCHAR PRIMARY KEY,
            source_key VARCHAR,
            file_name VARCHAR,
            size_bytes BIGINT,
            mtime_sec DOUBLE,
            ingested_offset BIGINT,
            records_count BIGINT,
            records_count_jsonl BIGINT,
            records_count_duckdb BIGINT,
            lag_rows BIGINT,
            parquet_path VARCHAR,
            parquet_size_bytes BIGINT,
            parquet_mtime_sec DOUBLE,
            last_ingested_at TIMESTAMPTZ
        )
        """
    )
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS source_key VARCHAR")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS records_count_jsonl BIGINT")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS records_count_duckdb BIGINT")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS lag_rows BIGINT")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS parquet_path VARCHAR")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS parquet_size_bytes BIGINT")
    conn.execute("ALTER TABLE file_registry ADD COLUMN IF NOT EXISTS parquet_mtime_sec DOUBLE")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages_raw (
            row_hash VARCHAR PRIMARY KEY,
            source_jsonl VARCHAR,
            source_key VARCHAR,
            source_offset BIGINT,
            chat_id BIGINT,
            chat_username VARCHAR,
            chat_title VARCHAR,
            sender_id BIGINT,
            sender_username VARCHAR,
            sender_name VARCHAR,
            message_id BIGINT,
            text VARCHAR,
            date_utc TIMESTAMPTZ,
            date_utc_raw VARCHAR,
            reply_to_msg_id BIGINT,
            has_media BOOLEAN,
            media_path VARCHAR,
            file_mtime_sec DOUBLE,
            ingested_at TIMESTAMPTZ
        )
        """
    )
    conn.execute("ALTER TABLE messages_raw ADD COLUMN IF NOT EXISTS source_key VARCHAR")
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
        CREATE TABLE IF NOT EXISTS crm_contacts (
            row_key VARCHAR PRIMARY KEY,
            lead VARCHAR,
            source_selector VARCHAR,
            message_id BIGINT,
            date_utc_raw VARCHAR,
            text VARCHAR,
            sender_username VARCHAR,
            sender_name VARCHAR,
            full_name VARCHAR,
            first_name VARCHAR,
            last_name VARCHAR,
            patronymic VARCHAR,
            name_components_count INTEGER,
            job_title VARCHAR,
            companies_json VARCHAR,
            phones_json VARCHAR,
            emails_json VARCHAR,
            city VARCHAR,
            match_sources_json VARCHAR,
            field_provenance_json VARCHAR,
            updated_at TIMESTAMPTZ
        )
        """
    )
    conn.execute("ALTER TABLE crm_contacts ADD COLUMN IF NOT EXISTS field_provenance_json VARCHAR")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_messages (
            row_key VARCHAR PRIMARY KEY,
            keyword_hash VARCHAR,
            lead VARCHAR,
            source_selector VARCHAR,
            message_id BIGINT,
            date_utc_raw VARCHAR,
            event_date VARCHAR,
            event_date_confidence DOUBLE,
            event_date_source VARCHAR,
            event_date_updated_at TIMESTAMPTZ,
            text VARCHAR,
            sender_username VARCHAR,
            sender_name VARCHAR,
            matched_keywords_json VARCHAR,
            updated_at TIMESTAMPTZ
        )
        """
    )
    conn.execute("ALTER TABLE event_messages ADD COLUMN IF NOT EXISTS event_date VARCHAR")
    conn.execute("ALTER TABLE event_messages ADD COLUMN IF NOT EXISTS event_date_confidence DOUBLE")
    conn.execute("ALTER TABLE event_messages ADD COLUMN IF NOT EXISTS event_date_source VARCHAR")
    conn.execute("ALTER TABLE event_messages ADD COLUMN IF NOT EXISTS event_date_updated_at TIMESTAMPTZ")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS outreach_crm_fields (
            item_id VARCHAR PRIMARY KEY,
            field_type VARCHAR,
            field_label VARCHAR,
            value VARCHAR,
            contact_key VARCHAR,
            lead VARCHAR,
            source_selector VARCHAR,
            message_id BIGINT,
            date_utc_raw VARCHAR,
            text VARCHAR,
            sender_username VARCHAR,
            sender_name VARCHAR,
            status VARCHAR,
            created_at VARCHAR
        )
        """
    )
    conn.execute("ALTER TABLE outreach_crm_fields ADD COLUMN IF NOT EXISTS contact_key VARCHAR")
