# Backend Architecture

Current imported shape:

- `app/main.py` is the stable ASGI entrypoint and currently imports `back.app`.
- `back.py` is the monolithic FastAPI application.
- `app/core/config.py` is the migration target for environment settings.
- `app/routers/health.py` provides `/healthz` and `/api/health` smoke endpoints.
- `app/routers/config.py` provides the extracted settings/setup/auth route layer and calls `app/services/config.py`.
- `app/routers/license.py` provides the extracted license/tariff/update-status route layer and calls `app/services/license.py`.
- `app/routers/leads.py` provides the extracted leads/chat/lead-analysis route layer and calls `app/services/leads.py`.
- `app/routers/channels.py` provides the extracted Telegram source/channel/import-sync route layer and calls `app/services/channels.py`.
- `app/routers/routes.py` provides the extracted route-analysis route layer and calls `app/services/routes.py`.
- `app/routers/monitoring.py` provides the extracted runtime logs/status/metrics/DuckDB/dashboard monitoring route layer and calls `app/services/monitoring.py`.
- `app/services/*` provides domain-level service facades for the extracted route layer.
- `app/repositories/legacy.py` is the temporary DB/legacy boundary used while SQL-heavy code is moved out of `back.py`.
- `app/schemas/*` provides domain schema aliases for the extracted route layer.
- `security.py` contains security/license helpers.
- `tokens_counter.py` contains local token counting helpers.
- `jur_entities_structure.py` contains XLSX/legal-entity structure helpers.
- `x_files_license/` contains shared license code.
- `scripts/` contains operational scripts.
- `tests/` contains backend smoke and acceptance tests.

Planned optimized shape:

- `app/main.py` - stable FastAPI entrypoint, then application factory after the split.
- `app/core/config.py` - environment and settings.
- `app/routers/*` - HTTP routers by domain.
- `app/services/*` - business logic by domain.
- `app/repositories/*` - DB access by domain.
- `app/schemas/*` - Pydantic schemas by domain.
