import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.requests import Request

import app.services.license_runtime as license_runtime


def _request(path: str, method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "server": ("testserver", 80),
            "client": ("testclient", 1234),
        }
    )


class XFilesLicenseRuntimeBlockingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.blocked_status = {
            "ok": False,
            "status": "license_server_unavailable",
            "disabled_reason": "license-server недоступен",
        }
        self.active_status = {"ok": True, "status": "active"}
        self.base_patches = [
            patch.object(license_runtime, "_xfiles_client_delivery_mode", return_value=True),
            patch.object(
                license_runtime,
                "XFILES_LICENSE_BLOCKED_STATUSES",
                {
                    "missing",
                    "not_activated",
                    "expired",
                    "revoked",
                    "license_server_unavailable",
                    "license_server_invalid_response",
                },
                create=True,
            ),
            patch.object(
                license_runtime,
                "XFILES_LICENSE_PUBLIC_API_PREFIXES",
                ("/api/payme/license", "/api/payme/auth", "/api/payme/tariffs"),
                create=True,
            ),
            patch.object(
                license_runtime,
                "XFILES_LICENSE_PUBLIC_API_PATHS",
                {"/api/payme/settings"},
                create=True,
            ),
            patch.object(
                license_runtime,
                "XFILES_LICENSE_RENEWAL_PUBLIC_HTML",
                {"/settings.html"},
                create=True,
            ),
        ]
        for active_patch in self.base_patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

    def test_unchecked_license_redirects_all_html_except_settings(self) -> None:
        with patch.object(license_runtime, "_xfiles_license_status_payload", return_value=self.blocked_status):
            self.assertIsNone(license_runtime._xfiles_renewal_only_response(_request("/settings.html")))

            setup_response = license_runtime._xfiles_renewal_only_response(_request("/setup_wizard.html"))
            self.assertIsInstance(setup_response, RedirectResponse)
            self.assertEqual("/settings.html#license", setup_response.headers["location"])

            index_response = license_runtime._xfiles_renewal_only_response(_request("/"))
            self.assertIsInstance(index_response, RedirectResponse)
            self.assertEqual("/settings.html#license", index_response.headers["location"])

    def test_unchecked_license_blocks_feature_api_but_keeps_settings_and_status_api(self) -> None:
        with patch.object(license_runtime, "_xfiles_license_status_payload", return_value=self.blocked_status):
            self.assertIsNone(license_runtime._xfiles_renewal_only_response(_request("/api/payme/settings")))
            self.assertIsNone(license_runtime._xfiles_renewal_only_response(_request("/api/payme/license/status")))

            response = license_runtime._xfiles_renewal_only_response(_request("/api/payme/telegram/dialogs"))
            self.assertIsInstance(response, JSONResponse)
            self.assertEqual(403, response.status_code)

    def test_active_license_does_not_block_html_or_api(self) -> None:
        with patch.object(license_runtime, "_xfiles_license_status_payload", return_value=self.active_status):
            self.assertIsNone(license_runtime._xfiles_renewal_only_response(_request("/index.html")))
            self.assertIsNone(license_runtime._xfiles_renewal_only_response(_request("/api/payme/telegram/dialogs")))


if __name__ == "__main__":
    unittest.main()
