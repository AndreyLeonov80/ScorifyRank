"""Legacy demo API routes extracted from the monolith."""

from __future__ import annotations

from app.repositories import legacy

# Compatibility bridge while helpers/state still live in back.py.
legacy.refresh_globals(globals(), setdefault=True)

def list_leads():
    return list(DB.values())

def get_lead(lead_id: str):
    lead = DB.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead

def create_lead(lead: Lead):
    if lead.id in DB:
        lead.id = str(uuid4())
    DB[lead.id] = lead
    return lead

def update_lead(lead_id: str, data: Lead):
    if lead_id not in DB:
        raise HTTPException(status_code=404, detail="Lead not found")
    patched = data.copy(update={"id": lead_id})
    DB[lead_id] = patched
    return patched

def delete_lead(lead_id: str):
    if lead_id not in DB:
        raise HTTPException(status_code=404, detail="Lead not found")
    del DB[lead_id]
    return None

def create_message(m: MessageIn):
    msg = {
        "id": str(uuid4()),
        "lead_id": m.lead_id,
        "text": m.text,
        "from": "me",
        "when": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    DBmessages["messages"].append(msg)
    return msg
