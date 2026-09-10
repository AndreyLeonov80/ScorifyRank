import errno
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import back
from app.core.state import StateRepository, load_json_object


class TelegramStateSaveFallbackTests(unittest.TestCase):
    def _new_sync(self, state_path: Path):
        sync = back.TelegramSync.__new__(back.TelegramSync)
        sync.state_path = state_path
        sync.state = {"chat": {"last_message_id": 123}}
        return sync

    def test_save_state_falls_back_when_tmp_file_disappears_before_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            sync = self._new_sync(state_path)

            original_replace = Path.replace

            def replace_missing_tmp(path: Path, target: Path) -> Path:
                if path.name.startswith("state.json.") and path.name.endswith(".tmp"):
                    path.unlink(missing_ok=True)
                    raise FileNotFoundError(errno.ENOENT, "missing tmp", str(path), str(target))
                return original_replace(path, target)

            with patch.object(Path, "replace", replace_missing_tmp):
                sync.save_state()

            self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), sync.state)

    def test_save_state_falls_back_when_atomic_replace_is_busy_or_cross_device(self) -> None:
        for err in (errno.EBUSY, errno.EXDEV):
            with self.subTest(errno=err), tempfile.TemporaryDirectory() as tmpdir:
                state_path = Path(tmpdir) / "state.json"
                sync = self._new_sync(state_path)

                def replace_raises(path: Path, target: Path) -> Path:
                    raise OSError(err, "atomic replace unavailable", str(path), str(target))

                with patch.object(Path, "replace", replace_raises):
                    sync.save_state()

                self.assertEqual(json.loads(state_path.read_text(encoding="utf-8")), sync.state)

    def test_save_state_concurrent_writers_leave_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            errors = []

            def save(index: int) -> None:
                try:
                    sync = self._new_sync(state_path)
                    sync.state = {"writer": index, "nested": {"ok": True}}
                    sync.save_state()
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=save, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual([], errors)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("writer", payload)
            self.assertEqual({"ok": True}, payload["nested"])

    def test_restart_reload_preserves_worker_and_cache_state_after_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "selected_chats": ["@chat_a"],
                        "telegram_import_sync": {"enabled": True, "selectors": ["@chat_a"]},
                        "chat_cache": {"chat_a": {"messages": 30}},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            loaded = load_json_object(state_path)
            sync = self._new_sync(state_path)
            sync.state = {
                **loaded,
                "worker_heartbeat": {"telegram": "2026-05-24T12:00:00+00:00"},
            }

            sync.save_state()
            reloaded = load_json_object(state_path)

        self.assertEqual(["@chat_a"], reloaded["selected_chats"])
        self.assertEqual({"enabled": True, "selectors": ["@chat_a"]}, reloaded["telegram_import_sync"])
        self.assertEqual({"chat_a": {"messages": 30}}, reloaded["chat_cache"])
        self.assertEqual({"telegram": "2026-05-24T12:00:00+00:00"}, reloaded["worker_heartbeat"])

    def test_state_repository_preserves_twenty_parallel_limit_group_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            repository = StateRepository(state_path)
            errors = []

            def save(index: int) -> None:
                try:
                    def mutate(state):
                        limits = state.setdefault("source_limits", {})
                        groups = state.setdefault("source_groups", {})
                        selector = f"@chat_{index}"
                        limits[selector] = {"months": index + 1, "messages": (index + 1) * 100}
                        groups[selector] = "A" if index % 2 == 0 else "C"

                    repository.update(mutate)
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=save, args=(index,)) for index in range(20)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual([], errors)
            reloaded = load_json_object(state_path)

        self.assertEqual(20, len(reloaded["source_limits"]))
        self.assertEqual(20, len(reloaded["source_groups"]))
        self.assertEqual({"months": 20, "messages": 2000}, reloaded["source_limits"]["@chat_19"])
        self.assertEqual("A", reloaded["source_groups"]["@chat_18"])

    def test_state_repository_restart_reload_keeps_latest_limit_and_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            repository = StateRepository(state_path)
            repository.update(
                lambda state: {
                    **state,
                    "source_limits": {"@breakfast_with_harskii": {"months": 2, "messages": 2000}},
                    "source_groups": {"@breakfast_with_harskii": "A"},
                }
            )

            restarted_repository = StateRepository(state_path)
            reloaded = restarted_repository.load()

        self.assertEqual({"months": 2, "messages": 2000}, reloaded["source_limits"]["@breakfast_with_harskii"])
        self.assertEqual("A", reloaded["source_groups"]["@breakfast_with_harskii"])
