"""enReach/outReach services extracted from the legacy backend route handlers."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
# Extracted functions below execute with the same runtime objects but no longer
# keep their route-handler bodies inside the monolith.
legacy.refresh_globals(globals(), setdefault=True)

def api_payme_outreach_add_item(payload: OutreachCrmFieldPayload):
    item = _upsert_outreach_item(_outreach_item_from_payload(payload))
    return OutreachCrmFieldActionDTO(
        ok=True,
        message=f"{item.field_label} добавлено в enReach",
        item=item,
    )

def api_payme_outreach_delete_item(item_id: str):
    removed = _delete_outreach_item(item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Outreach item not found")
    return OutreachCrmFieldActionDTO(ok=True, message="Элемент удалён из enReach", item=None)

async def api_payme_outreach_expand_values():
    return await asyncio.to_thread(_expand_existing_outreach_values_sync)

def api_payme_outreach_items(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    field_type: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    items = _load_outreach_items(
        query=str(query or "").strip().lower(),
        field_type=str(field_type or "").strip().lower(),
        limit=max(1, int(limit or 1)),
    )
    return OutreachCrmFieldsPageDTO(**_paginate_items(items, page=page, page_size=page_size))

def api_payme_outreach_sequence_create(payload: XFilesOutreachSequencePayload):
    item = _xfiles_create_outreach_sequence(payload)
    return XFilesOutreachSequenceActionDTO(
        ok=True,
        message="outReach sequence подготовлена. Автоотправка отключена.",
        item=item,
    )

def api_payme_outreach_sequence_from_enreach(item_id: str):
    item = _xfiles_create_outreach_sequence_from_enreach(item_id)
    return XFilesOutreachSequenceActionDTO(
        ok=True,
        message="outReach sequence создана из enReach. Автоотправка отключена.",
        item=item,
    )

def api_payme_outreach_sequence_update(sequence_id: str, payload: XFilesOutreachSequencePatchPayload):
    item = _xfiles_update_outreach_sequence(sequence_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="outReach sequence not found")
    return XFilesOutreachSequenceActionDTO(
        ok=True,
        message="outReach sequence обновлена",
        item=item,
    )

def api_payme_outreach_sequences(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
):
    items = _xfiles_load_outreach_sequences(
        query=str(query or "").strip(),
        status=str(status or "").strip(),
        limit=max(1, int(limit or 1)),
    )
    return XFilesOutreachSequencesPageDTO(**_paginate_items(items, page=page, page_size=page_size))

def api_payme_outreach_stats():
    return _xfiles_outreach_stats()

def api_payme_outreach_touch_status(sequence_id: str, touch_key: str, payload: XFilesOutreachTouchStatusPayload):
    item = _xfiles_update_outreach_touch_status(sequence_id, touch_key, payload.status)
    if not item:
        raise HTTPException(status_code=404, detail="outReach sequence not found")
    return XFilesOutreachSequenceActionDTO(
        ok=True,
        message="Статус касания обновлён",
        item=item,
    )
