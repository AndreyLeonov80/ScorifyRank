# Backend API

The current public API is preserved from `back.py`.

Important endpoint groups:

- setup and settings;
- Telegram import/sync;
- chats/messages;
- CRM/events/contacts;
- media/OCR;
- dashboard/logs/runtime status;
- license and feature flags.

Before removing or renaming any endpoint, add a smoke test and confirm the matching frontend page no longer calls it.

