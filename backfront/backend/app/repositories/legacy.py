"""Repository bridge to the legacy monolith during incremental extraction."""

from __future__ import annotations

import functools
import inspect
import sys
from collections.abc import Callable
from typing import Any

import back


def _iter_runtime_sources() -> tuple[Any, ...]:
    sources: list[Any] = []
    runtime = sys.modules.get("app.legacy_runtime")
    if runtime is not None:
        sources.append(runtime)
    if back is not None:
        sources.append(back)
    return tuple(sources)


def refresh_globals(
    target_globals: dict[str, Any],
    *,
    setdefault: bool = False,
    exclude: set[str] | None = None,
) -> None:
    skipped = exclude or set()
    for source in _iter_runtime_sources():
        for name, value in vars(source).items():
            if name.startswith("__") or name in skipped:
                continue
            if setdefault:
                target_globals.setdefault(name, value)
            else:
                target_globals[name] = value


def get_constant(name: str) -> Any:
    return getattr(back, name)


def bind(name: str) -> Callable[..., Any]:
    target = getattr(back, name)
    if inspect.iscoroutinefunction(target):

        @functools.wraps(target)
        async def async_delegate(*args: Any, **kwargs: Any) -> Any:
            return await target(*args, **kwargs)

        return async_delegate

    @functools.wraps(target)
    def sync_delegate(*args: Any, **kwargs: Any) -> Any:
        return target(*args, **kwargs)

    return sync_delegate
