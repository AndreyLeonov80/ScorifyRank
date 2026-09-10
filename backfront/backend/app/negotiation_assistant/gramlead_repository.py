from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from .config import NegotiationSettings
from .schemas import ContactDTO, MessageDTO


class GramLeadReadRepository:
    """Read-only adapter for GramLead data.

    DuckDB is preferred when available. JSONL fallback is intentionally kept for
    resilience: real GramLead installs can have schema drift while artifacts are
    still readable.
    """

    def __init__(self, settings: NegotiationSettings):
        self.settings = settings

    def status(self) -> dict:
        return {
            "duckdb_path": str(self.settings.duckdb_file),
            "duckdb_exists": self.settings.duckdb_file.exists(),
            "jsonl_dir": str(self.settings.jsonl_path),
            "jsonl_exists": self.settings.jsonl_path.exists(),
            "jsonl_files": len(list(self._jsonl_files())),
        }

    def list_contacts(self, query: str = "", source: str = "", limit: int = 50, offset: int = 0) -> tuple[list[ContactDTO], int]:
        contacts = self._contacts_from_jsonl()
        if query:
            q = query.lower()
            contacts = [c for c in contacts if q in c.title.lower() or q in (c.username or "").lower() or q in c.id.lower()]
        if source:
            contacts = [c for c in contacts if (c.source_id or "") == source or (c.source_title or "") == source]
        contacts.sort(key=lambda c: (c.last_message_at or "", c.messages_count), reverse=True)
        total = len(contacts)
        return contacts[offset : offset + limit], total

    def get_contact(self, contact_id: str) -> ContactDTO | None:
        contacts, _ = self.list_contacts(limit=100000)
        return next((contact for contact in contacts if contact.id == contact_id), None)

    def list_messages(self, contact_id: str, limit: int = 80) -> list[MessageDTO]:
        messages: list[MessageDTO] = []
        for path in self._jsonl_files():
            for item in self._iter_jsonl(path):
                sender = item.get("sender") or {}
                chat = item.get("chat") or {}
                message = item.get("message") or {}
                current_id = self._contact_id(sender, chat)
                if current_id != contact_id:
                    continue
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                messages.append(
                    MessageDTO(
                        id=f"{chat.get('username') or chat.get('id') or path.stem}:{message.get('id')}",
                        contact_id=current_id,
                        source_id=str(chat.get("username") or chat.get("id") or path.stem),
                        sender_name=sender.get("name"),
                        sender_username=sender.get("username"),
                        text=text,
                        date_utc=message.get("date_utc"),
                    )
                )
        messages.sort(key=lambda item: item.date_utc or "")
        return messages[-limit:]

    def list_sources(self) -> list[dict]:
        sources: dict[str, dict] = {}
        for path in self._jsonl_files():
            first = next(self._iter_jsonl(path), None)
            if not first:
                continue
            chat = first.get("chat") or {}
            source_id = str(chat.get("username") or chat.get("id") or path.stem)
            sources[source_id] = {
                "id": source_id,
                "title": chat.get("title") or source_id,
                "jsonl": str(path),
            }
        return sorted(sources.values(), key=lambda item: item["title"].lower())

    def _contacts_from_jsonl(self) -> list[ContactDTO]:
        counts: Counter[str] = Counter()
        meta: dict[str, dict] = {}
        last_at: dict[str, str] = {}
        for path in self._jsonl_files():
            for item in self._iter_jsonl(path):
                sender = item.get("sender") or {}
                chat = item.get("chat") or {}
                message = item.get("message") or {}
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                contact_id = self._contact_id(sender, chat)
                counts[contact_id] += 1
                source_id = str(chat.get("username") or chat.get("id") or path.stem)
                meta.setdefault(
                    contact_id,
                    {
                        "title": sender.get("name") or sender.get("username") or str(sender.get("id") or contact_id),
                        "username": sender.get("username"),
                        "telegram_id": str(sender.get("id") or ""),
                        "source_id": source_id,
                        "source_title": chat.get("title") or source_id,
                    },
                )
                date_utc = message.get("date_utc")
                if date_utc and date_utc > last_at.get(contact_id, ""):
                    last_at[contact_id] = date_utc
        return [
            ContactDTO(
                id=contact_id,
                title=data["title"],
                username=data.get("username"),
                telegram_id=data.get("telegram_id"),
                source_id=data.get("source_id"),
                source_title=data.get("source_title"),
                messages_count=count,
                last_message_at=last_at.get(contact_id),
            )
            for contact_id, count in counts.items()
            for data in [meta[contact_id]]
        ]

    def _jsonl_files(self) -> Iterable[Path]:
        if not self.settings.jsonl_path.exists():
            return []
        return (path for path in self.settings.jsonl_path.glob("*.jsonl") if path.is_file())

    @staticmethod
    def _iter_jsonl(path: Path) -> Iterable[dict]:
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return

    @staticmethod
    def _contact_id(sender: dict, chat: dict) -> str:
        source = chat.get("username") or chat.get("id") or "unknown"
        sender_id = sender.get("id") or sender.get("username") or sender.get("name") or "unknown"
        return f"gramlead:contact:telegram:{source}:{sender_id}"

