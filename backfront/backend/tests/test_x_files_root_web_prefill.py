import importlib
import json
import tempfile
import sys
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[3]
LICENSE_LOCAL_FRONT = ROOT / "license.local-front"

if str(LICENSE_LOCAL_FRONT) not in sys.path:
    sys.path.insert(0, str(LICENSE_LOCAL_FRONT))

web = importlib.import_module("x_files_root.web")
root = importlib.import_module("x_files_root.root")


def valid_payload(**overrides):
    data = {
        "client_email": "client@example.com",
        "client_name": "Client Example",
        "activation_key": "",
        "invite_batch_id": "",
        "invite_code_required": False,
        "root_email": "owner@example.com",
        "release": "2026.05.22-test",
        "plan": "starter",
        "license_kind": "activation",
        "duration_days": None,
        "activation_duration_days": None,
        "valid_until": "",
        "source_limit": None,
        "version_min": "",
        "version_max": "",
        "update_channel": "stable",
        "license_server_url": "http://license.example.local:8015",
        "ocr_url": "http://x-files-ocr:8010",
        "disable_menu": [],
        "image_tar": [],
        "backfront_digest": "",
        "db_digest": "",
        "ocr_digest": "",
        "allow_repeat": False,
        "signing_secret": "test-root-signing-secret",
    }
    data.update(overrides)
    return web.BundleRequest(**data)


