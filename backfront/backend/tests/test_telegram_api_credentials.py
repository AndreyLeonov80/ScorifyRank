import json
import asyncio
import os
import unittest
from datetime import datetime, timezone
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import back


def _request_for_path(path: str, query_string: bytes = b""):
    return back.Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "query_string": query_string,
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 123),
            "scheme": "http",
        }
    )


class TelegramApiCredentialsTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_mark_credentials_missing_when_empty(self) -> None:
        settings = back._coerce_app_settings({"telegram_api_id": "", "telegram_api_hash": ""})

        self.assertFalse(settings["telegram_api_configured"])
        self.assertEqual(settings["telegram_api_credentials_source"], "missing")

    def test_settings_mark_credentials_configured_when_present(self) -> None:
        settings = back._coerce_app_settings({"telegram_api_id": "12345", "telegram_api_hash": "hash"})

        self.assertTrue(settings["telegram_api_configured"])
        self.assertEqual(settings["telegram_api_id"], "12345")
        self.assertEqual(settings["telegram_api_hash"], "hash")

    def test_runtime_integration_settings_are_replaceable_without_rebuild(self) -> None:
        settings = back._coerce_app_settings(
            {
                "telegram_api_id": "12345",
                "telegram_api_hash": "hash",
                "openrouter_api_key": "sk-or-test",
                "openrouter_model": "openai/gpt-oss-120b:free",
                "ocr_service_url": "http://192.168.0.90/",
                "license_email_host": "imap.example.com",
                "license_email_port": 993,
                "license_email_smtp_host": "smtp.example.com",
                "license_email_smtp_port": 465,
                "license_email_login": "client@example.com",
            }
        )

        self.assertEqual(settings["telegram_api_id"], "12345")
        self.assertEqual(settings["telegram_api_hash"], "hash")
        self.assertEqual(settings["openrouter_api_key"], "sk-or-test")
        self.assertEqual(settings["openrouter_model"], "openai/gpt-oss-120b:free")
        self.assertEqual(settings["ocr_service_url"], "http://192.168.0.90")
        self.assertEqual(settings["license_email_host"], "imap.example.com")
        self.assertEqual(settings["license_email_port"], 993)
        self.assertEqual(settings["license_email_smtp_host"], "smtp.example.com")
        self.assertEqual(settings["license_email_smtp_port"], 465)
        self.assertEqual(settings["license_email_login"], "client@example.com")

    def test_client_delivery_defaults_do_not_prefill_owner_secrets_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "XFILES_CLIENT_DELIVERY": "1",
                "TELEGRAM_API_ID": "12345",
                "TELEGRAM_API_HASH": "owner-hash",
                "TELEGRAM_PHONE": "+79990000000",
                "OPENROUTER_API_KEY": "sk-owner",
                "PAYME_OPENROUTER_API_KEY": "sk-owner-payme",
            },
            clear=False,
        ):
            settings = back._default_app_settings()

        self.assertEqual(settings["telegram_api_id"], "")
        self.assertEqual(settings["telegram_api_hash"], "")
        self.assertEqual(settings["telegram_phone"], "")
        self.assertEqual(settings["openrouter_api_key"], "")

    def test_client_delivery_first_start_sanitizes_stale_prefilled_secrets(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state

        try:
            with patch.dict(os.environ, {"XFILES_CLIENT_DELIVERY": "1"}, clear=False):
                sync.state = {
                    back.APP_SETTINGS_STATE_KEY: {
                        "setup_wizard_completed": False,
                        "telegram_api_id": "12345",
                        "telegram_api_hash": "stale-hash",
                        "telegram_phone": "+79990000000",
                        "openrouter_api_key": "sk-stale",
                    }
                }

                settings = back._get_app_settings()

            self.assertFalse(settings["client_setup_started"])
            self.assertEqual(settings["telegram_api_id"], "")
            self.assertEqual(settings["telegram_api_hash"], "")
            self.assertEqual(settings["telegram_phone"], "")
            self.assertEqual(settings["openrouter_api_key"], "")
        finally:
            sync.state = original_state

    def test_client_delivery_manual_setup_keeps_user_entered_secrets(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state

        try:
            with patch.dict(os.environ, {"XFILES_CLIENT_DELIVERY": "1"}, clear=False):
                sync.state = {back.APP_SETTINGS_STATE_KEY: {}}
                with patch.object(sync, "save_state", lambda: None):
                    settings = back._save_app_settings(
                        {
                            "telegram_api_id": "12345",
                            "telegram_api_hash": "client-hash",
                            "telegram_phone": "+79991112233",
                        }
                    )

            self.assertTrue(settings["client_setup_started"])
            self.assertEqual(settings["telegram_api_id"], "12345")
            self.assertEqual(settings["telegram_api_hash"], "client-hash")
            self.assertEqual(settings["telegram_phone"], "+79991112233")
        finally:
            sync.state = original_state

    def test_client_license_email_password_is_saved_as_secret(self) -> None:
        settings = back._coerce_app_settings(
            {
                "license_email_enabled": True,
                "license_email_host": "imap.example.com",
                "license_email_login": "client@example.com",
                "license_email_password": "plain-app-password",
            }
        )

        dumped = json.dumps(settings, ensure_ascii=False)
        self.assertTrue(settings["license_email_password_configured"])
        self.assertIn("license_email_password_secret", settings)
        self.assertNotIn("plain-app-password", dumped)

    def test_saved_client_license_email_secret_survives_settings_update(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state

        try:
            sync.state = {back.APP_SETTINGS_STATE_KEY: {}}
            with patch.object(sync, "save_state", lambda: None):
                first = back._save_app_settings(
                    {
                        "license_email_enabled": True,
                        "license_email_host": "imap.example.com",
                        "license_email_login": "client@example.com",
                        "license_email_password": "plain-app-password",
                    }
                )
                second = back._save_app_settings({"license_email_login": "changed@example.com"})

            self.assertTrue(first["license_email_password_configured"])
            self.assertTrue(second["license_email_password_configured"])
            self.assertEqual(second["license_email_login"], "changed@example.com")
            stored = json.dumps(sync.state[back.APP_SETTINGS_STATE_KEY], ensure_ascii=False)
            self.assertNotIn("plain-app-password", stored)
        finally:
            sync.state = original_state

    def test_client_license_email_secret_can_be_decrypted_for_runtime_use(self) -> None:
        settings = back._coerce_app_settings({"license_email_password": "mail-app-secret"})

        self.assertEqual(
            back._decrypt_client_email_password(settings["license_email_password_secret"]),
            "mail-app-secret",
        )

    def test_invite_license_is_extracted_from_email_attachment(self) -> None:
        document = {
            "payload": {
                "schema": back.XFILES_LICENSE_SCHEMA,
                "license_id": "lic_email",
            },
            "signature": "signed",
        }
        message = EmailMessage()
        message["From"] = "root@example.com"
        message["To"] = "client@example.com"
        message["Subject"] = "invite"
        message.set_content("invite attached")
        message.add_attachment(
            json.dumps(document).encode("utf-8"),
            maintype="application",
            subtype="json",
            filename="invite-license.json",
        )

        extracted = back._xfiles_extract_invite_license_from_email(message.as_bytes())

        self.assertEqual(extracted, document)

    def test_email_import_endpoint_applies_invite_and_sends_optional_receipt(self) -> None:
        document = {
            "payload": {
                "schema": back.XFILES_LICENSE_SCHEMA,
                "license_id": "lic_email",
                "root_email": "root@example.com",
            },
            "signature": "signed",
        }
        action = back.XFilesLicenseActionDTO(
            ok=True,
            message="ok",
            status=back.XFilesLicenseStatusDTO(ok=True, status="active", message="active"),
        )

        with patch.object(back, "_xfiles_fetch_invite_license_from_email_sync", return_value=(document, "42")) as fetch:
            with patch.object(back, "_xfiles_apply_invite_license", return_value=action) as apply:
                with patch.object(back, "_save_app_settings", return_value={}) as save:
                    with patch.object(back, "_get_app_settings", return_value={"license_email_allow_activation_receipt": True}):
                        with patch.object(back, "_xfiles_send_activation_receipt_email_sync", return_value=True) as send:
                            with patch.object(back, "_xfiles_append_license_audit", lambda **kwargs: None):
                                result = back.api_payme_license_email_import()

        fetch.assert_called_once()
        self.assertEqual(apply.call_args.kwargs["action"], "email_import")
        self.assertIn("upgrade", apply.call_args.kwargs["allowed_kinds"])
        save.assert_called_once()
        send.assert_called_once_with(target_email="root@example.com")
        self.assertTrue(result.activation_receipt_sent)
        self.assertEqual(result.email_message_id, "42")

    async def test_runtime_status_requests_api_credentials_before_phone_auth(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_client = sync.client
        original_step = sync._auth_step
        original_error = sync._auth_last_error

        try:
            sync.state = {back.APP_SETTINGS_STATE_KEY: {"telegram_api_id": "", "telegram_api_hash": ""}}
            sync.api_id = None
            sync.api_hash = ""
            sync.client = None
            sync._auth_step = "api"
            sync._auth_last_error = None

            status = await back._runtime_status()

            self.assertEqual(status.auth_status, "needs_api_credentials")
            self.assertEqual(status.auth_step, "api")
            self.assertFalse(status.telegram_api_configured)
        finally:
            sync.state = original_state
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.client = original_client
            sync._auth_step = original_step
            sync._auth_last_error = original_error

    async def test_telegram_auth_sent_code_app_is_visible_in_runtime_status(self) -> None:
        class SentCodeTypeApp:
            pass

        class SentCodeTypeSms:
            pass

        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_client = sync.client
        original_auth_phone = sync._auth_phone
        original_auth_hash = sync._auth_phone_code_hash
        original_auth_step = sync._auth_step
        original_delivery = getattr(sync, "_auth_code_delivery_type", None)
        original_next = getattr(sync, "_auth_code_next_type", None)
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)
        original_hash_present = getattr(sync, "_auth_code_hash_present", False)
        original_delivery = getattr(sync, "_auth_code_delivery_type", None)
        original_next = getattr(sync, "_auth_code_next_type", None)
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)
        original_hash_present = getattr(sync, "_auth_code_hash_present", False)

        try:
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                }
            }
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync._auth_phone = "+79999980872"
            sync._auth_phone_code_hash = "phone-code-hash"
            sync._auth_step = "code"
            sync.client = SimpleNamespace(is_connected=lambda: True, is_user_authorized=AsyncMock(return_value=False))
            sync._record_auth_sent_code(
                SimpleNamespace(
                    type=SentCodeTypeApp(),
                    next_type=SentCodeTypeSms(),
                    timeout=120,
                    phone_code_hash="phone-code-hash",
                )
            )

            status = await back._runtime_status()

            self.assertEqual(status.auth_status, "needs_auth")
            self.assertEqual(status.auth_code_delivery_type, "SentCodeTypeApp")
            self.assertEqual(status.auth_code_next_type, "SentCodeTypeSms")
            self.assertEqual(status.auth_code_timeout_sec, 120)
            self.assertTrue(status.auth_code_hash_present)
            self.assertIn("приложение Telegram", status.auth_code_message)
        finally:
            sync.state = original_state
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.client = original_client
            sync._auth_phone = original_auth_phone
            sync._auth_phone_code_hash = original_auth_hash
            sync._auth_step = original_auth_step
            sync._auth_code_delivery_type = original_delivery
            sync._auth_code_next_type = original_next
            sync._auth_code_timeout_sec = original_timeout
            sync._auth_code_requested_at = original_requested
            sync._auth_code_message = original_message
            sync._auth_code_hash_present = original_hash_present

    async def test_telegram_auth_sent_code_sms_is_visible_in_runtime_status(self) -> None:
        class SentCodeTypeSms:
            pass

        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_client = sync.client
        original_auth_phone = sync._auth_phone
        original_auth_hash = sync._auth_phone_code_hash
        original_auth_step = sync._auth_step
        original_delivery = getattr(sync, "_auth_code_delivery_type", None)
        original_next = getattr(sync, "_auth_code_next_type", None)
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)
        original_hash_present = getattr(sync, "_auth_code_hash_present", False)

        try:
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                }
            }
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync._auth_phone = "+79999980872"
            sync._auth_phone_code_hash = "phone-code-hash"
            sync._auth_step = "code"
            sync.client = SimpleNamespace(is_connected=lambda: True, is_user_authorized=AsyncMock(return_value=False))
            sync._record_auth_sent_code(
                SimpleNamespace(type=SentCodeTypeSms(), next_type=None, timeout=None, phone_code_hash="phone-code-hash")
            )

            status = await back._runtime_status()

            self.assertEqual(status.auth_code_delivery_type, "SentCodeTypeSms")
            self.assertIn("SMS", status.auth_code_message)
        finally:
            sync.state = original_state
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.client = original_client
            sync._auth_phone = original_auth_phone
            sync._auth_phone_code_hash = original_auth_hash
            sync._auth_step = original_auth_step
            sync._auth_code_delivery_type = original_delivery
            sync._auth_code_next_type = original_next
            sync._auth_code_timeout_sec = original_timeout
            sync._auth_code_requested_at = original_requested
            sync._auth_code_message = original_message
            sync._auth_code_hash_present = original_hash_present

    async def test_telegram_auth_floodwait_returns_human_eta(self) -> None:
        sync = back.telegram_sync
        original_client = sync.client
        original_auth_step = sync._auth_step
        original_error = sync._auth_last_error
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)

        class FakeClient:
            async def send_code_request(self, _phone, **_kwargs):
                exc = back.FloodWaitError()
                exc.seconds = 42
                raise exc

        try:
            sync.client = FakeClient()
            sync._auth_step = "phone"
            with patch.object(sync, "_pause_sync_for_auth", AsyncMock()):
                with patch.object(sync, "_reset_client", AsyncMock()) as reset:
                    with patch.object(sync, "_ensure_connected_for_auth", AsyncMock()):
                        with self.assertRaises(ValueError) as ctx:
                            await sync.start_web_auth("+79999980872")

            reset.assert_awaited_once()
            self.assertIn("42 сек", str(ctx.exception))
            self.assertEqual(sync._auth_code_timeout_sec, 42)
            self.assertIn("ограничил", sync._auth_last_error or "")
        finally:
            sync.client = original_client
            sync._auth_step = original_auth_step
            sync._auth_last_error = original_error
            sync._auth_code_timeout_sec = original_timeout
            sync._auth_code_requested_at = original_requested
            sync._auth_code_message = original_message

    async def test_telegram_auth_pauses_sync_before_requesting_code(self) -> None:
        class SentCodeTypeApp:
            pass

        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_client = sync.client
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_auth_phone = sync._auth_phone
        original_auth_hash = sync._auth_phone_code_hash
        original_auth_step = sync._auth_step
        original_pause_status = getattr(sync, "_auth_pause_previous_status", None)
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)

        class FakeClient:
            def is_connected(self) -> bool:
                return True

            async def is_user_authorized(self) -> bool:
                return False

            async def send_code_request(self, phone, **kwargs):
                return SimpleNamespace(
                    type=SentCodeTypeApp(),
                    next_type=None,
                    timeout=None,
                    phone_code_hash=f"hash-for-{phone}",
                )

        try:
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                }
            }
            sync.client = FakeClient()
            sync._auth_step = "phone"
            sync._auth_code_timeout_sec = None
            sync._auth_code_requested_at = None
            sync._auth_code_message = None
            with patch.dict(os.environ, {"PAYME_AUTH_SESSION_RELEASE_GRACE_SEC": "0"}):
                with patch.object(sync, "load_state", return_value={}):
                    with patch.object(sync, "save_state", lambda: None):
                        with patch.object(sync, "_release_session_handles_for_pause", AsyncMock()) as release:
                            with patch.object(sync, "_reset_client", AsyncMock()) as reset:
                                with patch.object(sync, "_ensure_connected_for_auth", AsyncMock()):
                                    message = await sync.start_web_auth("+79999980872")

            release.assert_awaited()
            reset.assert_awaited_once()
            self.assertTrue(sync.get_sync_control_status()["paused"])
            self.assertEqual(sync.get_sync_control_status()["reason"], "telegram authorization")
            self.assertEqual(sync._auth_phone_code_hash, "hash-for-+79999980872")
            self.assertIn("Код запрошен", message)
            self.assertIn("приложение Telegram", message)
            self.assertIn("приложение Telegram", sync._auth_code_message)

            status = await back._runtime_status()
            self.assertEqual(status.auth_code_delivery_type, "SentCodeTypeApp")
            self.assertIn("приложение Telegram", status.auth_code_message)
        finally:
            sync.state = original_state
            sync.client = original_client
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync._auth_phone = original_auth_phone
            sync._auth_phone_code_hash = original_auth_hash
            sync._auth_step = original_auth_step
            sync._auth_pause_previous_status = original_pause_status
            sync._auth_code_timeout_sec = original_timeout
            sync._auth_code_requested_at = original_requested
            sync._auth_code_message = original_message

    async def test_telegram_auth_phone_request_is_idempotent_while_code_pending(self) -> None:
        sync = back.telegram_sync
        original_phone = sync._auth_phone
        original_hash = sync._auth_phone_code_hash
        original_step = sync._auth_step
        original_message = getattr(sync, "_auth_code_message", None)

        class FailIfCalled:
            async def send_code_request(self, *_args, **_kwargs):
                raise AssertionError("send_code_request should not be called for pending code")

        original_client = sync.client
        try:
            sync.client = FailIfCalled()
            sync._auth_phone = "+79999980872"
            sync._auth_phone_code_hash = "phone-code-hash"
            sync._auth_step = "code"
            sync._auth_code_message = "Telegram отправил код в приложение Telegram на этом аккаунте."

            message = await sync.start_web_auth("+79999980872")

            self.assertIn("Код уже запрошен", message)
            self.assertIn("приложение Telegram", message)
        finally:
            sync.client = original_client
            sync._auth_phone = original_phone
            sync._auth_phone_code_hash = original_hash
            sync._auth_step = original_step
            sync._auth_code_message = original_message

    async def test_telegram_auth_floodwait_cooldown_is_persisted_and_blocks_repeat(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_timeout = getattr(sync, "_auth_code_timeout_sec", None)
        original_requested = getattr(sync, "_auth_code_requested_at", None)
        original_message = getattr(sync, "_auth_code_message", None)
        original_hash = sync._auth_phone_code_hash
        original_auth_step = sync._auth_step

        class FailIfCalled:
            async def send_code_request(self, *_args, **_kwargs):
                raise AssertionError("send_code_request should not be called during persisted cooldown")

        original_client = sync.client
        try:
            sync.state = {}
            sync.client = FailIfCalled()
            sync._auth_phone_code_hash = None
            sync._auth_step = "phone"
            sync._auth_code_timeout_sec = 120
            sync._auth_code_requested_at = datetime.now(timezone.utc).isoformat()
            sync._auth_code_message = "Telegram временно ограничил повторную отправку кода. Повторите примерно через 120 сек."
            with patch.object(sync, "save_state", lambda: None):
                sync._persist_auth_code_status()
            sync._auth_code_timeout_sec = None
            sync._auth_code_requested_at = None
            sync._auth_code_message = None

            with self.assertRaises(ValueError) as ctx:
                await sync.start_web_auth("+79999980872")

            self.assertIn("ограничил", str(ctx.exception))
            self.assertIn("_telegram_auth_code", sync.state)
        finally:
            sync.state = original_state
            sync.client = original_client
            sync._auth_code_timeout_sec = original_timeout
            sync._auth_code_requested_at = original_requested
            sync._auth_code_message = original_message
            sync._auth_phone_code_hash = original_hash
            sync._auth_step = original_auth_step

    async def test_telegram_auth_resume_after_success_when_auth_paused_sync(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_pause_status = getattr(sync, "_auth_pause_previous_status", None)

        try:
            sync.state = {}
            sync.set_sync_paused(True, reason="telegram authorization")
            sync._auth_pause_previous_status = {"paused": False}
            await sync._resume_sync_after_auth_if_needed()

            self.assertFalse(sync.get_sync_control_status()["paused"])
            self.assertEqual(sync.get_sync_control_status()["reason"], "telegram authorization complete")
        finally:
            sync.state = original_state
            sync._auth_pause_previous_status = original_pause_status

    async def test_telegram_auth_resume_keeps_manual_pause(self) -> None:
        sync = back.telegram_sync
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_pause_status = getattr(sync, "_auth_pause_previous_status", None)

        try:
            sync.state = {}
            sync.set_sync_paused(True, reason="manual dashboard")
            sync._auth_pause_previous_status = {"paused": True, "reason": "manual dashboard"}
            await sync._resume_sync_after_auth_if_needed()

            self.assertTrue(sync.get_sync_control_status()["paused"])
            self.assertEqual(sync.get_sync_control_status()["reason"], "manual dashboard")
        finally:
            sync.state = original_state
            sync._auth_pause_previous_status = original_pause_status

    async def test_telegram_pause_releases_client_session_handles(self) -> None:
        sync = back.telegram_sync
        original_client = sync.client
        original_started = sync._started
        original_entities = dict(sync.entities_by_chat_key)
        disconnected = False

        class FakeClient:
            async def disconnect(self):
                nonlocal disconnected
                disconnected = True

        try:
            sync.client = FakeClient()
            sync._started = True
            sync.entities_by_chat_key["chat"] = object()
            await sync._release_session_handles_for_pause("test")

            self.assertTrue(disconnected)
            self.assertIsNone(sync.client)
            self.assertFalse(sync._started)
            self.assertEqual(sync.entities_by_chat_key, {})
        finally:
            sync.client = original_client
            sync._started = original_started
            sync.entities_by_chat_key.clear()
            sync.entities_by_chat_key.update(original_entities)

    async def test_telegram_auth_code_after_restart_requests_new_code(self) -> None:
        sync = back.telegram_sync
        original_phone = sync._auth_phone
        original_hash = sync._auth_phone_code_hash
        original_step = sync._auth_step
        original_error = sync._auth_last_error

        try:
            sync._auth_phone = "+79999980872"
            sync._auth_phone_code_hash = None
            sync._auth_step = "code"
            with self.assertRaises(ValueError) as ctx:
                await sync.submit_web_auth_code("12345")

            self.assertIn("Сначала запросите код", str(ctx.exception))
        finally:
            sync._auth_phone = original_phone
            sync._auth_phone_code_hash = original_hash
            sync._auth_step = original_step
            sync._auth_last_error = original_error

    async def test_frontend_html_redirects_to_setup_when_telegram_not_authorized(self) -> None:
        async def runtime_status():
            return back.RuntimeStatusDTO(
                auth_status="needs_auth",
                auth_message="Нужна авторизация Telegram.",
                session_file_exists=False,
                connected=False,
                auth_step="phone",
            )

        with patch("back._runtime_status", runtime_status):
            response = await back._telegram_setup_wizard_redirect_response(
                _request_for_path("/dashboard.html")
            )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 307)
        self.assertIn("/setup_wizard.html", response.headers["location"])
        self.assertIn("reason=needs_auth", response.headers["location"])

    async def test_frontend_html_does_not_redirect_while_session_is_reconnecting(self) -> None:
        async def runtime_status():
            return back.RuntimeStatusDTO(
                auth_status="session_present",
                auth_message="Сессия Telegram найдена, backend подключается.",
                session_file_exists=True,
                connected=False,
                auth_step="phone",
            )

        with patch("back._runtime_status", runtime_status):
            response = await back._telegram_setup_wizard_redirect_response(
                _request_for_path("/")
            )

        self.assertIsNone(response)

    async def test_runtime_status_does_not_block_on_slow_telegram_auth_check(self) -> None:
        class SlowAuthorizedClient:
            def is_connected(self) -> bool:
                return True

            async def is_user_authorized(self) -> bool:
                await asyncio.sleep(2)
                return True

        class ExistingSessionPath:
            def exists(self) -> bool:
                return True

        sync = back.telegram_sync
        original_client = sync.client
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_handlers = sync._live_handlers_installed
        original_entities = sync.entities_by_chat_key

        try:
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                    "telegram_phone": "+10000000000",
                }
            }
            sync.client = SlowAuthorizedClient()
            sync._live_handlers_installed = False
            sync.entities_by_chat_key = {}

            with patch("app.services.runtime_status._telegram_session_file_path", return_value=ExistingSessionPath()):
                with patch("app.services.runtime_status._RUNTIME_STATUS_TELEGRAM_AUTH_TIMEOUT_SEC", 0.01):
                    status = await back._runtime_status()

            self.assertEqual(status.auth_status, "session_present")
            self.assertTrue(status.session_file_exists)
        finally:
            sync.client = original_client
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.state = original_state
            sync._live_handlers_installed = original_handlers
            sync.entities_by_chat_key = original_entities

    async def test_runtime_status_does_not_autostart_telegram_sync_by_default(self) -> None:
        class DisconnectedClient:
            def is_connected(self) -> bool:
                return False

        class ExistingSessionPath:
            def exists(self) -> bool:
                return True

        sync = back.telegram_sync
        original_client = sync.client
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_step = sync._auth_step

        try:
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                    "telegram_phone": "+10000000000",
                }
            }
            sync.client = DisconnectedClient()
            sync._auth_step = "phone"

            with patch("app.services.runtime_status._telegram_session_file_path", return_value=ExistingSessionPath()):
                with patch("app.services.runtime_status._RUNTIME_STATUS_TELEGRAM_AUTOSTART_ENABLED", False):
                    with patch.object(sync, "start", new=AsyncMock()) as start_mock:
                        status = await back._runtime_status()

            self.assertEqual(status.auth_status, "session_present")
            start_mock.assert_not_awaited()
        finally:
            sync.client = original_client
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.state = original_state
            sync._auth_step = original_step

    async def test_runtime_status_exposes_separate_telegram_runtime_flags(self) -> None:
        class ConnectedUnauthorizedClient:
            def is_connected(self) -> bool:
                return True

            async def is_user_authorized(self) -> bool:
                return False

        class ExistingSessionPath:
            def exists(self) -> bool:
                return True

        sync = back.telegram_sync
        original_client = sync.client
        original_api_id = sync.api_id
        original_api_hash = sync.api_hash
        original_state = dict(sync.state) if isinstance(sync.state, dict) else sync.state
        original_step = sync._auth_step

        try:
            sync.api_id = 12345
            sync.api_hash = "hash"
            sync.state = {
                back.APP_SETTINGS_STATE_KEY: {
                    "telegram_api_id": "12345",
                    "telegram_api_hash": "hash",
                    "telegram_phone": "+10000000000",
                }
            }
            sync.set_sync_paused(True, reason="unit-test")
            sync.client = ConnectedUnauthorizedClient()
            sync._auth_step = "phone"

            with patch("app.services.runtime_status._telegram_session_file_path", return_value=ExistingSessionPath()):
                with patch(
                    "app.services.runtime_status._telegram_job_runtime_state",
                    return_value={
                        "worker_connected": True,
                        "sync_reading": True,
                        "sync_reading_stage": "history",
                        "status_detail": "unit worker reads history",
                    },
                ):
                    status = await back._runtime_status()

            self.assertTrue(status.session_file_exists)
            self.assertFalse(status.telegram_authorized)
            self.assertTrue(status.connected)
            self.assertTrue(status.worker_connected)
            self.assertTrue(status.sync_paused)
            self.assertEqual(status.sync_pause_reason, "unit-test")
            self.assertTrue(status.sync_reading)
            self.assertEqual(status.sync_reading_stage, "history")
            self.assertEqual(status.sync_status_detail, "unit worker reads history")
        finally:
            sync.client = original_client
            sync.api_id = original_api_id
            sync.api_hash = original_api_hash
            sync.state = original_state
            sync._auth_step = original_step

    async def test_setup_wizard_is_not_redirected_by_telegram_guard(self) -> None:
        async def runtime_status():
            raise AssertionError("setup wizard must not call runtime redirect guard")

        with patch("back._runtime_status", runtime_status):
            response = await back._telegram_setup_wizard_redirect_response(
                _request_for_path("/setup_wizard.html")
            )

        self.assertIsNone(response)


if __name__ == "__main__":
    unittest.main()
