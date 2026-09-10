from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.crm_exports import bitrix24


def test_bitrix24_settings_masks_secrets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bitrix24, "STATE_PATH", tmp_path / "bitrix24.json")

    saved = bitrix24.save_settings(
        bitrix24.Bitrix24ConnectionPayload(
            portal_url="https://company.bitrix24.ru/",
            auth_mode="webhook",
            webhook_url="https://company.bitrix24.ru/rest/1/secret-token/",
            selected_entity="lead",
            dry_run_limit=10,
        )
    )

    assert saved["ok"] is True
    assert "webhook_url" not in saved["settings"]
    assert saved["settings"]["webhook_configured"] is True
    assert saved["settings"]["webhook_url_masked"].startswith("https:")

    loaded = bitrix24.get_settings()
    assert loaded["settings"]["portal_url"] == "https://company.bitrix24.ru"
    assert "secret-token" not in str(loaded)


def test_bitrix24_dry_run_builds_contact_and_lead(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bitrix24, "STATE_PATH", tmp_path / "bitrix24.json")
    monkeypatch.setattr(
        bitrix24,
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
                "source_title": "Breakfast chat",
                "latest_message_text": "хочу узнать подробнее",
                "message_id": 1001,
                "score": 0.8,
                "last_message_at": "2026-06-04T09:00:00+00:00",
            }
        ],
    )

    result = bitrix24.dry_run(bitrix24.Bitrix24RunPayload(dry_run=True, limit=1))

    assert result["ok"] is True
    assert result["counts"]["contacts"] == 1
    assert result["counts"]["leads"] == 1
    assert result["sample"]["contact"]["UF_CRM_GRAMLEAD_EXTERNAL_ID"] == "gramlead:contact:telegram:chat:42"
    assert result["sample"]["lead"]["UF_CRM_GRAMLEAD_MESSAGE_ID"] == "1001"


def test_bitrix24_client_builds_webhook_method_url():
    client = bitrix24.Bitrix24Client({"auth_mode": "webhook", "webhook_url": "https://portal/rest/1/token/"})

    assert client._method_url("profile") == "https://portal/rest/1/token/profile.json"


