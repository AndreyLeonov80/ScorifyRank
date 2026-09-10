"""Telethon import compatibility for local test/runtime environments.

Docker/runtime images install Telethon from requirements. Some local macOS
system Python runs do not, so importing the backend should still work and fail
only when Telegram functionality is actually used.
"""

from __future__ import annotations

from typing import Any


TELETHON_IMPORT_ERROR: Exception | None = None

try:  # pragma: no cover - exercised when dependency is installed
    from telethon import TelegramClient, events  # type: ignore
    from telethon.errors import (  # type: ignore
        AuthKeyUnregisteredError,
        FloodWaitError,
        PasswordHashInvalidError,
        PeerFloodError,
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        SessionPasswordNeededError,
        UserPrivacyRestrictedError,
    )
    from telethon.tl.types import Message as TelegramMessage  # type: ignore
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local env
    TELETHON_IMPORT_ERROR = exc

    class _MissingTelethonError(RuntimeError):
        pass

    class AuthKeyUnregisteredError(Exception):
        pass

    class FloodWaitError(Exception):
        seconds = 60

    class PasswordHashInvalidError(Exception):
        pass

    class PeerFloodError(Exception):
        pass

    class PhoneCodeExpiredError(Exception):
        pass

    class PhoneCodeInvalidError(Exception):
        pass

    class PhoneNumberInvalidError(Exception):
        pass

    class SessionPasswordNeededError(Exception):
        pass

    class UserPrivacyRestrictedError(Exception):
        pass

    class TelegramClient:  # type: ignore[no-redef]
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise _MissingTelethonError(
                "Telethon is not installed in this Python environment. "
                "Install backend requirements or run inside Docker."
            )

    class _MissingEvents:
        @staticmethod
        def NewMessage(*_args: Any, **_kwargs: Any) -> Any:
            raise _MissingTelethonError(
                "Telethon is not installed in this Python environment. "
                "Install backend requirements or run inside Docker."
            )

    class TelegramMessage:  # type: ignore[no-redef]
        pass

    events = _MissingEvents()


TELETHON_AVAILABLE = TELETHON_IMPORT_ERROR is None

