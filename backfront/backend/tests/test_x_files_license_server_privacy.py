import unittest
import tempfile
import sys
import base64
from pathlib import Path

from fastapi import HTTPException
try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    if exc.name != "httpx":
        raise
    TestClient = None

ROOT = Path(__file__).resolve().parents[1]
LICENSE_SERVER = ROOT.parents[1] / "license.xfiles.codeboost.ru"
if str(LICENSE_SERVER) not in sys.path:
    sys.path.insert(0, str(LICENSE_SERVER))

import x_files_license_server.server as license_server


class XFilesLicenseServerPrivacyTest(unittest.TestCase):
    def test_license_server_accepts_license_metadata_only_payload(self) -> None:
        license_server.reject_client_data(
            {
                "license_id": "lic_test",
                "license_token": "token-test",
                "client_id": "cli_test",
                "instance_hash": "device_hash",
                "device_hash": "device_hash",
                "client_email": "client@example.com",
                "activation_key": "win-15d-testhash",
                "activation_duration_days": 15,
                "invite_batch_id": "universal-15d-20260525-100k",
                "invite_code_required": True,
                "invite_code": "XF15DTEST0001",
                "plan": "free-demo-first-touch-vip",
                "release": "2026.05.08-test",
            }
        )

    def test_license_server_accepts_enterprise_feature_flags(self) -> None:
        license_server.reject_client_data(
            {
                "payload": {
                    "license_id": "lic_test",
                    "license_token": "token-test",
                    "client_id": "cli_test",
                    "device_hash": "device_hash",
                    "client_email": "client@example.com",
                    "plan": "enterprise",
                    "release": "2026.05.22-test",
                    "features": {
                        "contacts": True,
                        "crm": True,
                        "deals": True,
                        "telegram_unlimited_import": True,
                    },
                    "limits": {
                        "import_history_months_max": 0,
                        "import_message_limit_max": 0,
                    },
                }
            }
        )

    def test_license_server_rejects_nested_telegram_messages(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            license_server.reject_client_data({"payload": {"messages": ["secret client text"]}})
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("messages", str(cm.exception.detail))

    def test_license_server_rejects_nested_crm_and_deals_payloads(self) -> None:
        for forbidden_key in ("contacts", "crm", "deals", "ocr_text", "jsonl"):
            with self.subTest(forbidden_key=forbidden_key):
                with self.assertRaises(HTTPException) as cm:
                    license_server.reject_client_data({"metadata": {"nested": {forbidden_key: "client data"}}})
                self.assertEqual(cm.exception.status_code, 422)
                self.assertIn(forbidden_key, str(cm.exception.detail))

    def test_license_server_revoke_trust_time_and_update_entitlement(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                client = TestClient(license_server.app)
                state = license_server.load_state()
                invite_code = "XF15DTEST0001"
                invite_code_hash = license_server.token_hash(invite_code)
                state.setdefault("invite_codes", {})[invite_code_hash] = {
                    "invite_code": invite_code,
                    "invite_code_hash": invite_code_hash,
                    "invite_batch_id": "universal-15d-20260525-100k",
                    "activation_key": "win-15d-testhash",
                    "status": "issued",
                    "created_at": license_server.utc_now(),
                }
                license_server.save_state(state)

                activation = client.post(
                    "/api/license/activate",
                    json={
                        "license_id": "lic_test",
                        "license_token": "token-test",
                        "client_id": "cli_test",
                        "instance_hash": "device_hash",
                        "device_hash": "device_hash",
                        "client_email": "client@example.com",
                        "activation_key": "win-15d-testhash",
                        "activation_duration_days": 15,
                        "invite_batch_id": "universal-15d-20260525-100k",
                        "invite_code_required": True,
                        "invite_code": invite_code,
                        "plan": "free-demo-first-touch-vip",
                        "release": "2026.05.08-test",
                    },
                )
                self.assertEqual(200, activation.status_code, activation.text)
                self.assertEqual("active", activation.json()["status"])
                self.assertIn("server_time", activation.json())
                self.assertIn("trusted_time", activation.json())
                self.assertEqual(
                    "win-15d-testhash",
                    license_server.load_state()["activations"]["lic_test"]["activation_key"],
                )
                self.assertEqual(
                    15,
                    license_server.load_state()["activations"]["lic_test"]["activation_duration_days"],
                )
                activated_row = license_server.load_state()["activations"]["lic_test"]
                self.assertTrue(activated_row["expires_at"])
                activated_at = license_server.datetime.fromisoformat(activated_row["activated_at"])
                expires_at = license_server.datetime.fromisoformat(activated_row["expires_at"])
                self.assertEqual(15, (expires_at - activated_at).days)
                self.assertEqual(
                    invite_code,
                    license_server.load_state()["activations"]["lic_test"]["invite_code"],
                )
                self.assertEqual(
                    "activated",
                    license_server.load_state()["invite_codes"][invite_code_hash]["status"],
                )

                same_device_activation = client.post(
                    "/api/license/activate",
                    json={
                        "license_id": "lic_test",
                        "license_token": "token-test",
                        "client_id": "cli_test",
                        "instance_hash": "device_hash",
                        "device_hash": "device_hash",
                        "client_email": "client@example.com",
                        "plan": "free-demo-first-touch-vip",
                        "release": "2026.05.08-test",
                    },
                )
                self.assertEqual(200, same_device_activation.status_code, same_device_activation.text)

                different_device_activation = client.post(
                    "/api/license/activate",
                    json={
                        "license_id": "lic_test",
                        "license_token": "token-test",
                        "client_id": "cli_test",
                        "instance_hash": "device_hash_b",
                        "device_hash": "device_hash_b",
                        "client_email": "client@example.com",
                        "plan": "free-demo-first-touch-vip",
                        "release": "2026.05.08-test",
                    },
                )
                self.assertEqual(409, different_device_activation.status_code)
                self.assertIn("another device", different_device_activation.text)

                reused_invite_other_license = client.post(
                    "/api/license/activate",
                    json={
                        "license_id": "lic_other",
                        "license_token": "token-other",
                        "client_id": "cli_other",
                        "instance_hash": "device_hash_c",
                        "device_hash": "device_hash_c",
                        "client_email": "other@example.com",
                        "activation_key": "win-15d-testhash",
                        "activation_duration_days": 15,
                        "invite_batch_id": "universal-15d-20260525-100k",
                        "invite_code_required": True,
                        "invite_code": invite_code,
                        "plan": "free-demo-first-touch-vip",
                        "release": "2026.05.08-test",
                    },
                )
                self.assertEqual(409, reused_invite_other_license.status_code)
                self.assertIn("already activated", reused_invite_other_license.text)

                token = base64.b64encode(b"owner:secret").decode("ascii")
                old_admin_user = license_server.ADMIN_USER
                old_admin_password = license_server.ADMIN_PASSWORD
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                try:
                    diagnose = client.get(
                        f"/api/admin/invite-codes/diagnose/{invite_code}",
                        headers={"Authorization": f"Basic {token}"},
                    )
                finally:
                    license_server.ADMIN_USER = old_admin_user
                    license_server.ADMIN_PASSWORD = old_admin_password
                self.assertEqual(200, diagnose.status_code, diagnose.text)
                self.assertEqual("activated", diagnose.json()["status"])
                self.assertTrue(diagnose.json()["errors"])

                trust_time = client.get("/api/license/trust-time")
                self.assertEqual(200, trust_time.status_code, trust_time.text)
                self.assertIn("server_time", trust_time.json())

                allowed = client.post(
                    "/api/license/update-entitlement",
                    json={
                        "license_id": "lic_test",
                        "instance_hash": "device_hash",
                        "target_version": "2026.06.01",
                        "version_min": "2026.05.01",
                        "version_max": "2026.12.31",
                        "update_channel": "stable",
                    },
                )
                self.assertEqual(200, allowed.status_code, allowed.text)
                self.assertTrue(allowed.json()["allowed"])

                revoke = client.post("/api/license/revoke", json={"license_id": "lic_test", "reason": "test"})
                self.assertEqual(200, revoke.status_code, revoke.text)
                self.assertEqual("revoked", revoke.json()["status"])

                revoke_status = client.get("/api/license/revoke-status/lic_test")
                self.assertEqual(200, revoke_status.status_code, revoke_status.text)
                self.assertTrue(revoke_status.json()["revoked"])

                old_admin_user = license_server.ADMIN_USER
                old_admin_password = license_server.ADMIN_PASSWORD
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                try:
                    extend = client.post(
                        "/api/admin/license/extend",
                        headers={"Authorization": f"Basic {token}"},
                        json={
                            "license_id": "lic_test",
                            "expires_at": "2026-09-01",
                            "reason": "owner renewal after revoke",
                        },
                    )
                finally:
                    license_server.ADMIN_USER = old_admin_user
                    license_server.ADMIN_PASSWORD = old_admin_password
                self.assertEqual(200, extend.status_code, extend.text)
                self.assertEqual("active", license_server.load_state()["activations"]["lic_test"]["status"])
                self.assertNotIn("lic_test", license_server.load_state()["revocations"])

                denied = client.post(
                    "/api/license/update-entitlement",
                    json={
                        "license_id": "lic_test",
                        "instance_hash": "device_hash",
                        "target_version": "2026.06.01",
                        "version_min": "2026.05.01",
                        "version_max": "2026.12.31",
                    },
                )
                self.assertEqual(200, denied.status_code, denied.text)
                self.assertTrue(denied.json()["allowed"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path

    def test_license_server_respects_max_activations_device_limit(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                client = TestClient(license_server.app)
                state = license_server.load_state()
                for code in ("XFMULTI0001", "XFMULTI0002", "XFMULTI0003"):
                    code_hash = license_server.token_hash(code)
                    state.setdefault("invite_codes", {})[code_hash] = {
                        "invite_code": code,
                        "invite_code_hash": code_hash,
                        "invite_batch_id": "multi-device",
                        "activation_key": "multi-key",
                        "status": "issued",
                        "created_at": license_server.utc_now(),
                    }
                license_server.save_state(state)

                base_payload = {
                    "license_id": "lic_multi",
                    "license_token": "token-multi",
                    "client_id": "cli_multi",
                    "client_email": "multi@example.com",
                    "activation_key": "multi-key",
                    "activation_duration_days": 15,
                    "invite_batch_id": "multi-device",
                    "invite_code_required": True,
                    "plan": "enterprise",
                    "release": "2026.05.26-test",
                    "max_activations": 2,
                    "limits": {"telegram_sources_total": 10},
                    "features": {"deals": True},
                }

                first = client.post(
                    "/api/license/activate",
                    json={**base_payload, "instance_hash": "device-a", "device_hash": "device-a", "invite_code": "XFMULTI0001"},
                )
                second = client.post(
                    "/api/license/activate",
                    json={**base_payload, "instance_hash": "device-b", "device_hash": "device-b", "invite_code": "XFMULTI0002"},
                )
                third = client.post(
                    "/api/license/activate",
                    json={**base_payload, "instance_hash": "device-c", "device_hash": "device-c", "invite_code": "XFMULTI0003"},
                )

                self.assertEqual(200, first.status_code, first.text)
                self.assertEqual(200, second.status_code, second.text)
                self.assertEqual(409, third.status_code)
                stored = license_server.load_state()["activations"]["lic_multi"]
                self.assertEqual(2, stored["activation_count"])
                self.assertEqual(2, stored["max_activations"])
                self.assertEqual({"device-a", "device-b"}, {item["instance_hash"] for item in stored["devices"]})
                self.assertEqual({"telegram_sources_total": 10}, stored["limits"])
                self.assertEqual({"deals": True}, stored["features"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path

    def test_renewal_invite_code_creates_new_activation_without_feature_loss(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                state = license_server.load_state()
                renewal_code = "XFRENEW0001"
                renewal_hash = license_server.token_hash(renewal_code)
                state.setdefault("invite_codes", {})[renewal_hash] = {
                    "invite_code": renewal_code,
                    "invite_code_hash": renewal_hash,
                    "invite_batch_id": "renew-lic-old",
                    "activation_key": "renewal-key",
                    "status": "issued",
                    "created_at": license_server.utc_now(),
                }
                license_server.save_state(state)
                client = TestClient(license_server.app)

                response = client.post(
                    "/api/license/activate",
                    json={
                        "license_id": "lic_renewed",
                        "license_token": "token-renewed",
                        "client_id": "cli_test",
                        "instance_hash": "device_hash",
                        "device_hash": "device_hash",
                        "client_email": "client@example.com",
                        "activation_key": "renewal-key",
                        "activation_duration_days": 15,
                        "invite_batch_id": "renew-lic-old",
                        "invite_code_required": True,
                        "invite_code": renewal_code,
                        "plan": "enterprise",
                        "release": "2026.05.25-renewal",
                    },
                )

                self.assertEqual(200, response.status_code, response.text)
                state_after = license_server.load_state()
                renewed = state_after["activations"]["lic_renewed"]
                self.assertEqual("enterprise", renewed["plan"])
                self.assertEqual("renew-lic-old", renewed["invite_batch_id"])
                self.assertEqual("activated", state_after["invite_codes"][renewal_hash]["status"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path

    def test_license_server_rate_limits_metadata_endpoints(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            old_max = license_server.RATE_LIMIT_MAX_REQUESTS
            old_window = license_server.RATE_LIMIT_WINDOW_SECONDS
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                license_server.RATE_LIMIT_MAX_REQUESTS = 2
                license_server.RATE_LIMIT_WINDOW_SECONDS = 60
                client = TestClient(license_server.app)

                self.assertEqual(200, client.get("/api/license/trust-time").status_code)
                self.assertEqual(200, client.get("/api/license/trust-time").status_code)
                limited = client.get("/api/license/trust-time")
                self.assertEqual(429, limited.status_code)
                self.assertEqual("rate_limited", limited.json()["detail"]["error"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path
                license_server.RATE_LIMIT_MAX_REQUESTS = old_max
                license_server.RATE_LIMIT_WINDOW_SECONDS = old_window

    def test_admin_invite_batches_summary_counts_codes(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            old_admin_user = license_server.ADMIN_USER
            old_admin_password = license_server.ADMIN_PASSWORD
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                state = license_server.load_state()
                for code, status in (("XF15DONE", "activated"), ("XF15DTWO", "issued")):
                    code_hash = license_server.token_hash(code)
                    state.setdefault("invite_codes", {})[code_hash] = {
                        "invite_code": code,
                        "invite_code_hash": code_hash,
                        "invite_batch_id": "universal-15d",
                        "activation_key": "win-15d-test",
                        "platforms": "windows",
                        "status": status,
                        "created_at": "2026-05-25T00:00:00+00:00",
                        "activated_at": "2026-05-25T01:00:00+00:00" if status == "activated" else "",
                    }
                license_server.save_state(state)
                client = TestClient(license_server.app)
                token = base64.b64encode(b"owner:secret").decode("ascii")
                response = client.get("/api/admin/invite-codes/batches", headers={"Authorization": f"Basic {token}"})

                self.assertEqual(200, response.status_code, response.text)
                payload = response.json()
                self.assertEqual(1, payload["total"])
                batch = payload["items"][0]
                self.assertEqual("universal-15d", batch["invite_batch_id"])
                self.assertEqual(2, batch["total"])
                self.assertEqual(1, batch["activated"])
                self.assertEqual(1, batch["issued"])
                self.assertEqual(0, batch["expired"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path
                license_server.ADMIN_USER = old_admin_user
                license_server.ADMIN_PASSWORD = old_admin_password

    def test_admin_extend_license_updates_activated_expiry(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            old_admin_user = license_server.ADMIN_USER
            old_admin_password = license_server.ADMIN_PASSWORD
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                state = license_server.load_state()
                state.setdefault("activations", {})["lic_extend"] = {
                    "license_id": "lic_extend",
                    "client_email": "client@example.com",
                    "instance_hash": "device_hash",
                    "status": "active",
                    "expires_at": "2026-06-01T00:00:00+00:00",
                }
                license_server.save_state(state)
                client = TestClient(license_server.app)
                token = base64.b64encode(b"owner:secret").decode("ascii")

                response = client.post(
                    "/api/admin/license/extend",
                    headers={"Authorization": f"Basic {token}"},
                    json={
                        "license_id": "lic_extend",
                        "expires_at": "2026-07-15",
                        "reason": "owner renewal smoke",
                    },
                )

                self.assertEqual(200, response.status_code, response.text)
                self.assertTrue(response.json()["ok"])
                self.assertEqual("2026-07-15T23:59:59+00:00", response.json()["expires_at"])
                renewed = license_server.load_state()["activations"]["lic_extend"]
                self.assertEqual("2026-07-15T23:59:59+00:00", renewed["expires_at"])
                self.assertEqual("active", renewed["status"])
                self.assertEqual("owner renewal smoke", renewed["last_extension_reason"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path
                license_server.ADMIN_USER = old_admin_user
                license_server.ADMIN_PASSWORD = old_admin_password

    def test_admin_revoke_license_updates_authoritative_status(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            old_admin_user = license_server.ADMIN_USER
            old_admin_password = license_server.ADMIN_PASSWORD
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                state = license_server.load_state()
                state.setdefault("activations", {})["lic_revoke"] = {
                    "license_id": "lic_revoke",
                    "client_email": "client@example.com",
                    "instance_hash": "device_hash",
                    "status": "active",
                    "expires_at": "2026-06-01T00:00:00+00:00",
                }
                license_server.save_state(state)
                client = TestClient(license_server.app)
                token = base64.b64encode(b"owner:secret").decode("ascii")

                response = client.post(
                    "/api/admin/license/revoke",
                    headers={"Authorization": f"Basic {token}"},
                    json={"license_id": "lic_revoke", "reason": "owner revoke smoke"},
                )

                self.assertEqual(200, response.status_code, response.text)
                self.assertTrue(response.json()["ok"])
                self.assertEqual("revoked", response.json()["status"])
                state_after = license_server.load_state()
                self.assertEqual("revoked", state_after["activations"]["lic_revoke"]["status"])
                self.assertEqual("revoked", state_after["revocations"]["lic_revoke"]["status"])
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path
                license_server.ADMIN_USER = old_admin_user
                license_server.ADMIN_PASSWORD = old_admin_password

    def test_admin_page_has_tabs_paging_formatted_dates_and_status_colors(self) -> None:
        if TestClient is None:
            self.skipTest("httpx dependency is not installed")
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = license_server.DATA_DIR
            old_state_path = license_server.STATE_PATH
            old_admin_user = license_server.ADMIN_USER
            old_admin_password = license_server.ADMIN_PASSWORD
            try:
                license_server.DATA_DIR = Path(tmpdir)
                license_server.STATE_PATH = Path(tmpdir) / "license-server-state.json"
                license_server.ADMIN_USER = "owner"
                license_server.ADMIN_PASSWORD = "secret"
                state = license_server.load_state()
                state.setdefault("activations", {})["lic_admin"] = {
                    "license_id": "lic_admin",
                    "client_email": "client@example.com",
                    "plan": "enterprise",
                    "status": "active",
                    "expires_at": "2026-07-01T23:59:59+00:00",
                    "activated_at": "2026-05-27T15:48:50+00:00",
                    "last_seen_at": "2026-05-27T15:49:10+00:00",
                }
                license_server.save_state(state)
                client = TestClient(license_server.app)
                token = base64.b64encode(b"owner:secret").decode("ascii")

                response = client.get(
                    "/admin?tab=licenses&page=1&page_size=25",
                    headers={"Authorization": f"Basic {token}"},
                )

                self.assertEqual(200, response.status_code, response.text)
                html = response.text
                self.assertIn("Лицензии", html)
                self.assertIn("Invite codes", html)
                self.assertIn("1 / 1", html)
                self.assertIn("01.07.2026, 23:59", html)
                self.assertIn('pill green">active', html)
            finally:
                license_server.DATA_DIR = old_data_dir
                license_server.STATE_PATH = old_state_path
                license_server.ADMIN_USER = old_admin_user
                license_server.ADMIN_PASSWORD = old_admin_password

    def test_vps_deployment_contract_is_privacy_safe(self) -> None:
        deploy_dir = ROOT / "deploy" / "x-files-license-server-vps"
        compose = (deploy_dir / "docker-compose.yml").read_text(encoding="utf-8")
        readme = (deploy_dir / "README.md").read_text(encoding="utf-8")
        env_example = (deploy_dir / ".env.example").read_text(encoding="utf-8")

        self.assertIn("x-files-license-server", compose)
        self.assertIn("127.0.0.1", compose)
        self.assertIn("/license-server-data", compose)
        self.assertIn("/api/license/trust-time", compose)
        self.assertIn("XFILES_LICENSE_SERVER_IMAGE", env_example)
        self.assertIn("license metadata", readme)

        bundle_text = "\n".join([compose, readme, env_example]).lower()
        for forbidden in ("telegram", "ocr-текст", "jsonl", "duckdb/postgresql"):
            self.assertIn(forbidden, bundle_text)
        for forbidden_env in ("telegram_api_hash", "openrouter_api_key", "payme_state_path", "payme_out_dir"):
            self.assertNotIn(forbidden_env, bundle_text)


if __name__ == "__main__":
    unittest.main()