class XFilesRootWebPrefillTest(unittest.TestCase):
    def test_json_only_owner_mode_can_run_without_postgres(self) -> None:
        old_disable = getattr(web, "DISABLE_POSTGRES", False)
        old_data_dir = web.DATA_DIR
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                web.DISABLE_POSTGRES = True
                web.DATA_DIR = Path(tmpdir)
                registry = root.ensure_registry(web.DATA_DIR)
                registry["clients"]["client@example.com"] = {
                    "client_id": "cli_json",
                    "client_email": "client@example.com",
                    "client_name": "Client JSON",
                    "activation_key": "json-key",
                    "root_email": "owner@example.com",
                    "last_release": "2026.06.02-json",
                    "last_plan": "enterprise",
                    "updated_at": "2026-06-02T10:00:00+00:00",
                }
                registry["licenses"]["lic_json"] = {
                    "license_id": "lic_json",
                    "client_id": "cli_json",
                    "client_email": "client@example.com",
                    "plan": "enterprise",
                    "created_at": "2026-06-02T10:00:00+00:00",
                }
                registry["downloads"].append(
                    {
                        "download_id": "dl_json",
                        "client_email": "client@example.com",
                        "license_id": "lic_json",
                        "bundle_name": "client.zip",
                        "created_at": "2026-06-02T10:00:00+00:00",
                    }
                )
                root.save_registry(web.DATA_DIR, registry)

                web.init_db()
                synced = web.sync_registry_to_postgres()
                clients = web.fetch_clients()
                licenses = web.fetch_licenses()
                downloads = web.fetch_downloads()
        finally:
            web.DISABLE_POSTGRES = old_disable
            web.DATA_DIR = old_data_dir

        self.assertEqual("cli_json", synced["clients"]["client@example.com"]["client_id"])
        self.assertEqual("Client JSON", clients[0]["client_name"])
        self.assertEqual("lic_json", licenses[0]["license_id"])
        self.assertEqual("dl_json", downloads[0]["download_id"])

    def test_activation_prefill_uses_existing_client_but_stays_editable_new_license(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            registry = root.ensure_registry(data_dir)
            registry["clients"][root.client_key("Client@Example.com")] = {
                "client_id": "cli_existing",
                "client_email": "Client@Example.com",
                "client_name": "Client Example",
                "root_email": "owner@example.com",
                "last_release": "2026.05.20-web",
                "last_plan": "starter",
                "updated_at": "2026-05-21T10:00:00+00:00",
            }
            root.save_registry(data_dir, registry)

            prefill = web.build_bundle_prefill(
                mode="activation",
                client_email="client@example.com",
                registry=root.ensure_registry(data_dir),
            )

        self.assertTrue(prefill["ok"])
        self.assertEqual("create", prefill["mode"])
        self.assertEqual("Client@Example.com", prefill["form"]["client_email"])
        self.assertEqual("Client Example", prefill["form"]["client_name"])
        self.assertEqual("owner@example.com", prefill["form"]["root_email"])
        self.assertEqual("starter", prefill["form"]["plan"])
        self.assertEqual("activation", prefill["form"]["license_kind"])
        self.assertEqual((root.utc_now() + timedelta(days=15)).date().isoformat(), prefill["form"]["valid_until"])
        self.assertFalse(prefill["form"]["allow_repeat"])

    def test_renewal_prefill_uses_source_license_limits_and_renewal_flags(self) -> None:
        registry = {
            "clients": {
                root.client_key("client@example.com"): {
                    "client_id": "cli_existing",
                    "client_email": "client@example.com",
                    "client_name": "Client Example",
                    "root_email": "owner@example.com",
                    "last_plan": "starter",
                }
            },
            "licenses": {
                "lic_old": {
                    "license_id": "lic_old",
                    "client_id": "cli_existing",
                    "client_email": "client@example.com",
                    "plan": "growth-20",
                    "license_kind": "activation",
                    "limits": {"telegram_sources_total": 25},
                    "disabled_menus": ["contacts", "crm"],
                    "created_at": "2026-05-21T10:00:00+00:00",
                }
            },
        }

        prefill = web.build_bundle_prefill(mode="renewal", license_id="lic_old", registry=registry)

        self.assertEqual("renew", prefill["mode"])
        self.assertEqual("lic_old", prefill["source_license_id"])
        self.assertEqual("client@example.com", prefill["form"]["client_email"])
        self.assertEqual("Client Example", prefill["form"]["client_name"])
        self.assertEqual("growth-20", prefill["form"]["plan"])
        self.assertEqual("renewal", prefill["form"]["license_kind"])
        self.assertEqual(30, prefill["form"]["duration_days"])
        self.assertEqual((root.utc_now() + timedelta(days=10)).date().isoformat(), prefill["form"]["valid_until"])
        self.assertEqual(25, prefill["form"]["source_limit"])
        self.assertEqual(["contacts", "crm"], prefill["form"]["disable_menu"])
        self.assertTrue(prefill["form"]["allow_repeat"])

    def test_root_web_create_form_has_single_build_release_submit_and_calendar_date(self) -> None:
        html = web.HTML

        self.assertIn("type: 'date'", html)
        self.assertIn(r"/^\d{4}-\d{2}-\d{2}$/", html)
        self.assertIn("Собрать Docker/ZIP и проверить", html)
        self.assertIn("/api/releases/build/jobs", html)
        self.assertIn("pollReleaseJob", html)
        self.assertIn("inviteRegistrationLabel", html)
        self.assertIn("boot.license_authority", html)
        self.assertNotIn("mode === 'renew' ? 'Продлить / перевыпустить' : 'Создать лицензию'", html)
        self.assertIn("invite-code-cell", html)
        self.assertIn("formatDateReadable", html)
        self.assertIn("datePlusDays(15)", html)
        self.assertIn("licenseClientFilter", html)
        self.assertIn("Дата выпуска", html)
        self.assertIn("registryTab === 'clients'", html)
        self.assertNotIn("JSON.stringify(lic.limits", html)
        self.assertNotIn("e('div', {className: 'mono'}, (lic.bundle_path || '').split('/').pop())", html)

    def test_activation_prefill_from_client_does_not_attach_source_license_to_ui(self) -> None:
        registry = {
            "clients": {
                root.client_key("client@example.com"): {
                    "client_email": "client@example.com",
                    "client_name": "Client Example",
                    "last_plan": "starter",
                }
            },
            "licenses": {
                "lic_old": {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "growth-50",
                    "limits": {"telegram_sources_total": 50},
                    "created_at": "2026-05-21T10:00:00+00:00",
                }
            },
        }

        prefill = web.build_bundle_prefill(mode="activation", client_email="client@example.com", registry=registry)

        self.assertEqual("create", prefill["mode"])
        self.assertEqual("", prefill["source_license_id"])
        self.assertIsNone(prefill["source_license"])
        self.assertEqual("growth-50", prefill["form"]["plan"])
        self.assertEqual(50, prefill["form"]["source_limit"])

    def test_prefill_rejects_unknown_mode(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.build_bundle_prefill(mode="renwal", registry={"clients": {}, "licenses": {}})

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("renwal", str(cm.exception.detail))

    def test_prefill_falls_back_when_stored_plan_is_unknown(self) -> None:
        registry = {
            "clients": {
                root.client_key("client@example.com"): {
                    "client_email": "client@example.com",
                    "client_name": "Client Example",
                    "last_plan": "starter",
                }
            },
            "licenses": {
                "lic_old": {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "old-growth-plan",
                    "created_at": "2026-05-21T10:00:00+00:00",
                }
            },
        }

        prefill = web.build_bundle_prefill(mode="renewal", license_id="lic_old", registry=registry)

        self.assertEqual("starter", prefill["form"]["plan"])

    def test_prefill_prefers_latest_non_revoked_license_for_client(self) -> None:
        registry = {
            "clients": {
                root.client_key("client@example.com"): {
                    "client_email": "client@example.com",
                    "client_name": "Client Example",
                    "last_plan": "starter",
                }
            },
            "licenses": {
                "lic_active_old": {
                    "license_id": "lic_active_old",
                    "client_email": "client@example.com",
                    "plan": "starter",
                    "status": "issued",
                    "created_at": "2026-05-20T10:00:00+00:00",
                    "limits": {"telegram_sources_total": 6},
                },
                "lic_revoked_new": {
                    "license_id": "lic_revoked_new",
                    "client_email": "client@example.com",
                    "plan": "growth-100",
                    "status": "revoked",
                    "created_at": "2026-05-21T10:00:00+00:00",
                    "limits": {"telegram_sources_total": 100},
                },
            },
        }

        prefill = web.build_bundle_prefill(mode="renewal", client_email="client@example.com", registry=registry)

        self.assertEqual("lic_active_old", prefill["source_license_id"])
        self.assertEqual("starter", prefill["form"]["plan"])
        self.assertEqual(6, prefill["form"]["source_limit"])

    def test_renewal_prefill_rejects_unknown_explicit_license_id(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.build_bundle_prefill(mode="renewal", license_id="lic_missing", registry={"clients": {}, "licenses": {}})

        self.assertEqual(404, cm.exception.status_code)
        self.assertIn("lic_missing", str(cm.exception.detail))

    def test_bundle_registry_keeps_disabled_menus_for_future_renewal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = type(
                "Args",
                (),
                {
                    "data_dir": str(Path(tmpdir) / "root-data"),
                    "output_dir": str(Path(tmpdir) / "releases"),
                    "client_email": "client@example.com",
                    "client_name": "Client Example",
                    "root_email": "owner@example.com",
                    "release": "2026.05.22-test",
                    "plan": "starter",
                    "license_kind": "activation",
                    "duration_days": None,
                    "valid_until": "",
                    "source_limit": None,
                    "version_min": "",
                    "version_max": "",
                    "update_channel": "stable",
                    "license_server_url": "http://license.example.local:8015",
                    "ocr_url": "http://x-files-ocr:8010",
                    "disable_menu": ["contacts", "crm"],
                    "image_tar": [],
                    "backfront_digest": "",
                    "db_digest": "",
                    "ocr_digest": "",
                    "allow_repeat": False,
                    "signing_secret": "test-root-signing-secret",
                },
            )()

            result = root.bundle(args)
            registry = root.ensure_registry(Path(tmpdir) / "root-data")
            stored = registry["licenses"][result.license_id]

        self.assertEqual(["contacts", "crm"], stored["disabled_menus"])

    def test_make_namespace_rejects_empty_client_email(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.make_namespace(valid_payload(client_email="   "))

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("Email клиента", str(cm.exception.detail))

    def test_make_namespace_rejects_non_positive_duration_days(self) -> None:
        for value in (0, -3):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as cm:
                    web.make_namespace(valid_payload(duration_days=value))
                self.assertEqual(400, cm.exception.status_code)
                self.assertIn("Длительность", str(cm.exception.detail))

    def test_make_namespace_rejects_negative_source_limit(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.make_namespace(valid_payload(source_limit=-1))

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("Лимит источников", str(cm.exception.detail))

    def test_license_delivery_templates_include_editable_release_defaults(self) -> None:
        templates = {item["key"]: item for item in web.license_delivery_templates()}

        self.assertIn("activation-default", templates)
        self.assertIn("renewal-default", templates)
        self.assertIn("windows-docker-default", templates)
        self.assertIn("mac-docker-default", templates)
        self.assertEqual(["windows", "mac"], templates["activation-default"]["form"]["target_platforms"])
        self.assertEqual(["windows"], templates["windows-docker-default"]["form"]["target_platforms"])
        self.assertEqual(["mac"], templates["mac-docker-default"]["form"]["target_platforms"])
        self.assertEqual("renewal", templates["renewal-default"]["form"]["license_kind"])
        self.assertTrue(templates["renewal-default"]["form"]["allow_repeat"])
        self.assertTrue(templates["windows-invite-15d"]["form"]["invite_code_required"])
        self.assertEqual(1, templates["windows-invite-15d"]["form"]["invite_code_count"])
        self.assertEqual(["windows"], templates["windows-invite-15d"]["form"]["target_platforms"])
        self.assertEqual(["mac"], templates["mac-invite-15d"]["form"]["target_platforms"])
        self.assertEqual("renewal", templates["renewal-new-invite-code"]["form"]["license_kind"])
        self.assertTrue(templates["renewal-new-invite-code"]["form"]["invite_code_required"])

    def test_image_tar_defaults_describe_current_split_runtime_not_legacy_backfront(self) -> None:
        default_text = "\n".join(web.DEFAULT_IMAGE_TAR_HINTS)

        self.assertIn("x-files-backfront-new-front.tar", default_text)
        self.assertIn("x-files-backfront-new-back.tar", default_text)
        self.assertIn("x-files-client-db.tar", default_text)
        self.assertIn("rabbitmq-3.13-management-alpine.tar", default_text)
        self.assertIn("redis-7-alpine.tar", default_text)
        self.assertNotIn("x-files-client-backfront.tar", default_text)

    def test_root_web_compose_supports_untracked_admin_password_secret_file(self) -> None:
        compose = (ROOT / "x-files-client-db" / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("XFILES_ROOT_LICENSE_SERVER_ADMIN_PASSWORD_FILE", compose)
        self.assertIn("/run/secrets/x-files-root/license-server-admin-password", compose)
        self.assertIn("${XFILES_ROOT_ADMIN_SECRETS_DIR:-./credentials/root-web}:/run/secrets/x-files-root:ro", compose)

    def test_platform_specific_image_tars_override_generic_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir)
            images = data_dir / "images"
            (images / "mac").mkdir(parents=True)
            images.mkdir(exist_ok=True)
            generic = images / "rabbitmq-3.13-management-alpine.tar"
            native = images / "mac" / "rabbitmq-3.13-management-alpine.tar"
            generic.write_text("generic", encoding="utf-8")
            native.write_text("mac-native", encoding="utf-8")

            paths = web.default_existing_image_tar_paths(data_dir=data_dir, platforms=["mac"])

            self.assertIn(str(native), paths)
            self.assertNotIn(str(generic), paths)

    def test_default_bundle_request_autodetects_current_client_image_tars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "root-data"
            images_dir = data_dir / "images"
            images_dir.mkdir(parents=True)
            expected_names = [
                "x-files-backfront-new-front.tar",
                "x-files-backfront-new-back.tar",
                "x-files-client-db.tar",
                "rabbitmq-3.13-management-alpine.tar",
                "redis-7-alpine.tar",
            ]
            for name in expected_names:
                (images_dir / name).write_bytes(b"fake tar marker")

            paths = web.default_existing_image_tar_paths(data_dir)

        self.assertEqual([str(images_dir / name) for name in expected_names], paths)

    def test_default_client_menu_keeps_only_core_and_ext_visible(self) -> None:
        disabled = set(root.DEFAULT_DISABLED_MENU_KEYS)

        self.assertNotIn("import", disabled)
        self.assertNotIn("grid", disabled)
        self.assertNotIn("chats", disabled)
        self.assertNotIn("ext", disabled)
        self.assertNotIn("dashboard", disabled)
        self.assertNotIn("settings", disabled)
        self.assertIn("logs", disabled)
        self.assertIn("media", disabled)

    def test_release_response_can_generate_invite_code_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                payload = web.ReleaseBuildRequest(
                    **{
                        **valid_payload(
                            client_email="win-15d-testhash@universal.xfiles.local",
                            client_name="Universal Windows 15d",
                            activation_key="win-15d-testhash",
                            invite_batch_id="renew-lic-test",
                            invite_code_required=True,
                            invite_code_count=2,
                            release="2026.05.25-universal-win",
                            plan="enterprise",
                            duration_days=15,
                            activation_duration_days=15,
                            target_platforms=["windows"],
                            allow_repeat=True,
                        ).model_dump(),
                        "run_autotests": False,
                    }
                )
                result = root.BundleResult(
                    zip_path=web.OUTPUT_DIR / "dummy.zip",
                    license_id="lic_test",
                    client_id="cli_test",
                    release="2026.05.25-universal-win",
                )

                generated = web.generate_invite_codes_csv(result, payload, ["windows"])
                self.assertIsNotNone(generated)
                assert generated is not None
                csv_path = Path(generated["csv_path"])
                lines = csv_path.read_text(encoding="utf-8").splitlines()
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir

        self.assertEqual(3, len(lines))
        self.assertIn("invite_code", lines[0])
        self.assertIn("renew-lic-test", lines[1])
        self.assertEqual("skipped", generated["registration"]["status"])

    def test_invite_code_csv_embeds_primary_code_into_zip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                zip_path = web.OUTPUT_DIR / "dummy.zip"
                with zipfile.ZipFile(zip_path, "w") as bundle:
                    bundle.writestr("license/INVITE-CODE.md", "old placeholder")
                    bundle.writestr("readme-install.md", "install")
                payload = web.ReleaseBuildRequest(
                    **{
                        **valid_payload(
                            client_email="win-15d-zip@universal.xfiles.local",
                            client_name="Universal Windows Zip",
                            activation_key="win-15d-zip",
                            invite_batch_id="zip-invite-test",
                            invite_code_required=True,
                            invite_code_count=1,
                            release="2026.05.25-universal-zip",
                            plan="enterprise",
                            duration_days=15,
                            activation_duration_days=15,
                            target_platforms=["windows"],
                            allow_repeat=True,
                        ).model_dump(),
                        "run_autotests": False,
                    }
                )
                result = root.BundleResult(
                    zip_path=zip_path,
                    license_id="lic_zip",
                    client_id="cli_zip",
                    release="2026.05.25-universal-zip",
                )

                generated = web.generate_invite_codes_csv(result, payload, ["windows"])
                assert generated is not None
                with zipfile.ZipFile(zip_path, "r") as bundle:
                    invite_md = bundle.read("license/INVITE-CODE.md").decode("utf-8")
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir

        self.assertIn("Invite-code для активации GramLead", invite_md)
        self.assertIn("zip-invite-test", invite_md)
        self.assertNotIn("old placeholder", invite_md)

    def test_invite_code_csv_can_auto_register_with_license_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                payload = web.ReleaseBuildRequest(
                    **{
                        **valid_payload(
                            client_email="mac-15d-testhash@universal.xfiles.local",
                            client_name="Universal Mac 15d",
                            activation_key="mac-15d-testhash",
                            invite_batch_id="renew-lic-auto",
                            invite_code_required=True,
                            invite_code_count=1,
                            release="2026.05.25-universal-mac",
                            plan="enterprise",
                            duration_days=15,
                            activation_duration_days=15,
                            target_platforms=["mac"],
                            allow_repeat=True,
                        ).model_dump(),
                        "run_autotests": False,
                    }
                )
                result = root.BundleResult(
                    zip_path=web.OUTPUT_DIR / "dummy.zip",
                    license_id="lic_auto",
                    client_id="cli_auto",
                    release="2026.05.25-universal-mac",
                )

                def fake_register(**kwargs):
                    self.assertEqual("renew-lic-auto", kwargs["invite_batch_id"])
                    self.assertEqual("mac-15d-testhash", kwargs["activation_key"])
                    self.assertEqual(["mac"], kwargs["platforms"])
                    self.assertEqual(1, len(kwargs["codes"]))
                    return {"ok": True, "status": "registered", "imported": 1, "skipped": 0}

                original_register = web.register_invite_codes_with_license_server
                web.register_invite_codes_with_license_server = fake_register
                try:
                    generated = web.generate_invite_codes_csv(result, payload, ["mac"])
                finally:
                    web.register_invite_codes_with_license_server = original_register
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir

        self.assertIsNotNone(generated)
        assert generated is not None
        self.assertTrue(generated["registration"]["ok"])
        self.assertEqual("registered", generated["registration"]["status"])
        self.assertEqual(1, generated["registration"]["imported"])

    def test_target_platform_validation_rejects_empty_and_unknown_values(self) -> None:
        self.assertEqual(["windows", "mac"], web.validate_target_platforms(["windows", "mac", "windows"]))

        with self.assertRaises(HTTPException) as empty_cm:
            web.validate_target_platforms([])
        self.assertEqual(400, empty_cm.exception.status_code)
        self.assertIn("Выберите", str(empty_cm.exception.detail))

        with self.assertRaises(HTTPException) as unknown_cm:
            web.validate_target_platforms(["linux"])
        self.assertEqual(400, unknown_cm.exception.status_code)
        self.assertIn("linux", str(unknown_cm.exception.detail))

    def test_release_bundle_autotests_gate_download_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = type(
                "Args",
                (),
                {
                    "data_dir": str(Path(tmpdir) / "root-data"),
                    "output_dir": str(Path(tmpdir) / "releases"),
                    "client_email": "release-client@example.com",
                    "client_name": "Release Client",
                    "root_email": "owner@example.com",
                    "release": "2026.05.25-release-test",
                    "plan": "starter",
                    "license_kind": "activation",
                    "duration_days": None,
                    "valid_until": "",
                    "source_limit": None,
                    "version_min": "",
                    "version_max": "",
                    "update_channel": "stable",
                    "license_server_url": "http://license.example.local:8015",
                    "ocr_url": "http://x-files-ocr:8010",
                    "disable_menu": [],
                    "image_tar": [],
                    "backfront_digest": "",
                    "db_digest": "",
                    "ocr_digest": "",
                    "allow_repeat": False,
                    "signing_secret": "test-root-signing-secret",
                },
            )()

            result = root.bundle(args)
            report = web.run_bundle_autotests(result.zip_path, ["windows", "mac"], args.signing_secret, "online")

        self.assertTrue(report["ok"], report)
        check_names = {item["name"] for item in report["checks"]}
        self.assertIn("verify_bundle", check_names)
        self.assertIn("windows_delivery_files", check_names)
        self.assertIn("mac_delivery_files", check_names)
        self.assertIn("online_images_not_required", check_names)

    def test_release_build_job_runs_bundle_and_exposes_progress_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            old_bundle = root.bundle
            old_response = web.release_build_response
            old_thread = web.threading.Thread
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.release_jobs.clear()

                class ImmediateThread:
                    def __init__(self, target, args=(), daemon=False):
                        self.target = target
                        self.args = args
                        self.daemon = daemon

                    def start(self):
                        self.target(*self.args)

                def fake_bundle(args):
                    web.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                    zip_path = web.OUTPUT_DIR / "job.zip"
                    with zipfile.ZipFile(zip_path, "w") as bundle:
                        bundle.writestr("ok.txt", "ok")
                    return root.BundleResult(
                        zip_path=zip_path,
                        license_id="lic_job",
                        client_id="cli_job",
                        release=args.release,
                    )

                def fake_response(result, payload):
                    return {
                        "ok": True,
                        "zip_name": result.zip_path.name,
                        "license_id": result.license_id,
                        "message": "job ok",
                    }

                root.bundle = fake_bundle
                web.release_build_response = fake_response
                web.threading.Thread = ImmediateThread
                response = web.start_release_build_job(
                    web.ReleaseBuildRequest(**valid_payload(client_email="job@example.com").model_dump())
                )
                snapshot = web.get_release_build_job(response["job_id"])["job"]
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir
                root.bundle = old_bundle
                web.release_build_response = old_response
                web.threading.Thread = old_thread
                web.release_jobs.clear()

        self.assertTrue(response["ok"])
        self.assertEqual("completed", snapshot["status"])
        self.assertEqual(100, snapshot["percent"])
        self.assertEqual("job ok", snapshot["response"]["message"])

    def test_license_authority_diagnostics_reports_missing_and_configured_admin_password(self) -> None:
        old_password = web.LICENSE_SERVER_ADMIN_PASSWORD
        old_file = web.LICENSE_SERVER_ADMIN_PASSWORD_FILE
        try:
            web.LICENSE_SERVER_ADMIN_PASSWORD = ""
            web.LICENSE_SERVER_ADMIN_PASSWORD_FILE = ""
            missing = web.license_authority_diagnostics()
            web.LICENSE_SERVER_ADMIN_PASSWORD = "secret"
            configured = web.license_authority_diagnostics()
        finally:
            web.LICENSE_SERVER_ADMIN_PASSWORD = old_password
            web.LICENSE_SERVER_ADMIN_PASSWORD_FILE = old_file

        self.assertEqual("missing_admin_password", missing["status"])
        self.assertFalse(missing["admin_password_configured"])
        self.assertEqual("ready", configured["status"])
        self.assertTrue(configured["admin_password_configured"])

    def test_license_authority_admin_password_can_be_read_from_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_path = Path(tmpdir) / "license-server-admin-password"
            secret_path.write_text("secret-from-file\n", encoding="utf-8")

            self.assertEqual("secret-from-file", web.read_secret_file(str(secret_path)))

    def test_release_bundle_autotests_require_offline_image_tars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = type(
                "Args",
                (),
                {
                    "data_dir": str(Path(tmpdir) / "root-data"),
                    "output_dir": str(Path(tmpdir) / "releases"),
                    "client_email": "offline-client@example.com",
                    "client_name": "Offline Client",
                    "root_email": "owner@example.com",
                    "release": "2026.05.26-offline-test",
                    "plan": "starter",
                    "license_kind": "activation",
                    "duration_days": None,
                    "valid_until": "",
                    "source_limit": None,
                    "version_min": "",
                    "version_max": "",
                    "update_channel": "stable",
                    "license_server_url": "http://license.example.local:8015",
                    "ocr_url": "http://x-files-ocr:8010",
                    "disable_menu": [],
                    "image_tar": [],
                    "backfront_digest": "",
                    "db_digest": "",
                    "ocr_digest": "",
                    "allow_repeat": False,
                    "signing_secret": "test-root-signing-secret",
                },
            )()

            result = root.bundle(args)
            missing_report = web.run_bundle_autotests(result.zip_path, ["mac"], args.signing_secret, "offline")

            image_dir = Path(tmpdir) / "images"
            image_dir.mkdir()
            image_tars = []
            for rel_path in sorted(web.REQUIRED_OFFLINE_IMAGE_TARS):
                image_path = image_dir / Path(rel_path).name
                image_path.write_bytes(b"fake-tar")
                image_tars.append(str(image_path))
            args.image_tar = image_tars
            result_with_images = root.bundle(args)
            old_min_size = web.MIN_OFFLINE_ZIP_BYTES
            try:
                web.MIN_OFFLINE_ZIP_BYTES = 1
                ready_report = web.run_bundle_autotests(
                    result_with_images.zip_path,
                    ["mac"],
                    args.signing_secret,
                    "offline",
                )
            finally:
                web.MIN_OFFLINE_ZIP_BYTES = old_min_size

        self.assertFalse(missing_report["ok"], missing_report)
        missing_checks = {item["name"]: item for item in missing_report["checks"]}
        self.assertFalse(missing_checks["offline_images_required"]["ok"])
        self.assertTrue(ready_report["ok"], ready_report)
        ready_checks = {item["name"]: item for item in ready_report["checks"]}
        self.assertTrue(ready_checks["offline_images_required"]["ok"])

    def test_client_bundle_uses_current_split_runtime_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = type(
                "Args",
                (),
                {
                    "data_dir": str(Path(tmpdir) / "root-data"),
                    "output_dir": str(Path(tmpdir) / "releases"),
                    "client_email": "split-runtime@example.com",
                    "client_name": "Split Runtime",
                    "root_email": "owner@example.com",
                    "release": "2026.05.26-split-test",
                    "plan": "starter",
                    "license_kind": "activation",
                    "duration_days": None,
                    "valid_until": "",
                    "source_limit": None,
                    "version_min": "",
                    "version_max": "",
                    "update_channel": "stable",
                    "license_server_url": "http://license.example.local:8015",
                    "ocr_url": "http://x-files-ocr:8010",
                    "disable_menu": [],
                    "image_tar": [],
                    "backfront_digest": "",
                    "db_digest": "",
                    "ocr_digest": "",
                    "allow_repeat": False,
                    "signing_secret": "test-root-signing-secret",
                },
            )()

            result = root.bundle(args)
            with zipfile.ZipFile(result.zip_path, "r") as bundle:
                compose = bundle.read("docker-compose.client.yml").decode("utf-8")
                env_example = bundle.read(".env.example").decode("utf-8")
                manifest = root.verify_signed_doc(
                    json.loads(bundle.read("release-manifest.json").decode("utf-8")),
                    args.signing_secret,
                    "manifest",
                )
                readme = bundle.read("readme-install.md").decode("utf-8")

        for service in (
            "x-files-rabbitmq",
            "x-files-redis",
            "x-files-backfront-new-back",
            "x-files-backfront-new-front",
            "celery_worker_telegram",
            "celery_worker_preprocess",
            "celery_worker_llm",
            "celery_worker_leads",
            "celery_worker_export",
        ):
            self.assertIn(service, compose)
            self.assertIn(service, manifest["images"])
        self.assertNotIn("x-files-client-backfront", compose)
        self.assertIn("HOST_FRONTEND_PORT=8008", env_example)
        self.assertIn("HOST_BACKEND_PORT=8009", env_example)
        self.assertIn("CELERY_BROKER_URL=amqp://gramlead:gramlead@x-files-rabbitmq:5672//", env_example)
        self.assertIn("CELERY_RESULT_BACKEND=redis://x-files-redis:6379/1", env_example)
        self.assertNotIn("PAYME_SOURCE_PATH", env_example)
        self.assertIn("http://127.0.0.1:8008/", readme)

    def test_invite_required_create_hides_zip_when_registration_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            old_register = web.register_invite_codes_with_license_server
            old_sync = web.sync_registry_to_postgres
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.sync_registry_to_postgres = lambda: root.ensure_registry(web.DATA_DIR)
                web.register_invite_codes_with_license_server = lambda **kwargs: {
                    "ok": False,
                    "status": "failed",
                    "message": "license-server offline",
                }

                response = web.create_license(
                    valid_payload(
                        client_email="invite-required@example.com",
                        activation_key="invite-required",
                        invite_batch_id="invite-required-batch",
                        invite_code_required=True,
                        invite_code_count=1,
                        target_platforms=["windows"],
                        allow_repeat=True,
                    )
                )
                registry = root.ensure_registry(web.DATA_DIR)
                license_row = registry["licenses"][response["license_id"]]
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir
                web.register_invite_codes_with_license_server = old_register
                web.sync_registry_to_postgres = old_sync

        self.assertFalse(response["ok"])
        self.assertEqual("", response["download_url"])
        self.assertIn("ссылка скрыта", response["message"])
        self.assertEqual("failed", license_row["invite_registration_status"])
        self.assertFalse(license_row["invite_registration_ok"])

    def test_retry_invite_code_registration_reads_csv_and_updates_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            old_register = web.register_invite_codes_with_license_server
            old_sync = web.sync_registry_to_postgres
            calls = []
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.sync_registry_to_postgres = lambda: root.ensure_registry(web.DATA_DIR)
                payload = web.ReleaseBuildRequest(
                    **{
                        **valid_payload(
                            client_email="retry@example.com",
                            activation_key="retry-key",
                            invite_batch_id="retry-batch",
                            invite_code_required=True,
                            invite_code_count=1,
                            target_platforms=["mac"],
                            allow_repeat=True,
                        ).model_dump(),
                        "run_autotests": False,
                    }
                )
                result = root.BundleResult(
                    zip_path=web.OUTPUT_DIR / "dummy.zip",
                    license_id="lic_retry",
                    client_id="cli_retry",
                    release="2026.05.26-retry",
                )
                web.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(result.zip_path, "w") as bundle:
                    bundle.writestr("license/INVITE-CODE.md", "placeholder")
                web.register_invite_codes_with_license_server = lambda **kwargs: {
                    "ok": False,
                    "status": "failed",
                    "message": "first fail",
                }
                generated = web.generate_invite_codes_csv(result, payload, ["mac"])
                assert generated is not None

                def fake_register(**kwargs):
                    calls.append(kwargs)
                    return {"ok": True, "status": "registered", "imported": len(kwargs["codes"])}

                web.register_invite_codes_with_license_server = fake_register
                response = web.retry_invite_code_registration("lic_retry")
                registry = root.ensure_registry(web.DATA_DIR)
                license_row = registry["licenses"]["lic_retry"]
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir
                web.register_invite_codes_with_license_server = old_register
                web.sync_registry_to_postgres = old_sync

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(calls))
        self.assertEqual("retry-batch", calls[0]["invite_batch_id"])
        self.assertEqual(["mac"], calls[0]["platforms"])
        self.assertEqual("registered", license_row["invite_registration_status"])
        self.assertTrue(license_row["invite_registration_ok"])

    def test_bundle_registry_keeps_activation_key_for_universal_release(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            args = type(
                "Args",
                (),
                {
                    "data_dir": str(Path(tmpdir) / "root-data"),
                    "output_dir": str(Path(tmpdir) / "releases"),
                    "client_email": "win-15d-testhash@universal.xfiles.local",
                    "client_name": "Universal Windows 15d",
                    "activation_key": "win-15d-testhash",
                    "invite_batch_id": "universal-15d-20260525-100k",
                    "invite_code_required": True,
                    "root_email": "owner@example.com",
                    "release": "2026.05.25-universal-win",
                    "plan": "enterprise",
                    "license_kind": "activation",
                    "duration_days": 15,
                    "activation_duration_days": 15,
                    "valid_until": "",
                    "source_limit": None,
                    "version_min": "",
                    "version_max": "",
                    "update_channel": "stable",
                    "license_server_url": "http://license.example.local:8015",
                    "ocr_url": "http://x-files-ocr:8010",
                    "disable_menu": [],
                    "image_tar": [],
                    "backfront_digest": "",
                    "db_digest": "",
                    "ocr_digest": "",
                    "allow_repeat": True,
                    "signing_secret": "test-root-signing-secret",
                },
            )()

            result = root.bundle(args)
            registry = root.ensure_registry(Path(tmpdir) / "root-data")
            stored = registry["licenses"][result.license_id]
            client = registry["clients"][root.client_key(args.client_email)]
            license_doc = root.read_license_from_bundle(result.zip_path, args.signing_secret)

        self.assertEqual("win-15d-testhash", stored["activation_key"])
        self.assertEqual("win-15d-testhash", client["activation_key"])
        self.assertEqual(15, license_doc["payload"]["duration_days"])
        self.assertEqual(15, license_doc["payload"]["activation_duration_days"])
        self.assertEqual("universal-15d-20260525-100k", license_doc["payload"]["invite_batch_id"])
        self.assertTrue(license_doc["payload"]["invite_code_required"])

    def test_make_namespace_rejects_invalid_valid_until(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.make_namespace(valid_payload(valid_until="not-a-date"))

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("valid-until", str(cm.exception.detail))

    def test_make_namespace_rejects_past_valid_until(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.make_namespace(valid_payload(valid_until="2000-01-01"))

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("будущем", str(cm.exception.detail))

    def test_renew_endpoint_rejects_non_renewal_license_kind_before_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {"license_id": "lic_old", "client_email": "client@example.com"}
                root.save_registry(web.DATA_DIR, registry)

                with self.assertRaises(HTTPException) as cm:
                    web.renew_license("lic_old", valid_payload(license_kind="activation"))
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("license_kind=renewal", str(cm.exception.detail))

    def test_create_endpoint_preserves_validation_http_status(self) -> None:
        with self.assertRaises(HTTPException) as cm:
            web.create_license(valid_payload(client_email=""))

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("Email клиента", str(cm.exception.detail))

    def test_renew_endpoint_preserves_validation_http_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {"license_id": "lic_old", "client_email": "client@example.com"}
                root.save_registry(web.DATA_DIR, registry)

                with self.assertRaises(HTTPException) as cm:
                    web.renew_license("lic_old", valid_payload(license_kind="renewal", source_limit=-1))
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir

        self.assertEqual(400, cm.exception.status_code)
        self.assertIn("Лимит источников", str(cm.exception.detail))

    def test_renew_endpoint_extends_active_license_on_license_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            old_extender = web.extend_license_activation_with_license_server
            old_sync = web.sync_registry_to_postgres
            calls = []
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.sync_registry_to_postgres = lambda: None
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "starter",
                    "disabled_menus": ["contacts"],
                }
                root.save_registry(web.DATA_DIR, registry)

                def fake_extender(**kwargs):
                    calls.append(kwargs)
                    return {"ok": True, "status": "extended", "expires_at": kwargs["expires_at"]}

                web.extend_license_activation_with_license_server = fake_extender
                response = web.renew_license(
                    "lic_old",
                    valid_payload(
                        license_kind="renewal",
                        plan="starter",
                        valid_until="2026-07-15",
                        allow_repeat=True,
                    ),
                )
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir
                web.extend_license_activation_with_license_server = old_extender
                web.sync_registry_to_postgres = old_sync

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(calls))
        self.assertEqual("lic_old", calls[0]["license_id"])
        self.assertEqual("2026-07-15T23:59:59+00:00", calls[0]["expires_at"])
        self.assertEqual("extended", response["license_server_extension"]["status"])

    def test_renew_endpoint_hides_zip_when_license_server_extension_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_output_dir = web.OUTPUT_DIR
            old_extender = web.extend_license_activation_with_license_server
            old_sync = web.sync_registry_to_postgres
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.OUTPUT_DIR = Path(tmpdir) / "releases"
                web.sync_registry_to_postgres = lambda: None
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "starter",
                    "disabled_menus": [],
                }
                root.save_registry(web.DATA_DIR, registry)
                web.extend_license_activation_with_license_server = lambda **kwargs: {
                    "ok": False,
                    "status": "failed",
                    "message": "license is not activated",
                }

                response = web.renew_license(
                    "lic_old",
                    valid_payload(
                        license_kind="renewal",
                        plan="starter",
                        valid_until="2026-07-15",
                        allow_repeat=True,
                    ),
                )
                registry = root.ensure_registry(web.DATA_DIR)
            finally:
                web.DATA_DIR = old_data_dir
                web.OUTPUT_DIR = old_output_dir
                web.extend_license_activation_with_license_server = old_extender
                web.sync_registry_to_postgres = old_sync

        self.assertFalse(response["ok"])
        self.assertEqual("", response["download_url"])
        self.assertIn("не подтвердил продление", response["message"])
        self.assertEqual("failed", registry["licenses"]["lic_old"]["remote_extend_status"])

    def test_revoke_endpoint_calls_license_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_revoker = getattr(web, "revoke_license_activation_with_license_server", None)
            old_sync = web.sync_registry_to_postgres
            calls = []
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.sync_registry_to_postgres = lambda: None
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "starter",
                    "status": "issued",
                }
                root.save_registry(web.DATA_DIR, registry)

                def fake_revoker(**kwargs):
                    calls.append(kwargs)
                    return {"ok": True, "status": "revoked", "license_id": kwargs["license_id"]}

                web.revoke_license_activation_with_license_server = fake_revoker
                response = web.revoke_license("lic_old", web.RevokeRequest(reason="owner test revoke"))
            finally:
                web.DATA_DIR = old_data_dir
                web.sync_registry_to_postgres = old_sync
                if old_revoker is not None:
                    web.revoke_license_activation_with_license_server = old_revoker

        self.assertTrue(response["ok"])
        self.assertEqual("revoked", response["status"])
        self.assertEqual(1, len(calls))
        self.assertEqual("lic_old", calls[0]["license_id"])
        self.assertEqual("owner test revoke", calls[0]["reason"])
        self.assertEqual("revoked", response["license_server_revocation"]["status"])

    def test_revoke_endpoint_keeps_local_license_when_license_server_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            old_data_dir = web.DATA_DIR
            old_revoker = getattr(web, "revoke_license_activation_with_license_server", None)
            old_sync = web.sync_registry_to_postgres
            try:
                web.DATA_DIR = Path(tmpdir) / "root-data"
                web.sync_registry_to_postgres = lambda: None
                registry = root.ensure_registry(web.DATA_DIR)
                registry["licenses"]["lic_old"] = {
                    "license_id": "lic_old",
                    "client_email": "client@example.com",
                    "plan": "starter",
                    "status": "issued",
                }
                root.save_registry(web.DATA_DIR, registry)
                web.revoke_license_activation_with_license_server = lambda **kwargs: {
                    "ok": False,
                    "status": "failed",
                    "message": "license authority offline",
                }

                with self.assertRaises(HTTPException) as cm:
                    web.revoke_license("lic_old", web.RevokeRequest(reason="owner test revoke"))
                registry = root.ensure_registry(web.DATA_DIR)
            finally:
                web.DATA_DIR = old_data_dir
                web.sync_registry_to_postgres = old_sync
                if old_revoker is not None:
                    web.revoke_license_activation_with_license_server = old_revoker

        self.assertEqual(502, cm.exception.status_code)
        self.assertEqual("issued", registry["licenses"]["lic_old"]["status"])

    def test_bulk_release_request_defaults_match_owner_paths(self) -> None:
        payload = web.BulkReleaseRequest()

        self.assertEqual(["mac", "windows"], payload.platforms)
        self.assertEqual("2026-07-01", payload.valid_until)
        self.assertEqual(30, payload.count)
        self.assertEqual("/Volumes/t5/_gramlead_lic_demo/mac", payload.output_dirs["mac"])
        self.assertEqual("/Volumes/t5/_gramlead_lic_demo/win", payload.output_dirs["windows"])


if __name__ == "__main__":
    unittest.main()
