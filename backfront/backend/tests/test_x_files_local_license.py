import json
import unittest
from datetime import datetime, timedelta, timezone

from x_files_license.core import (
    LICENSE_SCHEMA,
    LicenseError,
    append_license_audit_record,
    append_migration_audit_record,
    apply_license,
    build_license_server_activation_payload,
    build_license_audit_record,
    build_migration_audit_record,
    compute_effective_allowed_menus,
    create_metadata_backup,
    license_status,
    load_license_state,
    read_license_audit_records,
    read_migration_audit_records,
    refresh_license_server_status,
    restore_metadata_backup,
    sign_payload,
    validate_version_entitlement,
    validate_schema_compatibility,
    verify_signed_document,
)
from x_files_license.tariffs import license_capabilities


SECRET = "test-signing-secret"
TEST_NOW = datetime(2026, 5, 8, 12, 1, tzinfo=timezone.utc)


def make_license(**overrides):
    now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
    payload = {
        "schema": LICENSE_SCHEMA,
        "license_id": "lic_test",
        "license_token": "token-test",
        "client_id": "cli_test",
        "client_email": "client@example.com",
        "root_email": "aidialog@mail.ru",
        "release": "2026.05.08-test",
        "plan": "free-demo-first-touch-vip",
        "plan_title": "Free Demo First Touch VIP",
        "license_kind": "activation",
        "valid_from": now.isoformat(),
        "valid_until": (now + timedelta(days=7)).isoformat(),
        "duration_days": 7,
        "offline_allowed": True,
        "hardware_binding_policy": "one_device",
        "max_activations": 1,
        "limits": {"telegram_sources_total": 10},
        "features": {"deals": True, "postgres": True, "ocr": True},
        "allowed_menus": ["dashboard", "deals", "settings"],
        "disabled_menus": [],
        "license_server_url": "http://license.example.local:8015",
    }
    payload.update(overrides)
    return {"payload": payload, "signature_alg": "HMAC-SHA256", "signature": sign_payload(payload, SECRET)}


