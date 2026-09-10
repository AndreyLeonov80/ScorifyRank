import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "release_client_zips.sh"


class ReleaseClientZipScriptTest(unittest.TestCase):
    def run_dry(self, *args: str) -> list[dict]:
        completed = subprocess.run(
            ["bash", str(SCRIPT), "--dry-run", *args],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_dry_run_can_build_windows_only_payload(self) -> None:
        payloads = self.run_dry(
            "--win",
            "2",
            "--mac",
            "0",
            "--output-root",
            "/tmp/releases",
            "--valid-until",
            "2026-07-01",
        )

        self.assertEqual(1, len(payloads))
        self.assertEqual(["windows"], payloads[0]["platforms"])
        self.assertEqual(2, payloads[0]["count"])
        self.assertEqual("2026-07-01", payloads[0]["valid_until"])
        self.assertEqual("/tmp/releases/win", payloads[0]["output_dirs"]["windows"])
        self.assertEqual("/tmp/releases/mac", payloads[0]["output_dirs"]["mac"])

    def test_dry_run_can_build_mac_only_payload(self) -> None:
        payloads = self.run_dry(
            "--win",
            "0",
            "--mac",
            "1",
            "--output-root",
            "/tmp/releases",
        )

        self.assertEqual(1, len(payloads))
        self.assertEqual(["mac"], payloads[0]["platforms"])
        self.assertEqual(1, payloads[0]["count"])


if __name__ == "__main__":
    unittest.main()
