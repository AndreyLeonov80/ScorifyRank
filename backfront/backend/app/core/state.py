"""JSON state IO helpers with Docker bind-mount-safe writes."""

from __future__ import annotations

import errno
import contextlib
import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback for local tooling.
    fcntl = None  # type: ignore[assignment]


_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.RLock()


def _path_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[resolved] = lock
        return lock


@contextlib.contextmanager
def _file_lock(path: Path):
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        return {}

    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def atomic_write_json_with_bind_mount_fallback(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except (FileNotFoundError, OSError) as exc:
        # Docker bind-mounted single files on macOS can reject atomic replace with
        # EBUSY/EXDEV; fallback preserves state instead of surfacing an error to UI.
        if isinstance(exc, OSError) and exc.errno not in {errno.ENOENT, errno.EBUSY, errno.EXDEV}:
            raise
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if tmp.exists():
            tmp.unlink(missing_ok=True)


class StateRepository:
    """Thread/process-safe JSON object repository for shared runtime state."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = _path_lock(path)

    def load(self) -> dict[str, Any]:
        with self._lock:
            with _file_lock(self.path):
                return load_json_object(self.path)

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        snapshot = dict(payload)
        with self._lock:
            with _file_lock(self.path):
                atomic_write_json_with_bind_mount_fallback(self.path, snapshot)
        return snapshot

    def update(self, mutator: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
        with self._lock:
            with _file_lock(self.path):
                state = load_json_object(self.path)
                result = mutator(state)
                if isinstance(result, dict):
                    state = result
                atomic_write_json_with_bind_mount_fallback(self.path, state)
                return state
