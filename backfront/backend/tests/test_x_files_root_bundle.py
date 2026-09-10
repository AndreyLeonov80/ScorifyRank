import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from x_files_license.core import apply_license, build_activation_receipt, verify_signed_document
from x_files_root import root


SECRET = "test-root-signing-secret"


def make_bundle_args(
    base: Path,
    *,
    plan: str = "free-demo-first-touch-vip",
    allow_repeat: bool = False,
    license_kind: str = "activation",
    root_email: str = "aidialog@mail.ru",
):
    return SimpleNamespace(
        data_dir=str(base / "root-data"),
        output_dir=str(base / "releases"),
        client_email="client@example.com",
        client_name="Client Example",
        root_email=root_email,
        release="2026.05.08-test",
        plan=plan,
        license_kind=license_kind,
        duration_days=None,
        source_limit=None,
        version_min="2026.05.01",
        version_max="2026.12.31",
        update_channel="stable",
        license_server_url="http://license.example.local:8015",
        ocr_url="http://x-files-ocr:8010",
        disable_menu=[],
        image_tar=[],
        backfront_digest="sha256:" + "a" * 64,
        db_digest="sha256:" + "b" * 64,
        ocr_digest="sha256:" + "c" * 64,
        allow_repeat=allow_repeat,
        signing_secret=SECRET,
    )


