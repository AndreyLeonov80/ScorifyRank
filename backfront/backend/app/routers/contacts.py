"""Telegram contact HTTP routes extracted from the legacy backend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.schemas import contacts as contacts_schemas
from app.services import contacts as contacts_service

router = APIRouter(tags=["payme"])


@router.get("/api/payme/contacts/status", response_model=contacts_schemas.AnalysisStatusDTO)
def api_payme_contacts_status():
    return contacts_service.api_payme_contacts_status()


@router.post("/api/payme/contacts/refresh", response_model=contacts_schemas.AnalysisActionDTO)
async def api_payme_contacts_refresh():
    return await contacts_service.api_payme_contacts_refresh()


@router.post("/api/payme/contacts/config", response_model=contacts_schemas.AnalysisActionDTO)
def api_payme_contacts_config(payload: contacts_schemas.AnalysisConfigPayload):
    return contacts_service.api_payme_contacts_config(payload)


@router.get(
    "/api/payme/contacts/qualification-prompts",
    response_model=contacts_schemas.ContactQualificationPromptsDTO,
)
def api_payme_contact_qualification_prompts():
    return contacts_service.api_payme_contact_qualification_prompts()


@router.get(
    "/api/payme/contacts/{contact_key}/qualifications",
    response_model=contacts_schemas.ContactQualificationsDTO,
)
def api_payme_contact_qualifications(contact_key: str):
    return contacts_service.api_payme_contact_qualifications(contact_key)


@router.post(
    "/api/payme/contacts/{contact_key}/qualify",
    response_model=contacts_schemas.ContactQualificationDTO,
)
def api_payme_contact_qualify(contact_key: str, payload: contacts_schemas.ContactQualificationRequestDTO):
    return contacts_service.api_payme_contact_qualify(contact_key, payload)


@router.post(
    "/api/payme/contacts/{contact_key}/do-not-contact",
    response_model=contacts_schemas.ContactDoNotContactActionDTO,
)
def api_payme_contact_do_not_contact(contact_key: str, payload: contacts_schemas.ContactDoNotContactPayload):
    return contacts_service.api_payme_contact_do_not_contact(contact_key, payload)


@router.get("/api/payme/contacts/chats", response_model=contacts_schemas.TelegramContactChatFiltersDTO)
def api_payme_contacts_chats(limit: int = Query(default=50000, ge=1, le=50000)):
    return contacts_service.api_payme_contacts_chats(limit=limit)


@router.get("/api/payme/contacts", response_model=contacts_schemas.TelegramContactsPageDTO)
def api_payme_contacts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=5000, ge=1, le=50000),
    query: str = Query(default=""),
    lead: str = Query(default=""),
    qualified_template: str = Query(default="all"),
    lead_temperature: str = Query(default="all"),
    signals: str = Query(default=""),
):
    return contacts_service.api_payme_contacts(
        page=page,
        page_size=page_size,
        limit=limit,
        query=query,
        lead=lead,
        qualified_template=qualified_template,
        lead_temperature=lead_temperature,
        signals=signals,
    )


@router.get(
    "/api/payme/contacts/{contact_key}/messages",
    response_model=contacts_schemas.TelegramContactMessagesPageDTO,
)
def api_payme_contact_messages(
    contact_key: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    query: str = Query(default=""),
    lead: str = Query(default=""),
):
    return contacts_service.api_payme_contact_messages(
        contact_key,
        page=page,
        page_size=page_size,
        query=query,
        lead=lead,
    )
