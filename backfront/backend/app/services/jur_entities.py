"""Jur-entity parser routes extracted from the monolith."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
legacy.refresh_globals(globals(), setdefault=True)

async def api_payme_jur_entities(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    parser_filter: str = Query(default="all"),
    sync: bool = Query(default=False),
):
    if sync:
        await _sync_jur_entities_xlsx()
    items = _list_jur_entities_rows(query=query, parser_filter=parser_filter)
    payload = _paginate_items(items, page=page, page_size=page_size)
    state = _get_jur_entities_state()
    return JurEntityFilesPageDTO(
        **payload,
        channel=_jur_entities_channel_key(),
        last_sync_at=state.get("last_sync_at"),
        sync_error=state.get("last_error"),
    )

async def api_payme_jur_entities_sync():
    return await _sync_jur_entities_xlsx()

def api_payme_jur_entities_parser_add(payload: JurEntityActionPayload):
    file_key = str(payload.file_key or "").strip()
    if not file_key:
        raise HTTPException(status_code=400, detail="Укажите файл")
    selected = _get_jur_entities_parser_selected()
    if file_key not in selected:
        selected.append(file_key)
    normalized = _set_jur_entities_parser_selected(selected)
    return JurEntityActionDTO(
        ok=True,
        message="Файл добавлен в парсер",
        file_key=file_key,
        parser_selected=normalized,
    )

def api_payme_jur_entities_parser_remove(payload: JurEntityActionPayload):
    file_key = str(payload.file_key or "").strip()
    if not file_key:
        raise HTTPException(status_code=400, detail="Укажите файл")
    normalized = _set_jur_entities_parser_selected(
        [item for item in _get_jur_entities_parser_selected() if item != file_key]
    )
    return JurEntityActionDTO(
        ok=True,
        message="Файл удалён из парсера",
        file_key=file_key,
        parser_selected=normalized,
    )
