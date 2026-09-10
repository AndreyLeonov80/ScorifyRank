import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import back


def _root_signature(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class XFilesUpdateStatusTest(unittest.TestCase):
    def test_update_status_reports_missing_manifest_without_blocking_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "release-manifest.json")
            with patch.dict(
                os.environ,
                {
                    "XFILES_RELEASE_MANIFEST_PATH": missing,
                    "XFILES_RELEASE_SIGNING_SECRET": "",
                    "XFILES_ROOT_SIGNING_SECRET": "",
                },
            ):
                status = back._xfiles_update_status_payload()

        self.assertFalse(status["ok"])
        self.assertEqual(status["status"], "manifest_missing")
        self.assertFalse(status["manifest_exists"])

    def test_update_status_verifies_signed_release_manifest_when_secret_is_available(self):
        secret = "test-release-secret"
        payload = {
            "schema": "x-files-release-manifest/v1",
            "release": "2026.05.09-test",
            "images": {"x-files-client-backfront": "x-files-client-backfront:2026.05.09-test"},
            "image_digests": {"x-files-client-backfront": "sha256:" + "a" * 64},
            "image_refs": {"x-files-client-backfront": "x-files-client-backfront:2026.05.09-test@sha256:" + "a" * 64},
            "files": [],
        }
        document = {
            "payload": payload,
            "signature_algorithm": "HMAC-SHA256",
            "signature": _root_signature(payload, secret),
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "release-manifest.json"
            manifest.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "XFILES_RELEASE_MANIFEST_PATH": str(manifest),
                    "XFILES_RELEASE_SIGNING_SECRET": secret,
                    "XFILES_ROOT_SIGNING_SECRET": "",
                },
            ):
                status = back._xfiles_update_status_payload()

        self.assertTrue(status["ok"])
        self.assertEqual(status["status"], "verified")
        self.assertTrue(status["manifest_verified"])
        self.assertEqual(status["release"], "2026.05.09-test")
        self.assertEqual(status["image_digests"]["x-files-client-backfront"], "sha256:" + "a" * 64)


if __name__ == "__main__":
    unittest.main()
