import unittest

from fastapi import HTTPException

import back


class HeavyRefreshGuardTest(unittest.TestCase):
    def test_routes_full_refresh_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            back._require_confirmed_full_refresh(True, False, "Маршруты")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("confirm_full_refresh=true", str(ctx.exception.detail))

    def test_duckdb_full_refresh_requires_explicit_confirmation_before_dependency_check(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            back._require_confirmed_full_refresh(True, False, "DuckDB")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("confirm_full_refresh=true", str(ctx.exception.detail))

    def test_incremental_refresh_does_not_require_confirmation(self) -> None:
        back._require_confirmed_full_refresh(False, False, "DuckDB")


if __name__ == "__main__":
    unittest.main()
