import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.data_sources.registry import plugin_registry
from app.services.data_sources.service import DataSourceService
from x_files_license.tariffs import license_capabilities

try:
    import duckdb  # type: ignore
except Exception:  # pragma: no cover - optional local dependency
    duckdb = None


class DataSourcePluginTest(unittest.TestCase):
    def test_registry_contains_builtin_plugin_manifests(self):
        registry = plugin_registry()

        manifests = {item.plugin_type: item for item in registry.list_manifests()}

        self.assertIn("telegram", manifests)
        self.assertIn("sqlite", manifests)
        self.assertIn("duckdb", manifests)
        self.assertTrue(manifests["sqlite"].capabilities.incremental_sync)
        self.assertTrue(manifests["duckdb"].capabilities.full_rescan)

    def test_sqlite_plugin_introspects_and_previews_canonical_messages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "external.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    "CREATE TABLE messages (id INTEGER PRIMARY KEY, author TEXT, body TEXT, created_at TEXT)"
                )
                conn.execute(
                    "INSERT INTO messages (author, body, created_at) VALUES (?, ?, ?)",
                    ("Anna", "Нужна консультация по продукту", "2026-05-22T08:00:00+00:00"),
                )

            adapter = plugin_registry().get("sqlite")
            connection = {"path": str(db_path)}

            connect_result = adapter.connect(connection)
            self.assertTrue(connect_result.ok)

            entities = adapter.introspect(connection)
            self.assertEqual(["messages"], [item.entity_key for item in entities])

            preview = adapter.preview(
                connection,
                {
                    "table": "messages",
                    "id_column": "id",
                    "author_column": "author",
                    "text_column": "body",
                    "created_at_column": "created_at",
                },
                limit=5,
            )
            self.assertEqual(1, len(preview))
            self.assertEqual("sqlite", preview[0].source_type)
            self.assertEqual("messages", preview[0].entity_key)
            self.assertEqual("Нужна консультация по продукту", preview[0].text)
            self.assertEqual("Anna", preview[0].author_display_name)

    @unittest.skipIf(duckdb is None, "duckdb package is not installed")
    def test_duckdb_plugin_prefers_read_snapshot_for_writer_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer_path = Path(tmpdir) / "gramlead.duckdb"
            read_path = Path(tmpdir) / "gramlead-read.duckdb"
            writer_conn = duckdb.connect(str(writer_path))
            writer_conn.execute("CREATE TABLE writer_only (id INTEGER)")
            writer_conn.close()
            read_conn = duckdb.connect(str(read_path))
            read_conn.execute("CREATE TABLE messages (id INTEGER, author TEXT, body TEXT, created_at TEXT)")
            read_conn.execute(
                "INSERT INTO messages VALUES (1, 'Anna', 'Snapshot text', '2026-05-26T00:00:00+00:00')"
            )
            read_conn.close()

            adapter = plugin_registry().get("duckdb")
            connection = {"path": str(writer_path)}

            connect_result = adapter.connect(connection)
            self.assertTrue(connect_result.ok)
            self.assertTrue(connect_result.metadata["snapshot_used"])
            self.assertEqual(str(read_path), connect_result.metadata["opened_path"])

            entities = adapter.introspect(connection)
            self.assertEqual(["messages"], [item.entity_key for item in entities])

    def test_service_registers_selects_and_disconnects_plugin_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = DataSourceService(state_path=Path(tmpdir) / "state.json")
            registered = service.register_source(
                {
                    "source_type": "sqlite",
                    "source_name": "External SQLite",
                    "connection": {"path": "/tmp/external.sqlite"},
                    "payload": {"purpose": "smoke"},
                }
            )

            selected = service.select_entity(
                registered.source_id,
                {
                    "entity_key": "messages",
                    "entity_type": "table",
                    "title": "Messages",
                },
            )
            self.assertEqual(f"sqlite:{registered.source_id}:messages", selected.selector)
            self.assertTrue(selected.enabled)

            sources = service.list_sources()
            self.assertEqual(1, len(sources))
            self.assertEqual("External SQLite", sources[0].source_name)
            self.assertTrue(sources[0].entities[0].is_selected)

            disabled = service.disconnect_source(registered.source_id)
            self.assertFalse(disabled.enabled)
            self.assertFalse(disabled.scan_enabled)

    def test_data_source_plugins_license_capability_is_enterprise_only(self):
        free_caps = license_capabilities("free-demo")
        enterprise_caps = license_capabilities("enterprise")

        self.assertFalse(free_caps["data_source_plugins"])
        self.assertTrue(enterprise_caps["data_source_plugins"])
        self.assertEqual(0, enterprise_caps["data_source_plugins_max"])
        self.assertEqual(0, enterprise_caps["data_source_plugin_entities_max"])

    def test_data_source_plugin_routes_are_registered(self):
        client = TestClient(app)

        response = client.get("/api/payme/data-sources/plugins")

        self.assertEqual(200, response.status_code)
        plugin_types = {item["plugin_type"] for item in response.json()["items"]}
        self.assertIn("sqlite", plugin_types)
        self.assertIn("duckdb", plugin_types)


if __name__ == "__main__":
    unittest.main()