def test_bitrix24_settings_can_load_from_local_yaml(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "bitrix24.json"
    yaml_path = tmp_path / "crm_exports.local.yaml"
    yaml_path.write_text(
        """
bitrix24:
  portal_url: "https://b24-k4pmx0.bitrix24.ru/online"
  auth_mode: "webhook"
  webhook_url: "https://b24-k4pmx0.bitrix24.ru/rest/1/real-code/"
  selected_entity: "lead"
  dry_run_limit: 25
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(bitrix24, "STATE_PATH", state_path)
    monkeypatch.setattr(bitrix24, "YAML_CONFIG_PATH", yaml_path)

    loaded = bitrix24.get_settings()

    assert loaded["ok"] is True
    assert loaded["settings"]["portal_url"] == "https://b24-k4pmx0.bitrix24.ru/online"
    assert loaded["settings"]["auth_mode"] == "webhook"
    assert loaded["settings"]["webhook_configured"] is True
    assert "real-code" not in str(loaded)


def test_bitrix24_source_title_from_jsonl():
    assert bitrix24._source_title_from_jsonl("/data/out/breakfast_with_harskii.jsonl") == "breakfast_with_harskii"
    assert bitrix24._source_title_from_jsonl("plain_source") == "plain_source"


def test_bitrix24_setup_custom_fields_dry_run(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bitrix24, "STATE_PATH", tmp_path / "bitrix24.json")

    result = bitrix24.setup_custom_fields(dry_run=True)

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["custom_fields"]
    assert {item["entity"] for item in result["custom_fields"]} == {"contact", "lead"}


def test_bitrix24_contact_payload_contains_message_artifact_links():
    row = {
        "contact_key": "telegram:breakfast:ivan",
        "fio": "Иван Иванов",
        "source": "breakfast",
        "source_title": "Breakfast chat",
        "artifact_jsonl_url": "http://127.0.0.1:8024/files/a.jsonl",
        "artifact_html_url": "http://127.0.0.1:8024/files/a.html",
        "artifact_xlsx_url": "http://127.0.0.1:8024/files/a.xlsx",
        "artifact_docx_url": "http://127.0.0.1:8024/files/a.docx",
        "openrouter_answer": "Покупатель вероятен: спрашивает про цену.",
        "messages_count": 7,
    }

    payload = bitrix24._contact_payload(row, batch_id="batch")

    assert payload["UF_CRM_GRAMLEAD_CONTACT_JSONL_URL"] == row["artifact_jsonl_url"]
    assert payload["UF_CRM_GRAMLEAD_CONTACT_HTML_URL"] == row["artifact_html_url"]
    assert payload["UF_CRM_GRAMLEAD_CONTACT_XLSX_URL"] == row["artifact_xlsx_url"]
    assert payload["UF_CRM_GRAMLEAD_CONTACT_DOCX_URL"] == row["artifact_docx_url"]
    assert payload["UF_CRM_GRAMLEAD_CONTACT_MESSAGES_COUNT"] == 7
    assert "Покупатель вероятен" in payload["COMMENTS"]
    assert "http://127.0.0.1:8024/files/a.docx" in payload["COMMENTS"]
    assert payload["SOURCE_DESCRIPTION"] == "breakfast"


def test_bitrix24_timeline_comment_contains_openrouter_and_links():
    row = {
        "fio": "Иван Иванов",
        "source_title": "Breakfast chat",
        "messages_count": 7,
        "openrouter_answer": "Покупатель вероятен: спрашивает про цену.",
        "artifact_jsonl_url": "http://127.0.0.1:8024/files/a.jsonl",
        "artifact_html_url": "http://127.0.0.1:8024/files/a.html",
        "artifact_xlsx_url": "http://127.0.0.1:8024/files/a.xlsx",
        "artifact_docx_url": "http://127.0.0.1:8024/files/a.docx",
    }

    comment = bitrix24._contact_timeline_comment(row)

    assert "GramLead" in comment
    assert "Покупатель вероятен" in comment
    assert "JSONL" in comment
    assert "DOCX" in comment


def test_bitrix24_writes_contact_message_artifacts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bitrix24, "ARTIFACTS_DIR", tmp_path / "artifacts")
    monkeypatch.setattr(bitrix24, "PUBLIC_BASE_URL", "http://127.0.0.1:8024")
    contact = {
        "contact_key": "telegram:breakfast:ivan",
        "fio": "Иван Иванов",
        "username": "ivan",
        "source_title": "Breakfast chat",
    }
    messages = [
        {
            "message_id": 1,
            "date_utc_raw": "2026-06-05T08:00:00+00:00",
            "sender_username": "ivan",
            "sender_name": "Иван Иванов",
            "text": "Когда ближайшее мероприятие?",
            "source_jsonl": "/data/out/breakfast.jsonl",
        }
    ]

    result = bitrix24._write_contact_message_artifacts(contact, messages, openrouter_answer="Ответ LLM")

    assert result["messages_count"] == 1
    assert Path(result["jsonl_path"]).exists()
    assert Path(result["html_path"]).exists()
    assert Path(result["xlsx_path"]).exists()
    assert Path(result["docx_path"]).exists()
    assert result["jsonl_url"].startswith("http://127.0.0.1:8024/files/")
    assert "Ответ LLM" in Path(result["html_path"]).read_text(encoding="utf-8")
    assert "Когда ближайшее мероприятие?" in Path(result["jsonl_path"]).read_text(encoding="utf-8")


def test_bitrix24_settings_include_openrouter_prompt_and_duckdb_path(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bitrix24, "STATE_PATH", tmp_path / "bitrix24.json")

    saved = bitrix24.save_settings(
        bitrix24.Bitrix24ConnectionPayload(
            portal_url="https://company.bitrix24.ru/",
            auth_mode="webhook",
            webhook_url="https://company.bitrix24.ru/rest/1/secret-token/",
            selected_entity="lead",
            dry_run_limit=10,
            duckdb_read_path="/data/db/duckdb/gramlead-read.duckdb",
            openrouter_api_key="sk-or-test",
            openrouter_model="openai/gpt-oss-120b:free",
            openrouter_prompt="Найди вероятность покупки.",
        )
    )

    assert saved["settings"]["duckdb_read_path"] == "/data/db/duckdb/gramlead-read.duckdb"
    assert saved["settings"]["openrouter_model"] == "openai/gpt-oss-120b:free"
    assert saved["settings"]["openrouter_prompt"] == "Найди вероятность покупки."
    assert "sk-or-test" not in str(saved)


def test_bitrix24_openrouter_settings_fallback_to_owner_app_settings(monkeypatch, tmp_path: Path):
    state_path = tmp_path / "state.json"
    state_path.write_text(
        '{"_app_settings":{"openrouter_api_key":"sk-owner","openrouter_model":"openai/gpt-oss-120b:free"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(bitrix24, "APP_SETTINGS_PATH", state_path)

    settings = bitrix24._openrouter_settings({"openrouter_api_key": "", "openrouter_model": ""})

    assert settings["api_key"] == "sk-owner"
    assert settings["model"] == "openai/gpt-oss-120b:free"
