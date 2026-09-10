from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app


@app.get("/api/payme/__test_api_response_shape/http-object")
def _test_http_object_error():
    raise HTTPException(
        status_code=422,
        detail={
            "error": "bad_settings",
            "fields": {"telegram_api_id": "required", "telegram_api_hash": "required"},
        },
    )


@app.get("/api/payme/__test_api_response_shape/unhandled")
def _test_unhandled_error():
    raise RuntimeError("secret internal failure")


def test_validation_errors_have_stable_text_and_structured_detail() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/payme/source-stats", params={"page": "not-int"})

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert isinstance(payload["error"], str)
    assert payload["error"]
    assert "[object Object]" not in payload["error"]
    assert isinstance(payload["detail"], list)
    assert payload["error_code"] == "unknown"
    assert payload["recovery_hint"]


def test_http_exception_object_detail_has_human_error_string() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/payme/__test_api_response_shape/http-object")

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"] == "bad_settings"
    assert payload["detail"]["fields"]["telegram_api_id"] == "required"
    assert "[object Object]" not in payload["error"]


def test_unhandled_errors_hide_internal_detail_and_return_request_id() -> None:
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/payme/__test_api_response_shape/unhandled")

    assert response.status_code == 500
    payload = response.json()
    assert payload["ok"] is False
    assert "secret internal failure" not in payload["error"]
    assert payload["request_id"]
    assert payload["detail"] == "Внутренняя ошибка сервера. Детали сохранены в backend-логе."

