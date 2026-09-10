"""Application settings helpers extracted from the legacy backend."""

from __future__ import annotations

import os
import sys


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime")
    legacy_back = sys.modules.get("back")
    for source in (runtime, legacy_back):
        if source is None:
            continue
        for name, value in vars(source).items():
            if not name.startswith("__") and name != "refresh_legacy_globals":
                globals()[name] = value


refresh_legacy_globals()


def _client_delivery_mode_enabled() -> bool:
    raw = str(os.environ.get("XFILES_CLIENT_DELIVERY") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _client_setup_manual_update(raw: Dict[str, Any]) -> bool:
    watched_keys = (
        "telegram_api_id",
        "telegram_api_hash",
        "telegram_phone",
        "openrouter_api_key",
        "setup_wizard_completed",
    )
    return any(str(raw.get(key) or "").strip() for key in watched_keys)


def _sanitize_client_delivery_first_start_settings(raw: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not _client_delivery_mode_enabled() or not isinstance(raw, dict):
        return raw
    if raw.get("setup_wizard_completed") or raw.get("client_setup_started"):
        return raw
    sanitized = dict(raw)
    for key in ("telegram_api_id", "telegram_api_hash", "telegram_phone", "openrouter_api_key"):
        sanitized[key] = ""
    sanitized["client_setup_started"] = False
    return sanitized

def _coerce_contact_qualification_prompts(raw: Any) -> List[Dict[str, str]]:
    source = raw if isinstance(raw, list) and raw else _default_contact_qualification_prompts()
    prompts: List[Dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or f"Шаблон {index + 1}").strip()
        prompt = str(item.get("prompt") or item.get("text") or "").strip()
        if not prompt:
            continue
        prompt_id = _normalize_contact_prompt_id(item.get("id"), title, prompt)
        if prompt_id in seen:
            prompt_id = f"{prompt_id}_{index + 1}"
        seen.add(prompt_id)
        prompts.append({"id": prompt_id, "title": title or prompt_id, "prompt": prompt})
    for item in _default_contact_qualification_prompts():
        prompt_id = _normalize_contact_prompt_id(item.get("id"), item.get("title", ""), item.get("prompt", ""))
        if prompt_id and prompt_id not in seen:
            seen.add(prompt_id)
            prompts.append({"id": prompt_id, "title": item["title"], "prompt": item["prompt"]})
    return prompts or _default_contact_qualification_prompts()


def _bounded_float(value: Any, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _bounded_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(min_value, min(max_value, parsed))


def _default_llm_answer_prompts() -> List[Dict[str, Any]]:
    return [
        {
            "id": "answer1",
            "title": "Ответ 1 · мягкое знакомство",
            "is_default": True,
            "provider": DEFAULT_LLM_PROVIDER,
            "model": DEFAULT_OPENROUTER_MODEL_ID,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 2048,
            "prompt": (
                "Сформулируй короткий, живой и безопасный ответ для первого касания. "
                "Тон: уважительно, без давления, как человек человеку. Цель: начать диалог."
            ),
        },
        {
            "id": "answer2",
            "title": "Ответ 2 · польза и вопрос",
            "is_default": False,
            "provider": DEFAULT_LLM_PROVIDER,
            "model": DEFAULT_OPENROUTER_MODEL_ID,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 2048,
            "prompt": (
                "Сформулируй ответ, где сначала есть польза или наблюдение по контексту, "
                "а в конце один простой вопрос, который помогает понять потребность человека."
            ),
        },
        {
            "id": "answer3",
            "title": "Ответ 3 · следующий шаг",
            "is_default": False,
            "provider": DEFAULT_LLM_PROVIDER,
            "model": DEFAULT_OPENROUTER_MODEL_ID,
            "temperature": 0.2,
            "top_p": 0.9,
            "max_tokens": 2048,
            "prompt": (
                "Сформулируй ответ с предложением понятного следующего шага: короткий созвон, "
                "обмен материалом или уточнение задачи. Без навязчивой продажи."
            ),
        },
    ]


def _coerce_llm_answer_prompts(raw: Any) -> List[Dict[str, Any]]:
    defaults = _default_llm_answer_prompts()
    source = raw if isinstance(raw, list) and raw else defaults
    prompts: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    def _prompt_id(item: Dict[str, Any], index: int) -> str:
        raw_id = str(item.get("id") or "").strip().lower()
        raw_id = re.sub(r"[^a-z0-9_-]+", "_", raw_id).strip("_")
        return raw_id[:80] or f"answer{index + 1}"

    for index, item in enumerate(source[:20]):
        if not isinstance(item, dict):
            continue
        fallback = defaults[min(index, len(defaults) - 1)]
        prompt_id = _prompt_id(item, index)
        if prompt_id in seen:
            prompt_id = f"{prompt_id}_{index + 1}"
        seen.add(prompt_id)
        title = str(item.get("title") or fallback.get("title") or prompt_id).strip()
        prompt = str(item.get("prompt") or fallback.get("prompt") or "").strip()
        if not prompt:
            continue
        provider = str(item.get("provider") or DEFAULT_LLM_PROVIDER).strip().lower()
        if provider not in {"openrouter", "local"}:
            provider = DEFAULT_LLM_PROVIDER
        model = str(item.get("model") or DEFAULT_OPENROUTER_MODEL_ID).strip() or DEFAULT_OPENROUTER_MODEL_ID
        prompts.append(
            {
                "id": prompt_id,
                "title": title or prompt_id,
                "prompt": prompt,
                "is_default": bool(item.get("is_default")),
                "provider": provider,
                "model": model,
                "temperature": _bounded_float(item.get("temperature"), 0.2, 0.0, 2.0),
                "top_p": _bounded_float(item.get("top_p"), 0.9, 0.0, 1.0),
                "max_tokens": _bounded_int(item.get("max_tokens"), 2048, 1, 262144),
            }
        )

    if not prompts:
        prompts = [dict(item) for item in defaults]

    if not any(item.get("is_default") for item in prompts):
        prompts[0]["is_default"] = True
    default_seen = False
    for item in prompts:
        if item.get("is_default") and not default_seen:
            default_seen = True
        else:
            item["is_default"] = False
    return prompts


def _select_llm_answer_prompt(settings: Dict[str, Any], prompt_id: Optional[str] = None) -> Dict[str, Any]:
    prompts = _coerce_llm_answer_prompts(settings.get("llm_answer_prompts"))
    wanted = str(prompt_id or "").strip().lower()
    if wanted:
        for item in prompts:
            if str(item.get("id") or "").lower() == wanted:
                return item
    for item in prompts:
        if item.get("is_default"):
            return item
    return prompts[0]


def _default_app_settings() -> Dict[str, Any]:
    client_delivery = _client_delivery_mode_enabled()
    return {
        "setup_wizard_completed": False,
        "localhost_bind": _normalize_local_web_bind(os.environ.get("HOST_WEB_BIND") or "127.0.0.1"),
        "localhost_port": _default_local_web_port(),
        "telegram_api_id": "" if client_delivery else _default_telegram_api_id(),
        "telegram_api_hash": "" if client_delivery else _default_telegram_api_hash(),
        "telegram_phone": "" if client_delivery else str(os.environ.get("TELEGRAM_PHONE") or "").strip(),
        "telegram_client_backend": "telethon",
        "telegram_scan_groups": _default_telegram_scan_groups(),
        "telegram_scan_group_assignments": {},
        "ocr_images_enabled": False,
        "ocr_delete_images_after_processing": False,
        "ocr_service_url": _default_ocr_service_url(),
        "openrouter_api_key": "" if client_delivery else str(
            os.environ.get("PAYME_OPENROUTER_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        ).strip(),
        "llm_provider": DEFAULT_LLM_PROVIDER,
        "lmstudio_base_url": str(os.environ.get("PAYME_LMSTUDIO_BASE_URL") or DEFAULT_LMSTUDIO_BASE_URL).strip(),
        "lmstudio_model": str(os.environ.get("PAYME_LMSTUDIO_MODEL") or "local-model").strip(),
        "openrouter_model": DEFAULT_OPENROUTER_MODEL_ID,
        "openrouter_paid_model": DEFAULT_OPENROUTER_PAID_MODEL_ID,
        "openrouter_paid_model_enabled": False,
        "openrouter_show_paid_models": False,
        "openrouter_temperature": 0.2,
        "openrouter_top_p": 0.9,
        "openrouter_max_tokens": 2048,
        "openrouter_frequency_penalty": 0.0,
        "openrouter_presence_penalty": 0.0,
        "openrouter_event_date_message_days": 30,
        "openrouter_timeout_sec": min(300.0, max(5.0, OPENROUTER_REQUEST_TIMEOUT_SEC)),
        "openrouter_allow_pii": False,
        "runtime_log_mask_pii": True,
        "contact_qualification_prompts": _default_contact_qualification_prompts(),
        "llm_answer_prompts": _default_llm_answer_prompts(),
        "import_default_add_limit": 50,
        "import_default_history_months": 1,
        "import_default_message_limit": 1000,
        "telegram_unlimited_import_enabled": False,
        "local_import_limits_enabled": False,
        "local_import_max_history_months": 1,
        "local_import_max_message_limit": 1000,
        "local_telegram_source_limit_enabled": False,
        "local_telegram_source_limit": 50,
        "outreach_auto_send_enabled": False,
        "license_email_enabled": False,
        "license_email_host": "",
        "license_email_port": 993,
        "license_email_smtp_host": "",
        "license_email_smtp_port": 465,
        "license_email_login": "",
        "license_email_password_secret": {},
        "license_email_password_configured": False,
        "license_email_inbox_folder": "INBOX",
        "license_email_allow_activation_receipt": False,
        "license_email_last_import_at": "",
        "show_contact_qualification_prompt_settings": False,
        "show_license_email_settings": False,
        "dashboard_show_money_metrics": False,
        "client_setup_started": False,
    }


def _coerce_app_settings(raw: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    settings = _default_app_settings()
    if isinstance(raw, dict):
        settings.update(raw)

    settings["client_setup_started"] = bool(settings.get("client_setup_started", False))
    settings["setup_wizard_completed"] = bool(settings.get("setup_wizard_completed", False))
    settings["localhost_bind"] = _normalize_local_web_bind(settings.get("localhost_bind") or os.environ.get("HOST_WEB_BIND"))
    settings["ocr_images_enabled"] = bool(settings.get("ocr_images_enabled", False))
    settings["ocr_delete_images_after_processing"] = bool(settings.get("ocr_delete_images_after_processing", False))
    settings["ocr_service_url"] = _normalize_ocr_service_url(settings.get("ocr_service_url") or _default_ocr_service_url())
    telegram_api_id = _normalize_telegram_api_id(settings.get("telegram_api_id"))
    telegram_api_hash = _normalize_telegram_api_hash(settings.get("telegram_api_hash"))
    settings["telegram_api_id"] = telegram_api_id
    settings["telegram_api_hash"] = telegram_api_hash
    settings["telegram_phone"] = str(settings.get("telegram_phone") or "").strip()
    settings["telegram_api_configured"] = bool(telegram_api_id and telegram_api_hash)
    if not settings["telegram_api_configured"]:
        settings["telegram_api_credentials_source"] = "missing"
    elif telegram_api_id == _telegram_api_env_id() and telegram_api_hash == _telegram_api_env_hash():
        settings["telegram_api_credentials_source"] = "env"
    else:
        settings["telegram_api_credentials_source"] = "settings"
    telegram_client_backend = str(settings.get("telegram_client_backend") or "telethon").strip().lower()
    if telegram_client_backend not in {"telethon", "tdlib"}:
        telegram_client_backend = "telethon"
    settings["telegram_client_backend"] = telegram_client_backend
    settings["telegram_scan_groups"] = _coerce_telegram_scan_groups(settings.get("telegram_scan_groups"))
    settings["telegram_scan_group_assignments"] = _coerce_telegram_scan_group_assignments(
        settings.get("telegram_scan_group_assignments"),
        settings["telegram_scan_groups"],
    )
    settings["openrouter_api_key"] = str(settings.get("openrouter_api_key") or "").strip()
    llm_provider = str(settings.get("llm_provider") or DEFAULT_LLM_PROVIDER).strip().lower()
    if llm_provider not in {"openrouter", "local"}:
        llm_provider = DEFAULT_LLM_PROVIDER
    settings["llm_provider"] = llm_provider
    lmstudio_base_url = str(settings.get("lmstudio_base_url") or DEFAULT_LMSTUDIO_BASE_URL).strip().rstrip("/")
    settings["lmstudio_base_url"] = lmstudio_base_url or DEFAULT_LMSTUDIO_BASE_URL
    settings["lmstudio_model"] = str(settings.get("lmstudio_model") or "local-model").strip() or "local-model"
    settings["openrouter_model"] = _normalize_openrouter_model_id(settings.get("openrouter_model"))
    settings["openrouter_paid_model"] = _normalize_openrouter_model_id(
        settings.get("openrouter_paid_model") or DEFAULT_OPENROUTER_PAID_MODEL_ID
    )
    settings["openrouter_paid_model_enabled"] = bool(settings.get("openrouter_paid_model_enabled", False))
    settings["openrouter_show_paid_models"] = bool(settings.get("openrouter_show_paid_models", False))

    def _float_setting(name: str, default: float, min_value: float, max_value: float) -> float:
        try:
            value = float(settings.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(min_value, min(max_value, value))

    def _int_setting(name: str, default: int, min_value: int, max_value: int) -> int:
        try:
            value = int(settings.get(name, default))
        except (TypeError, ValueError):
            value = default
        return max(min_value, min(max_value, value))

    settings["openrouter_temperature"] = _float_setting("openrouter_temperature", 0.2, 0.0, 2.0)
    settings["openrouter_top_p"] = _float_setting("openrouter_top_p", 0.9, 0.0, 1.0)
    settings["openrouter_max_tokens"] = _int_setting("openrouter_max_tokens", 2048, 1, 262144)
    settings["openrouter_frequency_penalty"] = _float_setting("openrouter_frequency_penalty", 0.0, -2.0, 2.0)
    settings["openrouter_presence_penalty"] = _float_setting("openrouter_presence_penalty", 0.0, -2.0, 2.0)
    settings["openrouter_event_date_message_days"] = _int_setting("openrouter_event_date_message_days", 30, 1, 3650)
    settings["openrouter_timeout_sec"] = _float_setting("openrouter_timeout_sec", min(300.0, max(5.0, OPENROUTER_REQUEST_TIMEOUT_SEC)), 5.0, 300.0)
    settings["localhost_port"] = _int_setting("localhost_port", _default_local_web_port(), 1, 65535)
    settings["openrouter_allow_pii"] = bool(settings.get("openrouter_allow_pii", False))
    settings["runtime_log_mask_pii"] = bool(settings.get("runtime_log_mask_pii", True))
    settings["contact_qualification_prompts"] = _coerce_contact_qualification_prompts(
        settings.get("contact_qualification_prompts")
    )
    settings["llm_answer_prompts"] = _coerce_llm_answer_prompts(settings.get("llm_answer_prompts"))
    settings["import_default_add_limit"] = _int_setting("import_default_add_limit", 50, 1, 1000000)
    settings["telegram_unlimited_import_enabled"] = bool(settings.get("telegram_unlimited_import_enabled", False))
    settings["local_import_limits_enabled"] = bool(settings.get("local_import_limits_enabled", False)) or settings["telegram_unlimited_import_enabled"]
    settings["local_import_max_history_months"] = 0 if settings["telegram_unlimited_import_enabled"] else _int_setting(
        "local_import_max_history_months",
        1,
        1,
        1200,
    )
    settings["local_import_max_message_limit"] = 0 if settings["telegram_unlimited_import_enabled"] else _int_setting(
        "local_import_max_message_limit",
        1000,
        1,
        100000000,
    )
    settings["local_telegram_source_limit_enabled"] = bool(settings.get("local_telegram_source_limit_enabled", False))
    settings["local_telegram_source_limit"] = _int_setting("local_telegram_source_limit", 50, 0, 1000000)
    import_max_history_months = _xfiles_import_history_months_max()
    import_max_message_limit = _xfiles_import_message_limit_max()
    if settings["telegram_unlimited_import_enabled"]:
        import_max_history_months = 0
        import_max_message_limit = 0
    elif settings["local_import_limits_enabled"]:
        import_max_history_months = max(import_max_history_months, settings["local_import_max_history_months"])
        import_max_message_limit = max(import_max_message_limit, settings["local_import_max_message_limit"])
    settings["import_max_history_months"] = import_max_history_months
    settings["import_max_message_limit"] = import_max_message_limit
    settings["import_default_history_months"] = 0 if import_max_history_months == 0 else _int_setting(
        "import_default_history_months",
        1,
        1,
        max(1, import_max_history_months),
    )
    settings["import_default_message_limit"] = 0 if import_max_message_limit == 0 else _int_setting(
        "import_default_message_limit",
        1000,
        1,
        max(1, import_max_message_limit),
    )
    settings["outreach_auto_send_enabled"] = bool(settings.get("outreach_auto_send_enabled", False))
    settings["license_email_enabled"] = bool(settings.get("license_email_enabled", False))
    settings["license_email_host"] = str(settings.get("license_email_host") or "").strip()
    settings["license_email_port"] = _int_setting("license_email_port", 993, 1, 65535)
    settings["license_email_smtp_host"] = str(settings.get("license_email_smtp_host") or "").strip()
    settings["license_email_smtp_port"] = _int_setting("license_email_smtp_port", 465, 1, 65535)
    settings["license_email_login"] = str(settings.get("license_email_login") or "").strip()
    settings["license_email_inbox_folder"] = str(settings.get("license_email_inbox_folder") or "INBOX").strip() or "INBOX"
    settings["license_email_allow_activation_receipt"] = bool(
        settings.get("license_email_allow_activation_receipt", False)
    )
    settings["license_email_last_import_at"] = str(settings.get("license_email_last_import_at") or "").strip()
    raw_password = str(settings.pop("license_email_password", "") or "")
    clear_password = bool(settings.pop("license_email_clear_password", False))
    existing_secret = settings.get("license_email_password_secret")
    if clear_password:
        secret: Dict[str, str] = {}
    elif raw_password:
        secret = _encrypt_client_email_password(raw_password)
    elif _client_email_password_configured(existing_secret):
        secret = dict(existing_secret)
    else:
        secret = {}
    settings["license_email_password_secret"] = secret
    settings["license_email_password_configured"] = _client_email_password_configured(secret)
    settings["show_contact_qualification_prompt_settings"] = bool(
        settings.get("show_contact_qualification_prompt_settings", False)
    )
    settings["show_license_email_settings"] = bool(settings.get("show_license_email_settings", False))
    settings["dashboard_show_money_metrics"] = bool(settings.get("dashboard_show_money_metrics", False))
    settings["first_start_wizard_required"] = bool(
        not settings["setup_wizard_completed"] or not settings["telegram_api_configured"]
    )
    return settings


def _get_app_settings() -> Dict[str, Any]:
    sync = globals().get("telegram_sync")
    state = getattr(sync, "state", None)
    if isinstance(state, dict):
        raw = _sanitize_client_delivery_first_start_settings(state.get(APP_SETTINGS_STATE_KEY))
        settings = _coerce_app_settings(raw if isinstance(raw, dict) else None)
        state[APP_SETTINGS_STATE_KEY] = settings
        return settings

    if STATE_PATH.exists():
        try:
            state_payload = json.loads(STATE_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(state_payload, dict):
                raw = _sanitize_client_delivery_first_start_settings(state_payload.get(APP_SETTINGS_STATE_KEY))
                return _coerce_app_settings(raw if isinstance(raw, dict) else None)
        except Exception:
            pass
    return _coerce_app_settings()


def _save_app_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    current = _get_app_settings()
    merged = {**current, **settings}
    if _client_delivery_mode_enabled() and _client_setup_manual_update(settings):
        merged["client_setup_started"] = True
    normalized = _coerce_app_settings(merged)
    sync = globals().get("telegram_sync")
    if sync is not None and isinstance(getattr(sync, "state", None), dict):
        sync.state[APP_SETTINGS_STATE_KEY] = normalized
        sync.save_state()
        return normalized

    state_payload: Dict[str, Any] = {}
    if STATE_PATH.exists():
        try:
            raw = json.loads(STATE_PATH.read_text(encoding="utf-8", errors="replace"))
            if isinstance(raw, dict):
                state_payload = raw
        except Exception:
            state_payload = {}
    state_payload[APP_SETTINGS_STATE_KEY] = normalized
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def _contact_prompt_by_id(template_id: str) -> Optional[Dict[str, str]]:
    normalized = _normalize_contact_prompt_id(template_id)
    for prompt in _coerce_contact_qualification_prompts(_get_app_settings().get("contact_qualification_prompts")):
        if prompt.get("id") == normalized:
            return prompt
    return None


__all__ = [
    "refresh_legacy_globals",
    "_coerce_app_settings",
    "_coerce_contact_qualification_prompts",
    "_coerce_llm_answer_prompts",
    "_contact_prompt_by_id",
    "_default_app_settings",
    "_default_llm_answer_prompts",
    "_get_app_settings",
    "_save_app_settings",
    "_select_llm_answer_prompt",
]
