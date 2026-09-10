from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ComposeHealthchecksTest(unittest.TestCase):
    def test_root_and_license_services_have_healthchecks(self) -> None:
        compose = (ROOT / "x-files-client-db" / "docker-compose.yml").read_text(encoding="utf-8")
        for service in ("x-files-root-web", "x-files-license-server"):
            marker = f"  {service}:"
            start = compose.find(marker)
            self.assertNotEqual(-1, start, service)
            next_service = compose.find("\n  x-files-", start + len(marker))
            block = compose[start: next_service if next_service != -1 else len(compose)]
            self.assertIn("healthcheck:", block, service)
            self.assertIn("urllib.request.urlopen", block, service)


if __name__ == "__main__":
    unittest.main()
