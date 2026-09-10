"""Search routes extracted from the monolith."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
legacy.refresh_globals(globals(), setdefault=True)

def api_payme_search_messages(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=5, ge=1, le=100),
    limit: int = Query(default=5000, ge=1, le=50000),
    query: str = Query(default=""),
    lead: str = Query(default=""),
    author: str = Query(default=""),
    company: str = Query(default=""),
    phone: str = Query(default=""),
    email: str = Query(default=""),
    city: str = Query(default=""),
    title: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    payload = _duckdb_search_messages_page(
        page=page,
        page_size=page_size,
        limit=limit,
        query=str(query or "").strip().lower(),
        lead_filter=str(lead or "").strip().lower(),
        author_filter=str(author or "").strip().lower(),
        company_filter=str(company or "").strip().lower(),
        phone_filter=str(phone or "").strip().lower(),
        email_filter=str(email or "").strip().lower(),
        city_filter=str(city or "").strip().lower(),
        title_filter=str(title or "").strip().lower(),
        date_from=str(date_from or "").strip(),
        date_to=str(date_to or "").strip(),
    )
    return SearchMessagesPageDTO(**payload)

def api_payme_search_context(
    query: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=200),
    lead: str = Query(default=""),
    author: str = Query(default=""),
    company: str = Query(default=""),
    phone: str = Query(default=""),
    email: str = Query(default=""),
    city: str = Query(default=""),
    title: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
):
    payload = _duckdb_search_messages_page(
        page=1,
        page_size=min(max(1, int(limit)), 200),
        limit=min(max(1, int(limit)), 200),
        query=str(query or "").strip().lower(),
        lead_filter=str(lead or "").strip().lower(),
        author_filter=str(author or "").strip().lower(),
        company_filter=str(company or "").strip().lower(),
        phone_filter=str(phone or "").strip().lower(),
        email_filter=str(email or "").strip().lower(),
        city_filter=str(city or "").strip().lower(),
        title_filter=str(title or "").strip().lower(),
        date_from=str(date_from or "").strip(),
        date_to=str(date_to or "").strip(),
    )
    items = [SearchMessageDTO(**item).model_dump() for item in payload.get("items", [])]
    return SearchContextDTO(
        query=str(query or "").strip(),
        total_matches=int(payload.get("total", 0) or 0),
        context_blocks=_build_search_context_blocks(items),
        items=[SearchMessageDTO(**item) for item in items],
    )
