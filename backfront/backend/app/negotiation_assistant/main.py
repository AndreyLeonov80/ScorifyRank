from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .brief_service import BriefService
from .config import settings
from .gramlead_repository import GramLeadReadRepository
from .schemas import (
    ApiResponse,
    GenerateBriefRequest,
    GenerateBriefResponse,
    JobDTO,
    LLMRunLogDTO,
    NegotiationBriefDTO,
    PromptTemplateDTO,
)
from .storage import build_store, new_id


app = FastAPI(title="GramLead Negotiation Assistant", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

repo = GramLeadReadRepository(settings)
store = build_store(settings)
brief_service = BriefService(settings)


def ok(data):
    return ApiResponse(ok=True, data=data)


@app.get("/health")
def health():
    status = repo.status()
    return {"ok": True, "service": "negotiation-assistant", "data": status}


@app.get("/api/status")
def api_status():
    data = repo.status()
    data.update({"store": settings.store, "openrouter_configured": bool(settings.openrouter_api_key)})
    return ok(data)


@app.get("/api/settings")
def get_settings():
    return ok(
        {
            "public_base_url": settings.public_base_url,
            "duckdb_path": settings.duckdb_path,
            "jsonl_dir": settings.jsonl_dir,
            "artifacts_dir": settings.artifacts_dir,
            "openrouter_configured": bool(settings.openrouter_api_key),
            "openrouter_model": settings.openrouter_model,
            "max_messages_per_brief": settings.max_messages_per_brief,
        }
    )


@app.get("/api/contacts")
def contacts(query: str = "", source: str = "", limit: int = 50, offset: int = 0):
    rows, total = repo.list_contacts(query=query, source=source, limit=limit, offset=offset)
    return ok({"items": rows, "total": total, "limit": limit, "offset": offset})


@app.get("/api/contacts/{contact_id:path}")
def contact(contact_id: str):
    row = repo.get_contact(contact_id)
    if not row:
        raise HTTPException(status_code=404, detail="contact not found")
    return ok(row)


@app.get("/api/contacts/{contact_id:path}/messages")
def messages(contact_id: str, limit: int = 80):
    return ok({"items": repo.list_messages(contact_id, limit=limit), "limit": limit})


@app.get("/api/sources")
def sources():
    return ok({"items": repo.list_sources()})


@app.get("/api/prompts")
def prompts():
    return ok({"items": store.list_prompts()})


@app.put("/api/prompts/{prompt_id}")
def save_prompt(prompt_id: str, prompt: PromptTemplateDTO):
    prompt.id = prompt_id
    return ok(store.save_prompt(prompt))


@app.get("/api/briefs")
def briefs(contact_id: str | None = None):
    return ok({"items": store.list_briefs(contact_id=contact_id)})


@app.get("/api/briefs/{brief_id}")
def brief(brief_id: str):
    row = store.get_brief(brief_id)
    if not row:
        raise HTTPException(status_code=404, detail="brief not found")
    return ok(row)


@app.post("/api/briefs/generate")
def generate_brief(request: GenerateBriefRequest):
    contact = repo.get_contact(request.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="contact not found")
    prompt = store.get_prompt(request.prompt_id)
    limit = request.message_limit or settings.max_messages_per_brief
    messages = repo.list_messages(request.contact_id, limit=limit)
    job = JobDTO(id=new_id("job"), status="running", progress_percent=15, message="Собираю сообщения контакта")
    store.save_job(job)
    if not messages:
        job.status = "error"
        job.error = "Для анализа не выбраны текстовые сообщения"
        job.message = job.error
        job.progress_percent = 100
        store.save_job(job)
        raise HTTPException(status_code=400, detail=job.error)
    content = brief_service.build_content(contact, messages, prompt)
    job.progress_percent = 65
    job.message = "Генерирую файлы брифа"
    store.save_job(job)
    brief_id = new_id("brief")
    artifacts = brief_service.write_artifacts(brief_id, contact, messages, content)
    brief = NegotiationBriefDTO(
        id=brief_id,
        contact_id=contact.id,
        source_id=contact.source_id,
        prompt_id=prompt.id,
        content=content,
        artifacts=artifacts,
    )
    store.save_brief(brief)
    store.save_llm_run(
        LLMRunLogDTO(
            id=new_id("llm"),
            brief_id=brief.id,
            prompt_id=prompt.id,
            provider=prompt.provider,
            model=prompt.model,
            request_payload={"contact": contact.model_dump(), "messages_count": len(messages), "prompt": prompt.prompt},
            response_payload={"mode": "deterministic-local", "content": content.model_dump()},
        )
    )
    job.status = "done"
    job.progress_percent = 100
    job.message = "Бриф готов"
    store.save_job(job)
    store.audit("generate_brief", {"brief_id": brief.id, "contact_id": contact.id})
    return ok(GenerateBriefResponse(job_id=job.id, brief_id=brief.id, status=job.status))


@app.post("/api/briefs/{brief_id}/regenerate")
def regenerate_brief(brief_id: str, request: GenerateBriefRequest):
    existing = store.get_brief(brief_id)
    if not existing:
        raise HTTPException(status_code=404, detail="brief not found")
    request.contact_id = existing.contact_id
    return generate_brief(request)


@app.get("/api/jobs")
def jobs():
    return ok({"items": store.list_jobs()})


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    row = store.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return ok(row)


@app.get("/api/llm-runs/{brief_id}")
def llm_runs(brief_id: str):
    return ok({"items": store.list_llm_runs(brief_id=brief_id)})


@app.get("/files/{brief_id}/{filename}")
def files(brief_id: str, filename: str):
    path = (settings.artifacts_path / brief_id / filename).resolve()
    root = settings.artifacts_path.resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)

