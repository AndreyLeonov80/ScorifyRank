import unittest

import back
import x_files_root.root as root
from x_files_license.tariffs import tariff_catalog, tariff_features, tariff_license_limits, tariff_source_limit


class XFilesTariffCatalogTest(unittest.TestCase):
    def test_tariff_catalog_contains_backend_enforcement_matrix(self):
        plans = {item["key"]: item for item in tariff_catalog()}

        self.assertIn("free-demo", plans)
        self.assertIn("free-demo-first-touch-vip", plans)
        self.assertIn("starter", plans)
        self.assertIn("growth-20", plans)
        self.assertIn("growth-50", plans)
        self.assertIn("growth-100", plans)
        self.assertIn("enterprise", plans)

        for key, plan in plans.items():
            with self.subTest(plan=key):
                self.assertTrue(plan["features"]["postgresql"])
                self.assertTrue(plan["features"]["deals"])
                self.assertIn("telegram_sources_total", plan)
                self.assertIn("example_allocation", plan)

    def test_ocr_starts_from_starter_and_free_demo_keeps_postgres_deals(self):
        self.assertTrue(tariff_features("free-demo")["postgresql"])
        self.assertTrue(tariff_features("free-demo")["deals"])
        self.assertFalse(tariff_features("free-demo")["ocr"])
        self.assertTrue(tariff_features("starter")["ocr"])
        self.assertTrue(tariff_features("growth-20")["ocr"])

    def test_sum_source_limits_match_requested_tariffs(self):
        self.assertEqual(tariff_source_limit("free-demo"), 2)
        self.assertEqual(tariff_source_limit("starter"), 6)
        self.assertEqual(tariff_source_limit("growth-20"), 20)
        self.assertEqual(tariff_source_limit("growth-50"), 50)
        self.assertEqual(tariff_source_limit("growth-100"), 100)
        self.assertIsNone(tariff_source_limit("enterprise"))

        self.assertEqual(tariff_license_limits("starter")["telegram_sources_total"], 6)
        self.assertEqual(tariff_license_limits("growth-50")["channels_chats_bots_total"], 50)
        self.assertNotIn("telegram_sources_total", tariff_license_limits("enterprise"))

    def test_root_uses_same_tariff_catalog_for_invites(self):
        self.assertIs(root.PLAN_DEFS, root.TARIFF_PLANS)
        self.assertEqual(root.PLAN_DEFS["starter"]["telegram_sources_total"], 6)
        self.assertTrue(root.tariff_features("starter")["ocr"])

    def test_tariff_source_usage_warns_before_limit_and_suggests_upgrade(self):
        usage = back._xfiles_tariff_source_usage_payload(
            status_payload={
                "ok": True,
                "plan": "starter",
                "limits": {"telegram_sources_total": 6},
            },
            selectors=["a", "b", "c", "d", "e"],
        )

        self.assertEqual(usage["used"], 5)
        self.assertEqual(usage["limit"], 6)
        self.assertEqual(usage["severity"], "warning")
        self.assertTrue(usage["messages"])
        self.assertIn("Growth 20", usage["upgrade_hint"])

    def test_tariff_source_usage_marks_blocked_at_limit(self):
        usage = back._xfiles_tariff_source_usage_payload(
            status_payload={
                "ok": True,
                "plan": "free-demo",
                "limits": {"telegram_sources_total": 2},
            },
            selectors=["channel-a", "channel-b"],
        )

        self.assertEqual(usage["severity"], "blocked")
        self.assertEqual(usage["remaining"], 0)


if __name__ == "__main__":
    unittest.main()
