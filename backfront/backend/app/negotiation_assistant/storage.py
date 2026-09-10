from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg

from .config import NegotiationSettings
from .schemas import JobDTO, LLMRunLogDTO, NegotiationBriefDTO, PromptTemplateDTO


DEFAULT_PROMPT = """Ты ассистент подготовки менеджера к переговорам.
На основе сообщений клиента подготовь структурированный бриф:
1. кто клиент;
2. что уже обсуждали;
3. гипотезы болей;
4. сигналы покупки;
5. риски и возражения;
6. аргументы;
7. вопросы для встречи;
8. следующий шаг;
9. сообщение после встречи.
Пиши конкретно, без воды, на русском языке."""


class NegotiationStore:
    def init(self) -> None: ...
    def list_prompts(self) -> list[PromptTemplateDTO]: ...
    def get_prompt(self, prompt_id: str | None) -> PromptTemplateDTO: ...
    def save_prompt(self, prompt: PromptTemplateDTO) -> PromptTemplateDTO: ...
    def save_job(self, job: JobDTO) -> JobDTO: ...
    def get_job(self, job_id: str) -> JobDTO | None: ...
    def list_jobs(self) -> list[JobDTO]: ...
    def save_brief(self, brief: NegotiationBriefDTO) -> NegotiationBriefDTO: ...
    def get_brief(self, brief_id: str) -> NegotiationBriefDTO | None: ...
    def list_briefs(self, contact_id: str | None = None) -> list[NegotiationBriefDTO]: ...
    def save_llm_run(self, run: LLMRunLogDTO) -> LLMRunLogDTO: ...
    def list_llm_runs(self, brief_id: str | None = None) -> list[LLMRunLogDTO]: ...
    def audit(self, action: str, payload: dict[str, Any]) -> None: ...


class MemoryStore(NegotiationStore):
    def __init__(self):
        self.prompts: dict[str, PromptTemplateDTO] = {}
        self.jobs: dict[str, JobDTO] = {}
        self.briefs: dict[str, NegotiationBriefDTO] = {}
        self.llm_runs: dict[str, LLMRunLogDTO] = {}
        self.audit_log: list[dict] = []

    def init(self) -> None:
        if not self.prompts:
            self.save_prompt(
                PromptTemplateDTO(
                    id="default-negotiation-brief",
                    name="B2B negotiation brief",
                    prompt=DEFAULT_PROMPT,
                    is_default=True,
                )
            )

    def list_prompts(self) -> list[PromptTemplateDTO]:
        return sorted(self.prompts.values(), key=lambda item: (not item.is_default, item.name))

    def get_prompt(self, prompt_id: str | None) -> PromptTemplateDTO:
        self.init()
        if prompt_id and prompt_id in self.prompts:
            return self.prompts[prompt_id]
        return next((prompt for prompt in self.prompts.values() if prompt.is_default), next(iter(self.prompts.values())))

    def save_prompt(self, prompt: PromptTemplateDTO) -> PromptTemplateDTO:
        prompt.updated_at = datetime.now(timezone.utc).isoformat()
        self.prompts[prompt.id] = prompt
        return prompt

    def save_job(self, job: JobDTO) -> JobDTO:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        self.jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> JobDTO | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[JobDTO]:
        return sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)

    def save_brief(self, brief: NegotiationBriefDTO) -> NegotiationBriefDTO:
        brief.updated_at = datetime.now(timezone.utc).isoformat()
        self.briefs[brief.id] = brief
        return brief

    def get_brief(self, brief_id: str) -> NegotiationBriefDTO | None:
        return self.briefs.get(brief_id)

    def list_briefs(self, contact_id: str | None = None) -> list[NegotiationBriefDTO]:
        briefs = list(self.briefs.values())
        if contact_id:
            briefs = [brief for brief in briefs if brief.contact_id == contact_id]
        return sorted(briefs, key=lambda item: item.created_at, reverse=True)

    def save_llm_run(self, run: LLMRunLogDTO) -> LLMRunLogDTO:
        self.llm_runs[run.id] = run
        return run

    def list_llm_runs(self, brief_id: str | None = None) -> list[LLMRunLogDTO]:
        runs = list(self.llm_runs.values())
        if brief_id:
            runs = [run for run in runs if run.brief_id == brief_id]
        return sorted(runs, key=lambda item: item.created_at, reverse=True)

    def audit(self, action: str, payload: dict[str, Any]) -> None:
        self.audit_log.append({"action": action, "payload": payload, "created_at": datetime.now(timezone.utc).isoformat()})


