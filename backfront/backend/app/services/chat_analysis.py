"""Chat analysis helpers extracted from the legacy backend."""

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

def _chat_analysis_stats_payload(lead: str) -> Dict[str, Any]:
    messages = _iter_lead_analysis_messages(lead)
    by_sender: Dict[str, Dict[str, Any]] = {}
    total_tokens = 0
    for item in messages:
        tokens = int(item.get("tokens") or 0)
        total_tokens += tokens
        sender_key = str(item.get("sender_key") or "unknown")
        bucket = by_sender.setdefault(
            sender_key,
            {
                "sender_key": sender_key,
                "sender_name": str(item.get("sender_name") or ""),
                "sender_username": str(item.get("sender_username") or ""),
                "messages_count": 0,
                "tokens": 0,
            },
        )
        bucket["messages_count"] = int(bucket.get("messages_count") or 0) + 1
        bucket["tokens"] = int(bucket.get("tokens") or 0) + tokens

    senders = sorted(by_sender.values(), key=lambda item: int(item.get("tokens") or 0), reverse=True)
    senders_total = len(senders)
    # The UI only renders the top rows. Returning every one-time sender for large
    # chats makes "Обновить анализ" look frozen and can move megabytes per click.
    senders = senders[:200]
    return {
        "ok": True,
        "lead": lead,
        "total_messages": len(messages),
        "total_tokens": total_tokens,
        "max_messages": len(messages),
        "by_sender": senders,
        "by_sender_total": senders_total,
        "updated_at": _utc_now().isoformat(),
    }


def _chat_analysis_history_state() -> Dict[str, Any]:
    current = telegram_sync.state.get(CHAT_ANALYSIS_HISTORY_STATE_KEY)
    if not isinstance(current, dict):
        current = {"items_by_lead": {}, "updated_at": ""}
        telegram_sync.state[CHAT_ANALYSIS_HISTORY_STATE_KEY] = current
    if not isinstance(current.get("items_by_lead"), dict):
        current["items_by_lead"] = {}
    return current


def _chat_analysis_history_for_lead(lead: str) -> List[Dict[str, Any]]:
    state = _chat_analysis_history_state()
    items = state.get("items_by_lead", {}).get(str(lead), [])
    return items if isinstance(items, list) else []


def _run_chat_analysis_sync(lead: str, payload: ChatAnalysisPayload) -> Dict[str, Any]:
    messages = _select_chat_analysis_messages(lead, payload)
    if not messages:
        raise HTTPException(status_code=400, detail="Для анализа не выбраны текстовые сообщения")

    settings = _get_app_settings()
    provider = str(payload.provider or settings.get("llm_provider") or DEFAULT_LLM_PROVIDER).strip().lower()
    if provider not in {"openrouter", "local"}:
        provider = DEFAULT_LLM_PROVIDER
    prompt = str(payload.prompt or "").strip() or ChatAnalysisPayload().prompt
    sender_key = str(getattr(payload, "sender_key", "") or "").strip()
    sender_name = ""
    if sender_key and messages:
        first_sender = messages[0]
        sender_name = str(
            first_sender.get("sender_name")
            or first_sender.get("sender_username")
            or first_sender.get("sender_key")
            or sender_key
        )
    context = _chat_analysis_context(messages)
    total_tokens = sum(int(item.get("tokens") or 0) for item in messages)
    system_prompt = (
        "Ты аналитик продаж X-Files. Анализируй только предоставленные сообщения. "
        "Не выдумывай факты, отделяй наблюдения от гипотез, отвечай по-русски."
    )
    sender_line = f"Пользователь: {sender_name or sender_key}\n" if sender_key else ""
    user_prompt = (
        f"Источник: {lead}\n"
        f"Режим анализа: {payload.mode}\n"
        f"{sender_line}"
        f"Сообщений: {len(messages)}\n"
        f"Оценка токенов входного контекста: {total_tokens}\n\n"
        f"Задача пользователя:\n{prompt}\n\n"
        f"Сообщения в хронологическом порядке:\n{context}"
    )
    input_ids = {
        "lead": lead,
        "mode": payload.mode,
        "message_ids": [int(item.get("message_id") or 0) for item in messages],
        "messages_count": len(messages),
        "tokens_estimate": total_tokens,
        "sender_key": sender_key,
        "sender_name": sender_name,
    }
    model = str(payload.model or "").strip()
    if provider == "local":
        model = model or str(settings.get("lmstudio_model") or "local-model")
    else:
        model = _normalize_openrouter_model_id(model or settings.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL_ID)

    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": float(settings.get("openrouter_temperature", 0.2) or 0.2),
        "top_p": float(settings.get("openrouter_top_p", 0.9) or 0.9),
        "max_tokens": min(int(settings.get("openrouter_max_tokens", 2048) or 2048), 8192),
        "frequency_penalty": float(settings.get("openrouter_frequency_penalty", 0.0) or 0.0),
        "presence_penalty": float(settings.get("openrouter_presence_penalty", 0.0) or 0.0),
    }
    analysis_id = uuid.uuid4().hex
    item: Dict[str, Any] = {
        "analysis_id": analysis_id,
        "lead": lead,
        "status": "running",
        "provider": provider,
        "model": model,
        "mode": payload.mode,
        "prompt": prompt,
        "message_limit": payload.message_limit,
        "token_budget": payload.token_budget,
        "selected_message_ids": input_ids["message_ids"],
        "sender_key": sender_key,
        "sender_name": sender_name,
        "messages_count": len(messages),
        "tokens_estimate": total_tokens,
        "created_at": _utc_now().isoformat(),
        "finished_at": "",
        "result": "",
        "error": "",
    }
    _save_chat_analysis_item(lead, item)
    try:
        if provider == "local":
            _, result = _call_lmstudio_chat_completion_sync(
                kind="chat_analysis",
                base_url=str(settings.get("lmstudio_base_url") or DEFAULT_LMSTUDIO_BASE_URL),
                payload=request_payload,
                input_ids=input_ids,
            )
        else:
            api_key = str(settings.get("openrouter_api_key") or "").strip()
            if not api_key:
                raise HTTPException(status_code=400, detail="OpenRouter API key не настроен")
            _, result = _call_openrouter_chat_completion_sync(
                kind="chat_analysis",
                api_key=api_key,
                payload=request_payload,
                input_ids=input_ids,
            )
        item.update({"status": "ready", "result": result, "finished_at": _utc_now().isoformat()})
    except HTTPException:
        item.update({"status": "error", "finished_at": _utc_now().isoformat()})
        _save_chat_analysis_item(lead, item)
        raise
    except Exception as exc:
        item.update({"status": "error", "error": str(exc), "finished_at": _utc_now().isoformat()})
    history = _save_chat_analysis_item(lead, item)
    return {"item": item, "history": history}


