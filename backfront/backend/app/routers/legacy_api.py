"""Legacy demo API routes extracted from the monolith."""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any, Dict, List, Optional

from app.schemas.legacy_api import *  # noqa: F403
from app.services import legacy_api as legacy_api_service

router = APIRouter()

@router.get("/api/leads", response_model=List[Lead])
def list_leads():
    return legacy_api_service.list_leads()

@router.get("/api/leads/{lead_id}", response_model=Lead)
def get_lead(lead_id: str):
    return legacy_api_service.get_lead(lead_id=lead_id)

@router.post("/api/leads", response_model=Lead, status_code=201)
def create_lead(lead: Lead):
    return legacy_api_service.create_lead(lead=lead)

@router.put("/api/leads/{lead_id}", response_model=Lead)
def update_lead(lead_id: str, data: Lead):
    return legacy_api_service.update_lead(lead_id=lead_id, data=data)

@router.delete("/api/leads/{lead_id}", status_code=204)
def delete_lead(lead_id: str):
    return legacy_api_service.delete_lead(lead_id=lead_id)

@router.post("/api/messages", response_model=MessageOut)
def create_message(m: MessageIn):
    return legacy_api_service.create_message(m=m)