class XFilesLocalLicenseTest(unittest.TestCase):
    def test_signed_invite_rejects_tampering(self):
        document = make_license()
        tampered = json.loads(json.dumps(document))
        tampered["payload"]["plan"] = "enterprise"

        with self.assertRaises(LicenseError):
            verify_signed_document(tampered, SECRET, expected_schema=LICENSE_SCHEMA)

    def test_apply_license_persists_signed_state(self):
        with self.subTest("persistent signed state"):
            import tempfile

            with tempfile.TemporaryDirectory() as tmpdir:
                state_path = f"{tmpdir}/license-state.json"
                state = apply_license(
                    make_license(),
                    state_path=state_path,
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    now=datetime(2026, 5, 8, 12, 1, tzinfo=timezone.utc),
                )

                self.assertEqual(state["plan"], "free-demo-first-touch-vip")
                self.assertEqual(state["limits"]["telegram_sources_total"], 10)
                self.assertEqual(load_license_state(state_path, SECRET)["instance_hash"], "device-a")

    def test_activation_duration_starts_on_apply(self):
        import tempfile

        issued_at = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        applied_at = datetime(2026, 6, 10, 14, 30, tzinfo=timezone.utc)
        document = make_license(
            valid_from=issued_at.isoformat(),
            valid_until=(issued_at + timedelta(days=1)).isoformat(),
            duration_days=1,
            activation_duration_days=15,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            state = apply_license(
                document,
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=applied_at,
            )

        self.assertEqual(applied_at.isoformat(), state["activation_started_at"])
        self.assertEqual(applied_at.isoformat(), state["valid_from"])
        self.assertEqual((applied_at + timedelta(days=15)).isoformat(), state["valid_until"])
        self.assertEqual(15, state["duration_days"])

    def test_online_license_check_sends_metadata_only_and_persists_status(self):
        import tempfile

        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"status":"active","license_id":"lic_test"}'

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            state = apply_license(
                make_license(),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                online_check=True,
                urlopen=fake_urlopen,
                now=TEST_NOW,
            )

            self.assertEqual(captured["url"], "http://license.example.local:8015/api/license/activate")
            self.assertEqual(captured["payload"]["license_id"], "lic_test")
            self.assertEqual(captured["payload"]["license_token"], "token-test")
            self.assertEqual(captured["payload"]["client_id"], "cli_test")
            self.assertEqual(captured["payload"]["instance_hash"], "device-a")
            self.assertEqual(captured["payload"]["device_hash"], "device-a")
            self.assertEqual(captured["payload"]["client_email"], "client@example.com")
            self.assertEqual(captured["payload"]["max_activations"], 1)
            self.assertEqual(captured["payload"]["limits"]["telegram_sources_total"], 10)
            self.assertNotIn("messages", captured["payload"])
            self.assertNotIn("deals", captured["payload"])
            self.assertEqual(state["license_server"]["status"], "active")
            self.assertTrue(license_status(state_path=state_path, signing_secret=SECRET, now=TEST_NOW)["license_server"]["online"])

    def test_online_license_check_applies_authoritative_server_expiry_and_limits(self):
        import tempfile

        server_expires_at = "2026-08-01T23:59:59+00:00"

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "status": "active",
                        "license_id": "lic_test",
                        "expires_at": server_expires_at,
                        "max_activations": 2,
                        "activation_count": 1,
                        "limits": {"telegram_sources_total": 25},
                        "features": {"deals": True, "postgres": True, "ocr": False},
                        "allowed_menus": ["dashboard", "settings"],
                        "disabled_menus": ["ocr"],
                        "server_time": "2026-05-08T12:01:01+00:00",
                        "trusted_time": "2026-05-08T12:01:01+00:00",
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            state = apply_license(
                make_license(),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                online_check=True,
                urlopen=lambda request, timeout: FakeResponse(),
                now=TEST_NOW,
            )

        self.assertEqual(server_expires_at, state["valid_until"])
        self.assertEqual(25, state["limits"]["telegram_sources_total"])
        self.assertFalse(state["features"]["ocr"])
        self.assertEqual(["dashboard", "settings"], state["allowed_menus"])
        self.assertEqual(["ocr"], state["disabled_menus"])
        self.assertEqual(2, state["max_activations"])
        self.assertEqual(server_expires_at, state["license_server"]["expires_at"])

    def test_refresh_license_server_status_applies_owner_extension(self):
        import tempfile

        server_expires_at = "2026-09-10T23:59:59+00:00"

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "status": "active",
                        "license_id": "lic_test",
                        "expires_at": server_expires_at,
                        "limits": {"telegram_sources_total": 99},
                        "features": {"deals": True, "postgres": True, "ocr": True},
                        "server_time": "2026-05-08T12:02:00+00:00",
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            apply_license(make_license(), state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=TEST_NOW)
            status = license_status(state_path=state_path, signing_secret=SECRET, now=TEST_NOW)
            refreshed = refresh_license_server_status(
                status,
                server_url="http://license.example.local:8015",
                urlopen=lambda request, timeout: FakeResponse(),
            )

        self.assertTrue(refreshed["ok"])
        self.assertEqual("active", refreshed["status"])
        self.assertEqual(server_expires_at, refreshed["valid_until"])
        self.assertEqual(99, refreshed["limits"]["telegram_sources_total"])
        self.assertEqual("active", refreshed["license_server"]["status"])

    def test_refresh_license_server_status_blocks_revoked_license(self):
        import tempfile

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "status": "revoked",
                        "license_id": "lic_test",
                        "reason": "owner revoked",
                        "server_time": "2026-05-08T12:02:00+00:00",
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            apply_license(make_license(), state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=TEST_NOW)
            status = license_status(state_path=state_path, signing_secret=SECRET, now=TEST_NOW)
            refreshed = refresh_license_server_status(
                status,
                server_url="http://license.example.local:8015",
                urlopen=lambda request, timeout: FakeResponse(),
            )

        self.assertFalse(refreshed["ok"])
        self.assertEqual("revoked", refreshed["status"])
        self.assertTrue(refreshed["read_only"])
        self.assertIn("отозвана", refreshed["disabled_reason"])

    def test_refresh_license_server_status_blocks_when_server_unreachable(self):
        import tempfile

        def fake_urlopen(request, timeout):
            raise OSError("network down")

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            apply_license(make_license(), state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=TEST_NOW)
            status = license_status(state_path=state_path, signing_secret=SECRET, now=TEST_NOW)
            refreshed = refresh_license_server_status(
                status,
                server_url="http://license.example.local:8015",
                urlopen=fake_urlopen,
            )

        self.assertFalse(refreshed["ok"])
        self.assertEqual("license_server_unavailable", refreshed["status"])
        self.assertTrue(refreshed["read_only"])
        self.assertIn("license-server", refreshed["disabled_reason"])

    def test_refresh_license_server_status_blocks_not_active_server_status(self):
        import tempfile

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"status":"not_activated","license_id":"lic_test"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            apply_license(make_license(), state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=TEST_NOW)
            status = license_status(state_path=state_path, signing_secret=SECRET, now=TEST_NOW)
            refreshed = refresh_license_server_status(
                status,
                server_url="http://license.example.local:8015",
                urlopen=lambda request, timeout: FakeResponse(),
            )

        self.assertFalse(refreshed["ok"])
        self.assertEqual("not_activated", refreshed["status"])
        self.assertTrue(refreshed["read_only"])

    def test_online_license_check_blocks_revoked_code(self):
        import tempfile
        import urllib.error

        class ErrorBody:
            def read(self):
                return b'{"detail":"License is revoked"}'

            def close(self):
                return None

        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                hdrs=None,
                fp=ErrorBody(),
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(LicenseError):
                apply_license(
                    make_license(),
                    state_path=f"{tmpdir}/license-state.json",
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    online_check=True,
                    urlopen=fake_urlopen,
                    now=TEST_NOW,
                )

    def test_license_server_payload_is_privacy_safe(self):
        payload = make_license()["payload"]
        result = build_license_server_activation_payload(payload, instance_hash="device-a")

        self.assertEqual(
            set(result),
            {
                "license_id",
                "license_token",
                "client_id",
                "instance_hash",
                "device_hash",
                "client_email",
                "activation_key",
                "activation_duration_days",
                "invite_batch_id",
                "invite_code_required",
                "invite_code",
                "plan",
                "version",
                "max_activations",
                "limits",
                "features",
                "allowed_menus",
                "disabled_menus",
            },
        )

    def test_client_status_can_preview_signed_invite_before_activation(self):
        import tempfile
        import os
        from pathlib import Path
        import app.services.license_runtime as license_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            invite_path = Path(tmpdir) / "invite-license.json"
            invite_path.write_text(
                json.dumps(
                    make_license(
                        invite_code_required=True,
                        valid_until="2026-07-01T23:59:59+00:00",
                        activation_duration_days=15,
                    )
                ),
                encoding="utf-8",
            )
            old_env = {
                "XFILES_LICENSE_FILE": os.environ.get("XFILES_LICENSE_FILE"),
                "XFILES_LICENSE_SERVER_URL": os.environ.get("XFILES_LICENSE_SERVER_URL"),
            }
            try:
                os.environ["XFILES_LICENSE_FILE"] = str(invite_path)
                os.environ["XFILES_LICENSE_SERVER_URL"] = "http://license.example.local:8015"
                license_runtime.XFILES_LICENSE_SCHEMA = LICENSE_SCHEMA
                license_runtime.xfiles_verify_signed_document = verify_signed_document
                license_runtime.xfiles_license_capabilities = license_capabilities
                preview = license_runtime._xfiles_invite_license_preview_payload(SECRET)
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual("not_activated", preview["status"])
        self.assertEqual("client@example.com", preview["client_email"])
        self.assertEqual("free-demo-first-touch-vip", preview["plan"])
        self.assertTrue(preview["invite_code_required"])

    def test_safe_client_status_exposes_local_invite_code_only(self):
        import tempfile
        import os
        from pathlib import Path
        import app.services.license_runtime as license_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            invite_code_path = Path(tmpdir) / "INVITE-CODE.md"
            state_path = Path(tmpdir) / "license-state.json"
            invite_code_path.write_text(
                "# Invite\n\n`XF15D-SAFE-LOCAL-CODE`\n",
                encoding="utf-8",
            )
            old_env = {
                "XFILES_INVITE_CODE_FILE": os.environ.get("XFILES_INVITE_CODE_FILE"),
                "XFILES_LICENSE_STATE_PATH": os.environ.get("XFILES_LICENSE_STATE_PATH"),
            }
            try:
                os.environ["XFILES_INVITE_CODE_FILE"] = str(invite_code_path)
                os.environ["XFILES_LICENSE_STATE_PATH"] = str(state_path)
                safe = license_runtime._xfiles_safe_client_license_status(
                    {
                        "ok": True,
                        "status": "active",
                        "license_id": "lic_hidden_123456",
                        "invite_batch_id": "batch_hidden",
                        "invite_code_masked": "masked-hidden",
                        "license_server": {"url": "https://hidden.example", "online": True},
                    }
                )
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual("XF15D-SAFE-LOCAL-CODE", safe["invite_code_display"])
        self.assertEqual("lic_hidden_123456", safe["license_id_display"])
        self.assertNotIn("license_id", safe)
        self.assertNotIn("invite_batch_id", safe)
        self.assertNotIn("invite_code_masked", safe)
        self.assertNotIn("url", safe["license_server"])

    def test_safe_client_status_falls_back_to_local_state_license_id(self):
        import tempfile
        import os
        from pathlib import Path
        import app.services.license_runtime as license_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            invite_code_path = Path(tmpdir) / "missing-INVITE-CODE.md"
            state_path = Path(tmpdir) / "license-state.json"
            state_path.write_text(
                json.dumps({"payload": {"license_id": "lic_state_display_123456"}}),
                encoding="utf-8",
            )
            old_env = {
                "XFILES_INVITE_CODE_FILE": os.environ.get("XFILES_INVITE_CODE_FILE"),
                "XFILES_LICENSE_STATE_PATH": os.environ.get("XFILES_LICENSE_STATE_PATH"),
            }
            try:
                os.environ["XFILES_INVITE_CODE_FILE"] = str(invite_code_path)
                os.environ["XFILES_LICENSE_STATE_PATH"] = str(state_path)
                safe = license_runtime._xfiles_safe_client_license_status({"ok": True, "status": "active"})
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual("lic_state_display_123456", safe["license_id_display"])
        self.assertNotIn("license_id", safe)

    def test_safe_client_status_falls_back_to_local_state_invite_code(self):
        import tempfile
        import os
        from pathlib import Path
        import app.services.license_runtime as license_runtime

        with tempfile.TemporaryDirectory() as tmpdir:
            invite_code_path = Path(tmpdir) / "missing-INVITE-CODE.md"
            state_path = Path(tmpdir) / "license-state.json"
            state_path.write_text(
                json.dumps({"payload": {"invite_code": "XF15D-STATE-LOCAL-CODE"}}),
                encoding="utf-8",
            )
            old_env = {
                "XFILES_INVITE_CODE_FILE": os.environ.get("XFILES_INVITE_CODE_FILE"),
                "XFILES_LICENSE_STATE_PATH": os.environ.get("XFILES_LICENSE_STATE_PATH"),
            }
            try:
                os.environ["XFILES_INVITE_CODE_FILE"] = str(invite_code_path)
                os.environ["XFILES_LICENSE_STATE_PATH"] = str(state_path)
                safe = license_runtime._xfiles_safe_client_license_status({"ok": True, "status": "active"})
            finally:
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertEqual("XF15D-STATE-LOCAL-CODE", safe["invite_code_display"])

    def test_license_status_dto_keeps_invite_code_display(self):
        from app.schemas.compat_models import XFilesLicenseStatusDTO

        dto = XFilesLicenseStatusDTO(
            ok=True,
            status="active",
            license_id_display="lic_dto_display_123456",
            invite_code_display="XF15D-DTO-LOCAL-CODE",
        )

        self.assertEqual("lic_dto_display_123456", dto.license_id_display)
        self.assertEqual("XF15D-DTO-LOCAL-CODE", dto.invite_code_display)

    def test_client_status_auto_activates_zip_invite_code_when_server_is_online(self):
        import tempfile
        import os
        import urllib.request
        from pathlib import Path
        import app.services.license_runtime as license_runtime

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "status": "active",
                        "license_id": "lic_test",
                        "expires_at": "2026-07-01T23:59:59+00:00",
                    }
                ).encode("utf-8")

        captured = {}

        def fake_urlopen(request, timeout):
            captured.setdefault("urls", []).append(request.full_url)
            if getattr(request, "data", None):
                captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmpdir:
            invite_path = Path(tmpdir) / "invite-license.json"
            invite_code_path = Path(tmpdir) / "INVITE-CODE.md"
            state_path = Path(tmpdir) / "license-state.json"
            invite_path.write_text(
                json.dumps(
                    make_license(
                        invite_code_required=True,
                        valid_until="2026-07-01T23:59:59+00:00",
                        activation_duration_days=15,
                    )
                ),
                encoding="utf-8",
            )
            invite_code_path.write_text(
                "# Invite\n\n"
                "- License ID: `lic_test`\n"
                "- Activation hash-key: `stand-mac`\n\n"
                "## Код для клиента\n\n"
                "`XF15D-TEST-CODE`\n",
                encoding="utf-8",
            )
            old_env = {
                "XFILES_LICENSE_FILE": os.environ.get("XFILES_LICENSE_FILE"),
                "XFILES_INVITE_CODE_FILE": os.environ.get("XFILES_INVITE_CODE_FILE"),
                "XFILES_LICENSE_STATE_PATH": os.environ.get("XFILES_LICENSE_STATE_PATH"),
                "XFILES_LICENSE_SERVER_URL": os.environ.get("XFILES_LICENSE_SERVER_URL"),
                "XFILES_LICENSE_SIGNING_SECRET": os.environ.get("XFILES_LICENSE_SIGNING_SECRET"),
                "XFILES_CLIENT_DELIVERY": os.environ.get("XFILES_CLIENT_DELIVERY"),
            }
            old_urlopen = urllib.request.urlopen
            try:
                os.environ["XFILES_LICENSE_FILE"] = str(invite_path)
                os.environ["XFILES_INVITE_CODE_FILE"] = str(invite_code_path)
                os.environ["XFILES_LICENSE_STATE_PATH"] = str(state_path)
                os.environ["XFILES_LICENSE_SERVER_URL"] = "http://license.example.local:8015"
                os.environ["XFILES_LICENSE_SIGNING_SECRET"] = SECRET
                os.environ["XFILES_CLIENT_DELIVERY"] = "1"
                license_runtime.XFILES_LICENSE_SCHEMA = LICENSE_SCHEMA
                license_runtime.xfiles_verify_signed_document = verify_signed_document
                license_runtime.xfiles_apply_license = apply_license
                license_runtime.xfiles_license_status = license_status
                license_runtime.xfiles_license_capabilities = license_capabilities
                urllib.request.urlopen = fake_urlopen
                status = license_runtime._xfiles_license_status_payload()
            finally:
                urllib.request.urlopen = old_urlopen
                for key, value in old_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value

        self.assertTrue(status["ok"])
        self.assertEqual("active", status["status"])
        self.assertEqual("XF15D-TEST-CODE", captured["payload"]["invite_code"])
        self.assertIn("/api/license/activate", captured["urls"][0])

    def test_license_server_payload_includes_universal_activation_key(self):
        payload = make_license(activation_key="win-15d-testhash")["payload"]
        result = build_license_server_activation_payload(payload, instance_hash="device-a")

        self.assertEqual("win-15d-testhash", result["activation_key"])

    def test_invite_code_required_is_sent_to_license_server(self):
        payload = make_license(
            activation_key="win-15d-testhash",
            invite_batch_id="universal-15d-20260525-100k",
            invite_code_required=True,
        )["payload"]
        result = build_license_server_activation_payload(payload, instance_hash="device-a", invite_code="XF-ABC-123")

        self.assertEqual("universal-15d-20260525-100k", result["invite_batch_id"])
        self.assertTrue(result["invite_code_required"])
        self.assertEqual("XF-ABC-123", result["invite_code"])

    def test_invite_code_required_blocks_empty_activation_code(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(LicenseError):
                apply_license(
                    make_license(invite_code_required=True),
                    state_path=f"{tmpdir}/license-state.json",
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    online_check=True,
                    urlopen=lambda request, timeout: None,
                    now=TEST_NOW,
                )

    def test_one_device_binding_blocks_second_instance(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            apply_license(
                make_license(),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=TEST_NOW,
            )

            renewal = make_license(license_kind="renewal", license_id="lic_renewal")
            with self.assertRaises(LicenseError):
                apply_license(renewal, state_path=state_path, signing_secret=SECRET, instance_hash="device-b")

    def test_license_status_reports_grace_period(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
            expired_license = make_license(
                valid_from=(now - timedelta(days=10)).isoformat(),
                valid_until=(now - timedelta(days=1)).isoformat(),
            )
            apply_license(expired_license, state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=now)

            status = license_status(state_path=state_path, signing_secret=SECRET, now=now, grace_days=3)

            self.assertEqual(status["status"], "grace")
            self.assertTrue(status["ok"])
            self.assertFalse(status["read_only"])
            self.assertIn("grace period", status["message"])
            self.assertTrue(status["grace_until"])

    def test_expired_license_reports_read_only_disabled_mode(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            applied_at = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
            expired_license = make_license(
                valid_from=(applied_at - timedelta(days=1)).isoformat(),
                valid_until=(applied_at + timedelta(days=1)).isoformat(),
            )
            apply_license(
                expired_license,
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=applied_at,
            )

            status = license_status(
                state_path=state_path,
                signing_secret=SECRET,
                now=applied_at + timedelta(days=8),
                grace_days=3,
            )

            self.assertEqual(status["status"], "expired")
            self.assertFalse(status["ok"])
            self.assertTrue(status["read_only"])
            self.assertIn("read-only/disabled", status["message"])
            self.assertIn("продления тарифа", status["disabled_reason"])

    def test_license_status_touches_last_seen_and_blocks_clock_rollback(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            activated_at = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
            apply_license(
                make_license(),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=activated_at,
            )

            later = activated_at + timedelta(hours=2)
            ok_status = license_status(
                state_path=state_path,
                signing_secret=SECRET,
                now=later,
                touch_interval_seconds=0,
            )
            self.assertEqual(ok_status["clock_status"], "ok")
            self.assertEqual(ok_status["last_seen_at"], later.isoformat())

            rollback_status = license_status(
                state_path=state_path,
                signing_secret=SECRET,
                now=activated_at + timedelta(minutes=10),
                clock_skew_seconds=60,
            )
            self.assertEqual(rollback_status["status"], "clock_tampered")
            self.assertFalse(rollback_status["ok"])
            self.assertTrue(rollback_status["read_only"])

    def test_apply_license_refuses_renewal_after_clock_rollback(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            activated_at = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)
            apply_license(
                make_license(),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=activated_at,
            )
            license_status(
                state_path=state_path,
                signing_secret=SECRET,
                now=activated_at + timedelta(days=1),
                touch_interval_seconds=0,
            )
            renewal = make_license(license_kind="renewal", license_id="lic_renewal")
            with self.assertRaises(LicenseError):
                apply_license(
                    renewal,
                    state_path=state_path,
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    now=activated_at + timedelta(hours=1),
                    clock_skew_seconds=60,
                )

    def test_version_entitlement_blocks_unsupported_app_version(self):
        payload = make_license(version_min="2026.05.01", version_max="2026.05.31")["payload"]

        self.assertTrue(validate_version_entitlement(payload, "2026.05.08-test")["checked"])
        with self.assertRaises(LicenseError):
            validate_version_entitlement(payload, "2026.04.30")
        with self.assertRaises(LicenseError):
            validate_version_entitlement(payload, "2026.06.01")

    def test_apply_license_persists_version_window_and_rejects_invalid_update(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            with self.assertRaises(LicenseError):
                apply_license(
                    make_license(license_kind="update", version_min="2026.05.01"),
                    state_path=state_path,
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    app_version="2026.05.08",
                    now=TEST_NOW,
                )

            apply_license(
                make_license(version_min="2026.05.01", version_max="2026.05.31"),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                app_version="2026.05.08-test",
                now=TEST_NOW,
            )
            with self.assertRaises(LicenseError):
                apply_license(
                    make_license(
                        license_id="lic_other_client",
                        license_kind="update",
                        client_id="cli_other",
                        version_min="2026.05.01",
                    ),
                    state_path=state_path,
                    signing_secret=SECRET,
                    instance_hash="device-a",
                    app_version="2026.05.08-test",
                    now=TEST_NOW,
                )

            state = apply_license(
                make_license(
                    license_id="lic_update",
                    license_kind="update",
                    version_min="2026.05.01",
                    version_max="2026.05.31",
                ),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                app_version="2026.05.09",
                now=TEST_NOW,
            )

            self.assertEqual(state["license_id"], "lic_update")
            self.assertEqual(state["app_version"], "2026.05.09")
            self.assertEqual(state["version_min"], "2026.05.01")
            self.assertTrue(state["version_check"]["checked"])

    def test_upgrade_preserves_activation_and_adds_history(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = f"{tmpdir}/license-state.json"
            activated_at = datetime(2026, 5, 8, 12, 1, tzinfo=timezone.utc)
            apply_license(make_license(), state_path=state_path, signing_secret=SECRET, instance_hash="device-a", now=activated_at)
            upgraded = apply_license(
                make_license(
                    license_id="lic_growth",
                    license_kind="upgrade",
                    plan="growth-20",
                    plan_title="Growth 20",
                    limits={"telegram_sources_total": 20},
                ),
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
                now=datetime(2026, 5, 9, 12, 1, tzinfo=timezone.utc),
            )

            self.assertEqual(upgraded["plan"], "growth-20")
            self.assertEqual(upgraded["activated_at"], activated_at.isoformat())
            self.assertEqual(upgraded["limits"]["telegram_sources_total"], 20)
            self.assertEqual(len(upgraded["history"]), 2)

    def test_license_audit_records_do_not_store_raw_signature(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = f"{tmpdir}/license-audit.jsonl"
            document = make_license()
            status = {"status": "active", "plan": "free-demo-first-touch-vip", "license_id": "lic_test"}
            record = build_license_audit_record(action="activate", ok=True, document=document, status=status)
            append_license_audit_record(audit_path, record)

            rows = read_license_audit_records(audit_path, limit=1)

            self.assertEqual(rows[0]["action"], "activate")
            self.assertTrue(rows[0]["ok"])
            self.assertEqual(rows[0]["license_kind"], "activation")
            self.assertNotIn("signature", rows[0])
            self.assertNotIn("payload", rows[0])

    def test_metadata_backup_restore_and_migration_audit_are_data_safe(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            license_state = root / "license-state.json"
            settings = root / "settings.json"
            data_file = root / "customer-data.jsonl"
            audit_path = root / "audit" / "migration.jsonl"
            license_state.write_text('{"schema":"state","value":1}\n', encoding="utf-8")
            settings.write_text('{"theme":"light"}\n', encoding="utf-8")
            data_file.write_text('{"message":"must stay untouched"}\n', encoding="utf-8")

            backup = create_metadata_backup(
                {"license": license_state, "settings": settings},
                backup_dir=root / "backups",
                reason="before-schema-2",
                app_version="2026.05.09",
                schema_version=1,
                now=datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
            )
            license_state.write_text('{"schema":"state","value":2}\n', encoding="utf-8")
            settings.write_text('{"theme":"changed"}\n', encoding="utf-8")

            restored = restore_metadata_backup(backup["backup_path"])
            record = build_migration_audit_record(
                action="rollback",
                ok=True,
                migration="schema-2",
                from_schema=2,
                to_schema=1,
                backup_path=backup["backup_path"],
                app_version="2026.05.09",
            )
            append_migration_audit_record(audit_path, record)
            rows = read_migration_audit_records(audit_path, limit=1)

            self.assertEqual(backup["file_count"], 2)
            self.assertEqual(restored["restored_count"], 2)
            self.assertEqual(license_state.read_text(encoding="utf-8"), '{"schema":"state","value":1}\n')
            self.assertEqual(settings.read_text(encoding="utf-8"), '{"theme":"light"}\n')
            self.assertEqual(data_file.read_text(encoding="utf-8"), '{"message":"must stay untouched"}\n')
            self.assertEqual(rows[0]["migration"], "schema-2")
            self.assertNotIn("customer-data", json.dumps(rows[0], ensure_ascii=False))

    def test_schema_compatibility_blocks_unknown_versions(self):
        self.assertEqual(
            validate_schema_compatibility(3, min_supported=2, max_supported=5)["current_schema_version"],
            3,
        )
        with self.assertRaises(LicenseError):
            validate_schema_compatibility(1, min_supported=2, max_supported=5)
        with self.assertRaises(LicenseError):
            validate_schema_compatibility(6, min_supported=2, max_supported=5)

    def test_effective_allowed_menus_respects_allow_and_disable_lists(self):
        status = {
            "ok": True,
            "allowed_menus": ["dashboard", "deals", "settings", "unknown-extra"],
            "disabled_menus": ["settings"],
        }
        result = compute_effective_allowed_menus(
            status,
            ["dashboard", "deals", "settings", "crm"],
            fallback_menus=["dashboard", "tariffs"],
        )

        self.assertTrue(result["enforced"])
        self.assertEqual(result["effective_allowed_menus"], ["dashboard", "deals"])
        self.assertEqual(result["disabled_menus"], ["settings"])

    def test_effective_allowed_menus_uses_fallback_without_active_license(self):
        result = compute_effective_allowed_menus(
            {"ok": False, "disabled_menus": ["logs"]},
            ["dashboard", "deals", "logs"],
            fallback_menus=["dashboard", "logs"],
        )

        self.assertFalse(result["enforced"])
        self.assertTrue(result["fallback"])
        self.assertEqual(result["effective_allowed_menus"], ["dashboard"])

    def test_enterprise_license_capabilities_allow_unlimited_telegram_import(self):
        free_caps = license_capabilities("free-demo")
        enterprise_caps = license_capabilities("enterprise")

        self.assertFalse(free_caps["telegram_unlimited_import"])
        self.assertTrue(enterprise_caps["telegram_unlimited_import"])
        self.assertEqual(enterprise_caps["import_history_months_max"], 0)
        self.assertEqual(enterprise_caps["import_message_limit_max"], 0)


if __name__ == "__main__":
    unittest.main()
