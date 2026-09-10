# x-files-client-backfront backend

FastAPI backend for the client application.

This folder currently imports the existing backend code as-is first. The next safe refactor is to split the monolithic `back.py` by domain while preserving public API contracts.

## Refactor order

1. `config` and health endpoints.
2. License and settings endpoints.
3. Import/sync/chats endpoints.
4. LLM and analysis services.
5. Monitoring/dashboard endpoints.
6. Tests and compatibility smoke checks.

