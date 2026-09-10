import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import back

ROOT = Path(__file__).resolve().parents[1]


class SourcePolicySafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_policy = copy.deepcopy(
            back.telegram_sync.state.get(back.TELEGRAM_SOURCE_POLICY_STATE_KEY)
        )
        self._original_settings = copy.deepcopy(
            back.telegram_sync.state.get(back.APP_SETTINGS_STATE_KEY)
        )
        self._original_risky_state = copy.deepcopy(back.telegram_sync.state.get("risky_chat"))
        back.telegram_sync.state[back.TELEGRAM_SOURCE_POLICY_STATE_KEY] = {"items": {}}

    def tearDown(self) -> None:
        if self._original_policy is None:
            back.telegram_sync.state.pop(back.TELEGRAM_SOURCE_POLICY_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.TELEGRAM_SOURCE_POLICY_STATE_KEY] = self._original_policy
        if self._original_settings is None:
            back.telegram_sync.state.pop(back.APP_SETTINGS_STATE_KEY, None)
        else:
            back.telegram_sync.state[back.APP_SETTINGS_STATE_KEY] = self._original_settings
        if self._original_risky_state is None:
            back.telegram_sync.state.pop("risky_chat", None)
        else:
            back.telegram_sync.state["risky_chat"] = self._original_risky_state
        back._api_snapshot_cache_clear_prefix("leads:")
        back._lead_snapshot_cache["items"] = None

    def test_unknown_sources_are_visible_but_allowed_by_default(self) -> None:
        policy = back._source_policy_for_lead("demo_channel", "@demo_channel")

        self.assertEqual(policy.mode, "unknown")
        self.assertTrue(policy.scan_allowed)

    def test_blocked_source_policy_stops_telegram_scan(self) -> None:
        with patch.object(back.telegram_sync, "save_state", lambda: None):
            policy = back._set_source_policy(
                "blocked_channel",
                "@blocked_channel",
                "blocked",
                "manual risk review",
                source="test",
            )

        self.assertEqual(policy.mode, "blocked")
        self.assertFalse(policy.scan_allowed)
        self.assertFalse(back.telegram_sync._selector_scan_allowed("@blocked_channel"))
        self.assertTrue(back.telegram_sync._selector_scan_allowed("@allowed_channel"))

    def test_risk_error_marks_source_as_blocked(self) -> None:
        with patch.object(back.telegram_sync, "save_state", lambda: None):
            back.telegram_sync._mark_telegram_risk_blocked(
                RuntimeError("privacy or peer flood"),
                "unit test",
                chat_key="risky_chat",
            )

        policy = back._source_policy_for_lead("risky_chat")
        chat_state = back.telegram_sync.get_chat_state("risky_chat")
        self.assertEqual(policy.mode, "blocked")
        self.assertFalse(policy.scan_allowed)
        self.assertEqual(chat_state.get("telegram_status"), "risk_blocked")
        self.assertIn("privacy or peer flood", chat_state.get("last_error", ""))

    def test_outreach_auto_send_is_disabled_by_default(self) -> None:
        settings = back._coerce_app_settings({})

        self.assertFalse(settings["outreach_auto_send_enabled"])

    def test_runtime_code_does_not_depend_on_source_txt(self) -> None:
        checked_files = [
            *ROOT.joinpath("app").rglob("*.py"),
            ROOT / "back.py",
        ]
        offenders = []
        for path in checked_files:
            if "__pycache__" in path.parts:
                continue
            if "source.txt" in path.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(path.relative_to(ROOT)))

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
