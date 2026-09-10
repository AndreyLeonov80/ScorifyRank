"""Search routes extracted from the monolith."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from app.schemas.search import *  # noqa: F403
from app.services import search as search_service

router = APIRouter()

@router.get("/api/payme/search/messages", response_model=SearchMessagesPageDTO, tags=["payme"])
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
    return search_service.api_payme_search_messages(page=page, page_size=page_size, limit=limit, query=query, lead=lead, author=author, company=company, phone=phone, email=email, city=city, title=title, date_from=date_from, date_to=date_to)

@router.get("/api/payme/search/context", response_model=SearchContextDTO, tags=["payme"])
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
    return search_service.api_payme_search_context(query=query, limit=limit, lead=lead, author=author, company=company, phone=phone, email=email, city=city, title=title, date_from=date_from, date_to=date_to)
