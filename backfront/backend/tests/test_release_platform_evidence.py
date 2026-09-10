import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "collect_release_platform_evidence.py"


def evidence_payload(target: str) -> dict:
    return {
        "ok": True,
        "target": target,
        "actual_target": target,
        "runtime_smoke_required": True,
        "checks": [
            {"name": "target_detected", "ok": True},
            {"name": "docker_linux_containers", "ok": True},
            {"name": "docker_amd64_capable", "ok": True},
        ],
        "runtime_smoke": {
            "ok": True,
            "skipped": False,
            "parsed": {
                "dashboard": {"status": "ok", "url": "http://localhost:8001/dashboard.html"},
                "frontend_pages": [
                    {"path": "/dashboard.html", "expected_text": "Dashboard"},
                    {"path": "/settings.html", "expected_text": "Настройки"},
                    {"path": "/deals.html", "expected_text": "Сделки"},
                    {"path": "/tariffs.html", "expected_text": "Тарифы"},
                ],
                "data_survived_restart": True,
                "data_survived_backfront_update": True,
                "persistent_files_survived_restart": {
                    "telegram_session": True,
                    "license_state": True,
                    "settings": True,
                },
            },
        },
    }


class ReleasePlatformEvidenceTest(unittest.TestCase):
    def test_collects_required_platform_evidence_into_ready_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            mappings = []
            for target in ["windows-linux-containers", "mac-intel", "linux-amd64"]:
                path = base / f"{target}.json"
                path.write_text(json.dumps(evidence_payload(target)), encoding="utf-8")
                mappings.extend(["--evidence", f"{target}={path}"])
            out_path = base / "release-platform-evidence.json"

            result = subprocess.run(
                [sys.executable, str(SCRIPT), *mappings, "--out", str(out_path)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(len(report["results"]), 3)
            self.assertTrue(all(item["ok"] for item in report["results"]))
            self.assertEqual(report["next_steps"], [])

    def test_fails_when_runtime_smoke_was_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "windows.json"
            payload = evidence_payload("windows-linux-containers")
            payload["runtime_smoke"] = {"skipped": True, "reason": "--zip was not provided"}
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--evidence",
                    f"windows-linux-containers={path}",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report["ok"])
            self.assertIn("runtime smoke skipped", report["results"][0]["errors"][0])
            self.assertIn("smoke_release_zip_platform_matrix.py", report["results"][0]["next_step"])
            self.assertIn("windows-linux-containers", report["next_steps"][0])

    def test_fails_when_persistence_markers_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mac-intel.json"
            payload = evidence_payload("mac-intel")
            payload["runtime_smoke"]["parsed"]["persistent_files_survived_restart"]["telegram_session"] = False
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--evidence",
                    f"mac-intel={path}",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report["ok"])
            self.assertTrue(
                any("Telegram session/license/settings" in error for error in report["results"][0]["errors"])
            )
            self.assertIn("mac-intel", report["results"][0]["next_step"])

    def test_human_report_prints_next_step_for_missing_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing-windows.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--evidence",
                    f"windows-linux-containers={missing_path}",
                    "--human",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
            self.assertIn("missing evidence file", result.stdout)
            self.assertIn("next: python3 scripts/smoke_release_zip_platform_matrix.py", result.stdout)
            self.assertIn("--target windows-linux-containers", result.stdout)

    def test_deferred_targets_do_not_fail_current_release_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            windows_path = base / "windows.json"
            windows_path.write_text(json.dumps(evidence_payload("windows-linux-containers")), encoding="utf-8")
            out_path = base / "release-platform-evidence.json"

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--evidence",
                    f"windows-linux-containers={windows_path}",
                    "--defer",
                    "mac-intel",
                    "--defer",
                    "linux-amd64",
                    "--out",
                    str(out_path),
                    "--human",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertIn("mac-intel: DEFERRED", result.stdout)
            report = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["next_steps"], [])
            self.assertEqual(len(report["deferred_steps"]), 2)
            deferred = [item for item in report["results"] if item.get("deferred")]
            self.assertEqual({item["target"] for item in deferred}, {"mac-intel", "linux-amd64"})


if __name__ == "__main__":
    unittest.main()
