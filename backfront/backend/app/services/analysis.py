"""Chat analysis services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

from app.services.chat_analysis import (
    _chat_analysis_history_for_lead,
    _chat_analysis_stats_payload,
    _run_chat_analysis_sync,
    send_to_llm_and_store_response,
)

def api_payme_lead_analysis_history(lead: str):
    return ChatAnalysisHistoryDTO(lead=lead, items=_chat_analysis_history_for_lead(lead))

async def api_payme_lead_analysis_run(lead: str, payload: ChatAnalysisPayload):
    try:
        result = await asyncio.to_thread(_run_chat_analysis_sync, lead, payload)
        return ChatAnalysisRunDTO(
            ok=True,
            lead=lead,
            item=result.get("item") or {},
            history=result.get("history") or [],
            message="Анализ готов",
        )
    except HTTPException:
        raise
    except Exception as exc:
        item = {
            "analysis_id": uuid.uuid4().hex,
            "lead": lead,
            "status": "error",
            "provider": payload.provider,
            "model": payload.model,
            "mode": payload.mode,
            "prompt": payload.prompt,
            "message_limit": payload.message_limit,
            "token_budget": payload.token_budget,
            "selected_message_ids": payload.selected_message_ids,
            "messages_count": 0,
            "tokens_estimate": 0,
            "created_at": _utc_now().isoformat(),
            "finished_at": _utc_now().isoformat(),
            "result": "",
            "error": str(exc),
        }
        history = _save_chat_analysis_item(lead, item)
        return ChatAnalysisRunDTO(ok=False, lead=lead, item=item, history=history, message=str(exc))

def api_payme_lead_analysis_stats(lead: str):
    return ChatTokenStatsDTO(**_chat_analysis_stats_payload(lead))

async def api_payme_llm_run(payload: LlmRunPayload):
    """
    Заглушка для запуска LLM анализа.
    Параметры: chat_id (name лида), filename (*.jsonl)
    Ожидает 5 сек и возвращает результат.
    """
    print(f"[LLM-RUN] Получены параметры: chat_id={payload.chat_id}, filename={payload.filename}")

    # Заглушка: имитируем длительную обработку
    # await asyncio.sleep(1)

    requested_stem = Path(payload.filename).stem or payload.chat_id
    stem = _resolve_lead_basename(requested_stem) or requested_stem

    try:
        path = send_to_llm_and_store_response(stem, payload.prompt_id)
        print("Ответ сохранён:", path)
        _ensure_llm_html(stem)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM run failed: {exc}")

    print(f"[LLM-RUN] ✓ Обработка завершена для {stem}")
    return {
        "ok": True,
        "message": f"LLM анализ выполнен для {stem}",
        "chat_id": stem,
        "filename": f"{stem}.jsonl",
        "response_path": str(path),
    }
