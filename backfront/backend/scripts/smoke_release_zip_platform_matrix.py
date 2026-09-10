#!/usr/bin/env python3
"""Cross-platform acceptance runner for an X-Files release ZIP.

This script is intentionally a thin orchestration layer around
``smoke_release_zip_runtime.py``. It does not pretend that Windows or Intel Mac
were tested locally: instead it verifies the current host/platform contract and
then runs the same runtime smoke on that real machine.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SMOKE = ROOT / "scripts" / "smoke_release_zip_runtime.py"
PREFLIGHT = ROOT / "scripts" / "preflight_docker_daemon.py"

TARGETS = (
    "auto",
    "windows-linux-containers",
    "mac-apple-silicon",
    "mac-intel",
    "linux-amd64",
    "linux-arm64",
)


def run(command: list[str], timeout_sec: int, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=check,
        timeout=timeout_sec,
    )


def safe_run(command: list[str], timeout_sec: int, *, output_limit: int | None = 2000) -> dict[str, Any]:
    try:
        result = run(command, timeout_sec)
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout if isinstance(exc.stdout, str) else (exc.stdout or b"").decode("utf-8", "replace")
        if output_limit is not None:
            output = output[-output_limit:]
        return {
            "command": command,
            "ok": False,
            "returncode": None,
            "timed_out": True,
            "output": output.strip(),
        }
    output = result.stdout.strip()
    if output_limit is not None:
        output = output[-output_limit:]
    return {
        "command": command,
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "timed_out": False,
        "output": output,
    }


def normalize_machine(value: str) -> str:
    value = value.lower()
    if value in {"amd64", "x86_64"}:
        return "amd64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    return value


def detect_target() -> str:
    system = platform.system()
    machine = normalize_machine(platform.machine())
    if system == "Windows":
        return "windows-linux-containers"
    if system == "Darwin" and machine == "arm64":
        return "mac-apple-silicon"
    if system == "Darwin" and machine == "amd64":
        return "mac-intel"
    if system == "Linux" and machine == "amd64":
        return "linux-amd64"
    if system == "Linux" and machine == "arm64":
        return "linux-arm64"
    return f"{system.lower()}-{machine}"


def docker_info(timeout_sec: int) -> dict[str, Any]:
    result = safe_run(["docker", "info", "--format", "{{json .}}"], timeout_sec, output_limit=None)
    if not result["ok"]:
        return {"ok": False, "raw": result}
    try:
        info = json.loads(result["output"])
    except json.JSONDecodeError:
        return {"ok": False, "raw": result, "error": "docker info did not return JSON"}
    return {
        "ok": True,
        "OSType": info.get("OSType"),
        "Architecture": normalize_machine(str(info.get("Architecture") or "")),
        "OperatingSystem": info.get("OperatingSystem"),
        "ServerVersion": info.get("ServerVersion"),
    }


def platform_checks(expected_target: str, docker: dict[str, Any]) -> list[dict[str, Any]]:
    actual_target = detect_target()
    checks: list[dict[str, Any]] = [
        {
            "name": "target_detected",
            "ok": expected_target == "auto" or actual_target == expected_target,
            "expected": expected_target,
            "actual": actual_target,
        },
        {
            "name": "docker_linux_containers",
            "ok": docker.get("ok") and docker.get("OSType") == "linux",
            "expected": "linux",
            "actual": docker.get("OSType"),
        },
    ]
    if expected_target in {"linux-amd64", "windows-linux-containers", "mac-intel"}:
        checks.append(
            {
                "name": "docker_amd64_capable",
                "ok": docker.get("ok") and docker.get("Architecture") in {"amd64", "x86_64"},
                "expected": "amd64",
                "actual": docker.get("Architecture"),
            }
        )
    if expected_target in {"linux-arm64", "mac-apple-silicon"}:
        checks.append(
            {
                "name": "docker_arm64_capable",
                "ok": docker.get("ok") and docker.get("Architecture") in {"arm64", "aarch64"},
                "expected": "arm64",
                "actual": docker.get("Architecture"),
            }
        )
    return checks


def run_runtime_smoke(args: argparse.Namespace) -> dict[str, Any]:
    if not args.zip:
        return {"skipped": True, "reason": "--zip was not provided"}

    command = [
        sys.executable,
        str(RUNTIME_SMOKE),
        "--zip",
        str(Path(args.zip).expanduser()),
        "--start-timeout",
        str(args.start_timeout),
        "--docker-timeout",
        str(args.docker_timeout),
    ]
    if args.include_ocr:
        command.append("--include-ocr")
    if args.backfront_image:
        command.extend(["--backfront-image", args.backfront_image])
    if args.db_image:
        command.extend(["--db-image", args.db_image])
    if args.ocr_image:
        command.extend(["--ocr-image", args.ocr_image])

    result = safe_run(command, args.start_timeout + args.docker_timeout * 8)
    parsed: dict[str, Any] | None = None
    if result["ok"]:
        try:
            parsed = json.loads(result["output"])
        except json.JSONDecodeError:
            parsed = None
    return {"ok": result["ok"], "command": command, "result": result, "parsed": parsed}


def render_human(payload: dict[str, Any]) -> str:
    lines = [
        f"X-Files platform smoke: {'OK' if payload['ok'] else 'FAILED'}",
        f"target: {payload['target']}",
        f"actual_target: {payload['actual_target']}",
        f"host: {payload['host']['system']} {payload['host']['machine']}",
        f"docker: {payload['docker']}",
    ]
    lines.append("checks:")
    for check in payload["checks"]:
        lines.append(f"- {check['name']}: {'OK' if check['ok'] else 'FAIL'} ({check.get('actual')})")
    runtime = payload["runtime_smoke"]
    if runtime.get("skipped"):
        lines.append(f"runtime_smoke: skipped ({runtime['reason']})")
        if payload.get("runtime_smoke_required"):
            lines.append("runtime_smoke: REQUIRED, evidence is not complete")
    else:
        lines.append(f"runtime_smoke: {'OK' if runtime.get('ok') else 'FAIL'}")
        parsed = runtime.get("parsed") or {}
        if parsed.get("dashboard"):
            lines.append(f"dashboard: {parsed['dashboard']}")
    if payload.get("evidence_out"):
        lines.append(f"evidence_out: {payload['evidence_out']}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run X-Files release ZIP smoke for a real target platform.")
    parser.add_argument("--target", choices=TARGETS, default="auto", help="Expected platform being certified.")
    parser.add_argument("--zip", default="", help="Optional release ZIP to run through Docker Compose.")
    parser.add_argument("--include-ocr", action="store_true", help="Start OCR profile in runtime smoke.")
    parser.add_argument("--backfront-image", default="", help="Override XFILES_BACKFRONT_IMAGE for local smoke.")
    parser.add_argument("--db-image", default="", help="Override XFILES_DB_IMAGE for local smoke.")
    parser.add_argument("--ocr-image", default="", help="Override XFILES_OCR_IMAGE for local smoke.")
    parser.add_argument("--start-timeout", type=int, default=180)
    parser.add_argument("--docker-timeout", type=int, default=90)
    parser.add_argument("--human", action="store_true", help="Print a human-readable report.")
    parser.add_argument(
        "--evidence-out",
        default="",
        help="Write the full JSON evidence payload to this file for release certification.",
    )
    parser.add_argument(
        "--require-runtime-smoke",
        action="store_true",
        help="Fail if --zip is omitted or runtime smoke is skipped.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    preflight = safe_run([sys.executable, str(PREFLIGHT), "--timeout", str(min(8, args.docker_timeout))], args.docker_timeout)
    docker = docker_info(min(8, args.docker_timeout))
    checks = platform_checks(args.target, docker)
    runtime_smoke = run_runtime_smoke(args) if all(check["ok"] for check in checks) else {"skipped": True, "reason": "platform checks failed"}
    runtime_skipped = bool(runtime_smoke.get("skipped"))
    runtime_ok = bool(runtime_smoke.get("ok")) if not runtime_skipped else not args.require_runtime_smoke
    payload = {
        "ok": all(check["ok"] for check in checks) and runtime_ok,
        "target": args.target,
        "actual_target": detect_target(),
        "host": {"system": platform.system(), "machine": normalize_machine(platform.machine())},
        "docker": docker,
        "preflight": preflight,
        "checks": checks,
        "runtime_smoke_required": bool(args.require_runtime_smoke),
        "runtime_smoke": runtime_smoke,
    }
    if args.evidence_out:
        evidence_path = Path(args.evidence_out).expanduser()
        if not evidence_path.is_absolute():
            evidence_path = ROOT / evidence_path
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        payload["evidence_out"] = str(evidence_path)
        evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.human:
        print(render_human(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
