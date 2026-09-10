from __future__ import annotations

from app.routers.health import preflight_report


def test_preflight_report_exposes_runtime_dependencies_and_paths():
    payload = preflight_report()

    assert payload["ok"] is True
    assert payload["service"] == "x-files-backfront-new-back"
    assert "out" in payload["paths"]
    assert "duckdb" in payload["paths"]
    assert "state" in payload["paths"]
    assert "cache" in payload["paths"]
    assert "available" in payload["telethon"]
    assert "configured" in payload["redis"]
    assert "configured" in payload["rabbitmq"]
    assert "runtime_dir" in payload["license"]


def test_telethon_dependency_is_declared_and_reported_by_preflight():
    requirements = open("requirements.txt", encoding="utf-8").read()
    assert "telethon==" in requirements

    payload = preflight_report()
    assert set(payload["telethon"]).issuperset({"available", "error"})
    assert isinstance(payload["telethon"]["available"], bool)
