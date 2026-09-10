import unittest
import copy
from unittest.mock import patch

import back


class FakeCursor:
    def __init__(self) -> None:
        self.calls = []
        self.fetchone_rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql, params=None) -> None:
        self.calls.append((str(sql), params))

    def fetchall(self):
        return []

    def fetchone(self):
        if self.fetchone_rows:
            return self.fetchone_rows.pop(0)
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor_obj = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.commits += 1


class XFilesPostgresMigrationTest(unittest.TestCase):
    def test_migrations_create_deal_and_audit_tables(self) -> None:
        cursor = FakeCursor()

        back._postgres_apply_xfiles_migrations(cursor)

        sql = "\n".join(statement for statement, _params in cursor.calls)
        self.assertIn("CREATE TABLE IF NOT EXISTS xfiles_schema_migrations", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS xfiles_deals", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS xfiles_deal_audit", sql)
        migration_params = [params for statement, params in cursor.calls if "xfiles_schema_migrations" in statement]
        self.assertIn([1, "xfiles_deals_base"], migration_params)
        self.assertIn([2, "xfiles_deal_audit"], migration_params)

    def test_audit_uses_postgres_when_schema_is_available(self) -> None:
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        deal = back.XFilesDealDTO(
            id="deal-pg-audit",
            title="PostgreSQL audit",
            stage="proposal",
            expected_value=100000.0,
            probability=0.5,
            margin=0.4,
            expected_profit=20000.0,
            source="test",
            created_at="2026-05-06T10:00:00+00:00",
            updated_at="2026-05-06T10:00:00+00:00",
        )

        with (
            patch.object(back, "_postgres_ensure_xfiles_schema", return_value=True),
            patch.object(back, "_xfiles_migrate_state_deals_to_postgres_once", return_value=True),
            patch.object(back, "_postgres_connect", return_value=connection),
            patch.object(back.telegram_sync, "save_state", side_effect=AssertionError("state save should not be called")),
        ):
            item = back._xfiles_append_deal_audit("update", deal, changes={"stage": "proposal"})

        sql = "\n".join(statement for statement, _params in cursor.calls)
        self.assertIn("INSERT INTO xfiles_deal_audit", sql)
        self.assertEqual(connection.commits, 1)
        self.assertEqual(item.deal_id, "deal-pg-audit")
        self.assertEqual(item.after_stage, "proposal")

    def test_state_deals_are_migrated_to_postgres_once(self) -> None:
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        original_deals = copy.deepcopy(back.telegram_sync.state.get(back.XFILES_DEALS_STATE_KEY))
        original_audit = copy.deepcopy(back.telegram_sync.state.get(back.XFILES_DEAL_AUDIT_STATE_KEY))
        original_migrated = back._postgres_state_deals_migrated
        original_migration_error = back._postgres_state_deals_migration_last_error
        deal = back.XFilesDealDTO(
            id="deal-state-migrate",
            title="State deal",
            stage="lead",
            expected_value=50000.0,
            probability=0.25,
            margin=0.5,
            expected_profit=6250.0,
            source="state",
            created_at="2026-05-06T10:00:00+00:00",
            updated_at="2026-05-06T10:00:00+00:00",
        )
        audit = back.XFilesDealAuditDTO(
            id="audit-state-migrate",
            ts="2026-05-06T10:01:00+00:00",
            action="create",
            deal_id=deal.id,
            deal_title=deal.title,
            changes={"stage": "lead"},
        )
        try:
            back._postgres_state_deals_migrated = False
            back._postgres_state_deals_migration_last_error = None
            back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = {"items": [deal.model_dump()]}
            back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = {"items": [audit.model_dump()]}

            with (
                patch.object(back, "_postgres_connect", return_value=connection),
                patch.object(back.telegram_sync, "save_state", side_effect=AssertionError("state save should not be called")),
            ):
                migrated = back._xfiles_migrate_state_deals_to_postgres_once()

            sql = "\n".join(statement for statement, _params in cursor.calls)
            self.assertTrue(migrated)
            self.assertTrue(back._postgres_state_deals_migrated)
            self.assertIn("INSERT INTO xfiles_deals", sql)
            self.assertIn("INSERT INTO xfiles_deal_audit", sql)
            self.assertEqual(connection.commits, 1)
        finally:
            back._postgres_state_deals_migrated = original_migrated
            back._postgres_state_deals_migration_last_error = original_migration_error
            if original_deals is None:
                back.telegram_sync.state.pop(back.XFILES_DEALS_STATE_KEY, None)
            else:
                back.telegram_sync.state[back.XFILES_DEALS_STATE_KEY] = original_deals
            if original_audit is None:
                back.telegram_sync.state.pop(back.XFILES_DEAL_AUDIT_STATE_KEY, None)
            else:
                back.telegram_sync.state[back.XFILES_DEAL_AUDIT_STATE_KEY] = original_audit

    def test_audit_loader_reads_postgres_rows(self) -> None:
        row = {
            "id": "audit-1",
            "ts": "2026-05-06T10:00:00+00:00",
            "action": "update",
            "deal_id": "deal-1",
            "deal_title": "Deal",
            "actor": "user",
            "source": "ui",
            "before_stage": "lead",
            "after_stage": "proposal",
            "changes": {"stage": "proposal"},
        }

        item = back._xfiles_audit_from_pg_row(row)

        self.assertIsNotNone(item)
        self.assertEqual(item.id, "audit-1")
        self.assertEqual(item.before_stage, "lead")
        self.assertEqual(item.after_stage, "proposal")
        self.assertEqual(item.changes["stage"], "proposal")


if __name__ == "__main__":
    unittest.main()
