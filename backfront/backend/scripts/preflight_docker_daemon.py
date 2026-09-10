#!/usr/bin/env python3
"""Fast preflight for Docker daemon availability.

Runtime ZIP and Nuitka smoke tests are intentionally heavier: they build or run
containers. This preflight is a tiny guard that fails quickly when Docker CLI or
the daemon is unavailable, so acceptance work does not hang on `docker ps`.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TIMEOUT_SEC = 8
STALE_PROCESS_TIMEOUT_SEC = 3
DEFAULT_RUNTIME_PORTS = (8008, 8009, 5433, 6379, 15672)
DEFAULT_DATA_SUBDIRS = ("state", "out", "cache", "db", "tg-session", "license-runtime")
OLD_CONTAINER_NAMES = (
    "x-files-client-backfront",
    "x-files-root",
    "x-files-root-postgres",
    "x-files-root-web",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    command: list[str]
    ok: bool
    returncode: int | None
    timed_out: bool
    output: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "ok": self.ok,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "output": self.output[-2000:],
        }


def run_check(name: str, command: list[str], timeout_sec: int) -> CheckResult:
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        output = ""
        if exc.stdout:
            output += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            output += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
        return CheckResult(name, command, False, None, True, output.strip())
    return CheckResult(name, command, result.returncode == 0, result.returncode, False, result.stdout.strip())


def build_checks(args: argparse.Namespace) -> list[tuple[str, list[str], int]]:
    checks: list[tuple[str, list[str], int]] = [
        ("docker_cli", ["docker", "--version"], min(args.timeout, 5)),
        ("docker_daemon", ["docker", "version", "--format", "{{.Server.Version}}"], args.timeout),
        ("docker_ps", ["docker", "ps", "--format", "{{.Names}}\\t{{.Image}}\\t{{.Status}}"], args.timeout),
    ]
    if args.image:
        checks.append(
            (
                "docker_image",
                ["docker", "image", "inspect", args.image, "--format", "{{.Id}} {{.Size}}"],
                args.timeout,
            )
        )
    return checks


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, int(port))) != 0


def run_local_runtime_checks(args: argparse.Namespace, docker_ps: CheckResult | None = None) -> list[CheckResult]:
    if not args.check_local_runtime:
        return []
    checks: list[CheckResult] = []
    ports = [int(item.strip()) for item in str(args.local_ports or "").split(",") if item.strip()]
    occupied = [port for port in ports if not port_is_free(args.local_bind, port)]
    checks.append(
        CheckResult(
            "local_ports_free",
            ["socket", args.local_bind, ",".join(str(port) for port in ports)],
            not occupied,
            0 if not occupied else 1,
            False,
            "" if not occupied else f"Occupied ports on {args.local_bind}: {', '.join(map(str, occupied))}",
        )
    )

    data_root = Path(args.data_root).expanduser()
    missing = [name for name in DEFAULT_DATA_SUBDIRS if not (data_root / name).exists()]
    checks.append(
        CheckResult(
            "client_data_dirs_exist",
            ["stat", str(data_root)],
            not missing,
            0 if not missing else 1,
            False,
            "" if not missing else f"Missing data directories under {data_root}: {', '.join(missing)}",
        )
    )

    ps_output = docker_ps.output if docker_ps is not None else ""
    conflicts = sorted({name for name in OLD_CONTAINER_NAMES if name in ps_output})
    checks.append(
        CheckResult(
            "old_container_names_absent",
            ["docker", "ps", "--format", "{{.Names}}"],
            not conflicts,
            0 if not conflicts else 1,
            False,
            "" if not conflicts else f"Old/conflicting containers are present: {', '.join(conflicts)}",
        )
    )
    return checks


def find_docker_cli_processes() -> dict[str, Any]:
    """Return a best-effort list of Docker CLI commands that may be stuck."""

    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=STALE_PROCESS_TIMEOUT_SEC,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should never break preflight.
        return {"available": False, "error": repr(exc), "processes": []}

    current_pid = str(os.getpid())
    processes: list[dict[str, str]] = []
    interesting = ("docker ps", "docker version", "docker image inspect", "docker compose")
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pid, _, command = line.partition(" ")
        if pid == current_pid:
            continue
        if any(marker in command for marker in interesting):
            processes.append({"pid": pid, "command": command[:500]})
    return {"available": True, "error": "", "processes": processes[:20]}


def find_docker_desktop_processes() -> dict[str, Any]:
    """Return Docker Desktop backend processes to explain daemon timeouts."""

    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,etime=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=STALE_PROCESS_TIMEOUT_SEC,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics should never break preflight.
        return {"available": False, "error": repr(exc), "processes": []}

    current_pid = str(os.getpid())
    processes: list[dict[str, str]] = []
    interesting = (
        "com.docker.backend",
        "com.docker.virtualization",
        "Docker Desktop.app",
        "com.docker.build",
    )
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        pid, etime, command = parts
        if pid == current_pid:
            continue
        if any(marker in command for marker in interesting):
            processes.append({"pid": pid, "etime": etime, "command": command[:500]})
    return {"available": True, "error": "", "count": len(processes), "processes": processes[:20]}


def render_human(payload: dict[str, Any]) -> str:
    lines = [
        f"Docker preflight: {'OK' if payload['ok'] else 'FAILED'}",
        f"timeout_sec: {payload['timeout_sec']}",
    ]
    for check in payload["checks"]:
        status = "OK" if check["ok"] else "FAIL"
        if check["timed_out"]:
            status = "TIMEOUT"
        lines.append(f"- {check['name']}: {status}")
        if not check["ok"] and check["output"]:
            lines.append(f"  {check['output']}")
    diagnostics = payload.get("diagnostics", {})
    stale = diagnostics.get("docker_cli_processes", {})
    if stale.get("processes"):
        lines.append("Potential stuck Docker CLI commands:")
        for process in stale["processes"]:
            lines.append(f"- pid {process['pid']}: {process['command']}")
    desktop = diagnostics.get("docker_desktop_processes", {})
    if desktop.get("processes") and not payload["ok"]:
        lines.append("Docker Desktop backend processes:")
        for process in desktop["processes"]:
            lines.append(f"- pid {process['pid']} ({process['etime']}): {process['command']}")
    if not payload["ok"]:
        lines.append(
            "Hint: restart Docker Desktop, then rerun this preflight before runtime ZIP/Nuitka smoke tests."
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Docker CLI/daemon before heavier X-Files smoke tests.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="Per-command timeout in seconds.")
    parser.add_argument("--image", default="", help="Optional image to inspect, for example x-files-client-backfront:nuitka-dev.")
    parser.add_argument("--check-local-runtime", action="store_true", help="Also check local ports, data dirs, and old container names.")
    parser.add_argument("--local-bind", default="127.0.0.1", help="Host bind address for local port checks.")
    parser.add_argument(
        "--local-ports",
        default=",".join(str(port) for port in DEFAULT_RUNTIME_PORTS),
        help="Comma-separated local ports expected to be free before creating a fresh runtime.",
    )
    parser.add_argument(
        "--data-root",
        default=str(Path.cwd() / "x-files-client-db/docker-data/client"),
        help="Client data root that must contain persistent subdirectories.",
    )
    parser.add_argument("--human", action="store_true", help="Print a human-readable report instead of JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = [run_check(name, command, timeout) for name, command, timeout in build_checks(args)]
    docker_ps = next((check for check in checks if check.name == "docker_ps"), None)
    checks.extend(run_local_runtime_checks(args, docker_ps=docker_ps))
    payload = {
        "ok": all(check.ok for check in checks),
        "timeout_sec": args.timeout,
        "checks": [check.as_dict() for check in checks],
        "diagnostics": {
            "docker_cli_processes": find_docker_cli_processes(),
            "docker_desktop_processes": find_docker_desktop_processes(),
            "recovery_hint": (
                "Restart Docker Desktop, then rerun this preflight before runtime ZIP/Nuitka smoke tests."
            ),
        },
    }
    if args.human:
        print(render_human(payload))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