class XFilesRootBundleTest(unittest.TestCase):
    def test_vip_bundle_contains_manifest_license_scripts_and_optional_ocr_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir))

            result = root.bundle(args)
            root.verify_bundle(SimpleNamespace(zip_path=str(result.zip_path), signing_secret=SECRET))

            with zipfile.ZipFile(result.zip_path) as archive:
                names = set(archive.namelist())
                self.assertIn("docker-compose.client.yml", names)
                self.assertIn("docker-compose.windows.yml", names)
                self.assertIn("docker-compose.mac.yml", names)
                self.assertIn("readme-install.md", names)
                self.assertIn("RUNTIME-SERVICES.md", names)
                self.assertIn(".env.example", names)
                self.assertIn(".env.windows.example", names)
                self.assertIn(".env.mac.example", names)
                self.assertIn("VERIFY-INTEGRITY.md", names)
                self.assertIn("DEPENDENCIES.md", names)
                self.assertIn("INITIAL-SETUP.md", names)
                self.assertIn("license/invite-license.json", names)
                self.assertIn("license/INVITE-CODE.md", names)
                self.assertIn("release-manifest.json", names)
                self.assertIn("integrity-manifest.json", names)
                self.assertIn("scripts/start-x-files.sh", names)
                self.assertIn("scripts/start-x-files.ps1", names)
                self.assertIn("scripts/verify-integrity.sh", names)
                self.assertIn("scripts/verify-integrity.ps1", names)
                self.assertIn("scripts/verify-images.sh", names)
                self.assertIn("scripts/verify-images.ps1", names)
                self.assertIn("scripts/sign-images.sh", names)
                self.assertIn("scripts/sign-images.ps1", names)
                self.assertIn("images/README-images.md", names)

                compose = archive.read("docker-compose.client.yml").decode("utf-8")
                windows_compose = archive.read("docker-compose.windows.yml").decode("utf-8")
                mac_compose = archive.read("docker-compose.mac.yml").decode("utf-8")
                windows_env = archive.read(".env.windows.example").decode("utf-8")
                mac_env = archive.read(".env.mac.example").decode("utf-8")
                invite_md = archive.read("license/INVITE-CODE.md").decode("utf-8")
                setup_md = archive.read("INITIAL-SETUP.md").decode("utf-8")
                self.assertIn("Invite-code", invite_md)
                self.assertIn("Начальная настройка", setup_md)
                self.assertIn("x-files-backfront-new-front", compose)
                self.assertIn("x-files-backfront-new-back", compose)
                self.assertIn("x-files-rabbitmq", compose)
                self.assertIn("x-files-redis", compose)
                self.assertIn("celery_worker_telegram", compose)
                self.assertIn("x-files-client-db", compose)
                self.assertNotIn("x-files-client-backfront", compose)
                self.assertNotIn("x-files-root-web", compose)
                self.assertNotIn("x-files-license-server", compose)
                self.assertNotIn("x-files-root-postgres", compose)
                self.assertIn("x-files-ocr", compose)
                self.assertIn('profiles: ["ocr"]', compose)
                self.assertIn("Linux containers mode", windows_compose)
                self.assertIn("Apple Silicon", mac_compose)
                self.assertIn("XFILES_FRONTEND_IMAGE=x-files-backfront-new-front:2026.05.08-test", windows_env)
                self.assertIn("XFILES_BACKEND_IMAGE=x-files-backfront-new-back:2026.05.08-test", windows_env)
                self.assertIn("XFILES_FRONTEND_IMAGE=x-files-backfront-new-front:2026.05.08-test", mac_env)
                self.assertIn("XFILES_BACKEND_IMAGE=x-files-backfront-new-back:2026.05.08-test", mac_env)

                shell_start = archive.read("scripts/start-x-files.sh").decode("utf-8")
                powershell_start = archive.read("scripts/start-x-files.ps1").decode("utf-8")
                shell_update = archive.read("scripts/update-x-files.sh").decode("utf-8")
                powershell_update = archive.read("scripts/update-x-files.ps1").decode("utf-8")
                shell_load_images = archive.read("scripts/load-images.sh").decode("utf-8")
                powershell_load_images = archive.read("scripts/load-images.ps1").decode("utf-8")
                shell_verify_images = archive.read("scripts/verify-images.sh").decode("utf-8")
                powershell_verify_images = archive.read("scripts/verify-images.ps1").decode("utf-8")
                shell_sign_images = archive.read("scripts/sign-images.sh").decode("utf-8")
                powershell_sign_images = archive.read("scripts/sign-images.ps1").decode("utf-8")
                self.assertIn("sh scripts/verify-integrity.sh", shell_start)
                self.assertIn("sh scripts/verify-integrity.sh", shell_update)
                self.assertIn("sh scripts/verify-images.sh", shell_start)
                self.assertIn("sh scripts/verify-images.sh", shell_update)
                self.assertLess(shell_start.index("cp .env.example .env"), shell_start.index("sh scripts/verify-images.sh"))
                self.assertIn(". ./.env", shell_start)
                self.assertIn("/api/health", shell_start)
                self.assertIn("X-Files is ready", shell_start)
                self.assertIn(".\\scripts\\verify-integrity.ps1", powershell_start)
                self.assertIn(".\\scripts\\verify-integrity.ps1", powershell_update)
                self.assertIn(".\\scripts\\verify-images.ps1", powershell_start)
                self.assertIn(".\\scripts\\verify-images.ps1", powershell_update)
                self.assertLess(
                    powershell_start.index('Copy-Item ".env.example" ".env"'),
                    powershell_start.index(".\\scripts\\verify-images.ps1"),
                )
                self.assertIn('Get-Content ".env"', powershell_start)
                self.assertIn("Invoke-WebRequest", powershell_start)
                self.assertIn("/api/health", powershell_start)
                self.assertIn("find_loaded_tag_by_repo", shell_load_images)
                self.assertIn("Find-LoadedTagByRepo", powershell_load_images)
                self.assertIn("Test-DockerImage", powershell_load_images)
                self.assertIn('${Repo}:*', powershell_load_images)
                self.assertNotIn('$Repo:*', powershell_load_images)
                self.assertIn("--profile ocr up -d", shell_start)
                self.assertIn("--profile ocr up -d", powershell_start)
                self.assertIn("Docker image digest mismatch", shell_verify_images)
                self.assertIn("sha256:" + "a" * 64, shell_verify_images)
                self.assertIn("sha256:" + "b" * 64, powershell_verify_images)
                self.assertIn("cosign sign", shell_sign_images)
                self.assertIn("COSIGN_KEY", shell_sign_images)
                self.assertIn("x-files-backfront-new-front", shell_sign_images)
                self.assertIn("x-files-backfront-new-back", shell_sign_images)
                self.assertIn("sha256:" + "a" * 64, shell_sign_images)
                self.assertIn("cosign sign", powershell_sign_images)
                self.assertIn("COSIGN_KEY", powershell_sign_images)
                self.assertIn("x-files-backfront-new-front", powershell_sign_images)
                self.assertIn("x-files-backfront-new-back", powershell_sign_images)
                self.assertIn("sha256:" + "b" * 64, powershell_sign_images)

                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))
                manifest_doc = json.loads(archive.read("release-manifest.json").decode("utf-8"))
                integrity_doc = json.loads(archive.read("integrity-manifest.json").decode("utf-8"))
                verify_signed_document(license_doc, SECRET, expected_schema="x-files-license/v1")
                license_payload = license_doc["payload"]
                manifest_payload = manifest_doc["payload"]
                integrity_payload = integrity_doc["payload"]
                self.assertEqual(license_payload["plan"], "free-demo-first-touch-vip")
                self.assertFalse(license_payload["offline_allowed"])
                self.assertEqual(license_payload["max_activations"], 1)
                self.assertTrue(license_payload["features"]["ocr"])
                self.assertEqual(license_payload["version_min"], "2026.05.01")
                self.assertEqual(license_payload["version_max"], "2026.12.31")
                self.assertEqual(license_payload["update_channel"], "stable")
                self.assertEqual(manifest_payload["images"]["x-files-backfront-new-front"], "x-files-backfront-new-front:2026.05.08-test")
                self.assertEqual(manifest_payload["images"]["x-files-backfront-new-back"], "x-files-backfront-new-back:2026.05.08-test")
                self.assertEqual(manifest_payload["images"]["x-files-client-db"], "x-files-client-db:2026.05.08-test")
                self.assertEqual(manifest_payload["images"]["x-files-ocr"], "x-files-ocr:2026.05.08-test")
                self.assertEqual(manifest_payload["image_digests"]["x-files-backfront-new-front"], "sha256:" + "a" * 64)
                self.assertEqual(manifest_payload["image_digests"]["x-files-backfront-new-back"], "sha256:" + "a" * 64)
                self.assertEqual(
                    manifest_payload["image_refs"]["x-files-backfront-new-back"],
                    "x-files-backfront-new-back:2026.05.08-test@sha256:" + "a" * 64,
                )
                self.assertGreater(len(manifest_payload["files"]), 10)
                self.assertEqual(integrity_payload["schema"], "x-files-integrity-manifest/v1")
                critical = {item["path"]: item for item in integrity_payload["critical_files"]}
                for rel_path in root.CRITICAL_BUNDLE_PATHS:
                    self.assertIn(rel_path, critical)
                    actual = hashlib.sha256(archive.read(rel_path)).hexdigest()
                    self.assertEqual(critical[rel_path]["sha256"], actual)
                    self.assertGreaterEqual(critical[rel_path]["bytes"], 0)

                dependencies = archive.read("DEPENDENCIES.md").decode("utf-8")
                verify_doc = archive.read("VERIFY-INTEGRITY.md").decode("utf-8")
                self.assertIn("requirements.txt", dependencies)
                self.assertIn("verify-bundle", verify_doc)
                self.assertIn("verify-images.sh", verify_doc)
                self.assertIn("sign-images.sh", verify_doc)

    def test_release_zip_audit_script_accepts_generated_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir))
            result = root.bundle(args)

            audit = subprocess.run(
                [
                    sys.executable,
                    "scripts/audit_release_zip_contract.py",
                    "--zip",
                    str(result.zip_path),
                    "--signing-secret",
                    SECRET,
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(audit.returncode, 0, audit.stderr + audit.stdout)
            payload = json.loads(audit.stdout)
            self.assertEqual(payload["status"], "ok")
            self.assertIn("manifest-covers-every-file", payload["checks"])
            self.assertIn("compose-service-x-files-backfront-new-front", payload["checks"])
            self.assertIn("compose-service-x-files-backfront-new-back", payload["checks"])
            self.assertIn("windows-compose-relative-volume-postgres", payload["checks"])
            self.assertIn("windows-compose-relative-volume-tg-session", payload["checks"])
            self.assertIn("bundle-no-developer-absolute-host-paths", payload["checks"])
            self.assertIn("windows-scripts-no-python-runtime-requirement", payload["checks"])
            self.assertIn("powershell-start-uses-bundle-relative-root", payload["checks"])
            self.assertIn("powershell-start-uses-docker-compose-only", payload["checks"])
            self.assertIn("shell-backup-creates-transferable-archive", payload["checks"])
            self.assertIn("powershell-restore-transferable-archive", payload["checks"])

    def test_release_zip_runtime_smoke_script_covers_compose_dashboard_and_persistence(self):
        script = (Path(__file__).resolve().parents[1] / "scripts" / "smoke_release_zip_runtime.py").read_text(
            encoding="utf-8"
        )

        for marker in [
            "docker",
            "compose",
            "docker-compose.client.yml",
            "--env-file",
            "x-files-client-db",
            "x-files-backfront-new-front",
            "x-files-backfront-new-back",
            "x-files-ocr",
            "--include-ocr",
            "docker",
            "load",
            "/api/payme/dashboard/summary",
            "assert_required_frontend_pages",
            "/index.html",
            "/import.html",
            "/grid.html",
            "/dashboard.html",
            "/settings.html",
            "xfiles_release_smoke",
            "write_persistent_file_markers",
            "assert_persistent_file_markers",
            "tg_export_session.smoke",
            "license-state.smoke.json",
            "settings.smoke.json",
            "persistent_files_survived_restart",
            "data_survived_restart",
            "data_survived_backfront_update",
            "XFILES_DOCKER_COMMAND_TIMEOUT_SEC",
            "XFILES_RELEASE_START_TIMEOUT_SEC",
            "preflight_docker",
            "--skip-preflight",
            '"docker", "version"',
            '"docker", "compose", "version"',
            '"docker", "ps"',
            '"PAYME_STARTUP_TELEGRAM_BOOTSTRAP": "0"',
            "HOST_FRONTEND_PORT",
            "HOST_BACKEND_PORT",
        ]:
            self.assertIn(marker, script)

    def test_runtime_smoke_env_overrides_replace_existing_image_values(self):
        script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_release_zip_runtime.py"
        spec = importlib.util.spec_from_file_location("smoke_release_zip_runtime", script_path)
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as tmpdir:
            stage = Path(tmpdir)
            (stage / ".env.example").write_text(
                "\n".join(
                    [
                        "XFILES_FRONTEND_IMAGE=x-files-backfront-new-front:bundle-release",
                        "XFILES_BACKEND_IMAGE=x-files-backfront-new-back:bundle-release",
                        "XFILES_DB_IMAGE=x-files-client-db:bundle-release",
                        "XFILES_OCR_IMAGE=x-files-ocr:bundle-release",
                        "HOST_FRONTEND_BIND=127.0.0.1",
                        "HOST_FRONTEND_PORT=8008",
                        "HOST_BACKEND_PORT=8009",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            module.append_smoke_env(
                stage,
                SimpleNamespace(
                    backfront_image="x-files-backfront:local-smoke",
                    frontend_image="x-files-backfront-new-front:local-smoke",
                    backend_image="x-files-backfront-new-back:local-smoke",
                    db_image="x-files-client-db:local-smoke",
                    ocr_image="",
                ),
                39001,
                39002,
                "abc",
            )

            env_lines = [
                line
                for line in (stage / ".env").read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#")
            ]
            self.assertEqual(env_lines.count("XFILES_FRONTEND_IMAGE=x-files-backfront-new-front:local-smoke"), 1)
            self.assertEqual(env_lines.count("XFILES_BACKEND_IMAGE=x-files-backfront-new-back:local-smoke"), 1)
            self.assertEqual(env_lines.count("XFILES_DB_IMAGE=x-files-client-db:local-smoke"), 1)
            self.assertNotIn("XFILES_FRONTEND_IMAGE=x-files-backfront-new-front:bundle-release", env_lines)
            self.assertNotIn("XFILES_BACKEND_IMAGE=x-files-backfront-new-back:bundle-release", env_lines)
            self.assertNotIn("XFILES_DB_IMAGE=x-files-client-db:bundle-release", env_lines)
            self.assertIn("XFILES_OCR_IMAGE=x-files-ocr:bundle-release", env_lines)
            self.assertIn("HOST_FRONTEND_PORT=39001", env_lines)
            self.assertTrue(any(line.startswith("HOST_BACKEND_PORT=") for line in env_lines))

    def test_load_images_script_tags_loaded_dev_images_to_release_image_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            result = root.bundle(make_bundle_args(base))
            extract_dir = base / "extract"
            fake_bin = base / "fake-bin"
            docker_state = base / "docker-images.txt"
            fake_bin.mkdir()

            with zipfile.ZipFile(result.zip_path) as archive:
                archive.extractall(extract_dir)

            for image_name in (
                "x-files-backfront-new-front.tar",
                "x-files-backfront-new-back.tar",
                "x-files-client-db.tar",
            ):
                (extract_dir / "images" / image_name).write_text("fake image tar", encoding="utf-8")

            fake_docker = fake_bin / "docker"
            fake_docker.write_text(
                """#!/usr/bin/env sh
set -eu
state="${FAKE_DOCKER_STATE}"
cmd="${1:-}"
shift || true
case "$cmd" in
  load)
    image="${2:-}"
    case "$image" in
      *x-files-backfront-new-front*) echo "gramlead-main-new-optimize-x-files-backfront-new-front:latest" >> "$state" ;;
      *x-files-backfront-new-back*) echo "gramlead-main-new-optimize-x-files-backfront-new-back:latest" >> "$state" ;;
      *x-files-client-db*) echo "x-files-client-db:latest" >> "$state" ;;
    esac
    ;;
  image)
    sub="${1:-}"
    target="${2:-}"
    if [ "$sub" = "inspect" ] && grep -Fx "$target" "$state" >/dev/null 2>&1; then
      exit 0
    fi
    exit 1
    ;;
  tag)
    source="${1:-}"
    target="${2:-}"
    grep -Fx "$source" "$state" >/dev/null 2>&1
    echo "$target" >> "$state"
    ;;
  *)
    echo "unexpected docker command: $cmd $*" >&2
    exit 2
    ;;
esac
""",
                encoding="utf-8",
            )
            fake_docker.chmod(0o755)
            docker_state.write_text("", encoding="utf-8")

            env = os.environ.copy()
            env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
            env["FAKE_DOCKER_STATE"] = str(docker_state)

            run = subprocess.run(
                ["sh", "scripts/load-images.sh"],
                cwd=extract_dir,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
            loaded = set(docker_state.read_text(encoding="utf-8").splitlines())
            self.assertIn("x-files-backfront-new-front:2026.05.08-test", loaded)
            self.assertIn("x-files-backfront-new-back:2026.05.08-test", loaded)
            self.assertIn("x-files-client-db:2026.05.08-test", loaded)

    def test_client_bundle_does_not_include_owner_runtime_data_or_prefilled_customer_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            owner_runtime = base / "x-files-data"
            for rel, content in {
                "tg-session/tg_export_session.session": "owner telegram session",
                "db/paindb2.duckdb": "owner duckdb",
                "out/secret.jsonl": '{"secret":"owner"}',
                "state/settings.json": '{"telegram_api_id":"owner-api"}',
                "state/openrouter.json": '{"api_key":"owner-openrouter"}',
            }.items():
                path = owner_runtime / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            result = root.bundle(make_bundle_args(base))

            with zipfile.ZipFile(result.zip_path) as archive:
                names = set(archive.namelist())
                all_text = "\n".join(
                    archive.read(name).decode("utf-8", errors="ignore")
                    for name in names
                    if name.endswith((".md", ".json", ".env", ".yml", ".sh", ".ps1"))
                )

            forbidden_archive_paths = (
                "x-files-data/tg-session/tg_export_session.session",
                "x-files-data/db/paindb2.duckdb",
                "x-files-data/out/secret.jsonl",
                "x-files-data/state/settings.json",
                "x-files-data/state/openrouter.json",
            )
            for forbidden in forbidden_archive_paths:
                self.assertNotIn(forbidden, names)

            for secret in ("owner telegram session", "owner duckdb", "owner-openrouter", "owner-api"):
                self.assertNotIn(secret, all_text)

    def test_client_bundle_contains_only_clean_x_files_data_boundary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = root.bundle(make_bundle_args(Path(tmpdir)))

            with zipfile.ZipFile(result.zip_path) as archive:
                data_files = sorted(
                    name
                    for name in archive.namelist()
                    if name.startswith("x-files-data/") and not name.endswith("/")
                )

            self.assertEqual([], data_files)

    def test_client_db_backup_restore_and_update_scripts_preserve_data_boundary(self):
        shell_backup = root.backup_shell_script()
        shell_restore = root.restore_shell_script()
        shell_update = root.update_shell_script(include_ocr=True)
        powershell_backup = root.backup_powershell_script()
        powershell_restore = root.restore_powershell_script()
        powershell_update = root.update_powershell_script(include_ocr=True)

        for script in (shell_backup, powershell_backup):
            self.assertIn("x-files-data", script)
            self.assertIn("license", script)
            self.assertIn(".env", script)
            self.assertIn("docker-compose.client.yml", script)
            self.assertIn("release-manifest.json", script)
            self.assertIn("integrity-manifest.json", script)

        for script in (shell_restore, powershell_restore):
            self.assertIn("x-files-data", script)
            self.assertIn("docker-compose.client.yml", script)
            self.assertIn(".env", script)

        for script in (shell_backup, powershell_backup):
            self.assertIn("docker compose", script)
            self.assertIn("stop", script)
            self.assertIn("backups/x-files-data-", script)

        for script in (shell_restore, powershell_restore):
            self.assertIn("before-restore", script)
            self.assertIn("tar -xzf" if script == shell_restore else "Expand-Archive", script)
            self.assertNotIn("-v", script, "restore must not delete Docker volumes")

        for script in (shell_update, powershell_update):
            self.assertIn("verify-integrity", script)
            self.assertIn("verify-images", script)
            self.assertIn("up -d x-files-rabbitmq x-files-redis x-files-client-db x-files-backfront-new-back x-files-backfront-new-front", script)
            self.assertIn("without touching x-files-data", script)
            self.assertNotIn(" down", script)
            self.assertNotIn(" rm ", script)
            self.assertNotIn("x-files-client-db x-files-client-backfront", script)

    def test_client_bundle_uses_relative_data_paths_and_predictable_localhost_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = root.bundle(make_bundle_args(Path(tmpdir)))

            with zipfile.ZipFile(result.zip_path) as archive:
                compose = archive.read("docker-compose.client.yml").decode("utf-8")
                windows_compose = archive.read("docker-compose.windows.yml").decode("utf-8")
                mac_compose = archive.read("docker-compose.mac.yml").decode("utf-8")
                env_example = archive.read(".env.example").decode("utf-8")
                shell_start = archive.read("scripts/start-x-files.sh").decode("utf-8")
                powershell_start = archive.read("scripts/start-x-files.ps1").decode("utf-8")
                readme = archive.read("readme-install.md").decode("utf-8")

            bundle_text = "\n".join(
                [compose, windows_compose, mac_compose, env_example, shell_start, powershell_start, readme]
            )
            for forbidden in (
                str(root.REPO_ROOT),
                str(Path.home()),
                "/Users/",
                "/private/",
                "C:\\Users\\",
            ):
                self.assertNotIn(forbidden, bundle_text)

            for required_mount in (
                "./x-files-data/postgres:/var/lib/postgresql/data",
                "./x-files-data/state:/data/state",
                "./x-files-data/out:/data/out",
                "./x-files-data/cache:/data/cache",
                "./x-files-data/db:/data/db",
                "./x-files-data/jur_entities:/data/jur_entities",
                "./x-files-data/tg-session:/data/tg-session",
                "./x-files-data/license-runtime:/data/license",
                "./x-files-data/license-mirror-runtime:/data/license-mirror",
                "./x-files-data/rabbitmq:/var/lib/rabbitmq",
                "./x-files-data/redis:/data",
            ):
                self.assertIn(required_mount, compose)
                self.assertIn(required_mount, windows_compose)
                self.assertIn(required_mount, mac_compose)

            self.assertIn("./license/invite-license.json:/license/invite-license.json:ro", compose)
            self.assertIn("./license/invite-license.json:/license/invite-license.json:ro", windows_compose)
            self.assertIn("./license/invite-license.json:/license/invite-license.json:ro", mac_compose)
            self.assertIn("./license/INVITE-CODE.md:/license/INVITE-CODE.md:ro", compose)
            self.assertIn("./license/INVITE-CODE.md:/license/INVITE-CODE.md:ro", windows_compose)
            self.assertIn("./license/INVITE-CODE.md:/license/INVITE-CODE.md:ro", mac_compose)
            self.assertIn("XFILES_LICENSE_FILE=/license/invite-license.json", env_example)
            self.assertIn("XFILES_INVITE_CODE_FILE=/license/INVITE-CODE.md", env_example)
            self.assertIn(f"XFILES_LICENSE_SIGNING_SECRET={SECRET}", env_example)
            self.assertIn(f"XFILES_RELEASE_SIGNING_SECRET={SECRET}", env_example)
            self.assertNotIn("./license/invite-license.json:/data/license/invite-license.json:ro", compose)
            self.assertNotIn("XFILES_LICENSE_FILE=/data/license/invite-license.json", env_example)

            self.assertIn("${HOST_FRONTEND_BIND:-127.0.0.1}:${HOST_FRONTEND_PORT:-8008}:8008", compose)
            self.assertIn("${HOST_BACKEND_BIND:-127.0.0.1}:${HOST_BACKEND_PORT:-8009}:8009", compose)
            self.assertIn("HOST_FRONTEND_BIND=127.0.0.1", env_example)
            self.assertIn("HOST_FRONTEND_PORT=8008", env_example)
            self.assertIn("HOST_BACKEND_BIND=127.0.0.1", env_example)
            self.assertIn("HOST_BACKEND_PORT=8009", env_example)
            self.assertIn("${OCR_HOST_BIND:-127.0.0.1}:${OCR_HOST_PORT:-8010}:8010", compose)
            self.assertIn("OCR_HOST_BIND=127.0.0.1", env_example)
            self.assertIn("XFILES_CLIENT_DELIVERY=1", env_example)
            self.assertIn("PAYME_OCR_SERVICE_URL=", env_example)
            self.assertIn("http://127.0.0.1:${frontend_port}/", shell_start)
            self.assertIn("http://127.0.0.1:$frontendPort/", powershell_start)
            self.assertIn("http://127.0.0.1:8008/", readme)

    def test_client_start_scripts_keep_backend_running_without_browser(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = root.bundle(make_bundle_args(Path(tmpdir)))

            with zipfile.ZipFile(result.zip_path) as archive:
                shell_start = archive.read("scripts/start-x-files.sh").decode("utf-8")
                powershell_start = archive.read("scripts/start-x-files.ps1").decode("utf-8")
                readme = archive.read("readme-install.md").decode("utf-8")

            for script in (shell_start, powershell_start):
                self.assertIn("up -d", script)
                self.assertIn("/api/health", script)
                self.assertNotIn("open http://", script.lower())
                self.assertNotIn("start-process http", script.lower())

            self.assertIn("X-Files is ready", shell_start)
            self.assertIn("X-Files is ready", powershell_start)
            self.assertIn("Откройте: `http://127.0.0.1:8008/`", readme)

    def test_client_startup_integrity_script_accepts_clean_bundle_and_rejects_tamper(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            args = make_bundle_args(base)
            result = root.bundle(args)
            extract_dir = base / "extract"

            with zipfile.ZipFile(result.zip_path) as archive:
                archive.extractall(extract_dir)

            clean = subprocess.run(
                ["sh", "scripts/verify-integrity.sh"],
                cwd=extract_dir,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr + clean.stdout)
            self.assertIn("Integrity check OK", clean.stdout)

            image_script_syntax = subprocess.run(
                ["sh", "-n", "scripts/verify-images.sh"],
                cwd=extract_dir,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(image_script_syntax.returncode, 0, image_script_syntax.stderr)

            sign_script_syntax = subprocess.run(
                ["sh", "-n", "scripts/sign-images.sh"],
                cwd=extract_dir,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(sign_script_syntax.returncode, 0, sign_script_syntax.stderr)

            env_path = extract_dir / ".env.example"
            env_path.write_text(env_path.read_text(encoding="utf-8") + "\nTAMPERED=1\n", encoding="utf-8")
            tampered = subprocess.run(
                ["sh", "scripts/verify-integrity.sh"],
                cwd=extract_dir,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("integrity checksum mismatch", tampered.stderr)

    def test_verify_bundle_rejects_tampered_update_manifest_signature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            result = root.bundle(make_bundle_args(base))
            tampered_zip = base / "tampered-manifest.zip"

            with zipfile.ZipFile(result.zip_path) as source:
                manifest = json.loads(source.read("release-manifest.json").decode("utf-8"))
                manifest["payload"]["release"] = "tampered-release"
                with zipfile.ZipFile(tampered_zip, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for item in source.infolist():
                        data = source.read(item.filename)
                        if item.filename == "release-manifest.json":
                            data = (root.json_dumps(manifest) + "\n").encode("utf-8")
                        target.writestr(item, data)

            with self.assertRaises(SystemExit) as raised:
                root.verify_bundle(SimpleNamespace(zip_path=str(tampered_zip), signing_secret=SECRET))
            self.assertIn("manifest: invalid signature", str(raised.exception))

    def test_free_demo_bundle_keeps_ocr_disabled_by_license(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir), plan="free-demo")

            result = root.bundle(args)

            with zipfile.ZipFile(result.zip_path) as archive:
                compose = archive.read("docker-compose.client.yml").decode("utf-8")
                shell_start = archive.read("scripts/start-x-files.sh").decode("utf-8")
                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))

            self.assertIn('profiles: ["disabled-by-license"]', compose)
            self.assertNotIn("--profile ocr", shell_start)
            self.assertFalse(license_doc["payload"]["features"]["ocr"])

    def test_root_email_can_be_persisted_in_owner_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            data_dir = base / "root-data"
            root.update_root_settings(
                SimpleNamespace(data_dir=str(data_dir), root_email="owner@example.com")
            )

            result = root.bundle(make_bundle_args(base, root_email=""))

            with zipfile.ZipFile(result.zip_path) as archive:
                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))
            settings = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
            registry = json.loads((data_dir / "registry.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["root_email"], "owner@example.com")
            self.assertEqual(license_doc["payload"]["root_email"], "owner@example.com")
            self.assertEqual(registry["clients"]["client@example.com"]["root_email"], "owner@example.com")
            self.assertTrue(any(item["action"] == "root_settings_updated" for item in registry["audit"]))

    def test_root_email_password_is_not_stored_in_plain_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "root-data"
            root.update_root_settings(
                SimpleNamespace(
                    data_dir=str(data_dir),
                    root_email="owner@example.com",
                    root_email_login="owner@example.com",
                    root_email_password="app-password-123",
                    root_email_password_env=None,
                    root_email_password_docker_secret=None,
                    clear_root_email_password=False,
                    secret_passphrase="local-passphrase",
                )
            )

            raw = (data_dir / "settings.json").read_text(encoding="utf-8")
            settings = json.loads(raw)
            self.assertNotIn("app-password-123", raw)
            self.assertEqual(settings["root_email_login"], "owner@example.com")
            self.assertEqual(settings["root_email_password_secret"]["type"], "encrypted-local")
            self.assertEqual(
                root.decrypt_settings_secret(settings["root_email_password_secret"], "local-passphrase"),
                "app-password-123",
            )
            visible = root.redacted_root_settings(settings)
            self.assertTrue(visible["root_email_password_secret"]["redacted"])

    def test_root_email_password_can_reference_docker_secret(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "root-data"

            root.update_root_settings(
                SimpleNamespace(
                    data_dir=str(data_dir),
                    root_email=None,
                    root_email_login=None,
                    root_email_password=None,
                    root_email_password_env=None,
                    root_email_password_docker_secret="xfiles-root-email-password",
                    clear_root_email_password=False,
                    secret_passphrase="",
                )
            )

            settings = json.loads((data_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["root_email_password_secret"]["type"], "docker-secret")
            self.assertEqual(settings["root_email_password_secret"]["name"], "xfiles-root-email-password")

    def test_root_backup_can_be_encrypted_and_restored_with_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            data_dir = base / "root-data"
            root.update_root_settings(SimpleNamespace(data_dir=str(data_dir), root_email="owner@example.com"))
            root.bundle(make_bundle_args(base, root_email=""))
            backup_path = base / "root-backup.zip"

            root.export_backup(
                SimpleNamespace(
                    data_dir=str(data_dir),
                    output=str(backup_path),
                    passphrase="correct horse battery staple",
                    signing_secret=SECRET,
                )
            )

            with zipfile.ZipFile(backup_path) as archive:
                names = set(archive.namelist())
                manifest = json.loads(archive.read("backup-manifest.json").decode("utf-8"))
            self.assertIn("root-data.json.enc", names)
            self.assertNotIn("registry.json", names)
            self.assertNotIn("settings.json", names)
            self.assertTrue(manifest["payload"]["encrypted"])

            with self.assertRaises(SystemExit):
                root.import_backup(
                    SimpleNamespace(
                        data_dir=str(base / "bad-restore"),
                        backup=str(backup_path),
                        passphrase="wrong",
                        signing_secret=SECRET,
                    )
                )

            restore_dir = base / "restore"
            root.import_backup(
                SimpleNamespace(
                    data_dir=str(restore_dir),
                    backup=str(backup_path),
                    passphrase="correct horse battery staple",
                    signing_secret=SECRET,
                )
            )

            registry = json.loads((restore_dir / "registry.json").read_text(encoding="utf-8"))
            settings = json.loads((restore_dir / "settings.json").read_text(encoding="utf-8"))
            self.assertIn("client@example.com", registry["clients"])
            self.assertEqual(settings["root_email"], "owner@example.com")
            self.assertTrue(any(item["action"] == "root_backup_imported" for item in registry["audit"]))

    def test_update_invite_code_can_be_issued_with_version_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir), plan="growth-20", license_kind="update")

            result = root.bundle(args)

            with zipfile.ZipFile(result.zip_path) as archive:
                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))

            payload = license_doc["payload"]
            self.assertEqual(payload["license_kind"], "update")
            self.assertEqual(payload["plan"], "growth-20")
            self.assertEqual(payload["version_min"], "2026.05.01")
            self.assertEqual(payload["version_max"], "2026.12.31")
            self.assertEqual(payload["update_channel"], "stable")

    def test_enterprise_offline_bundles_are_signed_and_support_standard_terms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            for duration_days in (30, 90, 365, 123):
                args = make_bundle_args(base, plan="enterprise")
                args.client_email = f"enterprise-{duration_days}@example.com"
                args.duration_days = duration_days

                result = root.bundle(args)
                root.verify_bundle(SimpleNamespace(zip_path=str(result.zip_path), signing_secret=SECRET))

                with zipfile.ZipFile(result.zip_path) as archive:
                    license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))
                    manifest_doc = json.loads(archive.read("release-manifest.json").decode("utf-8"))
                    integrity_doc = json.loads(archive.read("integrity-manifest.json").decode("utf-8"))

                verify_signed_document(license_doc, SECRET, expected_schema="x-files-license/v1")
                root.verify_signed_doc(manifest_doc, SECRET, "manifest")
                root.verify_signed_doc(integrity_doc, SECRET, "integrity")
                payload = license_doc["payload"]
                issued_at = datetime.fromisoformat(payload["issued_at"])
                valid_until = datetime.fromisoformat(payload["valid_until"])
                self.assertEqual(payload["plan"], "enterprise")
                self.assertTrue(payload["offline_allowed"])
                self.assertEqual(payload["duration_days"], duration_days)
                self.assertEqual((valid_until - issued_at).days, duration_days)

    def test_enterprise_offline_update_and_renewal_codes_are_supported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            for license_kind in ("update", "renewal", "upgrade"):
                args = make_bundle_args(base, plan="enterprise", license_kind=license_kind)
                args.client_email = f"enterprise-{license_kind}@example.com"
                args.duration_days = 90

                result = root.bundle(args)
                root.verify_bundle(SimpleNamespace(zip_path=str(result.zip_path), signing_secret=SECRET))

                with zipfile.ZipFile(result.zip_path) as archive:
                    license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))
                payload = license_doc["payload"]
                self.assertEqual(payload["plan"], "enterprise")
                self.assertEqual(payload["license_kind"], license_kind)
                self.assertTrue(payload["offline_allowed"])
                self.assertEqual(payload["duration_days"], 90)

    def test_first_touch_vip_can_be_issued_only_once_without_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            args = make_bundle_args(base)
            root.bundle(args)

            with self.assertRaises(SystemExit):
                root.bundle(make_bundle_args(base))

            repeated = root.bundle(make_bundle_args(base, allow_repeat=True))
            self.assertTrue(repeated.zip_path.exists())

    def test_owner_can_revoke_issued_license(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            result = root.bundle(make_bundle_args(base))

            root.revoke_license(
                SimpleNamespace(
                    data_dir=str(base / "root-data"),
                    license_id=result.license_id,
                    reason="wrong client email",
                )
            )

            registry = json.loads((base / "root-data" / "registry.json").read_text(encoding="utf-8"))
            license_row = registry["licenses"][result.license_id]
            download = next(row for row in registry["downloads"] if row["license_id"] == result.license_id)
            self.assertEqual(license_row["status"], "revoked")
            self.assertEqual(download["status"], "revoked")
            self.assertEqual(license_row["revoke_reason"], "wrong client email")
            self.assertTrue(any(item["action"] == "license_revoked" for item in registry["audit"]))

    def test_verify_bundle_rejects_tampered_critical_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir))
            result = root.bundle(args)
            tampered = result.zip_path.with_name("tampered.zip")

            with zipfile.ZipFile(result.zip_path) as source, zipfile.ZipFile(tampered, "w") as target:
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == ".env.example":
                        data += b"\nTAMPERED=1\n"
                    target.writestr(info, data)

            with self.assertRaises(SystemExit):
                root.verify_bundle(SimpleNamespace(zip_path=str(tampered), signing_secret=SECRET))

    def test_verify_bundle_rejects_manifest_covered_source_or_client_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            args = make_bundle_args(Path(tmpdir))
            result = root.bundle(args)
            tampered = result.zip_path.with_name("source-leak.zip")
            leaked_source = b"print('customer should not receive open source')\n"

            with zipfile.ZipFile(result.zip_path) as source, zipfile.ZipFile(tampered, "w") as target:
                manifest = json.loads(source.read("release-manifest.json").decode("utf-8"))
                manifest["payload"]["files"].append(
                    {
                        "path": "app/leaked.py",
                        "sha256": hashlib.sha256(leaked_source).hexdigest(),
                    }
                )
                manifest["signature"] = root.sign_payload(manifest["payload"], SECRET)
                for info in source.infolist():
                    data = source.read(info.filename)
                    if info.filename == "release-manifest.json":
                        data = (root.json_dumps(manifest) + "\n").encode("utf-8")
                    target.writestr(info, data)
                target.writestr("app/leaked.py", leaked_source)

            with self.assertRaises(SystemExit) as raised:
                root.verify_bundle(SimpleNamespace(zip_path=str(tampered), signing_secret=SECRET))
            self.assertIn("forbidden source/data files", str(raised.exception))

    def test_activation_receipt_import_marks_license_and_client_activated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            args = make_bundle_args(base)
            result = root.bundle(args)
            with zipfile.ZipFile(result.zip_path) as archive:
                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))

            state_path = base / "client-state" / "license-state.json"
            apply_license(
                license_doc,
                state_path=state_path,
                signing_secret=SECRET,
                instance_hash="device-a",
            )
            receipt = build_activation_receipt(
                state_path=state_path,
                signing_secret=SECRET,
                app_version="2026.05.08-test",
            )
            receipt_path = base / "activation-receipt.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

            root.import_activation_receipt(
                SimpleNamespace(data_dir=str(base / "root-data"), receipt=str(receipt_path), signing_secret=SECRET)
            )

            registry = json.loads((base / "root-data" / "registry.json").read_text(encoding="utf-8"))
            client = registry["clients"]["client@example.com"]
            license_row = registry["licenses"][result.license_id]
            download = next(row for row in registry["downloads"] if row["license_id"] == result.license_id)
            self.assertEqual(client["active_license_id"], result.license_id)
            self.assertEqual(client["active_app_version"], "2026.05.08-test")
            self.assertEqual(license_row["status"], "activated")
            self.assertEqual(download["status"], "activated")
            self.assertTrue(any(item["action"] == "activation_receipt_imported" for item in registry["audit"]))

    def test_activation_receipt_import_rejects_customer_business_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            args = make_bundle_args(base)
            result = root.bundle(args)
            with zipfile.ZipFile(result.zip_path) as archive:
                license_doc = json.loads(archive.read("license/invite-license.json").decode("utf-8"))

            state_path = base / "client-state" / "license-state.json"
            apply_license(license_doc, state_path=state_path, signing_secret=SECRET, instance_hash="device-a")
            receipt = build_activation_receipt(state_path=state_path, signing_secret=SECRET)
            receipt["payload"]["messages"] = ["secret Telegram text"]
            receipt["signature"] = root.sign_payload(receipt["payload"], SECRET)
            receipt_path = base / "bad-activation-receipt.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(SystemExit):
                root.import_activation_receipt(
                    SimpleNamespace(data_dir=str(base / "root-data"), receipt=str(receipt_path), signing_secret=SECRET)
                )

    def test_invite_license_email_sends_only_license_metadata_and_audits(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            data_dir = base / "root-data"
            root.update_root_settings(
                SimpleNamespace(
                    data_dir=str(data_dir),
                    root_email="owner@example.com",
                    root_email_login="owner-login@example.com",
                    root_email_password="mail-app-password",
                    root_email_password_env=None,
                    root_email_password_docker_secret=None,
                    clear_root_email_password=False,
                    secret_passphrase="local-passphrase",
                )
            )
            result = root.bundle(make_bundle_args(base, root_email=""))
            sent_messages = []

            class FakeSMTP:
                def __init__(self, host, port, timeout):
                    self.host = host
                    self.port = port
                    self.timeout = timeout
                    self.started = False
                    self.logged_in = None

                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def starttls(self, context=None):
                    self.started = True

                def login(self, login, password):
                    self.logged_in = (login, password)

                def send_message(self, message):
                    self.sent_message = message
                    sent_messages.append((self, message))

            original_smtp = root.smtplib.SMTP
            root.smtplib.SMTP = FakeSMTP
            try:
                root.send_license_email(
                    SimpleNamespace(
                        data_dir=str(data_dir),
                        bundle_zip=str(result.zip_path),
                        smtp_host="smtp.example.local",
                        smtp_port=2525,
                        smtp_timeout=3,
                        smtp_starttls=True,
                        secret_passphrase="local-passphrase",
                        dry_run=False,
                        signing_secret=SECRET,
                    )
                )
            finally:
                root.smtplib.SMTP = original_smtp

            self.assertEqual(len(sent_messages), 1)
            smtp, message = sent_messages[0]
            self.assertEqual((smtp.host, smtp.port, smtp.timeout), ("smtp.example.local", 2525, 3))
            self.assertTrue(smtp.started)
            self.assertEqual(smtp.logged_in, ("owner-login@example.com", "mail-app-password"))
            self.assertEqual(message["From"], "owner@example.com")
            self.assertEqual(message["To"], "client@example.com")
            text_body = message.get_body(preferencelist=("plain",)).get_content()
            self.assertIn("invite-license.json", text_body)
            self.assertIn("лицензионные метаданные", text_body)
            self.assertNotIn("secret Telegram text", text_body)
            attachments = list(message.iter_attachments())
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0].get_filename(), "invite-license.json")
            license_doc = json.loads(attachments[0].get_content())
            payload = license_doc["payload"]
            self.assertEqual(payload["license_id"], result.license_id)
            self.assertNotIn("messages", payload)
            self.assertNotIn("crm_rows", payload)
            self.assertNotIn("deals", payload)
            self.assertNotIn("ocr_text", payload)
            self.assertNotIn("jsonl", payload)

            registry = json.loads((data_dir / "registry.json").read_text(encoding="utf-8"))
            audit = registry["audit"][-1]
            self.assertEqual(audit["action"], "invite_license_email_sent")
            self.assertEqual(audit["privacy"], "license_metadata_only")
            self.assertFalse(audit["dry_run"])
            self.assertEqual(registry["licenses"][result.license_id]["last_email_sent_to"], "client@example.com")


if __name__ == "__main__":
    unittest.main()
