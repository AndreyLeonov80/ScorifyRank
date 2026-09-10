#!/usr/bin/env python3
"""Runtime smoke-test for an X-Files client release ZIP.

The static ZIP audit proves that the bundle is well-formed. This smoke script
is the next gate: it extracts the ZIP into a temporary customer-like directory,
starts Docker Compose, waits for the dashboard API, writes a marker into
PostgreSQL, restarts the stack, and confirms that the marker survived.

It is intentionally explicit and timeout-bounded so a broken Docker daemon does
not hang local acceptance work forever.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCKER_TIMEOUT_SEC = int(os.environ.get("XFILES_DOCKER_COMMAND_TIMEOUT_SEC", "90") or "90")
DEFAULT_START_TIMEOUT_SEC = int(os.environ.get("XFILES_RELEASE_START_TIMEOUT_SEC", "180") or "180")


def _timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    timeout_sec: Optional[int] = DEFAULT_DOCKER_TIMEOUT_SEC,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        partial_output = _timeout_output(exc.stdout) + _timeout_output(exc.stderr)
        raise RuntimeError(
            f"{' '.join(args)} timed out after {timeout_sec}s\n{partial_output.strip()}"
        ) from exc
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed with {result.returncode}\n{result.stdout}")
    return result


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def extract_bundle(zip_path: Path, workdir: Path) -> Path:
    stage = workdir / "bundle"
    stage.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(stage)
    return stage


def append_smoke_env(
    stage: Path,
    args: argparse.Namespace,
    frontend_port: int,
    backend_port: int,
    suffix: str,
) -> None:
    env_path = stage / ".env"
    if not env_path.exists():
        example = stage / ".env.example"
        env_path.write_text(example.read_text(encoding="utf-8") if example.exists() else "", encoding="utf-8")
    overrides = {
        "HOST_FRONTEND_PORT": str(frontend_port),
        "HOST_BACKEND_PORT": str(backend_port),
        "NETWORK_NAME": f"x-files-smoke-net-{suffix}",
        "XFILES_DB_CONTAINER_NAME": f"x-files-smoke-db-{suffix}",
        "XFILES_BACKEND_CONTAINER_NAME": f"x-files-smoke-back-{suffix}",
        "XFILES_FRONTEND_CONTAINER_NAME": f"x-files-smoke-front-{suffix}",
        "XFILES_WORKER_TELEGRAM_CONTAINER_NAME": f"x-files-smoke-worker-telegram-{suffix}",
        "XFILES_WORKER_PREPROCESS_CONTAINER_NAME": f"x-files-smoke-worker-preprocess-{suffix}",
        "XFILES_WORKER_LLM_CONTAINER_NAME": f"x-files-smoke-worker-llm-{suffix}",
        "XFILES_WORKER_LEADS_CONTAINER_NAME": f"x-files-smoke-worker-leads-{suffix}",
        "XFILES_WORKER_EXPORT_CONTAINER_NAME": f"x-files-smoke-worker-export-{suffix}",
        "XFILES_OCR_CONTAINER_NAME": f"x-files-smoke-ocr-{suffix}",
        "PAYME_STARTUP_TELEGRAM_BOOTSTRAP": "0",
        "POSTGRES_USER": "gramlead",
        "POSTGRES_PASSWORD": "gramlead",
        "POSTGRES_DB": "gramlead",
    }
    if args.backfront_image:
        overrides["XFILES_BACKEND_IMAGE"] = args.backfront_image
        overrides["XFILES_FRONTEND_IMAGE"] = args.backfront_image
    if args.backend_image:
        overrides["XFILES_BACKEND_IMAGE"] = args.backend_image
    if args.frontend_image:
        overrides["XFILES_FRONTEND_IMAGE"] = args.frontend_image
    if args.db_image:
        overrides["XFILES_DB_IMAGE"] = args.db_image
    if args.ocr_image:
        overrides["XFILES_OCR_IMAGE"] = args.ocr_image

    # Docker Compose dotenv parsing can keep the first value for duplicate keys
    # on some Desktop versions. Rewrite keys instead of appending duplicates.
    kept_lines: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key not in overrides:
            kept_lines.append(line)
    kept_lines.append("")
    kept_lines.append("# Runtime smoke-test overrides. Safe to delete after acceptance.")
    kept_lines.extend(f"{key}={value}" for key, value in overrides.items())
    env_path.write_text("\n".join(kept_lines).rstrip() + "\n", encoding="utf-8")


def compose_args(include_ocr: bool) -> list[str]:
    args = ["docker", "compose", "-f", "docker-compose.client.yml", "--env-file", ".env"]
    if include_ocr:
        args.extend(["--profile", "ocr"])
    return args


def maybe_load_images(stage: Path, docker_timeout_sec: int) -> None:
    images_dir = stage / "images"
    if not images_dir.exists():
        return
    for image in sorted(list(images_dir.glob("*.tar")) + list(images_dir.glob("*.tar.gz"))):
        run(["docker", "load", "-i", str(image)], cwd=stage, timeout_sec=docker_timeout_sec)


def preflight_docker(docker_timeout_sec: int) -> None:
    """Fail fast before extracting/starting a bundle when Docker is unhealthy."""

    timeout = min(8, docker_timeout_sec)
    for command in [
        ["docker", "--version"],
        ["docker", "version", "--format", "{{.Server.Version}}"],
        ["docker", "compose", "version"],
        ["docker", "ps", "--format", "{{.Names}}"],
    ]:
        run(command, cwd=ROOT, timeout_sec=timeout)


def wait_for_dashboard_api(port: int, timeout_sec: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/api/payme/dashboard/summary"
    deadline = time.monotonic() + timeout_sec
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - smoke script reports last connection issue.
            last_error = repr(exc)
            time.sleep(2)
    raise RuntimeError(f"Dashboard did not answer in {timeout_sec}s at {url}; last error: {last_error}")


def wait_for_frontend_page(port: int, path: str, expected_text: str, timeout_sec: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{path}"
    deadline = time.monotonic() + timeout_sec
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                body = response.read().decode("utf-8", "replace")
                if expected_text in body:
                    return {"path": path, "expected_text": expected_text, "length": len(body)}
                last_error = f"expected text {expected_text!r} was not found"
        except Exception as exc:  # noqa: BLE001 - smoke script reports last connection issue.
            last_error = repr(exc)
        time.sleep(2)
    raise RuntimeError(f"Frontend page did not answer in {timeout_sec}s at {url}; last error: {last_error}")


def assert_required_frontend_pages(port: int, timeout_sec: int) -> list[dict[str, Any]]:
    return [
        wait_for_frontend_page(port, "/index.html", "Чат", timeout_sec),
        wait_for_frontend_page(port, "/import.html", "Импорт", timeout_sec),
        wait_for_frontend_page(port, "/grid.html", "Sync", timeout_sec),
        wait_for_frontend_page(port, "/dashboard.html", "Dashboard", timeout_sec),
        wait_for_frontend_page(port, "/settings.html", "Настройки", timeout_sec),
    ]


def write_persistent_file_markers(stage: Path) -> dict[str, Any]:
    """Create customer-data markers that must survive restart/update cycles."""

    token = f"runtime-persistence-{int(time.time())}"
    markers = {
        "telegram_session": stage / "x-files-data" / "tg-session" / "tg_export_session.smoke",
        "license_state": stage / "x-files-data" / "license-runtime" / "license-state.smoke.json",
        "settings": stage / "x-files-data" / "state" / "settings.smoke.json",
    }
    for label, path in markers.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"label": label, "token": token}, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"token": token, "files": markers}


def assert_persistent_file_markers(markers: dict[str, Any]) -> dict[str, bool]:
    token = str(markers["token"])
    survived: dict[str, bool] = {}
    for label, path in markers["files"].items():
        marker_path = Path(path)
        content = marker_path.read_text(encoding="utf-8") if marker_path.exists() else ""
        if token not in content:
            raise RuntimeError(f"{label} marker was lost from persistent data volume: {marker_path}")
        survived[label] = True
    return survived


def psql(stage: Path, sql: str, include_ocr: bool, docker_timeout_sec: int) -> str:
    result = run(
        compose_args(include_ocr)
        + [
            "exec",
            "-T",
            "x-files-client-db",
            "psql",
            "-U",
            "gramlead",
            "-d",
            "gramlead",
            "-v",
            "ON_ERROR_STOP=1",
            "-tAc",
            sql,
        ],
        cwd=stage,
        timeout_sec=docker_timeout_sec,
    )
    return result.stdout.strip()


def assert_postgres_marker_survives(stage: Path, include_ocr: bool, docker_timeout_sec: int) -> str:
    marker = f"zip-smoke-{int(time.time())}"
    psql(
        stage,
        "CREATE TABLE IF NOT EXISTS xfiles_release_smoke "
        "(id text PRIMARY KEY, created_at timestamptz DEFAULT now())",
        include_ocr,
        docker_timeout_sec,
    )
    psql(
        stage,
        f"INSERT INTO xfiles_release_smoke(id) VALUES ('{marker}') "
        "ON CONFLICT (id) DO NOTHING",
        include_ocr,
        docker_timeout_sec,
    )
    found = psql(
        stage,
        f"SELECT id FROM xfiles_release_smoke WHERE id = '{marker}'",
        include_ocr,
        docker_timeout_sec,
    )
    if marker not in found:
        raise RuntimeError("PostgreSQL marker was not found before restart")
    return marker


def assert_marker_after_restart(
    stage: Path,
    marker: str,
    include_ocr: bool,
    port: int,
    start_timeout_sec: int,
    docker_timeout_sec: int,
) -> None:
    run(compose_args(include_ocr) + ["restart", "x-files-client-db", "x-files-backfront-new-back", "x-files-backfront-new-front"], cwd=stage)
    wait_for_dashboard_api(port, start_timeout_sec)
    found = psql(
        stage,
        f"SELECT id FROM xfiles_release_smoke WHERE id = '{marker}'",
        include_ocr,
        docker_timeout_sec,
    )
    if marker not in found:
        raise RuntimeError("PostgreSQL marker was lost after Docker restart")


def assert_marker_after_backfront_update(
    stage: Path,
    marker: str,
    include_ocr: bool,
    port: int,
    start_timeout_sec: int,
    docker_timeout_sec: int,
) -> None:
    run(compose_args(include_ocr) + ["up", "-d", "x-files-backfront-new-back", "x-files-backfront-new-front", "celery_worker_telegram", "celery_worker_preprocess", "celery_worker_llm", "celery_worker_leads", "celery_worker_export"], cwd=stage, timeout_sec=docker_timeout_sec)
    wait_for_dashboard_api(port, start_timeout_sec)
    found = psql(
        stage,
        f"SELECT id FROM xfiles_release_smoke WHERE id = '{marker}'",
        include_ocr,
        docker_timeout_sec,
    )
    if marker not in found:
        raise RuntimeError("PostgreSQL marker was lost after backfront-only update")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test X-Files release ZIP in Docker Compose")
    parser.add_argument("--zip", required=True, help="Path to x-files-root generated client ZIP")
    parser.add_argument("--include-ocr", action="store_true", help="Start OCR compose profile too")
    parser.add_argument("--backfront-image", default="", help="Compat override: use one image tag for backend and frontend")
    parser.add_argument("--frontend-image", default="", help="Override XFILES_FRONTEND_IMAGE for local smoke")
    parser.add_argument("--backend-image", default="", help="Override XFILES_BACKEND_IMAGE for local smoke")
    parser.add_argument("--db-image", default="", help="Override XFILES_DB_IMAGE for local smoke")
    parser.add_argument("--ocr-image", default="", help="Override XFILES_OCR_IMAGE for local smoke")
    parser.add_argument("--start-timeout", type=int, default=DEFAULT_START_TIMEOUT_SEC)
    parser.add_argument("--docker-timeout", type=int, default=DEFAULT_DOCKER_TIMEOUT_SEC)
    parser.add_argument("--skip-preflight", action="store_true", help="Skip fast Docker daemon checks before smoke.")
    parser.add_argument("--keep-workdir", action="store_true", help="Keep extracted bundle for debugging")
    args = parser.parse_args()

    zip_path = Path(args.zip).expanduser().resolve()
    if not zip_path.exists():
        raise SystemExit(f"ZIP not found: {zip_path}")
    if not args.skip_preflight:
        preflight_docker(args.docker_timeout)

    workdir_obj = tempfile.TemporaryDirectory(prefix="x-files-release-smoke-")
    workdir = Path(workdir_obj.name)
    suffix = str(int(time.time()))[-8:]
    frontend_port = find_free_port()
    backend_port = find_free_port()
    stage = extract_bundle(zip_path, workdir)
    append_smoke_env(stage, args, frontend_port, backend_port, suffix)
    persistent_markers = write_persistent_file_markers(stage)

    status: dict[str, Any] = {
        "zip": str(zip_path),
        "stage": str(stage),
        "dashboard": f"http://127.0.0.1:{frontend_port}/dashboard.html",
        "backend_health": f"http://127.0.0.1:{backend_port}/api/health",
        "include_ocr": bool(args.include_ocr),
        "ocr_service": "x-files-ocr" if args.include_ocr else "disabled",
    }

    try:
        maybe_load_images(stage, args.docker_timeout)
        run(compose_args(args.include_ocr) + ["up", "-d"], cwd=stage, timeout_sec=args.docker_timeout)
        dashboard = wait_for_dashboard_api(backend_port, args.start_timeout)
        frontend_pages = assert_required_frontend_pages(frontend_port, args.start_timeout)
        marker = assert_postgres_marker_survives(stage, args.include_ocr, args.docker_timeout)
        assert_marker_after_restart(stage, marker, args.include_ocr, backend_port, args.start_timeout, args.docker_timeout)
        assert_marker_after_backfront_update(stage, marker, args.include_ocr, backend_port, args.start_timeout, args.docker_timeout)
        persistent_files = assert_persistent_file_markers(persistent_markers)
        status.update(
            {
                "status": "ok",
                "dashboard_keys": sorted(dashboard.keys())[:20],
                "frontend_pages": frontend_pages,
                "postgres_marker": marker,
                "data_survived_restart": True,
                "data_survived_backfront_update": True,
                "persistent_files_survived_restart": persistent_files,
            }
        )
    finally:
        run(compose_args(args.include_ocr) + ["down"], cwd=stage, check=False, timeout_sec=min(60, args.docker_timeout))
        if args.keep_workdir:
            status["kept_workdir"] = str(workdir)
        else:
            workdir_obj.cleanup()

    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
