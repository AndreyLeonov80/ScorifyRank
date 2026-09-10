"""Client/session helpers for Telegram sync."""

from __future__ import annotations

from pathlib import Path
from typing import List


def session_file_paths(session: str) -> List[Path]:
    session_path = Path(session)
    if session_path.suffix != ".session":
        session_path = session_path.with_suffix(".session")
    return [session_path, session_path.with_name(f"{session_path.name}-journal")]