def send_to_llm_and_store_response(stem: str, prompt_id: Optional[str] = None):
    settings = _get_app_settings()
    selected_prompt = _select_llm_answer_prompt(settings, prompt_id)
    llm_config = {
        "model": str(selected_prompt.get("model") or settings.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL_ID),
        "temperature": _bounded_float(selected_prompt.get("temperature"), 0.2, 0.0, 2.0),
        "top_p": _bounded_float(selected_prompt.get("top_p"), 0.9, 0.0, 1.0),
        "max_tokens": _bounded_int(selected_prompt.get("max_tokens"), 2048, 1, 262144),
        "stream": False,
    }

    if not LLM_SYSTEM_PROMPT_PATH.exists():
        raise FileNotFoundError(f"LLM system prompt not found: {LLM_SYSTEM_PROMPT_PATH}")

    artifacts = _ensure_tokens_artifacts(stem)
    tokens_txt_path = artifacts["tokens_txt"]

    msg1 = LLM_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8", errors="replace")
    msg2 = tokens_txt_path.read_text(encoding="utf-8", errors="replace")
    msg3 = (
        "Сгенерируй ровно 3 готовых варианта ответа для пользователя.\n"
        "Каждый вариант должен быть отдельным сообщением, которое можно сразу отправить в Telegram.\n"
        "Не используй markdown-таблицы, не добавляй длинные объяснения, не нумеруй ответы.\n"
        "Ориентируйся на выбранный промт и настройки пользователя:\n"
        f"{selected_prompt.get('title')}: {selected_prompt.get('prompt')}"
    )

    payload = {
        **llm_config,
        "messages": [
            {"role": "user", "content": msg1},
            {"role": "user", "content": msg3},
            {"role": "user", "content": msg2},
        ],
    }

    started_at = _utc_now()
    started_monotonic = time.monotonic()
    data: Dict[str, Any] = {}
    assistant_answer = ""
    try:
        response = _post_json_with_transient_retries(
            LLM_BASE_URL + LLM_ENDPOINT,
            json_payload=payload,
            timeout=_openrouter_timeout_sec(),
            label="Legacy lead LLM",
        )
        raw_data = response.json()
        data = raw_data if isinstance(raw_data, dict) else {}

        if "choices" not in data or not data["choices"]:
            raise RuntimeError("Некорректный ответ LLM")

        assistant_answer = str(data["choices"][0]["message"]["content"] or "")
        _record_llm_audit(
            kind="legacy_lead_analysis",
            provider="local",
            model=str(llm_config.get("model") or ""),
            request_payload=payload,
            input_ids={
                "stem": stem,
                "prompt_id": str(selected_prompt.get("id") or ""),
                "prompt_title": str(selected_prompt.get("title") or ""),
                "tokens_txt": str(tokens_txt_path.name),
                "tokens_sha256": hashlib.sha256(msg2.encode("utf-8")).hexdigest(),
            },
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="ready",
            result_text=assistant_answer,
            response_payload=data,
        )
    except Exception as exc:
        _record_llm_audit(
            kind="legacy_lead_analysis",
            provider="local",
            model=str(llm_config.get("model") or ""),
            request_payload=payload,
            input_ids={
                "stem": stem,
                "prompt_id": str(selected_prompt.get("id") or ""),
                "prompt_title": str(selected_prompt.get("title") or ""),
                "tokens_txt": str(tokens_txt_path.name),
                "tokens_sha256": hashlib.sha256(msg2.encode("utf-8")).hexdigest(),
            },
            started_at=started_at,
            duration_sec=time.monotonic() - started_monotonic,
            status="error",
            result_text=assistant_answer,
            response_payload=data,
            error=str(exc),
        )
        raise

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    sid = uuid.uuid4().hex[:8]

    out_dir = PAYME_OUT_DIR / stem / f"{timestamp}_{sid}"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "response.txt"
    out_path.write_text(assistant_answer, encoding="utf-8")

    return out_path


__all__ = [
    "refresh_legacy_globals",
    "_chat_analysis_history_for_lead",
    "_chat_analysis_history_state",
    "_chat_analysis_stats_payload",
    "_run_chat_analysis_sync",
    "send_to_llm_and_store_response",
]
