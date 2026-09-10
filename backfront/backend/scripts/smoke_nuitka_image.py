#!/usr/bin/env python3
"""Smoke-test and audit a compiled x-files-client-backfront image.

The script is intentionally small and CI-friendly:

1. Optionally builds Dockerfile.nuitka.
2. Starts the image in a temporary container.
3. Checks /api/payme/dashboard/summary from inside the container.
4. Prints image size and release labels.
5. Fails if backend Python sources are present in /app or /src.
6. Fails if release noise or customer data files are present in the runtime image.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE = "x-files-client-backfront:nuitka-dev"
DEFAULT_DOCKER_CLI_TIMEOUT_SEC = int(os.environ.get("XFILES_DOCKER_COMMAND_TIMEOUT_SEC", "90") or "90")
DEFAULT_BUILD_TIMEOUT_SEC = int(os.environ.get("XFILES_NUITKA_BUILD_TIMEOUT_SEC", "1800") or "1800")


def _timeout_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def run(
    args: list[str],
    *,
    check: bool = True,
    timeout_sec: Optional[int] = DEFAULT_DOCKER_CLI_TIMEOUT_SEC,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        partial_output = _timeout_output(exc.stdout) + _timeout_output(exc.stderr)
        raise RuntimeError(
            f"{' '.join(args)} timed out after {timeout_sec}s\n"
            f"{partial_output.strip()}"
        ) from exc
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed with {result.returncode}\n{result.stdout}")
    return result


def build_image(image: str, build_timeout_sec: int) -> None:
    run(
        [
            "docker",
            "build",
            "-f",
            "Dockerfile.nuitka",
            "-t",
            image,
            "--build-arg",
            f"BUILD_VERSION={os.environ.get('BUILD_VERSION', 'nuitka-dev')}",
            "--build-arg",
            f"BUILD_COMMIT={os.environ.get('BUILD_COMMIT', 'local')}",
            "--build-arg",
            f"BUILD_DATE={os.environ.get('BUILD_DATE', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))}",
            "--build-arg",
            f"RELEASE_CHANNEL={os.environ.get('RELEASE_CHANNEL', 'dev')}",
            ".",
        ],
        timeout_sec=build_timeout_sec,
    )


def inspect_image(image: str, docker_timeout_sec: int) -> dict[str, Any]:
    result = run(["docker", "image", "inspect", image], timeout_sec=docker_timeout_sec)
    payload = json.loads(result.stdout)
    if not payload:
        raise RuntimeError(f"Image {image} was not found")
    return payload[0]


def wait_for_dashboard(container: str, timeout_sec: int, docker_timeout_sec: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_output = ""
    probe = (
        "import json, urllib.request; "
        "data=urllib.request.urlopen('http://127.0.0.1:8001/api/payme/dashboard/summary', timeout=3).read(); "
        "print(data.decode())"
    )
    while time.monotonic() < deadline:
        result = run(
            ["docker", "exec", container, "python", "-c", probe],
            check=False,
            timeout_sec=min(8, docker_timeout_sec),
        )
        last_output = result.stdout.strip()
        if result.returncode == 0 and last_output:
            return json.loads(last_output)
        time.sleep(1)
    raise RuntimeError(f"Dashboard endpoint did not answer in {timeout_sec}s\nLast output:\n{last_output}")


def wait_for_frontend(container: str, timeout_sec: int, docker_timeout_sec: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last_output = ""
    probe = (
        "import json, urllib.request; "
        "text=urllib.request.urlopen('http://127.0.0.1:8001/dashboard.html', timeout=3).read().decode('utf-8', 'replace'); "
        "print(json.dumps({'has_dashboard': 'Dashboard' in text, 'has_dashboard_js': 'js/react.dashboard.js' in text, 'length': len(text)}))"
    )
    while time.monotonic() < deadline:
        result = run(
            ["docker", "exec", container, "python", "-c", probe],
            check=False,
            timeout_sec=min(8, docker_timeout_sec),
        )
        last_output = result.stdout.strip()
        if result.returncode == 0 and last_output:
            payload = json.loads(last_output)
            if payload.get("has_dashboard") and payload.get("has_dashboard_js"):
                return payload
        time.sleep(1)
    raise RuntimeError(f"Dashboard frontend did not answer in {timeout_sec}s\nLast output:\n{last_output}")


def assert_no_backend_sources(container: str, docker_timeout_sec: int) -> list[str]:
    find_cmd = "find /app /src -maxdepth 4 -type f \\( -name '*.py' -o -name '*.pyc' \\) 2>/dev/null || true"
    result = run(["docker", "exec", container, "sh", "-c", find_cmd], timeout_sec=docker_timeout_sec)
    leaked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if leaked:
        raise RuntimeError("Backend Python sources leaked into runtime image:\n" + "\n".join(leaked))
    return leaked


def assert_no_baked_release_noise_or_client_data(image: str, docker_timeout_sec: int) -> list[str]:
    """Audit files that must never be baked into the customer runtime image.

    The running backend can create ephemeral files in /data during smoke startup.
    That is fine when /data is backed by x-files-client-db/volumes. This audit
    runs before the app starts, with a shell entrypoint, so it catches only files
    that were baked into the image layers.
    """

    find_cmd = (
        "find /app /src /data -maxdepth 6 "
        "\\( "
        "-name '.git' -o -path '*/.git/*' -o "
        "-name '*.jsonl' -o -name '*.duckdb' -o -name '*.sqlite' -o -name '*.db' -o "
        "-name 'PG_VERSION' -o -path '*/base/*' -o -path '*/global/*' -o "
        "-name '*.session' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.png' -o -name '*.mp4' -o "
        "-name '*.zip' -o -name '*.docx' "
        "\\) -print 2>/dev/null || true"
    )
    result = run(
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", find_cmd],
        timeout_sec=docker_timeout_sec,
    )
    leaked = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if leaked:
        raise RuntimeError("Release noise or customer data leaked into runtime image:\n" + "\n".join(leaked))
    return leaked


def smoke_image(image: str, timeout_sec: int, docker_timeout_sec: int) -> dict[str, Any]:
    name = f"x-files-nuitka-smoke-{int(time.time())}"
    run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            name,
            "-e",
            "PAYME_STARTUP_TELEGRAM_BOOTSTRAP=0",
            "-e",
            "WEB_PORT=8001",
            "-e",
            "TELEGRAM_SESSION=/data/state/tg_export_session",
            image,
        ],
        timeout_sec=docker_timeout_sec,
    )
    try:
        dashboard = wait_for_dashboard(name, timeout_sec, docker_timeout_sec)
        frontend = wait_for_frontend(name, timeout_sec, docker_timeout_sec)
        source_leaks = assert_no_backend_sources(name, docker_timeout_sec)
    finally:
        run(["docker", "stop", name], check=False, timeout_sec=min(30, docker_timeout_sec))
    return {"dashboard": dashboard, "frontend": frontend, "source_leaks": source_leaks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Nuitka Docker image for X-Files client runtime")
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--build", action="store_true", help="Build Dockerfile.nuitka before smoke-test")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--build-timeout",
        type=int,
        default=DEFAULT_BUILD_TIMEOUT_SEC,
        help="Hard timeout for docker build in seconds. Prevents stuck Docker daemon/builds from hanging CI.",
    )
    parser.add_argument(
        "--docker-timeout",
        type=int,
        default=DEFAULT_DOCKER_CLI_TIMEOUT_SEC,
        help="Hard timeout for each docker CLI command in seconds. Keeps local smoke checks from hanging forever.",
    )
    args = parser.parse_args()

    if args.build:
        build_image(args.image, args.build_timeout)

    image_info = inspect_image(args.image, args.docker_timeout)
    baked_data_leaks = assert_no_baked_release_noise_or_client_data(args.image, args.docker_timeout)
    smoke = smoke_image(args.image, args.timeout, args.docker_timeout)
    dashboard = smoke["dashboard"]
    labels = image_info.get("Config", {}).get("Labels", {}) or {}
    size_mb = int(image_info.get("Size", 0)) / 1024 / 1024

    print(
        json.dumps(
            {
                "status": "ok",
                "image": args.image,
                "size_mb": round(size_mb, 1),
                "version": labels.get("org.opencontainers.image.version"),
                "revision": labels.get("org.opencontainers.image.revision"),
                "dashboard_keys": sorted(dashboard.keys())[:20],
                "frontend": smoke["frontend"],
                "source_leaks": smoke["source_leaks"],
                "data_leaks": baked_data_leaks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
