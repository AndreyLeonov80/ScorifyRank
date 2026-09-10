#!/usr/bin/env python3
"""Static acceptance audit for an X-Files client release ZIP.

The audit intentionally avoids Docker/network calls. It verifies the offline
contract that a generated bundle is complete, signed, data-safe, and ready for
platform smoke tests.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LICENSE_LOCAL_ROOT = ROOT.parents[1] / "license.local-front"
if LICENSE_LOCAL_ROOT.exists() and str(LICENSE_LOCAL_ROOT) not in sys.path:
    sys.path.insert(0, str(LICENSE_LOCAL_ROOT))

from x_files_root import root  # noqa: E402


def _read_json(archive: zipfile.ZipFile, name: str) -> dict[str, Any]:
    return json.loads(archive.read(name).decode("utf-8"))


def _read_text(archive: zipfile.ZipFile, name: str) -> str:
    return archive.read(name).decode("utf-8")


def _bundle_args(base: Path, signing_secret: str) -> SimpleNamespace:
    return SimpleNamespace(
        data_dir=str(base / "root-data"),
        output_dir=str(base / "releases"),
        client_email="audit-client@example.com",
        client_name="Audit Client",
        root_email="aidialog@mail.ru",
        release="2026.05.09-audit",
        plan="free-demo-first-touch-vip",
        license_kind="activation",
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
        allow_repeat=False,
        signing_secret=signing_secret,
    )


REQUIRED_OFFLINE_IMAGE_TARS = {
    "images/x-files-backfront-new-front.tar",
    "images/x-files-backfront-new-back.tar",
    "images/x-files-client-db.tar",
    "images/rabbitmq-3.13-management-alpine.tar",
    "images/redis-7-alpine.tar",
}
MIN_OFFLINE_ZIP_BYTES = 100 * 1024 * 1024


def audit_zip(zip_path: Path, signing_secret: str, require_image_tars: bool = False) -> dict[str, Any]:
    checks: list[str] = []
    errors: list[str] = []

    def check(condition: bool, name: str, message: str | None = None) -> None:
        if condition:
            checks.append(name)
        else:
            errors.append(message or name)

    try:
        with contextlib.redirect_stdout(io.StringIO()):
            root.verify_bundle(SimpleNamespace(zip_path=str(zip_path), signing_secret=signing_secret))
        checks.append("root.verify_bundle")
    except BaseException as exc:  # noqa: BLE001 - audit must report all contract breaks.
        errors.append(f"root.verify_bundle failed: {exc}")

    with zipfile.ZipFile(zip_path) as archive:
        all_names = set(archive.namelist())
        file_names = {name for name in all_names if not name.endswith("/")}

        required = set(root.CRITICAL_BUNDLE_PATHS) | {
            "release-manifest.json",
            "integrity-manifest.json",
            ".env.windows.example",
            ".env.mac.example",
            "docker-compose.windows.yml",
            "docker-compose.mac.yml",
            "images/README-images.md",
        }
        missing = sorted(required - file_names)
        check(not missing, "required-files-present", f"missing required files: {missing[:10]}")
        check(any(name.startswith("images/") for name in all_names), "images-directory-present")
        if require_image_tars:
            missing_image_tars = sorted(REQUIRED_OFFLINE_IMAGE_TARS - file_names)
            check(
                not missing_image_tars,
                "offline-image-tars-present",
                f"missing offline image tars: {missing_image_tars}",
            )
            check(
                zip_path.stat().st_size >= MIN_OFFLINE_ZIP_BYTES,
                "offline-zip-size",
                f"offline ZIP is too small: {zip_path.stat().st_size} bytes",
            )

        forbidden = sorted(name for name in file_names if root.is_forbidden_bundle_path(name))
        check(not forbidden, "no-forbidden-source-or-client-data", f"forbidden bundle files: {forbidden[:10]}")

        license_doc = _read_json(archive, "license/invite-license.json")
        manifest_doc = _read_json(archive, "release-manifest.json")
        integrity_doc = _read_json(archive, "integrity-manifest.json")
        license_payload = root.verify_signed_doc(license_doc, signing_secret, "license")
        manifest_payload = root.verify_signed_doc(manifest_doc, signing_secret, "manifest")
        integrity_payload = root.verify_signed_doc(integrity_doc, signing_secret, "integrity")
        checks.extend(["license-signature", "manifest-signature", "integrity-signature"])

        manifest_paths = {item["path"]: item["sha256"] for item in manifest_payload.get("files", [])}
        expected_manifest_paths = file_names - {"release-manifest.json"}
        check(
            set(manifest_paths) == expected_manifest_paths,
            "manifest-covers-every-file",
            "release-manifest.json does not cover every file",
        )
        checksum_errors = []
        for rel_path, expected_hash in manifest_paths.items():
            actual = root.sha256_bytes(archive.read(rel_path))
            if actual != expected_hash:
                checksum_errors.append(rel_path)
        check(not checksum_errors, "manifest-sha256-valid", f"checksum mismatches: {checksum_errors[:10]}")

        critical_paths = {item["path"] for item in integrity_payload.get("critical_files", [])}
        missing_critical = sorted(set(root.CRITICAL_BUNDLE_PATHS) - critical_paths)
        check(not missing_critical, "integrity-critical-files-covered", f"missing critical files: {missing_critical[:10]}")

        limits = license_payload.get("limits", {})
        features = license_payload.get("features", {})
        check(bool(license_payload.get("client_email")), "license-client-email")
        check(bool(license_payload.get("license_id")), "license-id")
        check(bool(license_payload.get("plan")), "license-plan-present")
        check(int(license_payload.get("duration_days", 0)) > 0, "license-duration-positive")
        check(isinstance(limits, dict), "license-limits-object")
        check(license_payload.get("hardware_binding_policy") == "one_device", "license-one-device")
        check(bool(features.get("ocr")), "license-ocr-enabled-for-vip")
        check(bool(features.get("postgresql") or features.get("postgres")), "license-postgres-enabled")
        check(bool(features.get("deals")), "license-deals-enabled")
        check(isinstance(license_payload.get("allowed_menus"), list), "license-allowed-menus")
        check(isinstance(license_payload.get("disabled_menus"), list), "license-disabled-menus")

        compose = _read_text(archive, "docker-compose.client.yml")
        compose_windows = _read_text(archive, "docker-compose.windows.yml")
        compose_mac = _read_text(archive, "docker-compose.mac.yml")
        env_example = _read_text(archive, ".env.example")
        shell_start = _read_text(archive, "scripts/start-x-files.sh")
        ps_start = _read_text(archive, "scripts/start-x-files.ps1")
        shell_update = _read_text(archive, "scripts/update-x-files.sh")
        ps_update = _read_text(archive, "scripts/update-x-files.ps1")
        shell_load = _read_text(archive, "scripts/load-images.sh")
        ps_load = _read_text(archive, "scripts/load-images.ps1")
        shell_backup = _read_text(archive, "scripts/backup-x-files.sh")
        ps_backup = _read_text(archive, "scripts/backup-x-files.ps1")
        shell_restore = _read_text(archive, "scripts/restore-x-files.sh")
        ps_restore = _read_text(archive, "scripts/restore-x-files.ps1")

        split_services = (
            "x-files-client-db",
            "x-files-rabbitmq",
            "x-files-redis",
            "x-files-backfront-new-back",
            "x-files-backfront-new-front",
            "celery_worker_telegram",
            "celery_worker_preprocess",
            "celery_worker_llm",
            "celery_worker_leads",
            "celery_worker_export",
            "x-files-ocr",
        )
        for service in split_services:
            check(service in compose, f"compose-service-{service}")
            check(service in manifest_payload.get("images", {}), f"manifest-image-{service}")
        check("x-files-client-backfront" not in compose, "compose-no-legacy-client-backfront")
        check("x-files-client-backfront" not in manifest_payload.get("images", {}), "manifest-no-legacy-client-backfront")
        for owner_service in ("x-files-root-web", "x-files-root-postgres", "x-files-license-server"):
            check(owner_service not in compose, f"compose-no-owner-service-{owner_service}")

        client_data_mounts = (
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
        )
        for mount in client_data_mounts:
            check(mount in compose, f"compose-relative-volume-{mount.split(':', 1)[0].rsplit('/', 1)[-1]}")
            check(mount in compose_windows, f"windows-compose-relative-volume-{mount.split(':', 1)[0].rsplit('/', 1)[-1]}")
            check(mount in compose_mac, f"mac-compose-relative-volume-{mount.split(':', 1)[0].rsplit('/', 1)[-1]}")
        check("./x-files-data/postgres:/var/lib/postgresql/data" in compose, "compose-relative-postgres-volume")
        license_bootstrap_mount = "./license/invite-license.json:/license/invite-license.json:ro"
        old_nested_license_mount = "./license/invite-license.json:/data/license/invite-license.json:ro"
        for label, compose_text in {
            "compose": compose,
            "windows-compose": compose_windows,
            "mac-compose": compose_mac,
        }.items():
            check(license_bootstrap_mount in compose_text, f"{label}-license-bootstrap-readonly-mount")
            check(
                old_nested_license_mount not in compose_text,
                f"{label}-no-nested-license-file-mount",
                "invite-license must not be mounted inside /data/license because Docker Desktop can fail nested bind mounts",
            )
        check(
            "XFILES_LICENSE_FILE=/license/invite-license.json" in env_example,
            "env-license-bootstrap-path",
        )
        check(
            "XFILES_LICENSE_FILE=/data/license/invite-license.json" not in env_example,
            "env-no-nested-license-path",
            "XFILES_LICENSE_FILE must point outside /data/license runtime volume",
        )
        bundle_runtime_text = "\n".join(
            [
                compose,
                compose_windows,
                compose_mac,
                env_example,
                shell_start,
                ps_start,
                shell_update,
                ps_update,
                shell_backup,
                ps_backup,
                shell_restore,
                ps_restore,
            ]
        )
        forbidden_host_paths = ("/Users/", "/private/", "C:\\Users\\", "C:/Users/")
        check(
            not any(path in bundle_runtime_text for path in forbidden_host_paths),
            "bundle-no-developer-absolute-host-paths",
            "bundle contains developer machine absolute paths",
        )
        windows_scripts_text = "\n".join([ps_start, ps_update, ps_backup, ps_restore, ps_load]).lower()
        forbidden_python_runtime_markers = ("python", "py.exe", "pip.exe", " pip ", ".venv", "virtualenv")
        check(
            not any(marker in windows_scripts_text for marker in forbidden_python_runtime_markers),
            "windows-scripts-no-python-runtime-requirement",
            "Windows client scripts must not require Python/pip/virtualenv",
        )
        for ps_name, ps_text in {
            "start": ps_start,
            "update": ps_update,
            "backup": ps_backup,
            "restore": ps_restore,
            "load-images": ps_load,
        }.items():
            check(
                'Set-Location (Join-Path $PSScriptRoot "..")' in ps_text,
                f"powershell-{ps_name}-uses-bundle-relative-root",
            )
        check("docker compose" in ps_start and "up -d" in ps_start, "powershell-start-uses-docker-compose-only")
        check("${HOST_FRONTEND_BIND:-127.0.0.1}:${HOST_FRONTEND_PORT:-8008}:8008" in compose, "compose-localhost-8008-frontend-port")
        check("${HOST_BACKEND_BIND:-127.0.0.1}:${HOST_BACKEND_PORT:-8009}:8009" in compose, "compose-localhost-8009-backend-port")
        check("HOST_FRONTEND_BIND=127.0.0.1" in env_example, "env-localhost-frontend-bind")
        check("HOST_BACKEND_BIND=127.0.0.1" in env_example, "env-localhost-backend-bind")
        check("RABBITMQ_URL=amqp://gramlead:gramlead@x-files-rabbitmq:5672//" in env_example, "env-rabbitmq-url")
        check("REDIS_URL=redis://x-files-redis:6379/0" in env_example, "env-redis-url")
        check("CELERY_BROKER_URL=amqp://gramlead:gramlead@x-files-rabbitmq:5672//" in env_example, "env-celery-broker")
        check("CELERY_RESULT_BACKEND=redis://x-files-redis:6379/1" in env_example, "env-celery-result-backend")
        check("PAYME_SOURCE_PATH=" not in env_example, "env-no-source-txt")
        check("${OCR_HOST_BIND:-127.0.0.1}:${OCR_HOST_PORT:-8010}:8010" in compose, "compose-localhost-ocr-port")
        check("OCR_HOST_BIND=127.0.0.1" in env_example, "env-localhost-ocr-bind")
        check("Linux containers mode" in compose_windows, "windows-compose-linux-containers-note")
        check("Apple Silicon" in compose_mac, "mac-compose-apple-silicon-note")
        check("OPENROUTER_API_KEY=" in env_example, "env-openrouter-placeholder")
        check("TELEGRAM_API_ID=" in env_example, "env-telegram-api-id-placeholder")
        check("TELEGRAM_API_HASH=" in env_example, "env-telegram-api-hash-placeholder")
        check("TELEGRAM_PHONE=" in env_example, "env-telegram-phone-placeholder")
        check("PAYME_OCR_SERVICE_URL=" in env_example, "env-ocr-empty-client-default")
        check("XFILES_CLIENT_DELIVERY=1" in env_example, "env-client-delivery-mode")
        check("cp .env.example .env" in shell_start, "shell-start-creates-env")
        check('Copy-Item ".env.example" ".env"' in ps_start, "powershell-start-creates-env")
        check("docker load" in shell_load, "shell-load-images")
        check("docker load" in ps_load, "powershell-load-images")
        check("find_loaded_tag_by_repo" in shell_load, "shell-load-retags-loaded-release-images")
        check("Find-LoadedTagByRepo" in ps_load and "Test-DockerImage" in ps_load, "powershell-load-retags-loaded-release-images")
        check('${Repo}:*' in ps_load and "$Repo:*" not in ps_load, "powershell-load-valid-repo-pattern-syntax")
        check("up -d x-files-rabbitmq x-files-redis x-files-client-db x-files-backfront-new-back x-files-backfront-new-front celery_worker_telegram celery_worker_preprocess celery_worker_llm celery_worker_leads celery_worker_export" in shell_update, "shell-update-split-runtime")
        check("up -d x-files-rabbitmq x-files-redis x-files-client-db x-files-backfront-new-back x-files-backfront-new-front celery_worker_telegram celery_worker_preprocess celery_worker_llm celery_worker_leads celery_worker_export" in ps_update, "powershell-update-split-runtime")
        check(" down" not in shell_update and " rm " not in shell_update, "shell-update-does-not-remove-data")
        check(" down" not in ps_update and " rm " not in ps_update, "powershell-update-does-not-remove-data")
        check("x-files-data" in shell_backup and "backups/x-files-data-" in shell_backup, "shell-backup-data-folder")
        check("x-files-data" in ps_backup and "backups/x-files-data-" in ps_backup, "powershell-backup-data-folder")
        check("tar -czf" in shell_backup, "shell-backup-creates-transferable-archive")
        check("Compress-Archive" in ps_backup, "powershell-backup-creates-transferable-archive")
        check("x-files-data.before-restore" in shell_restore, "shell-restore-keeps-previous-data-copy")
        check("x-files-data.before-restore" in ps_restore, "powershell-restore-keeps-previous-data-copy")
        check("tar -xzf" in shell_restore, "shell-restore-transferable-archive")
        check("Expand-Archive" in ps_restore, "powershell-restore-transferable-archive")

    return {
        "status": "ok" if not errors else "failed",
        "zip_path": str(zip_path),
        "checks_passed": len(checks),
        "checks": checks,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", default="", help="Existing x-files client release ZIP to audit")
    parser.add_argument("--signing-secret", default=root.DEFAULT_SIGNING_SECRET)
    parser.add_argument("--require-image-tars", action="store_true", help="Fail unless offline Docker image tar files are included")
    args = parser.parse_args()

    if args.zip:
        result = audit_zip(Path(args.zip), args.signing_secret, args.require_image_tars)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            fixture = root.bundle(_bundle_args(Path(tmpdir), args.signing_secret))
            result = audit_zip(fixture.zip_path, args.signing_secret, args.require_image_tars)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
