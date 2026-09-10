# Backend routing contract

Дата обновления: 2026-05-21

`app.main:app` остаётся стабильной точкой входа, а `back.py` сохраняется как compatibility entrypoint до полного Docker/Nuitka smoke.

## Extracted routers

| Router | Scope | Response models |
|---|---|---|
| `app.routers.health` | health checks | lightweight dict |
| `app.routers.config` | settings/auth/openrouter | schemas from `app.schemas.config` |
| `app.routers.license` | license/tariffs/menu access | schemas from `app.schemas.license` |
| `app.routers.leads` | leads/messages/send/chat stream/lead llm page | schemas from `app.schemas.leads` |
| `app.routers.analysis` | chat token stats/history/run + generic LLM run | schemas from `app.schemas.analysis` |
| `app.routers.channels` | source/import/sync controls | schemas from `app.schemas.channels` |
| `app.routers.routes` | address routes/geocode | schemas from `app.schemas.routes` |
| `app.routers.monitoring` | runtime logs/status/metrics/dashboard | schemas from `app.schemas.monitoring` |
| `app.routers.jobs` | durable job progress abstraction | schemas from `app.schemas.jobs` |
| `app.routers.events` | event keywords/messages/calendar event analysis | schemas from `app.schemas.events` |
| `app.routers.crm` | CRM status/config/contacts cleanup | schemas from `app.schemas.crm` |
| `app.routers.outreach` | enReach fields and outReach sequences | schemas from `app.schemas.outreach` |
| `app.routers.contacts` | Telegram contacts, qualifications and do-not-contact | schemas from `app.schemas.contacts` |

## Critical runtime paths/env

| Variable/path | Contract |
|---|---|
| `PAYME_STATE_PATH` / `/data/state/state.json` | JSON runtime state; writes are atomic first, then safe fallback for bind-mounted files. |
| `PAYME_CACHE_DIR` / `/data/cache` | Telegram/message/cache data must survive Docker rebuilds. |
| `PAYME_OUT_DIR` / `/app/out` | Static frontend output; missing directory must not block setup/import redirects. |
| `PAYME_OPENROUTER_*` | OpenRouter provider/model settings are read through settings/state adapters. |
| Telegram session files under `/data` | Docker deploy must keep volumes, state, auth and settings intact. |

## Response envelope target

New frontend TypeScript code uses:

```ts
type ApiResponse<T> = {
  ok: boolean;
  data?: T;
  error?: string;
};
```

Legacy endpoints may still return raw DTOs. Frontend must use `normalizeApiResponse`/`unwrapApiResponse` adapters until each backend route is migrated to the envelope.

## Job progress payload

Long-running operations should report:

- `job_id`
- `status`
- `progress_percent`
- `progress_label`
- `queue_started_at`
- `chunks_done`
- `chunks_total`
- `last_chunk_at`
- `eta_seconds`
- `error`

This enables dashboard, LLM popups and import popups to show one consistent progress format before RabbitMQ/Redis/Postgres-backed queue is chosen.
