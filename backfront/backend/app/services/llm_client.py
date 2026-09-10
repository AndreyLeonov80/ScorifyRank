"""OpenRouter client helpers extracted from the legacy backend."""

from __future__ import annotations

import sys


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime")
    legacy_back = sys.modules.get("back")
    for source in (runtime, legacy_back):
        if source is None:
            continue
        for name, value in vars(source).items():
            if not name.startswith("__") and name != "refresh_legacy_globals":
                globals()[name] = value


refresh_legacy_globals()

def _normalize_openrouter_model_id(value: Optional[str]) -> str:
    raw = str(value or "").strip()
    if raw.startswith("https://openrouter.ai/"):
        raw = raw.replace("https://openrouter.ai/", "", 1).strip("/")
    if raw.startswith("openrouter.ai/"):
        raw = raw.replace("openrouter.ai/", "", 1).strip("/")
    return raw or DEFAULT_OPENROUTER_MODEL_ID


def _record_llm_audit(
    *,
    kind: str,
    provider: str,
    model: str,
    request_payload: Dict[str, Any],
    input_ids: Dict[str, Any],
    started_at: datetime,
    duration_sec: float,
    status: str,
    result_text: str = "",
    response_payload: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> None:
    refresh_legacy_globals()
    try:
        prompt_hash = _stable_json_hash(
            {
                "provider": provider,
                "model": model,
                "messages": request_payload.get("messages") or [],
                "temperature": request_payload.get("temperature"),
                "top_p": request_payload.get("top_p"),
                "max_tokens": request_payload.get("max_tokens"),
                "frequency_penalty": request_payload.get("frequency_penalty"),
                "presence_penalty": request_payload.get("presence_penalty"),
            }
        )
        input_hash = _stable_json_hash(input_ids)
        request_id = hashlib.sha256(f"{kind}:{provider}:{prompt_hash}:{input_hash}".encode("utf-8")).hexdigest()[:24]
        usage = _openrouter_usage_estimate(response_payload, request_payload, result_text)
        cost_estimate_usd = (
            _estimate_openrouter_cost_usd(model, usage["input_tokens"], usage["output_tokens"])
            if provider == "openrouter"
            else 0.0
        )
        response_id = ""
        if isinstance(response_payload, dict):
            response_id = str(response_payload.get("id") or "")
        record = {
            "request_id": request_id,
            "kind": str(kind or "unknown"),
            "provider": str(provider or "unknown"),
            "model": str(model or ""),
            "prompt_hash": prompt_hash,
            "input_ids": input_ids,
            "status": str(status or "unknown"),
            "result": str(result_text or "")[:12000],
            "result_hash": hashlib.sha256(str(result_text or "").encode("utf-8")).hexdigest() if result_text else "",
            "duration_sec": round(max(0.0, float(duration_sec or 0.0)), 3),
            "cost_estimate_usd": cost_estimate_usd,
            "input_tokens_estimate": usage["input_tokens"],
            "output_tokens_estimate": usage["output_tokens"],
            "total_tokens_estimate": usage["total_tokens"],
            "response_id": response_id,
            "error": str(error or "")[:1000],
            "created_at": started_at.isoformat(),
        }
        items = [item for item in _xfiles_llm_audit_items() if item.get("request_id") != request_id]
        items.insert(0, record)
        telegram_sync.state[XFILES_LLM_AUDIT_STATE_KEY] = {
            "items": items[:XFILES_LLM_AUDIT_MAX_ITEMS],
            "updated_at": _utc_now().isoformat(),
        }
        telegram_sync.save_state()
    except Exception as exc:
        _append_runtime_log("llm-audit", f"Не удалось сохранить аудит LLM-запроса: {exc}")


def _call_openrouter_chat_completion_sync(
    *,
    kind: str,
    api_key: str,
    payload: Dict[str, Any],
    input_ids: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    refresh_legacy_globals()
    payload = _sanitize_openrouter_payload_for_pii(payload)
    started_at = _utc_now()
    started_monotonic = time.monotonic()
    model = str(payload.get("model") or "")
    response_payload: Optional[Dict[str, Any]] = None
    result_text = ""
    try:
        response = _post_json_with_transient_retries(
            OPENROUTER_CHAT_COMPLETIONS_URL,
            label=f"OpenRouter {kind}",
            headers=_openrouter_headers(api_key),
            json_payload=payload,
            timeout=_openrouter_timeout_sec(),
        )
        raw_payload = response.json()
        response_payload = raw_payload if isinstance(raw_payload, dict) else {}
        try:
            result_text = str(response_payload["choices"][0]["message"]["content"] or "").strip()
        except Exception:
            result_text = ""
        _record_llm_audit(
            kind=kind,
            provider="openrouter",
            model=model,
            request_payload=payload,
            input_ids=input_ids,
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="ready",
            result_text=result_text,
            response_payload=response_payload,
        )
        return response_payload, result_text
    except Exception as exc:
        _record_llm_audit(
            kind=kind,
            provider="openrouter",
            model=model,
            request_payload=payload,
            input_ids=input_ids,
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="error",
            result_text=result_text,
            response_payload=response_payload,
            error=str(exc),
        )
        raise


def _call_openrouter_contact_qualification_sync(
    contact: Dict[str, Any],
    prompt_template: Dict[str, str],
    messages: List[TelegramContactMessageDTO],
) -> Dict[str, str]:
    refresh_legacy_globals()
    settings = _get_app_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenRouter API key не настроен")

    context = _build_contact_qualification_context(str(contact.get("contact_key") or ""), messages)
    if not context:
        raise HTTPException(status_code=400, detail="У контакта нет текстовых сообщений для анализа")

    system_prompt = (
        "Ты CRM-аналитик X-Files. Анализируй только сообщения конкретного Telegram-автора. "
        "Отвечай по-русски, структурно, без markdown-таблиц. Не выдумывай факты; если данных мало, так и скажи."
    )
    user_prompt = (
        f"Контакт: {contact.get('display_name') or contact.get('contact_key')}\n"
        f"Username: {contact.get('sender_username') or '—'}\n"
        f"ID: {contact.get('sender_id') or '—'}\n"
        f"Шаблон задачи: {prompt_template.get('title')}\n"
        f"Промт:\n{prompt_template.get('prompt')}\n\n"
        f"Сообщения контакта в хронологическом порядке:\n{context}"
    )
    payload = {
        "model": _normalize_openrouter_model_id(settings.get("openrouter_model")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(settings.get("openrouter_temperature", 0.2) or 0.2),
        "top_p": float(settings.get("openrouter_top_p", 0.9) or 0.9),
        "max_tokens": min(int(settings.get("openrouter_max_tokens", 2048) or 2048), 4096),
        "frequency_penalty": float(settings.get("openrouter_frequency_penalty", 0.0) or 0.0),
        "presence_penalty": float(settings.get("openrouter_presence_penalty", 0.0) or 0.0),
    }
    _, content = _call_openrouter_chat_completion_sync(
        kind="contact_qualification",
        api_key=api_key,
        payload=payload,
        input_ids={
            "contact_key": str(contact.get("contact_key") or ""),
            "sender_id": str(contact.get("sender_id") or ""),
            "template_id": str(prompt_template.get("id") or prompt_template.get("title") or ""),
            "message_ids": [message.message_id for message in messages],
            "messages_fingerprint": _contact_messages_fingerprint(messages),
        },
    )
    return {"result_text": content, "model": str(payload["model"])}


def _call_openrouter_event_date_sync(row: Dict[str, Any]) -> Dict[str, Any]:
    refresh_legacy_globals()
    settings = _get_app_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    if not api_key:
        return {
            "event_date": None,
            "event_date_confidence": 0.0,
            "event_date_source": "openrouter:no_api_key",
        }

    text = str(row.get("text") or "").strip()
    message_date = str(row.get("date_utc") or "").strip()
    system_prompt = (
        "Ты извлекаешь дату мероприятия из Telegram-сообщения. "
        "Верни только JSON без markdown. Формат: "
        "{\"event_date\":\"YYYY-MM-DD или null\",\"confidence\":0.0,\"reason\":\"коротко\"}. "
        "Если в тексте нет явной даты события, верни null. "
        "Не используй дату публикации сообщения как дату мероприятия без явного указания в тексте."
    )
    user_prompt = (
        f"Дата публикации сообщения: {message_date or 'неизвестно'}\n"
        f"Канал: {row.get('lead') or ''}\n"
        "Полный текст сообщения:\n"
        f"{text[:12000]}"
    )
    payload = {
        "model": _normalize_openrouter_model_id(settings.get("openrouter_model")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": min(float(settings.get("openrouter_temperature", 0.2) or 0.2), 0.2),
        "top_p": float(settings.get("openrouter_top_p", 0.9) or 0.9),
        "max_tokens": min(int(settings.get("openrouter_max_tokens", 2048) or 2048), 256),
    }
    _, content = _call_openrouter_chat_completion_sync(
        kind="event_date",
        api_key=api_key,
        payload=payload,
        input_ids={
            "lead": str(row.get("lead") or ""),
            "message_id": str(row.get("message_id") or ""),
            "row_hash": str(row.get("row_hash") or ""),
            "date_utc": message_date,
        },
    )
    parsed = _extract_json_object_from_text(content)
    event_date = _normalize_llm_event_date(parsed.get("event_date") if parsed else content)
    try:
        confidence = float(parsed.get("confidence", 0.0)) if parsed else (0.6 if event_date else 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "event_date": event_date,
        "event_date_confidence": max(0.0, min(1.0, confidence)),
        "event_date_source": "openrouter" if event_date else "openrouter:none",
    }


def _call_openrouter_route_address_sync(row: Dict[str, Any], model_override: Optional[str] = None) -> Dict[str, Any]:
    refresh_legacy_globals()
    settings = _get_app_settings()
    api_key = str(settings.get("openrouter_api_key") or "").strip()
    if not api_key:
        return {
            "address": None,
            "address_key": None,
            "confidence": 0.0,
            "source": "openrouter:no_api_key",
            "reason": "OpenRouter API key is empty",
        }

    text = str(row.get("text") or "").strip()
    system_prompt = (
        "Ты извлекаешь физический адрес или место в Москве из Telegram-сообщения. "
        "Верни только JSON без markdown. Формат: "
        "{\"address\":\"строка или null\",\"confidence\":0.0,\"reason\":\"коротко\",\"lat\":null,\"lon\":null}. "
        "Если в сообщении есть только слово Москва без конкретного адреса, площадки, метро, улицы или места — верни address=null. "
        "Не выдумывай адрес и не заменяй площадку на центр Москвы. Если в тексте есть явный адрес, верни именно его. "
        "Если упомянут Soluxe Hotel Moscow или отель Soluxe, правильный адрес: ул. Вильгельма Пика, 16. "
        "Lat/lon заполняй только если уверен в координатах известного места."
    )
    user_prompt = (
        f"Дата сообщения: {row.get('date_utc') or ''}\n"
        f"Канал: {row.get('lead') or ''}\n"
        "Полный текст сообщения:\n"
        f"{text[:12000]}"
    )
    payload = {
        "model": _normalize_openrouter_model_id(model_override or settings.get("openrouter_model")),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": min(float(settings.get("openrouter_temperature", 0.2) or 0.2), 0.2),
        "top_p": float(settings.get("openrouter_top_p", 0.9) or 0.9),
        "max_tokens": min(int(settings.get("openrouter_max_tokens", 2048) or 2048), 320),
    }
    _, content = _call_openrouter_chat_completion_sync(
        kind="route_address",
        api_key=api_key,
        payload=payload,
        input_ids={
            "lead": str(row.get("lead") or ""),
            "message_id": str(row.get("message_id") or ""),
            "row_hash": str(row.get("row_hash") or ""),
            "date_utc": str(row.get("date_utc") or ""),
        },
    )
    parsed = _extract_json_object_from_text(content)
    address = _normalize_route_address(parsed.get("address") if parsed else "")
    address_key = _route_address_key(address)
    try:
        confidence = float(parsed.get("confidence", 0.0)) if parsed else 0.0
    except (TypeError, ValueError):
        confidence = 0.0
    lat = parsed.get("lat") if parsed else None
    lon = parsed.get("lon") if parsed else None
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (TypeError, ValueError):
        lat = None
        lon = None
    return {
        "address": address or None,
        "address_key": address_key or None,
        "confidence": max(0.0, min(1.0, confidence)),
        "source": "openrouter" if address else "openrouter:none",
        "reason": str(parsed.get("reason") or "").strip() if parsed else "",
        "lat": lat,
        "lon": lon,
    }


__all__ = [
    "refresh_legacy_globals",
    "_call_openrouter_chat_completion_sync",
    "_call_openrouter_contact_qualification_sync",
    "_call_openrouter_event_date_sync",
    "_call_openrouter_route_address_sync",
    "_normalize_openrouter_model_id",
    "_record_llm_audit",
]
