from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.crm_exports import amocrm


def test_amocrm_settings_masks_tokens(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(amocrm, "STATE_PATH", tmp_path / "amocrm.json")

    saved = amocrm.save_settings(
        amocrm.AmoCrmConnectionPayload(
            subdomain="https://company.amocrm.ru/",
            client_id="client-id",
            client_secret="client-secret-value",
            redirect_uri="https://gramlead.local/amocrm/callback",
            access_token="access-token-value",
            refresh_token="refresh-token-value",
            selected_pipeline_id="123",
            selected_status_id="456",
            dry_run_limit=10,
        )
    )

    assert saved["ok"] is True
    assert saved["settings"]["subdomain"] == "company.amocrm.ru"
    assert "access_token" not in saved["settings"]
    assert "refresh_token" not in saved["settings"]
    assert saved["settings"]["access_token_configured"] is True
    assert "access-token-value" not in str(saved)


def test_amocrm_dry_run_builds_contact_lead_and_note(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(amocrm, "STATE_PATH", tmp_path / "amocrm.json")
    monkeypatch.setattr(
        amocrm,
        "_load_crm_contact_rows",
        lambda limit: [
            {
                "contact_key": "telegram:chat:42",
                "fio": "Иван Иванов",
                "username": "ivan",
                "sender_id": 42,
                "phones": ["+79990000000"],
                "emails": ["ivan@example.com"],
                "latest_lead": "breakfast",
                "latest_message_text": "хочу узнать подробнее",
                "message_id": 1001,
                "score": 0.8,
                "last_message_at": "2026-06-04T09:00:00+00:00",
            }
        ],
    )

    result = amocrm.dry_run(amocrm.AmoCrmRunPayload(dry_run=True, limit=1))

    assert result["ok"] is True
    assert result["counts"]["contacts"] == 1
    assert result["counts"]["leads"] == 1
    assert result["counts"]["notes"] == 1
    contact_fields = result["sample"]["contact"]["custom_fields_values"]
    lead_fields = result["sample"]["lead"]["custom_fields_values"]
    assert any(item.get("field_name") == "GramLead External ID" for item in contact_fields)
    assert any(item.get("field_name") == "GramLead Message ID" for item in lead_fields)


def test_amocrm_client_builds_method_url():
    client = amocrm.AmoCrmClient({"subdomain": "company.amocrm.ru", "access_token": "token"})

    assert client._method_url("/api/v4/account") == "https://company.amocrm.ru/api/v4/account"


def test_amocrm_setup_custom_fields_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(amocrm, "STATE_PATH", tmp_path / "amocrm.json")

    result = amocrm.setup_custom_fields(dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["custom_fields"]
    assert {item["entity"] for item in result["custom_fields"]} == {"contacts", "leads"}
