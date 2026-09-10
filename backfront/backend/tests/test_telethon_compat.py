import unittest

from app.core import telethon_compat


class TelethonCompatTest(unittest.TestCase):
    def test_compat_module_always_exports_backend_names(self) -> None:
        for name in (
            "TelegramClient",
            "events",
            "AuthKeyUnregisteredError",
            "FloodWaitError",
            "PeerFloodError",
            "TelegramMessage",
            "TELETHON_AVAILABLE",
        ):
            self.assertTrue(hasattr(telethon_compat, name), name)

    def test_missing_telethon_fails_at_client_creation_not_import_time(self) -> None:
        if telethon_compat.TELETHON_AVAILABLE:
            self.skipTest("Telethon is installed in this environment")

        with self.assertRaisesRegex(RuntimeError, "Telethon is not installed"):
            telethon_compat.TelegramClient("session", 1, "hash")


if __name__ == "__main__":
    unittest.main()
