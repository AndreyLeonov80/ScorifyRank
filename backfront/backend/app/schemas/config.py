"""Settings and auth schemas."""

from __future__ import annotations

from app.schemas.compat_models import (
    AppSettingsDTO,
    AppSettingsPayload,
    OpenRouterModelsDTO,
    TelegramApiCredentialsPayload,
    TelegramAuthActionDTO,
    TelegramAuthCodePayload,
    TelegramAuthPasswordPayload,
    TelegramAuthPhonePayload,
    TelegramAuthPhoneResendPayload,
)

__all__ = [
    "AppSettingsDTO",
    "AppSettingsPayload",
    "OpenRouterModelsDTO",
    "TelegramApiCredentialsPayload",
    "TelegramAuthActionDTO",
    "TelegramAuthCodePayload",
    "TelegramAuthPasswordPayload",
    "TelegramAuthPhonePayload",
    "TelegramAuthPhoneResendPayload",
]
