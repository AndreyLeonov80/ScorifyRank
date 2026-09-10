"""Runtime state helpers shared by legacy glue and extracted services."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable


def clone_json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return value


def preserve_state_keys(current_state: Any, keys: Iterable[str]) -> dict[str, Any]:
    if not isinstance(current_state, dict):
        return {}
    preserved: dict[str, Any] = {}
    for key in keys:
        if key in current_state:
            preserved[key] = clone_json_safe(current_state[key])
    return preserved


def safe_clear_directory_contents(path: Path) -> None:
    resolved = path.resolve()
    if not resolved.exists():
        return
    for item in resolved.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except FileNotFoundError:
            pass


def clear_unique_directory_contents(paths: Iterable[Path], ensure_path: Path | None = None) -> None:
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        if path.exists():
            safe_clear_directory_contents(path)
        elif ensure_path is not None and path == ensure_path:
            path.mkdir(parents=True, exist_ok=True)
