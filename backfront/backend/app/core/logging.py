"""Runtime logging helpers for the split backend.

This module is intentionally small while the remaining log implementation is
being moved out of the legacy runtime.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("gramlead.backend")


def log_runtime_event(message: str, **extra: Any) -> None:
    if extra:
        logger.info("%s %s", message, extra)
    else:
        logger.info("%s", message)
