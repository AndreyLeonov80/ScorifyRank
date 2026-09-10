"""Compatibility loader for the legacy backend runtime.

`back.py` stays as the public import target, while the large runtime body is
stored in `app/legacy_runtime.py`. Executing it in this module namespace keeps
old `patch("back.*")` tests and scripts behaviorally compatible.
"""

from __future__ import annotations

from pathlib import Path

_LEGACY_RUNTIME_PATH = Path(__file__).resolve().parent / "app" / "legacy_runtime.py"
exec(compile(_LEGACY_RUNTIME_PATH.read_text(encoding="utf-8"), str(_LEGACY_RUNTIME_PATH), "exec"), globals(), globals())
