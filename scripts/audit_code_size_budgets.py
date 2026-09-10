from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BUDGETS = {
    "backfront/backend/app/legacy_runtime.py": 240 * 1024,
    "backfront/backend/app/services/contact_llm_runtime.py": 160 * 1024,
    "backfront/backend/app/services/telegram_sync_runtime.py": 110 * 1024,
    "backfront/backend/app/services/deals_runtime.py": 100 * 1024,
    "backfront/frontend/js/script.api.js": 48 * 1024,
    "backfront/frontend/js/legacy.lead.store.js": 75 * 1024,
    "backfront/frontend/js/react.index.js": 60 * 1024,
    "backfront/frontend/js/react.shared.js": 45 * 1024,
}


def main() -> None:
    errors: list[str] = []
    for relative, max_bytes in BUDGETS.items():
        path = ROOT / relative
        size = path.stat().st_size
        if size > max_bytes:
            errors.append(f"{relative}: {size} bytes exceeds {max_bytes} bytes")
    if errors:
        raise SystemExit("\n".join(errors))
    print("audit_code_size_budgets: ok")


if __name__ == "__main__":
    main()
