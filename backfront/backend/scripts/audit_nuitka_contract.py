#!/usr/bin/env python3
"""Static audit for the X-Files Nuitka Docker packaging contract.

This script intentionally does not require Docker. It protects the release
contract that is easy to break during fast product work:

* runtime image must be built from Nuitka output, not from open Python sources;
* runtime image must not copy customer data or repository noise;
* known dynamic adapters must be present in the Nuitka include list;
* deterministic build knobs must be present for repeatable CI builds.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKFRONT_ROOT = ROOT.parent
PROJECT_ROOT = BACKFRONT_ROOT.parent
FRONTEND_ROOT = BACKFRONT_ROOT / "frontend"
DOCKERFILE = ROOT / "Dockerfile.nuitka"
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "nuitka-docker.yml"

BACKEND_CONTRACT_FILES = [
    ROOT / "back.py",
    ROOT / "app" / "legacy_runtime.py",
    ROOT / "app" / "core" / "app_settings.py",
    ROOT / "app" / "core" / "menu_catalog.py",
    ROOT / "app" / "services" / "license_runtime.py",
    ROOT / "app" / "services" / "runtime_status.py",
    ROOT / "app" / "services" / "xfiles_deals_engine.py",
]


def read_contract_text(paths: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)

REQUIRED_INCLUDE_PACKAGES = {
    "x_files_license": "offline license verification and tariff enforcement",
    "fastapi": "backend API",
    "pydantic": "API DTO validation",
    "uvicorn": "ASGI server",
    "telethon": "Telegram provider",
    "duckdb": "analytics adapter",
    "psycopg": "PostgreSQL adapter",
    "requests": "OpenRouter and OCR-service HTTP adapters",
    "charset_normalizer": "requests runtime encoding detection without missing Nuitka hidden modules",
    "certifi": "requests CA bundle lookup through the Docker/Nuitka shim",
    "psutil": "runtime metrics",
}

REQUIRED_TEXT_MARKERS = {
    "Dockerfile.nuitka": [
        "COPY nuitka_shims/certifi /src/certifi",
        "ca-certificates libgomp1",
    ],
    "nuitka_shims/certifi/core.py": [
        "/etc/ssl/certs/ca-certificates.crt",
        "def where()",
        "def contents()",
    ],
}

FORBIDDEN_RUNTIME_PATTERNS = [
    r"COPY\s+\.\s+/app",
    r"COPY\s+\.\s+/src",
    r"COPY\s+back\.py\s+/app",
    r"COPY\s+back\.py\s+/src",
    r"COPY\s+tests\b",
    r"COPY\s+reports-todo\b",
    r"COPY\s+out\b",
    r"COPY\s+cache\b",
    r"COPY\s+db\b",
    r"COPY\s+state\.json\b",
    r"COPY\s+source\.txt\b",
    r"COPY\s+.*\.session\b",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def runtime_stage(dockerfile: str) -> str:
    marker = " AS runtime"
    index = dockerfile.find(marker)
    if index < 0:
        fail("Dockerfile.nuitka does not define a runtime stage")
    return dockerfile[index:]


def audit_dockerfile() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    runtime = runtime_stage(dockerfile)

    if "COPY --from=nuitka-builder /build/nuitka/nuitka_entrypoint.dist/ /app/runtime/" not in runtime:
        fail("runtime stage must copy only the Nuitka standalone output")
    if "COPY --from=frontend-assets /frontend/ /app/" not in runtime:
        fail("runtime stage must copy frontend assets from the dedicated frontend-assets stage")

    for pattern in FORBIDDEN_RUNTIME_PATTERNS:
        if re.search(pattern, runtime):
            fail(f"forbidden runtime copy pattern found: {pattern}")

    for package, reason in REQUIRED_INCLUDE_PACKAGES.items():
        marker = f"--include-package={package}"
        if marker not in dockerfile:
            fail(f"missing Nuitka include {marker} for {reason}")

    for relative_path, markers in REQUIRED_TEXT_MARKERS.items():
        path = ROOT / relative_path
        if not path.exists():
            fail(f"required Nuitka contract file is missing: {relative_path}")
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                fail(f"{relative_path}: missing required marker: {marker}")

    for marker in [
        "ARG SOURCE_DATE_EPOCH",
        "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}",
        "PYTHONHASHSEED=0",
        "PYTHONFAULTHANDLER=0",
        "PYTHONWARNINGS=ignore",
        "PAYME_OCR_SERVICE_URL",
        "PAYME_DUCKDB_PATH=/data/db/duckdb/gramlead.duckdb",
        "TELEGRAM_SESSION=/data/state/tg_export_session",
    ]:
        if marker not in dockerfile:
            fail(f"missing deterministic/runtime marker: {marker}")


def audit_safe_error_contract() -> None:
    backend = read_contract_text([ROOT / "back.py", ROOT / "app" / "legacy_runtime.py"])
    for marker in [
        "XFILES_PUBLIC_ERROR_MESSAGE",
        "@app.exception_handler(Exception)",
        "request_id",
        "logging.getLogger(\"xfiles.runtime\").exception",
        "JSONResponse",
    ]:
        if marker not in backend:
            fail(f"missing safe production error marker: {marker}")


def audit_first_start_settings_wizard() -> None:
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
        "XFILES_CLIENT_DELIVERY",
    ]:
        if marker not in backend:
            fail(f"missing backend first-start wizard marker: {marker}")
    for marker in ["react.page-loader.js", "setup_wizard.html", "react.setup_wizard.js"]:
        if marker not in (setup_html + manifest):
            fail(f"missing setup wizard loader marker: {marker}")
    for marker in [
        "setup_wizard_completed",
        "Telegram api_id/api_hash",
        "Проверить OpenRouter",
        "Завершить настройку и открыть Import",
        "при сетевой ошибке включите VPN",
    ]:
        if marker not in setup_page:
            fail(f"missing frontend setup wizard marker: {marker}")
    for marker in [
        "Стартовый мастер настройки",
        "Telegram api_id и api_hash",
    ]:
        if marker not in settings_page:
            fail(f"missing settings wizard UI marker: {marker}")
    for marker in [
        "client_delivery",
        "XFILES_CLIENT_DELIVERY_MENU_KEYS",
        '"jur-entities"',
        "'settings'",
    ]:
        if marker not in (backend + shared_page):
            fail(f"missing client delivery menu marker: {marker}")


def audit_postgres_waiting_contract() -> None:
    backend = read_contract_text(BACKEND_CONTRACT_FILES)
    dashboard = (FRONTEND_ROOT / "js" / "react.dashboard.js").read_text(encoding="utf-8")
    deals_page = (FRONTEND_ROOT / "js" / "react.deals.js").read_text(encoding="utf-8")
    for marker in [
        "postgresql_waiting",
        "PostgreSQL подключается или временно недоступен",
    ]:
        if marker not in backend:
            fail(f"missing backend PostgreSQL waiting marker: {marker}")
    for marker in [
        "dealsPostgresWaiting",
        "показываю кеш state.json, страница не пустеет",
    ]:
        if marker not in dashboard:
            fail(f"missing dashboard PostgreSQL waiting marker: {marker}")
    for marker in [
        "PostgreSQL подключается",
        "таблицы сделок показывают локальный кеш state.json",
    ]:
        if marker not in deals_page:
            fail(f"missing deals page PostgreSQL waiting marker: {marker}")


def audit_dashboard_startup_progress_contract() -> None:
    backend = read_contract_text(BACKEND_CONTRACT_FILES)
    dashboard = (FRONTEND_ROOT / "js" / "react.dashboard.js").read_text(encoding="utf-8")
    for marker in [
        "_startup_status_update",
        "_startup_status_snapshot",
        "\"startup\": startup",
        "startup_progress_percent",
    ]:
        if marker not in backend:
            fail(f"missing backend startup progress marker: {marker}")
    for marker in [
        "backendStartupRunning",
        "Backend запускается",
        "Ожидаем ответ backend",
        "startupLogRows",
    ]:
        if marker not in dashboard:
            fail(f"missing dashboard startup progress marker: {marker}")


def audit_smoke_timeout_contract() -> None:
    smoke_script = (ROOT / "scripts" / "smoke_nuitka_image.py").read_text(encoding="utf-8")
    for marker in [
        "subprocess.TimeoutExpired",
        "XFILES_DOCKER_COMMAND_TIMEOUT_SEC",
        "XFILES_NUITKA_BUILD_TIMEOUT_SEC",
        "--build-timeout",
        "--docker-timeout",
        "timed out after",
    ]:
        if marker not in smoke_script:
            fail(f"missing Nuitka smoke timeout marker: {marker}")


def audit_workflow() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    for marker in [
        "git log -1 --format=%ct",
        "git log -1 --format=%cI",
        "SOURCE_DATE_EPOCH=${{ steps.meta.outputs.source_date_epoch }}",
        "BUILD_DATE=${{ steps.meta.outputs.build_date }}",
        "linux/amd64",
        "linux/arm64",
        "Dockerfile.nuitka",
    ]:
        if marker not in workflow:
            fail(f"missing CI reproducibility/multiarch marker: {marker}")


def main() -> int:
    audit_dockerfile()
    audit_workflow()
    audit_safe_error_contract()
    audit_first_start_settings_wizard()
    audit_postgres_waiting_contract()
    audit_dashboard_startup_progress_contract()
    audit_smoke_timeout_contract()
    print("Nuitka packaging contract audit OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
