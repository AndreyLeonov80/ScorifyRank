#!/usr/bin/env python3
"""Collect platform smoke evidence JSON files into one release readiness report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TARGETS = (
    "windows-linux-containers",
    "mac-intel",
    "linux-amd64",
)

DEFAULT_EVIDENCE_FILES = {
    "windows-linux-containers": "windows-docker-evidence.json",
    "mac-intel": "mac-intel-docker-evidence.json",
    "linux-amd64": "linux-amd64-docker-evidence.json",
    "mac-apple-silicon": "mac-apple-silicon-docker-evidence.json",
    "linux-arm64": "linux-arm64-docker-evidence.json",
}


def platform_smoke_command(target: str, path: Path) -> str:
    display_path = path
    try:
        display_path = path.relative_to(ROOT)
    except ValueError:
        pass
    return (
        "python3 scripts/smoke_release_zip_platform_matrix.py "
        f"--target {target} "
        "--zip dist/x-files-root/releases/<bundle>.zip "
        "--require-runtime-smoke "
        f"--evidence-out {display_path} "
        "--human"
    )


def resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, f"missing evidence file: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {path}: {exc}"


def evidence_paths(args: argparse.Namespace) -> dict[str, Path]:
    if args.evidence:
        paths: dict[str, Path] = {}
        for raw in args.evidence:
            if "=" not in raw:
                raise SystemExit("--evidence must use target=path format")
            target, path = raw.split("=", 1)
            paths[target.strip()] = resolve_path(path.strip())
        return paths

    evidence_dir = resolve_path(args.evidence_dir)
    targets = args.target or list(DEFAULT_TARGETS)
    return {target: evidence_dir / DEFAULT_EVIDENCE_FILES[target] for target in targets}


def check_evidence(
    target: str,
    path: Path,
    payload: dict[str, Any] | None,
    load_error: str | None,
    *,
    deferred: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[str] = []
    next_step = platform_smoke_command(target, path)
    if deferred:
        return {
            "target": target,
            "path": str(path),
            "ok": True,
            "deferred": True,
            "checks": ["deferred-by-current-release-scope"],
            "errors": errors,
            "next_step": next_step,
        }
    if load_error:
        errors.append(load_error)
        return {
            "target": target,
            "path": str(path),
            "ok": False,
            "checks": checks,
            "errors": errors,
            "next_step": next_step,
        }
    assert payload is not None

    if payload.get("ok") is True:
        checks.append("payload-ok")
    else:
        errors.append("payload ok is not true")

    if payload.get("target") == target:
        checks.append("target-matches")
    else:
        errors.append(f"target mismatch: expected {target}, got {payload.get('target')}")

    if payload.get("runtime_smoke_required") is True:
        checks.append("runtime-smoke-required")
    else:
        errors.append("runtime smoke was not required")

    runtime = payload.get("runtime_smoke") or {}
    if runtime.get("skipped"):
        errors.append(f"runtime smoke skipped: {runtime.get('reason')}")
    elif runtime.get("ok") is True:
        checks.append("runtime-smoke-ok")
    else:
        errors.append("runtime smoke did not pass")

    parsed = runtime.get("parsed") or {}
    if parsed.get("dashboard"):
        checks.append("dashboard-checked")
    else:
        errors.append("runtime smoke did not report dashboard check")

    frontend_pages = parsed.get("frontend_pages") or []
    checked_paths = {item.get("path") for item in frontend_pages if isinstance(item, dict)}
    required_pages = {"/dashboard.html", "/settings.html", "/deals.html", "/tariffs.html"}
    missing_pages = sorted(required_pages - checked_paths)
    if missing_pages:
        errors.append(f"runtime smoke did not check required frontend pages: {', '.join(missing_pages)}")
    else:
        checks.append("frontend-pages-checked")

    if parsed.get("data_survived_restart") is True:
        checks.append("postgres-data-survived-restart")
    else:
        errors.append("runtime smoke did not confirm PostgreSQL data survived restart")

    if parsed.get("data_survived_backfront_update") is True:
        checks.append("postgres-data-survived-backfront-update")
    else:
        errors.append("runtime smoke did not confirm PostgreSQL data survived backfront-only update")

    persistent_files = parsed.get("persistent_files_survived_restart") or {}
    required_persistent = {"telegram_session", "license_state", "settings"}
    if isinstance(persistent_files, dict) and all(persistent_files.get(name) is True for name in required_persistent):
        checks.append("telegram-license-settings-survived-restart")
    else:
        errors.append("runtime smoke did not confirm Telegram session/license/settings markers survived restart")

    check_by_name = {item.get("name"): item for item in payload.get("checks", []) if isinstance(item, dict)}
    if (check_by_name.get("docker_linux_containers") or {}).get("ok") is True:
        checks.append("docker-linux-containers")
    else:
        errors.append("docker_linux_containers check is not ok")

    if target in {"windows-linux-containers", "mac-intel", "linux-amd64"}:
        if (check_by_name.get("docker_amd64_capable") or {}).get("ok") is True:
            checks.append("docker-amd64-capable")
        else:
            errors.append("docker_amd64_capable check is not ok")

    return {
        "target": target,
        "path": str(path),
        "ok": not errors,
        "checks": checks,
        "errors": errors,
        "next_step": "" if not errors else next_step,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    paths = evidence_paths(args)
    deferred_targets = set(args.defer or [])
    if deferred_targets:
        evidence_dir = resolve_path(args.evidence_dir)
        for target in sorted(deferred_targets):
            paths.setdefault(target, evidence_dir / DEFAULT_EVIDENCE_FILES[target])
    results = []
    for target, path in paths.items():
        if target in deferred_targets:
            results.append(check_evidence(target, path, None, None, deferred=True))
            continue
        payload, error = load_json(path)
        results.append(check_evidence(target, path, payload, error))
    return {
        "schema": "x-files-platform-evidence-report/v1",
        "ok": all(item["ok"] for item in results),
        "required_targets": list(paths.keys()),
        "results": results,
        "next_steps": [item["next_step"] for item in results if item.get("next_step") and not item.get("deferred")],
        "deferred_steps": [item["next_step"] for item in results if item.get("next_step") and item.get("deferred")],
    }


def render_human(report: dict[str, Any]) -> str:
    lines = [f"X-Files platform evidence: {'OK' if report['ok'] else 'FAILED'}"]
    for item in report["results"]:
        status = "DEFERRED" if item.get("deferred") else ("OK" if item["ok"] else "FAIL")
        lines.append(f"- {item['target']}: {status}")
        for error in item["errors"]:
            lines.append(f"  error: {error}")
        if item.get("next_step"):
            prefix = "deferred next" if item.get("deferred") else "next"
            lines.append(f"  {prefix}: {item['next_step']}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate platform evidence files before marking release ready.")
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(DEFAULT_EVIDENCE_FILES),
        help="Required target. Can be repeated. Defaults to Windows Linux containers, Mac Intel, Linux amd64.",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Explicit evidence mapping in target=path format. Can be repeated.",
    )
    parser.add_argument(
        "--defer",
        action="append",
        choices=tuple(DEFAULT_EVIDENCE_FILES),
        default=[],
        help="Mark a target as intentionally deferred for the current release scope without failing readiness.",
    )
    parser.add_argument("--evidence-dir", default="reports-todo", help="Directory with default evidence file names.")
    parser.add_argument("--out", default="", help="Optional JSON report output path.")
    parser.add_argument("--human", action="store_true", help="Print a human-readable report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.out:
        out_path = resolve_path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.human:
        print(render_human(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
