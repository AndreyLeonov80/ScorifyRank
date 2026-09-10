from pathlib import Path
import importlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_app(provider: str):
    sys.modules.pop("app.crm_export_app", None)
    import os

    os.environ["CRM_EXPORT_PROVIDER"] = provider
    return importlib.import_module("app.crm_export_app")


def test_standalone_bitrix24_app_imports():
    module = _load_app("bitrix24")

    assert module.PROVIDER == "bitrix24"
    assert module.app.title == "GramLead Bitrix24 Export"
    assert any(getattr(route, "path", "") == "/api/settings" for route in module.app.routes)


def test_standalone_amocrm_app_imports():
    module = _load_app("amocrm")

    assert module.PROVIDER == "amocrm"
    assert module.app.title == "GramLead amoCRM Export"
    assert any(getattr(route, "path", "") == "/api/settings" for route in module.app.routes)