class PostgresStore(MemoryStore):
    def __init__(self, settings: NegotiationSettings):
        super().__init__()
        self.settings = settings

    def _connect(self):
        return psycopg.connect(self.settings.postgres_dsn, connect_timeout=3)

    def init(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS negotiation_prompt_templates (
                        id TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        is_default BOOLEAN NOT NULL DEFAULT FALSE,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE TABLE IF NOT EXISTS negotiation_jobs (
                        id TEXT PRIMARY KEY,
                        payload JSONB NOT NULL,
                        status TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE TABLE IF NOT EXISTS negotiation_briefs (
                        id TEXT PRIMARY KEY,
                        contact_id TEXT NOT NULL,
                        source_id TEXT,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS idx_negotiation_briefs_contact ON negotiation_briefs(contact_id);
                    CREATE INDEX IF NOT EXISTS idx_negotiation_jobs_status ON negotiation_jobs(status);
                    CREATE TABLE IF NOT EXISTS negotiation_llm_runs (
                        id TEXT PRIMARY KEY,
                        brief_id TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE INDEX IF NOT EXISTS idx_negotiation_llm_runs_brief ON negotiation_llm_runs(brief_id);
                    CREATE TABLE IF NOT EXISTS negotiation_audit_log (
                        id BIGSERIAL PRIMARY KEY,
                        action TEXT NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    """
                )
                cur.execute("SELECT id FROM negotiation_prompt_templates WHERE is_default = TRUE LIMIT 1")
                if not cur.fetchone():
                    prompt = PromptTemplateDTO(id="default-negotiation-brief", name="B2B negotiation brief", prompt=DEFAULT_PROMPT, is_default=True)
                    cur.execute(
                        "INSERT INTO negotiation_prompt_templates(id, payload, is_default) VALUES (%s, %s, %s)",
                        (prompt.id, json.dumps(prompt.model_dump()), True),
                    )
            conn.commit()

    def list_prompts(self) -> list[PromptTemplateDTO]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM negotiation_prompt_templates ORDER BY is_default DESC, id ASC")
            return [PromptTemplateDTO.model_validate(row[0]) for row in cur.fetchall()]

    def get_prompt(self, prompt_id: str | None) -> PromptTemplateDTO:
        self.init()
        with self._connect() as conn, conn.cursor() as cur:
            if prompt_id:
                cur.execute("SELECT payload FROM negotiation_prompt_templates WHERE id = %s", (prompt_id,))
                row = cur.fetchone()
                if row:
                    return PromptTemplateDTO.model_validate(row[0])
            cur.execute("SELECT payload FROM negotiation_prompt_templates WHERE is_default = TRUE LIMIT 1")
            row = cur.fetchone()
            if row:
                return PromptTemplateDTO.model_validate(row[0])
        return PromptTemplateDTO(id="default-negotiation-brief", name="B2B negotiation brief", prompt=DEFAULT_PROMPT, is_default=True)

    def save_prompt(self, prompt: PromptTemplateDTO) -> PromptTemplateDTO:
        prompt.updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO negotiation_prompt_templates(id, payload, is_default, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, is_default = EXCLUDED.is_default, updated_at = now()
                """,
                (prompt.id, json.dumps(prompt.model_dump()), prompt.is_default),
            )
            conn.commit()
        return prompt

    def save_job(self, job: JobDTO) -> JobDTO:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO negotiation_jobs(id, payload, status, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, status = EXCLUDED.status, updated_at = now()
                """,
                (job.id, json.dumps(job.model_dump()), job.status),
            )
            conn.commit()
        return job

    def get_job(self, job_id: str) -> JobDTO | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM negotiation_jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            return JobDTO.model_validate(row[0]) if row else None

    def list_jobs(self) -> list[JobDTO]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM negotiation_jobs ORDER BY updated_at DESC LIMIT 100")
            return [JobDTO.model_validate(row[0]) for row in cur.fetchall()]

    def save_brief(self, brief: NegotiationBriefDTO) -> NegotiationBriefDTO:
        brief.updated_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO negotiation_briefs(id, contact_id, source_id, payload, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload, updated_at = now()
                """,
                (brief.id, brief.contact_id, brief.source_id, json.dumps(brief.model_dump())),
            )
            conn.commit()
        return brief

    def get_brief(self, brief_id: str) -> NegotiationBriefDTO | None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT payload FROM negotiation_briefs WHERE id = %s", (brief_id,))
            row = cur.fetchone()
            return NegotiationBriefDTO.model_validate(row[0]) if row else None

    def list_briefs(self, contact_id: str | None = None) -> list[NegotiationBriefDTO]:
        with self._connect() as conn, conn.cursor() as cur:
            if contact_id:
                cur.execute("SELECT payload FROM negotiation_briefs WHERE contact_id = %s ORDER BY updated_at DESC", (contact_id,))
            else:
                cur.execute("SELECT payload FROM negotiation_briefs ORDER BY updated_at DESC LIMIT 100")
            return [NegotiationBriefDTO.model_validate(row[0]) for row in cur.fetchall()]

    def save_llm_run(self, run: LLMRunLogDTO) -> LLMRunLogDTO:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO negotiation_llm_runs(id, brief_id, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload
                """,
                (run.id, run.brief_id, json.dumps(run.model_dump())),
            )
            conn.commit()
        return run

    def list_llm_runs(self, brief_id: str | None = None) -> list[LLMRunLogDTO]:
        with self._connect() as conn, conn.cursor() as cur:
            if brief_id:
                cur.execute("SELECT payload FROM negotiation_llm_runs WHERE brief_id = %s ORDER BY created_at DESC", (brief_id,))
            else:
                cur.execute("SELECT payload FROM negotiation_llm_runs ORDER BY created_at DESC LIMIT 100")
            return [LLMRunLogDTO.model_validate(row[0]) for row in cur.fetchall()]

    def audit(self, action: str, payload: dict[str, Any]) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO negotiation_audit_log(action, payload) VALUES (%s, %s)", (action, json.dumps(payload)))
            conn.commit()


def build_store(settings: NegotiationSettings) -> NegotiationStore:
    if settings.store == "memory":
        store: NegotiationStore = MemoryStore()
        store.init()
        return store
    try:
        store = PostgresStore(settings)
        store.init()
        return store
    except Exception:
        fallback = MemoryStore()
        fallback.init()
        return fallback


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

