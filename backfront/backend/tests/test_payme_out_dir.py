import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import back


class PaymeOutDirTests(unittest.TestCase):
    def test_ensure_dir_exists_creates_missing_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            self.assertFalse(out_dir.exists())

            with patch.object(back, "PAYME_OUT_DIR", out_dir), patch.object(back, "_sync_legacy_payme_outputs", lambda: None):
                back._ensure_dir_exists()

            self.assertTrue(out_dir.is_dir())
