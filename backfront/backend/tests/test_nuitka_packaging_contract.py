from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKFRONT_ROOT = ROOT.parent
PROJECT_ROOT = BACKFRONT_ROOT.parent
FRONTEND_ROOT = BACKFRONT_ROOT / "frontend"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "nuitka-docker.yml"
BACKEND_CONTRACT_FILES = [
    ROOT / "back.py",
    ROOT / "app" / "legacy_runtime.py",
    ROOT / "app" / "core" / "app_settings.py",
    ROOT / "app" / "core" / "lifespan.py",
    ROOT / "app" / "core" / "menu_catalog.py",
    ROOT / "app" / "services" / "license_runtime.py",
    ROOT / "app" / "services" / "runtime_status.py",
    ROOT / "app" / "services" / "xfiles_deals_engine.py",
]


def read_contract_text(paths: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


class NuitkaPackagingContractTest(unittest.TestCase):
    def test_dockerfile_uses_multi_stage_nuitka_runtime(self) -> None:
        dockerfile = (ROOT / "Dockerfile.nuitka").read_text(encoding="utf-8")

        self.assertIn("AS nuitka-builder", dockerfile)
        self.assertIn("AS frontend-assets", dockerfile)
        self.assertIn("AS runtime", dockerfile)
        self.assertIn('"nuitka==${NUITKA_VERSION}"', dockerfile)
        self.assertIn("python -m nuitka", dockerfile)
        self.assertIn("--standalone", dockerfile)
        self.assertIn("--include-package=x_files_license", dockerfile)
        self.assertIn("COPY --from=nuitka-builder", dockerfile)
        self.assertIn("COPY --from=frontend-assets /frontend/ /app/", dockerfile)
        self.assertNotIn("COPY . /app", dockerfile)
        self.assertNotIn("COPY . /src", dockerfile)

    def test_nuitka_static_audit_script_covers_source_and_adapter_contract(self) -> None:
        script = (ROOT / "scripts" / "audit_nuitka_contract.py").read_text(encoding="utf-8")
        dockerfile = (ROOT / "Dockerfile.nuitka").read_text(encoding="utf-8")

        for marker in [
            "REQUIRED_INCLUDE_PACKAGES",
            "FORBIDDEN_RUNTIME_PATTERNS",
            "COPY --from=nuitka-builder /build/nuitka/nuitka_entrypoint.dist/ /app/runtime/",
            "PAYME_OCR_SERVICE_URL",
            "git log -1 --format=%ct",
            "fastapi",
            "uvicorn",
            "telethon",
            "duckdb",
            "psycopg",
            "requests",
            "charset_normalizer",
            "certifi",
            "psutil",
            "COPY nuitka_shims/certifi /src/certifi",
            "audit_safe_error_contract",
            "audit_first_start_settings_wizard",
            "audit_postgres_waiting_contract",
            "audit_dashboard_startup_progress_contract",
            "audit_smoke_timeout_contract",
            "XFILES_DOCKER_COMMAND_TIMEOUT_SEC",
            "XFILES_NUITKA_BUILD_TIMEOUT_SEC",
        ]:
            self.assertIn(marker, script)

        for marker in [
            "ARG SOURCE_DATE_EPOCH",
            "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}",
            "PYTHONHASHSEED=0",
            "PYTHONFAULTHANDLER=0",
            "PYTHONWARNINGS=ignore",
            "TELEGRAM_SESSION=/data/state/tg_export_session",
        ]:
            self.assertIn(marker, dockerfile)

    def test_backend_has_safe_production_error_contract(self) -> None:
        backend = read_contract_text([ROOT / "back.py", ROOT / "app" / "legacy_runtime.py"])

        for marker in [
            "XFILES_PUBLIC_ERROR_MESSAGE",
            "@app.exception_handler(Exception)",
            "request_id",
            "logging.getLogger(\"xfiles.runtime\").exception",
            "JSONResponse",
        ]:
            self.assertIn(marker, backend)

        forbidden_public_markers = [
            "traceback.format_exc()",
            "content={\"detail\": str(exc)}",
            "content={\"detail\": repr(exc)}",
        ]
        for marker in forbidden_public_markers:
            self.assertNotIn(marker, backend)

    def test_setup_wizard_has_first_start_client_delivery_contract(self) -> None:
        backend = read_contract_text(BACKEND_CONTRACT_FILES)
        setup_html = (FRONTEND_ROOT / "app.html").read_text(encoding="utf-8")
        manifest = (FRONTEND_ROOT / "app.manifest.json").read_text(encoding="utf-8")
        setup_page = (FRONTEND_ROOT / "js" / "react.setup_wizard.js").read_text(encoding="utf-8")
        settings_page = (FRONTEND_ROOT / "js" / "react.settings.js").read_text(encoding="utf-8")
        shared_page = (FRONTEND_ROOT / "js" / "react.shared.js").read_text(encoding="utf-8")

        for marker in [
            "setup_wizard_completed",
            "first_start_wizard_required",
            "settings.get(\"first_start_wizard_required\")",
            '"/setup_wizard.html"',
        ]:
            self.assertIn(marker, backend)
        for marker in ["react.page-loader.js", "setup_wizard.html", "react.setup_wizard.js"]:
            self.assertIn(marker, setup_html + manifest)
        for marker in [
            "setup_wizard_completed",
            "Telegram api_id/api_hash",
            "Проверить OpenRouter",
            "Завершить настройку и открыть Import",
            "при сетевой ошибке включите VPN",
        ]:
            self.assertIn(marker, setup_page)

        for marker in [
            "Стартовый мастер настройки",
            "Telegram api_id и api_hash",
            "OpenRouter",
            "OCR-сервис",
        ]:
            self.assertIn(marker, settings_page)

        for marker in [
            "XFILES_CLIENT_DELIVERY",
            "client_delivery",
            "XFILES_CLIENT_DELIVERY_MENU_KEYS",
            '"jur-entities"',
            "'settings'",
        ]:
            self.assertIn(marker, backend + shared_page)

    def test_deals_page_has_postgres_waiting_contract(self) -> None:
        backend = read_contract_text(BACKEND_CONTRACT_FILES)
        dashboard = (FRONTEND_ROOT / "js" / "react.dashboard.js").read_text(encoding="utf-8")
        deals_page = (FRONTEND_ROOT / "js" / "react.deals.js").read_text(encoding="utf-8")

        for marker in [
            "postgresql_waiting",
            "PostgreSQL подключается или временно недоступен",
        ]:
            self.assertIn(marker, backend)
        for marker in [
            "dealsPostgresWaiting",
            "показываю кеш state.json, страница не пустеет",
        ]:
            self.assertIn(marker, dashboard)
        for marker in [
            "PostgreSQL подключается",
            "таблицы сделок показывают локальный кеш state.json",
        ]:
            self.assertIn(marker, deals_page)

    def test_dashboard_has_backend_startup_progress_contract(self) -> None:
        backend = read_contract_text(BACKEND_CONTRACT_FILES)
        dashboard = (FRONTEND_ROOT / "js" / "react.dashboard.js").read_text(encoding="utf-8")

        for marker in [
            "_startup_status_update",
            "_startup_status_snapshot",
            "\"startup\": startup",
            "startup_progress_percent",
            "FastAPI startup начат",
        ]:
            self.assertIn(marker, backend)
        for marker in [
            "backendStartupRunning",
            "Backend запускается",
            "Ожидаем ответ backend",
            "startupLogRows",
        ]:
            self.assertIn(marker, dashboard)

    def test_runtime_image_has_release_metadata_and_data_paths(self) -> None:
        dockerfile = (ROOT / "Dockerfile.nuitka").read_text(encoding="utf-8")

        for marker in [
            "org.opencontainers.image.title",
            "org.opencontainers.image.version",
            "org.opencontainers.image.revision",
            "org.opencontainers.image.created",
            "x-files.release.channel",
            "PAYME_STATE_PATH=/data/state/state.json",
            "PAYME_DUCKDB_PATH=/data/db/duckdb/gramlead.duckdb",
            'CMD ["/app/runtime/backfront-app"]',
        ]:
            self.assertIn(marker, dockerfile)

    def test_dockerignore_excludes_release_noise_and_user_data(self) -> None:
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        expected = {
            ".git",
            "tests/",
            "reports-todo/",
            "docker-data/",
            "x-files-data/",
            "cache/",
            "db/",
            "out/",
            "*.zip",
            "*.docx",
            "*.png",
            "*.jpg",
            "*.mp4",
            "*.session",
            ".pytest_cache/",
            "node_modules/",
        }
        missing = sorted(expected.difference(dockerignore))
        self.assertEqual([], missing)

    def test_entrypoint_sets_static_root_before_importing_app(self) -> None:
        entrypoint = (ROOT / "nuitka_entrypoint.py").read_text(encoding="utf-8")

        app_dir_pos = entrypoint.index('os.environ.setdefault("PAYME_APP_DIR", "/app")')
        import_pos = entrypoint.index("from app.main import app")
        self.assertLess(app_dir_pos, import_pos)
        self.assertIn("ensure_runtime_dirs", entrypoint)
        self.assertIn('state_path.write_text("{}\\n"', entrypoint)
        self.assertNotIn("source_path.write_text", entrypoint)

    def test_nuitka_binary_entrypoint_launches_fastapi_with_uvicorn(self) -> None:
        dockerfile = (ROOT / "Dockerfile.nuitka").read_text(encoding="utf-8")
        entrypoint = (ROOT / "nuitka_entrypoint.py").read_text(encoding="utf-8")

        for marker in [
            "import uvicorn",
            "from app.main import app",
            'web_port = int(os.environ.get("WEB_PORT", "8001"))',
            'uvicorn.run(app, host="0.0.0.0", port=web_port)',
        ]:
            self.assertIn(marker, entrypoint)

        for marker in [
            "--output-filename=backfront-app",
            "--include-package=fastapi",
            "--include-package=uvicorn",
            "--include-package=charset_normalizer",
            "--include-package=certifi",
            "COPY nuitka_shims/certifi /src/certifi",
            "--mount=type=cache,target=/root/.cache/ccache",
            "CCACHE_DIR=/root/.cache/ccache",
            'CMD ["/app/runtime/backfront-app"]',
        ]:
            self.assertIn(marker, dockerfile)

    def test_nuitka_certifi_shim_uses_system_ca_bundle(self) -> None:
        init_py = ROOT / "nuitka_shims" / "certifi" / "__init__.py"
        core_py = ROOT / "nuitka_shims" / "certifi" / "core.py"

        self.assertIn("where", init_py.read_text(encoding="utf-8"))
        core = core_py.read_text(encoding="utf-8")
        self.assertIn("/etc/ssl/certs/ca-certificates.crt", core)
        self.assertIn("def where()", core)
        self.assertIn("def contents()", core)

    def test_smoke_script_audits_compiled_runtime_image(self) -> None:
        script = (ROOT / "scripts" / "smoke_nuitka_image.py").read_text(encoding="utf-8")

        for marker in [
            "Dockerfile.nuitka",
            "docker",
            "build",
            "docker",
            "run",
            "/api/payme/dashboard/summary",
            "/dashboard.html",
            "wait_for_frontend",
            "has_dashboard",
            "has_dashboard_js",
            "assert_no_backend_sources",
            "assert_no_baked_release_noise_or_client_data",
            "TELEGRAM_SESSION=/data/state/tg_export_session",
            "docker",
            "image",
            "inspect",
            ".git",
            "*.jsonl",
            "*.duckdb",
            "*.session",
            "*.py",
            "*.pyc",
            "source_leaks",
            "data_leaks",
            "DEFAULT_DOCKER_CLI_TIMEOUT_SEC",
            "DEFAULT_BUILD_TIMEOUT_SEC",
            "XFILES_DOCKER_COMMAND_TIMEOUT_SEC",
            "XFILES_NUITKA_BUILD_TIMEOUT_SEC",
            "--build-timeout",
            "--docker-timeout",
            "subprocess.TimeoutExpired",
            "timed out after",
        ]:
            self.assertIn(marker, script)

    def test_runtime_packages_native_database_adapters(self) -> None:
        dockerfile = (ROOT / "Dockerfile.nuitka").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

        for marker in [
            "duckdb==",
            "psycopg[binary]==",
            "charset-normalizer==2.1.1",
        ]:
            self.assertIn(marker, requirements)

        for marker in [
            "--include-package=duckdb",
            "--include-package=psycopg",
            "--include-package=charset_normalizer",
            "libgomp1",
            "PAYME_DUCKDB_PATH=/data/db/duckdb/gramlead.duckdb",
        ]:
            self.assertIn(marker, dockerfile)

    def test_docker_preflight_is_timeout_bounded(self) -> None:
        script = (ROOT / "scripts" / "preflight_docker_daemon.py").read_text(encoding="utf-8")

        for marker in [
            "DEFAULT_TIMEOUT_SEC",
            "subprocess.TimeoutExpired",
            "docker",
            "--version",
            "docker_daemon",
            "docker_ps",
            "docker_image",
            "--image",
            "--human",
            "find_docker_cli_processes",
            "docker_cli_processes",
            "find_docker_desktop_processes",
            "docker_desktop_processes",
            "Docker Desktop backend processes",
            "restart Docker Desktop",
            "return 0 if payload[\"ok\"] else 2",
        ]:
            self.assertIn(marker, script)

    def test_release_zip_platform_matrix_smoke_targets_external_stands(self) -> None:
        script = (ROOT / "scripts" / "smoke_release_zip_platform_matrix.py").read_text(encoding="utf-8")

        for marker in [
            "windows-linux-containers",
            "mac-apple-silicon",
            "mac-intel",
            "linux-amd64",
            "linux-arm64",
            "docker_linux_containers",
            "docker_amd64_capable",
            "docker_arm64_capable",
            "smoke_release_zip_runtime.py",
            "preflight_docker_daemon.py",
            "--target",
            "--zip",
            "--backfront-image",
            "--db-image",
            "runtime_smoke",
            "--evidence-out",
            "--require-runtime-smoke",
            "runtime_smoke_required",
            "evidence_path.write_text",
        ]:
            self.assertIn(marker, script)

    def test_release_smoke_and_license_contract_cover_schema_compatibility(self) -> None:
        smoke_script = (ROOT / "scripts" / "smoke_release_zip_runtime.py").read_text(encoding="utf-8")
        license_tests = (ROOT / "tests" / "test_x_files_local_license.py").read_text(encoding="utf-8")

        for marker in [
            "assert_marker_after_backfront_update",
            "data_survived_backfront_update",
            "xfiles_release_smoke",
            "x-files-client-backfront",
        ]:
            self.assertIn(marker, smoke_script)

        for marker in [
            "test_schema_compatibility_blocks_unknown_versions",
            "validate_schema_compatibility",
            "min_supported=2",
            "max_supported=5",
            "LicenseError",
        ]:
            self.assertIn(marker, license_tests)

    def test_offline_update_contract_protects_enterprise_clients(self) -> None:
        root_bundle_tests = (ROOT / "tests" / "test_x_files_root_bundle.py").read_text(encoding="utf-8")
        local_license_tests = (ROOT / "tests" / "test_x_files_local_license.py").read_text(encoding="utf-8")

        for marker in [
            "test_enterprise_offline_update_and_renewal_codes_are_supported",
            "license_kind in (\"update\", \"renewal\", \"upgrade\")",
            "offline_allowed",
            "verify_bundle",
        ]:
            self.assertIn(marker, root_bundle_tests)

        for marker in [
            "test_apply_license_persists_version_window_and_rejects_invalid_update",
            "license_kind=\"update\"",
            "version_min=\"2026.05.01\"",
            "app_version=\"2026.05.09\"",
        ]:
            self.assertIn(marker, local_license_tests)

    def test_ci_workflow_builds_nuitka_image_for_amd64_and_arm64(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        for marker in [
            "Build metadata",
            "git log -1 --format=%ct",
            "git log -1 --format=%cI",
            "Dockerfile.nuitka",
            "docker/setup-qemu-action",
            "docker/setup-buildx-action",
            "docker/build-push-action",
            "linux/amd64",
            "linux/arm64",
            "x-files-client-backfront:nuitka-ci-${{ matrix.suffix }}",
            "SOURCE_DATE_EPOCH=${{ steps.meta.outputs.source_date_epoch }}",
            "BUILD_DATE=${{ steps.meta.outputs.build_date }}",
            "push: false",
        ]:
            self.assertIn(marker, workflow)

    def test_ci_workflow_builds_client_db_image_for_amd64_and_arm64(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        for marker in [
            "build-client-db-image",
            "Dockerfile.x-files-client-db",
            "x-files-client-db:nuitka-ci-${{ matrix.suffix }}",
            "linux/amd64",
            "linux/arm64",
            "docker/setup-qemu-action",
            "docker/setup-buildx-action",
            "docker/build-push-action",
            "push: false",
        ]:
            self.assertIn(marker, workflow)


if __name__ == "__main__":
    unittest.main()
