"""Shared Pydantic models extracted from the legacy backend."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Set, Union
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.common import (
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_OCR_SERVICE_URL,
    DEFAULT_OPENROUTER_MODEL_ID,
    DEFAULT_OPENROUTER_PAID_MODEL_ID,
    AnalysisKind,
    DealStage,
    OutreachTouchStatus,
    Stage,
    XFilesContractStatus,
    XFilesContractTemplateKind,
)


class Profile(BaseModel):
    topics: List[str] = []
    risks: List[str] = []
    nextStep: Optional[str] = None


class Deal(BaseModel):
    product: Optional[str] = None
    value: Optional[str] = None
    potential: float = 0
    budget: float = 0
    stage: Optional[Stage] = None
    probability: int = 0
    nextDate: Optional[str] = None
    nextTime: Optional[str] = None
    todo: Optional[str] = None


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    lang: Optional[str] = None
    company: Optional[str] = None
    city: Optional[str] = None
    role: Optional[str] = None
    source: Optional[str] = None
    activity: Optional[str] = "active"
    tags: List[str] = []
    score: int = 0
    stage: Optional[Stage] = None
    sentiment: Optional[str] = "neutral"
    lastAt: Optional[str] = None
    profile: Profile = Field(default_factory=Profile)
    deal: Deal = Field(default_factory=Deal)
    messages: List[Dict] = []
    notes: List[str] = []


class MessageIn(BaseModel):
    lead_id: str
    text: str


class MessageOut(MessageIn):
    id: str
    from_: str = Field("me", alias="from")
    when: str  # ISO-строка или любой ваш формат


class LeadsPageDTO(BaseModel):
    items: List[LeadDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class SourceStatsSummaryDTO(BaseModel):
    total_sources: int = 0
    selected_sources: int = 0
    imported_sources: int = 0
    active_sources: int = 0
    pending_sources: int = 0
    waiting_sources: int = 0
    error_sources: int = 0
    empty_sources: int = 0
    archived_sources: int = 0
    messages_total: int = 0
    messages_read: int = 0
    messages_remaining: int = 0
    progress_percent: float = 0.0
    generated_at: Optional[str] = None


class SourceStatsPageDTO(BaseModel):
    items: List[LeadDTO]
    summary: SourceStatsSummaryDTO = Field(default_factory=SourceStatsSummaryDTO)
    total: int
    page: int
    page_size: int
    total_pages: int


class SourceRuntimeStatusDTO(BaseModel):
    selector: str
    title: str
    chat_type: Literal["channel", "group", "private", "bot"] = "group"
    is_selected: bool = False
    has_jsonl: bool = False
    duckdb_rows: int = 0
    read_now: bool = False
    read_stage: Optional[str] = None
    live_connected: bool = False
    backfill_running: bool = False
    setup_running: bool = False
    paused: bool = False
    cooldown: bool = False
    waiting_schedule: bool = False
    read_done: int = 0
    read_total: int = 0
    remaining: int = 0
    progress_percent: float = 0.0
    scan_group: str = "C"
    scan_group_label: Optional[str] = None
    limit_months: int = 1
    limit_messages: int = 1000
    last_message_at: Optional[str] = None
    last_live_update_at: Optional[str] = None
    last_worker_heartbeat_at: Optional[str] = None
    status: str = "archived"
    status_reason: str = ""
    source_policy_mode: Literal["own", "allowed", "public", "unknown", "blocked"] = "unknown"
    source_scan_allowed: bool = True


class SourceRuntimeStatusPageDTO(BaseModel):
    items: List[SourceRuntimeStatusDTO]
    summary: SourceStatsSummaryDTO = Field(default_factory=SourceStatsSummaryDTO)
    total: int
    page: int
    page_size: int
    total_pages: int


class MessageDTO(BaseModel):
    id: int
    role: str           # "assistant" | "user" | "system"
    text: str
    date_utc: str
    reply_to_msg_id: Optional[int] = None
    has_media: Optional[bool] = None
    media_path: Optional[str] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None


class ChatTokenStatsDTO(BaseModel):
    ok: bool = True
    lead: str
    total_messages: int = 0
    total_tokens: int = 0
    max_messages: int = 0
    by_sender: List[ChatTokenSenderDTO] = Field(default_factory=list)
    updated_at: str = ""


class ChatAnalysisPayload(BaseModel):
    mode: Literal["all", "last_messages", "token_budget", "selected"] = "last_messages"
    message_limit: int = Field(default=10, ge=1, le=1_000_000)
    token_budget: int = Field(default=4000, ge=100, le=1_000_000)
    selected_message_ids: List[int] = Field(default_factory=list)
    prompt: str = (
        "Проанализируй выбранные сообщения чата. Выдели темы, потребности, сигналы продаж, "
        "риски и предложи следующие действия."
    )
    provider: Literal["openrouter", "local"] = "openrouter"
    model: str = ""
    sender_key: str = ""


class ChatAnalysisHistoryDTO(BaseModel):
    ok: bool = True
    lead: str
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ChatAnalysisRunDTO(BaseModel):
    ok: bool = True
    lead: str
    item: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    message: str = ""


class RuntimeLogDTO(BaseModel):
    id: int
    ts: str
    source: str
    channel: Literal["backend", "telegram"]
    message: str


class RuntimeStatusDTO(BaseModel):
    auth_status: Literal["authorized", "needs_api_credentials", "needs_auth", "session_present", "unknown"]
    auth_message: str
    session_file_exists: bool
    connected: bool
    telegram_authorized: Optional[bool] = None
    worker_connected: bool = False
    sync_paused: bool = False
    sync_pause_reason: Optional[str] = None
    sync_reading: bool = False
    sync_reading_stage: Optional[str] = None
    sync_status_detail: str = ""
    auth_step: Literal["api", "phone", "code", "password", "done"] = "phone"
    pending_phone: Optional[str] = None
    last_error: Optional[str] = None
    telegram_api_configured: bool = True
    telegram_api_id: Optional[str] = None
    telegram_api_credentials_source: str = ""
    auth_code_delivery_type: Optional[str] = None
    auth_code_next_type: Optional[str] = None
    auth_code_timeout_sec: Optional[int] = None
    auth_code_requested_at: Optional[str] = None
    auth_code_message: Optional[str] = None
    auth_code_hash_present: bool = False


class ServerRuntimeDTO(BaseModel):
    instance_id: str
    started_at: str
    uptime_sec: int
    pid: int
    hostname: str
    mode: Literal["docker", "local"]
    startup: Dict[str, Any] = Field(default_factory=dict)
    startup_running: bool = False
    startup_progress_percent: float = 100.0
    startup_phase: str = ""
    startup_summary: str = ""


class SystemMetricsDTO(BaseModel):
    ts: str
    sampler_interval_sec: float
    cpu_count: int
    cpu_percent: float = 0.0
    load_avg: List[float] = Field(default_factory=list)
    memory_used_mb: float = 0.0
    memory_total_mb: float = 0.0
    memory_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_total_gb: float = 0.0
    process_cpu_percent: float = 0.0
    process_memory_mb: float = 0.0
    open_files: int = 0
    threads: int = 0
    history: List[SystemMetricPointDTO] = Field(default_factory=list)
    tasks: List[BackgroundTaskStatusDTO] = Field(default_factory=list)


class TelegramAuthPhonePayload(BaseModel):
    phone: str


class TelegramAuthPhoneResendPayload(BaseModel):
    phone: str
    force_sms: bool = False
    reset_session: bool = False


class TelegramAuthCodePayload(BaseModel):
    code: str


class TelegramAuthPasswordPayload(BaseModel):
    password: str


class TelegramApiCredentialsPayload(BaseModel):
    api_id: str
    api_hash: str


class TelegramAuthActionDTO(BaseModel):
    ok: bool
    message: str
    status: RuntimeStatusDTO


class SourceSelectorPayload(BaseModel):
    selector: str


class SourceEditDTO(BaseModel):
    ok: bool
    message: str
    source_path: str
    selected: List[str]
    purge: Optional[Dict[str, Any]] = None


class SourcePolicyPayload(BaseModel):
    lead: str
    selector: Optional[str] = None
    mode: Literal["own", "allowed", "public", "unknown", "blocked"] = "unknown"
    reason: Optional[str] = None


class SourcePolicyActionDTO(BaseModel):
    ok: bool
    message: str
    item: SourcePolicyDTO


class SourcePolicyPageDTO(BaseModel):
    items: List[SourcePolicyDTO]
    total: int


class TelegramDialogsPageDTO(BaseModel):
    items: List[TelegramDialogDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class TelegramDialogsImportPayload(BaseModel):
    selectors: List[str]


class TelegramDialogsRemoveAddedPayload(BaseModel):
    selectors: List[str] = Field(default_factory=list)


class TelegramDialogSettingsPayload(BaseModel):
    selector: str
    import_history_months: int = Field(default=1, ge=0, le=1200)
    import_message_limit: int = Field(default=1000, ge=0, le=100000000)


class TelegramDialogSettingsDTO(BaseModel):
    ok: bool = True
    message: str = ""
    selector: str
    import_history_months: int
    import_message_limit: int
    import_max_history_months: int
    import_max_message_limit: int


class TelegramDialogsImportDTO(BaseModel):
    ok: bool
    message: str
    source_path: str
    selected: List[str]
    added_count: int
    added_selectors: List[str]


class TelegramDialogsRemoveAddedDTO(BaseModel):
    ok: bool
    message: str
    source_path: str
    selected: List[str]
    removed_count: int
    removed_selectors: List[str]


class ImportSyncStatusDTO(BaseModel):
    enabled: bool
    total_dialogs: int = 0
    completed_dialogs: int = 0
    active_dialogs: int = 0
    pending_dialogs: int = 0
    progress_percent: float = 0.0
    processed_units: int = 0
    total_units: int = 0
    eta_seconds: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    message: str


class ImportSyncActionDTO(BaseModel):
    ok: bool
    message: str
    status: ImportSyncStatusDTO


class ImageAssetsPageDTO(BaseModel):
    items: List[ImageAssetDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class ImageAssetTextDTO(BaseModel):
    media_path: str
    text_path: Optional[str] = None
    recognized: bool = False
    text: str = ""
    preview: Optional[str] = None
    crm_fields: List[Dict[str, str]] = Field(default_factory=list)
    crm_categories: List[str] = Field(default_factory=list)


class ImageOcrActionDTO(BaseModel):
    ok: bool
    message: str
    available: bool = False
    mode: str = "disabled"
    running: bool = False
    pending_count: int = 0
    processed_count: int = 0
    error_count: int = 0
    last_started_at: Optional[str] = None
    last_finished_at: Optional[str] = None
    last_error: Optional[str] = None


class OpenRouterModelsDTO(BaseModel):
    items: List[OpenRouterModelDTO]
    total: int
    source: str = "fallback"
    message: str = ""


class AppSettingsDTO(BaseModel):
    ok: bool = True
    message: str = "Настройки загружены"
    setup_wizard_completed: bool = False
    first_start_wizard_required: bool = True
    localhost_bind: str = "127.0.0.1"
    localhost_port: int = 8001
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_api_configured: bool = False
    telegram_api_credentials_source: str = "missing"
    telegram_client_backend: Literal["telethon", "tdlib"] = "telethon"
    telegram_scan_groups: List[Dict[str, Any]] = Field(default_factory=list)
    telegram_scan_group_assignments: Dict[str, str] = Field(default_factory=dict)
    ocr_images_enabled: bool = False
    ocr_delete_images_after_processing: bool = False
    ocr_service_url: str = DEFAULT_OCR_SERVICE_URL
    openrouter_api_key: str = ""
    llm_provider: Literal["openrouter", "local"] = DEFAULT_LLM_PROVIDER
    lmstudio_base_url: str = DEFAULT_LMSTUDIO_BASE_URL
    lmstudio_model: str = "local-model"
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL_ID
    openrouter_paid_model: str = DEFAULT_OPENROUTER_PAID_MODEL_ID
    openrouter_paid_model_enabled: bool = False
    openrouter_show_paid_models: bool = False
    openrouter_temperature: float = 0.2
    openrouter_top_p: float = 0.9
    openrouter_max_tokens: int = 2048
    openrouter_frequency_penalty: float = 0.0
    openrouter_presence_penalty: float = 0.0
    openrouter_event_date_message_days: int = 30
    openrouter_timeout_sec: float = 300.0
    openrouter_allow_pii: bool = False
    runtime_log_mask_pii: bool = True
    contact_qualification_prompts: List[Dict[str, str]] = Field(default_factory=list)
    llm_answer_prompts: List[Dict[str, Any]] = Field(default_factory=list)
    import_default_add_limit: int = 50
    import_default_history_months: int = 1
    import_default_message_limit: int = 1000
    import_max_history_months: int = 1
    import_max_message_limit: int = 1000
    telegram_unlimited_import_enabled: bool = False
    local_import_limits_enabled: bool = False
    local_import_max_history_months: int = 1
    local_import_max_message_limit: int = 1000
    local_telegram_source_limit_enabled: bool = False
    local_telegram_source_limit: int = 50
    outreach_auto_send_enabled: bool = False
    license_email_enabled: bool = False
    license_email_host: str = ""
    license_email_port: int = 993
    license_email_smtp_host: str = ""
    license_email_smtp_port: int = 465
    license_email_login: str = ""
    license_email_password_configured: bool = False
    license_email_inbox_folder: str = "INBOX"
    license_email_allow_activation_receipt: bool = False
    license_email_last_import_at: str = ""
    show_contact_qualification_prompt_settings: bool = False
    show_license_email_settings: bool = False
    dashboard_show_money_metrics: bool = False


class AppSettingsPayload(BaseModel):
    setup_wizard_completed: bool = False
    localhost_bind: str = "127.0.0.1"
    localhost_port: int = Field(default=8001, ge=1, le=65535)
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""
    telegram_client_backend: Literal["telethon", "tdlib"] = "telethon"
    telegram_scan_groups: List[Dict[str, Any]] = Field(default_factory=list)
    telegram_scan_group_assignments: Dict[str, str] = Field(default_factory=dict)
    ocr_images_enabled: bool = False
    ocr_delete_images_after_processing: bool = False
    ocr_service_url: str = DEFAULT_OCR_SERVICE_URL
    openrouter_api_key: str = ""
    llm_provider: Literal["openrouter", "local"] = DEFAULT_LLM_PROVIDER
    lmstudio_base_url: str = DEFAULT_LMSTUDIO_BASE_URL
    lmstudio_model: str = "local-model"
    openrouter_model: str = DEFAULT_OPENROUTER_MODEL_ID
    openrouter_paid_model: str = DEFAULT_OPENROUTER_PAID_MODEL_ID
    openrouter_paid_model_enabled: bool = False
    openrouter_show_paid_models: bool = False
    openrouter_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    openrouter_top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    openrouter_max_tokens: int = Field(default=2048, ge=1, le=262144)
    openrouter_frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    openrouter_presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    openrouter_event_date_message_days: int = Field(default=30, ge=1, le=3650)
    openrouter_timeout_sec: float = Field(default=300.0, ge=5.0, le=300.0)
    openrouter_allow_pii: bool = False
    runtime_log_mask_pii: bool = True
    contact_qualification_prompts: List[Dict[str, str]] = Field(default_factory=list)
    llm_answer_prompts: List[Dict[str, Any]] = Field(default_factory=list)
    import_default_add_limit: int = Field(default=50, ge=1, le=1000000)
    import_default_history_months: int = Field(default=1, ge=0, le=1200)
    import_default_message_limit: int = Field(default=1000, ge=0, le=100000000)
    telegram_unlimited_import_enabled: bool = False
    local_import_limits_enabled: bool = False
    local_import_max_history_months: int = Field(default=1, ge=0, le=1200)
    local_import_max_message_limit: int = Field(default=1000, ge=0, le=100000000)
    local_telegram_source_limit_enabled: bool = False
    local_telegram_source_limit: int = Field(default=50, ge=0, le=1000000)
    outreach_auto_send_enabled: bool = False
    license_email_enabled: bool = False
    license_email_host: str = ""
    license_email_port: int = Field(default=993, ge=1, le=65535)
    license_email_smtp_host: str = ""
    license_email_smtp_port: int = Field(default=465, ge=1, le=65535)
    license_email_login: str = ""
    license_email_password: str = ""
    license_email_clear_password: bool = False
    license_email_inbox_folder: str = "INBOX"
    license_email_allow_activation_receipt: bool = False
    show_contact_qualification_prompt_settings: bool = False
    show_license_email_settings: bool = False
    dashboard_show_money_metrics: bool = False


class XFilesLicenseStatusDTO(BaseModel):
    ok: bool = False
    status: str = "missing"
    message: str = ""
    read_only: bool = False
    disabled_reason: str = ""
    license_id: Optional[str] = None
    client_email: Optional[str] = None
    plan: Optional[str] = None
    plan_title: Optional[str] = None
    release: Optional[str] = None
    valid_until: Optional[str] = None
    grace_until: Optional[str] = None
    days_remaining: Optional[int] = None
    in_grace: bool = False
    limits: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    allowed_menus: List[str] = Field(default_factory=list)
    disabled_menus: List[str] = Field(default_factory=list)
    activated_at: Optional[str] = None
    last_applied_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    invite_batch_id: Optional[str] = None
    invite_code_required: bool = False
    invite_code_masked: str = ""
    license_id_display: str = ""
    invite_code_display: str = ""
    license_kind: Optional[str] = None
    activation_duration_days: Optional[int] = None
    max_activations: Optional[int] = None
    activation_count: Optional[int] = None
    history_count: int = 0
    license_server: Dict[str, Any] = Field(default_factory=dict)
    license_capabilities: Dict[str, Any] = Field(default_factory=dict)


class XFilesLicenseActivatePayload(BaseModel):
    invite_license: Optional[Dict[str, Any]] = None
    invite_license_json: str = ""
    invite_code: str = ""


class XFilesLicenseActionDTO(BaseModel):
    ok: bool = True
    message: str = ""
    status: XFilesLicenseStatusDTO


class XFilesLicenseEmailImportDTO(BaseModel):
    ok: bool = True
    message: str = ""
    email_message_id: str = ""
    activation_receipt_sent: bool = False
    status: XFilesLicenseStatusDTO


class XFilesLicenseAuditDTO(BaseModel):
    ts: str = ""
    action: str = ""
    ok: bool = False
    license_kind: str = ""
    license_id: str = ""
    client_id: str = ""
    client_email: str = ""
    plan: str = ""
    plan_title: str = ""
    release: str = ""
    valid_until: str = ""
    status: str = ""
    message: str = ""
    error: str = ""


class XFilesLicenseMenusDTO(BaseModel):
    ok: bool = False
    status: str = "missing"
    enforced: bool = False
    fallback: bool = True
    client_delivery: bool = False
    effective_allowed_menus: List[str] = Field(default_factory=list)
    disabled_menus: List[str] = Field(default_factory=list)
    default_disabled_menus: List[str] = Field(default_factory=list)
    items: List[XFilesLicenseMenuItemDTO] = Field(default_factory=list)


class XFilesLicenseMenuCheckPayload(BaseModel):
    menu: Optional[str] = None
    menus: List[str] = Field(default_factory=list)


class XFilesLicenseMenuCheckDTO(BaseModel):
    ok: bool = True
    status: str = "missing"
    allowed: Dict[str, bool] = Field(default_factory=dict)


class MediaStatusDTO(BaseModel):
    kind: Literal["media"] = "media"
    enabled: bool
    interval_sec: int = 0
    running: bool
    cache_ready: bool
    total_rows: int
    ocr_enabled: bool = False
    ocr_available: bool = False
    ocr_mode: str = "disabled"
    ocr_service_url: str = ""
    pending_count: int = 0
    processed_count: int = 0
    error_count: int = 0
    crm_rows_created: int = 0
    deleted_images: int = 0
    images_bytes: int = 0
    selected_leads_count: int = 0
    media_backfill_running: bool = False
    media_backfill_checked: int = 0
    media_backfill_downloaded: int = 0
    media_backfill_done_count: int = 0
    media_backfill_active_count: int = 0
    media_backfill_waiting_count: int = 0
    media_backfill_leads: List[Dict[str, Any]] = Field(default_factory=list)
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    progress_label: Optional[str] = None
    current_item: Optional[str] = None
    progress_started_at: Optional[str] = None
    progress_log: List[str] = Field(default_factory=list)
    last_refresh_at: Optional[str] = None
    last_error: Optional[str] = None
    next_refresh_at: Optional[str] = None
    stale_reason: Optional[str] = None


class MediaLeadPayload(BaseModel):
    lead: str


class MediaLeadsPayload(BaseModel):
    leads: List[str] = Field(default_factory=list)


class MediaConfigDTO(BaseModel):
    ok: bool
    message: str
    selected_leads: List[str]


class MediaClearDTO(BaseModel):
    ok: bool
    message: str
    deleted_images: int = 0
    deleted_texts: int = 0
    selected_leads: List[str]


class JurEntityFilesPageDTO(BaseModel):
    items: List[JurEntityFileDTO]
    total: int
    page: int
    page_size: int
    total_pages: int
    channel: str
    last_sync_at: Optional[str] = None
    sync_error: Optional[str] = None


class JurEntityActionPayload(BaseModel):
    file_key: str


class JurEntityActionDTO(BaseModel):
    ok: bool
    message: str
    file_key: str
    parser_selected: List[str]


class JurEntitySyncDTO(BaseModel):
    ok: bool
    message: str
    channel: str
    total_items: int
    downloaded_count: int = 0
    reused_count: int = 0
    last_sync_at: Optional[str] = None
    sync_error: Optional[str] = None


class LeadActionPayload(BaseModel):
    lead: str
    selector: Optional[str] = None


class LeadActionDTO(BaseModel):
    ok: bool
    message: str
    lead: str
    selected: List[str]


class LeadGroupPayload(BaseModel):
    lead: str
    selector: Optional[str] = None
    scan_group: str = "C"


class LeadGroupActionDTO(BaseModel):
    ok: bool
    message: str
    lead: str
    scan_group: str
    scan_group_label: Optional[str] = None
    scan_group_frequency: Optional[str] = None
    scan_group_interval_minutes: Optional[int] = None


class EventKeywordsDTO(BaseModel):
    keywords: List[str]
    message: str


class EventKeywordsPayload(BaseModel):
    keywords: List[str]


class EventMessagesPageDTO(BaseModel):
    items: List[EventMessageDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class EventMessageDeletePayload(BaseModel):
    lead: str = ""
    source_selector: Optional[str] = None
    message_id: Optional[int] = None
    text: str = ""


class EventMessageDeleteDTO(BaseModel):
    ok: bool
    message: str
    removed_count: int = 0


class SearchMessagesPageDTO(BaseModel):
    items: List[SearchMessageDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class SearchContextDTO(BaseModel):
    query: str
    total_matches: int
    context_blocks: List[str] = Field(default_factory=list)
    items: List[SearchMessageDTO] = Field(default_factory=list)


class AnalysisStatusDTO(BaseModel):
    kind: AnalysisKind
    enabled: bool
    interval_sec: int
    running: bool
    cache_ready: bool
    total_rows: int
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    progress_label: Optional[str] = None
    current_item: Optional[str] = None
    progress_started_at: Optional[str] = None
    progress_log: List[str] = Field(default_factory=list)
    last_refresh_at: Optional[str] = None
    last_error: Optional[str] = None
    next_refresh_at: Optional[str] = None
    stale_reason: Optional[str] = None
    event_date_running: bool = False
    event_date_total: int = 0
    event_date_processed: int = 0
    event_date_found: int = 0
    event_date_pending: int = 0
    event_date_percent: float = 0.0
    event_date_rate_per_min: float = 0.0
    event_date_started_at: Optional[str] = None
    event_date_updated_at: Optional[str] = None
    event_date_last_error: Optional[str] = None


class AnalysisConfigPayload(BaseModel):
    enabled: bool
    interval_sec: int = Field(ge=15, le=86400)


class AnalysisActionDTO(BaseModel):
    ok: bool
    message: str
    status: AnalysisStatusDTO


class DuckDbStatusDTO(BaseModel):
    kind: Literal["duckdb"] = "duckdb"
    available: bool
    enabled: bool
    running: bool
    cache_ready: bool
    db_path: str
    read_snapshot_path: Optional[str] = None
    read_snapshot_exists: bool = False
    read_snapshot_mtime: Optional[str] = None
    lock_status: Dict[str, Any] = Field(default_factory=dict)
    source_files_total: int = 0
    source_files_indexed: int = 0
    files_on_disk: int = 0
    files_selected: int = 0
    files_indexed: int = 0
    files_with_rows: int = 0
    tracked_files: int = 0
    message_rows: int = 0
    jsonl_rows_total: int = 0
    duckdb_rows_total: int = 0
    lag_rows_total: int = 0
    duplicate_message_rows: int = 0
    last_deduplicated_rows: int = 0
    file_registry_rows: int = 0
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    progress_label: Optional[str] = None
    current_item: Optional[str] = None
    progress_started_at: Optional[str] = None
    progress_updated_at: Optional[str] = None
    bytes_total: int = 0
    bytes_processed: int = 0
    rows_ingested_in_run: int = 0
    rows_per_sec: float = 0.0
    mb_per_sec: float = 0.0
    average_batch_size: float = 0.0
    current_file_rows_per_sec: float = 0.0
    current_file_mb_per_sec: float = 0.0
    sync_mode: str = "idle"
    current_phase: str = "idle"
    indexes_ready: bool = False
    parquet_stage_enabled: bool = False
    parquet_stage_used: bool = False
    parquet_stage_files: int = 0
    corrupt_jsonl_files: int = 0
    corrupt_jsonl_examples: List[str] = Field(default_factory=list)
    last_file_name: Optional[str] = None
    last_file_duration_sec: float = 0.0
    last_file_rows: int = 0
    derived_queued: List[str] = Field(default_factory=list)
    progress_log: List[str] = Field(default_factory=list)
    progress_history: List[str] = Field(default_factory=list)
    last_refresh_at: Optional[str] = None
    last_error: Optional[str] = None
    next_refresh_at: Optional[str] = None
    stale_reason: Optional[str] = None


class DuckDbActionDTO(BaseModel):
    ok: bool
    message: str
    status: DuckDbStatusDTO


class DuckDbExportDTO(BaseModel):
    ok: bool
    message: str
    parquet_dir: str
    exported_files: List[str] = Field(default_factory=list)
    status: DuckDbStatusDTO


class DuckDbParquetSidecarsDTO(BaseModel):
    ok: bool
    message: str
    parquet_dir: str
    created_files: List[str] = Field(default_factory=list)
    reused_files: List[str] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    parquet_files_total: int = 0
    parquet_bytes_total: int = 0
    selected_bytes_total: int = 0
    status: DuckDbStatusDTO


class DuckDbLegacyCacheCleanupDTO(BaseModel):
    ok: bool
    message: str
    archive_dir: str
    archived_files: List[str] = Field(default_factory=list)
    skipped_files: List[str] = Field(default_factory=list)
    status: DuckDbStatusDTO


class CrmContactsPageDTO(BaseModel):
    items: List[CrmContactDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class OutreachCrmFieldPayload(BaseModel):
    field_type: str
    field_label: Optional[str] = None
    value: str
    contact_key: Optional[str] = None
    lead: Optional[str] = None
    source_selector: Optional[str] = None
    message_id: Optional[int] = None
    date_utc: Optional[str] = None
    text: Optional[str] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None


class OutreachCrmFieldsPageDTO(BaseModel):
    items: List[OutreachCrmFieldDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class OutreachCrmFieldActionDTO(BaseModel):
    ok: bool
    message: str
    item: Optional[OutreachCrmFieldDTO] = None


class ContactDoNotContactPayload(BaseModel):
    enabled: bool = True
    reason: Optional[str] = None


class ContactDoNotContactActionDTO(BaseModel):
    ok: bool
    message: str
    contact_key: str
    do_not_contact: bool = False
    do_not_contact_reason: str = ""
    do_not_contact_updated_at: Optional[str] = None
    removed_outreach_items: int = 0


class XFilesOutreachSequencePayload(BaseModel):
    source_item_id: Optional[str] = None
    stable_key: Optional[str] = None
    title: Optional[str] = None
    contact_name: Optional[str] = None
    lead: Optional[str] = None
    source_selector: Optional[str] = None
    need: Optional[str] = None
    product_match: Optional[str] = None


class XFilesOutreachTouchStatusPayload(BaseModel):
    status: OutreachTouchStatus


class XFilesOutreachSequencePatchPayload(BaseModel):
    selected_variant: Optional[str] = None
    status: Optional[OutreachTouchStatus] = None


class XFilesOutreachSequenceActionDTO(BaseModel):
    ok: bool
    message: str
    item: Optional[XFilesOutreachSequenceDTO] = None


class XFilesOutreachSequencesPageDTO(BaseModel):
    items: List[XFilesOutreachSequenceDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class XFilesOutreachStatsDTO(BaseModel):
    total: int = 0
    sent: int = 0
    replies: int = 0
    reply_rate_percent: float = 0.0
    by_template: List[XFilesOutreachReplyRateDTO] = Field(default_factory=list)
    by_source: List[XFilesOutreachReplyRateDTO] = Field(default_factory=list)
    by_group: List[XFilesOutreachReplyRateDTO] = Field(default_factory=list)
    by_product: List[XFilesOutreachReplyRateDTO] = Field(default_factory=list)


class XFilesDealPayload(BaseModel):
    title: str
    stable_key: Optional[str] = None
    stage: DealStage = "lead"
    score: int = Field(default=0, ge=0, le=100)
    expected_value: float = Field(default=0.0, ge=0.0)
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    margin: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    contact_key: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = None
    source_chat: Optional[str] = None
    source_message_id: Optional[str] = None
    need: Optional[str] = None
    product_match: Optional[str] = None
    next_action: Optional[str] = None
    next_action_at: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None


class XFilesDealPatchPayload(BaseModel):
    title: Optional[str] = None
    stable_key: Optional[str] = None
    stage: Optional[DealStage] = None
    score: Optional[int] = Field(default=None, ge=0, le=100)
    expected_value: Optional[float] = Field(default=None, ge=0.0)
    probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    margin: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    contact_key: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = None
    source_chat: Optional[str] = None
    source_message_id: Optional[str] = None
    need: Optional[str] = None
    product_match: Optional[str] = None
    next_action: Optional[str] = None
    next_action_at: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None


class XFilesDealsPageDTO(BaseModel):
    items: List[XFilesDealDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class XFilesDealsKanbanDTO(BaseModel):
    items: List[XFilesDealsKanbanColumnDTO]
    total: int = 0
    limit_per_stage: int = 20


class XFilesDealActionDTO(BaseModel):
    ok: bool
    message: str
    item: Optional[XFilesDealDTO] = None


class XFilesDealAssistantDTO(BaseModel):
    deal_id: str
    generated_at: str
    contact_summary: str = ""
    who: str = ""
    discussed: List[str] = Field(default_factory=list)
    wants: List[str] = Field(default_factory=list)
    can_buy: str = ""
    next_best_message: str = ""
    objections: List[Dict[str, str]] = Field(default_factory=list)
    qualification_questions: List[str] = Field(default_factory=list)
    call_agenda: List[str] = Field(default_factory=list)
    five_minute_brief: List[str] = Field(default_factory=list)
    ten_bullets: List[str] = Field(default_factory=list)
    do_not_write: List[str] = Field(default_factory=list)
    recommended_score: int = 0
    recommended_next_action: str = ""
    source_messages: int = 0


class XFilesNegotiationBriefDTO(BaseModel):
    deal_id: str
    generated_at: str
    title: str = ""
    stage: DealStage = "lead"
    recommended_score: int = 0
    source_messages: int = 0
    brief: List[str] = Field(default_factory=list)
    strategy: List[str] = Field(default_factory=list)
    next_best_message: str = ""
    objection_replies: List[Dict[str, str]] = Field(default_factory=list)
    qualification_questions: List[str] = Field(default_factory=list)
    call_agenda: List[str] = Field(default_factory=list)
    do_not_write: List[str] = Field(default_factory=list)


class XFilesDealContractStatusPayload(BaseModel):
    contract_status: XFilesContractStatus


class XFilesDealContractKitDTO(BaseModel):
    deal_id: str
    generated_at: str
    contract_status: XFilesContractStatus = "needs_data"
    short_proposal: str = ""
    proposal_document: str = ""
    checklist: List[Dict[str, Any]] = Field(default_factory=list)
    missing_fields: List[str] = Field(default_factory=list)
    templates: List[XFilesContractTemplateDTO] = Field(default_factory=list)
    jur_matches: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class XFilesContractTemplatesPageDTO(BaseModel):
    items: List[XFilesContractTemplateDTO]
    total: int = 0
    generated_at: str


class XFilesContractMetricsDTO(BaseModel):
    generated_at: str
    deals_total: int = 0
    statuses: Dict[str, int] = Field(default_factory=dict)
    missing_fields_top: List[Dict[str, Any]] = Field(default_factory=list)
    duration_metrics: Dict[str, Any] = Field(default_factory=dict)
    ready_to_send: int = 0
    signed_or_paid: int = 0
    message: str = ""


class XFilesEventSalesPlanDTO(BaseModel):
    items: List[XFilesEventSalesPlanItemDTO]
    meeting_days: List[XFilesRouteMeetingDayDTO]
    total_events: int = 0
    events_with_dates: int = 0
    events_with_routes: int = 0
    group_outreach_candidates: int = 0
    generated_at: str


class XFilesProductMarginDTO(BaseModel):
    id: str
    name: str
    keywords: List[str] = Field(default_factory=list)
    margin: float = 1.0
    icp: str = ""
    pains: str = ""
    outcomes: str = ""
    price: str = ""
    timeline: str = ""
    proofs: str = ""
    cases: str = ""
    limitations: str = ""
    sell_to: str = ""
    do_not_sell_to: str = ""
    updated_at: str


class XFilesProductMarginPayload(BaseModel):
    id: Optional[str] = None
    name: str
    keywords: List[str] = Field(default_factory=list)
    margin: float = Field(default=1.0, ge=0.0, le=1.0)
    icp: Optional[str] = None
    pains: Optional[str] = None
    outcomes: Optional[str] = None
    price: Optional[str] = None
    timeline: Optional[str] = None
    proofs: Optional[str] = None
    cases: Optional[str] = None
    limitations: Optional[str] = None
    sell_to: Optional[str] = None
    do_not_sell_to: Optional[str] = None


class XFilesProductMarginsPageDTO(BaseModel):
    items: List[XFilesProductMarginDTO]
    total: int = 0


class XFilesDealAuditPageDTO(BaseModel):
    items: List[XFilesDealAuditDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class XFilesDealsStatusDTO(BaseModel):
    ok: bool = True
    storage: Literal["postgresql", "state"] = "state"
    postgresql_configured: bool = False
    postgresql_available: bool = False
    postgresql_waiting: bool = False
    total: int = 0
    active: int = 0
    won: int = 0
    lost: int = 0
    overdue: int = 0
    due_soon: int = 0
    sla_green: int = 0
    sla_yellow: int = 0
    sla_red: int = 0
    expected_value: float = 0.0
    expected_profit: float = 0.0
    pipeline_value: float = 0.0
    pipeline_profit: float = 0.0
    average_margin: float = 1.0
    margin_products: int = 0
    pipeline_attention_hours: float = 0.0
    pipeline_profit_per_attention_hour: float = 0.0
    qualified_leads_today: int = 0
    qualified_leads_per_day: float = 0.0
    avg_time_to_next_action_minutes: float = 0.0
    next_action_ready: int = 0
    next_action_missing: int = 0
    new_signals_today: int = 0
    qualified_active: int = 0
    stale_actions: int = 0
    conversion_funnel: List[XFilesFunnelStepDTO] = Field(default_factory=list)
    conversion_bottleneck: Optional[str] = None
    cost_metrics: Dict[str, Any] = Field(default_factory=dict)
    speed_metrics: Dict[str, Any] = Field(default_factory=dict)
    bottlenecks: List[XFilesDashboardInsightDTO] = Field(default_factory=list)
    recommended_actions: List[XFilesDashboardInsightDTO] = Field(default_factory=list)
    daily_plan: List[XFilesDailyPlanBucketDTO] = Field(default_factory=list)
    daily_plan_summary: str = ""
    priority_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    quick_money_deals: List[Dict[str, Any]] = Field(default_factory=list)
    strategic_deals: List[Dict[str, Any]] = Field(default_factory=list)
    source_roi: List[Dict[str, Any]] = Field(default_factory=list)
    source_group_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    profit_per_user_hour: float = 0.0
    message: str = ""
    last_error: Optional[str] = None


class XFilesDealRemindersDTO(BaseModel):
    items: List[XFilesDealReminderDTO]
    total: int = 0
    overdue: int = 0
    due_soon: int = 0
    generated_at: str


class XFilesDealConversionDTO(BaseModel):
    generated_at: str
    deal_total: int = 0
    active_deals: int = 0
    outreach_total: int = 0
    outreach_sent: int = 0
    outreach_replies: int = 0
    outreach_meetings: int = 0
    proposals: int = 0
    reply_rate_percent: float = 0.0
    meeting_rate_percent: float = 0.0
    proposal_rate_percent: float = 0.0
    funnel: List[XFilesFunnelStepDTO] = Field(default_factory=list)
    bottleneck: Optional[str] = None
    message: str = ""


class XFilesProfitOptimizationDTO(BaseModel):
    generated_at: str
    ranked_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    quick_money_deals: List[Dict[str, Any]] = Field(default_factory=list)
    strategic_deals: List[Dict[str, Any]] = Field(default_factory=list)
    source_roi: List[Dict[str, Any]] = Field(default_factory=list)
    source_group_recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    cost_metrics: Dict[str, Any] = Field(default_factory=dict)
    template_model_benchmarks: List[XFilesTemplateModelBenchmarkDTO] = Field(default_factory=list)
    recommendations: List[XFilesDashboardInsightDTO] = Field(default_factory=list)
    daily_plan: List[XFilesDailyPlanBucketDTO] = Field(default_factory=list)
    profit_per_user_hour: float = 0.0
    message: str = ""


class XFilesDealOpportunitiesDTO(BaseModel):
    items: List[XFilesDealOpportunityDTO]
    total: int = 0
    generated_at: str
    cached: bool = True
    message: str = ""


class XFilesNorthStarDTO(BaseModel):
    generated_at: str
    north_star_metric: str = "pipeline profit / час внимания пользователя"
    pipeline_profit_per_attention_hour: float = 0.0
    qualified_leads_per_day: float = 0.0
    avg_time_to_next_action_minutes: float = 0.0
    function_impacts: List[XFilesFunctionImpactDTO] = Field(default_factory=list)
    history: List[XFilesMetricHistoryPointDTO] = Field(default_factory=list)
    message: str = ""


class XFilesDailyContactsDTO(BaseModel):
    items: List[XFilesDailyContactDTO]
    total: int
    generated_at: str


class XFilesNeedSignalsPageDTO(BaseModel):
    items: List[XFilesNeedSignalDTO]
    total: int
    page: int
    page_size: int
    total_pages: int
    generated_at: str
    auto_created_deals: int = 0


class ContactQualificationPromptsDTO(BaseModel):
    items: List[ContactQualificationPromptDTO]
    total: int


class ContactQualificationDTO(BaseModel):
    contact_key: str
    template_id: str
    template_title: str
    prompt: str
    result_text: str = ""
    model: str = ""
    messages_count: int = 0
    status: Literal["ready", "error"] = "ready"
    error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages_fingerprint: str = ""
    latest_message_at: Optional[str] = None
    cache_hit: bool = False


class ContactQualificationsDTO(BaseModel):
    items: List[ContactQualificationDTO]
    total: int


class ContactQualificationRequestDTO(BaseModel):
    template_id: str
    force: bool = False


class TelegramContactChatFiltersDTO(BaseModel):
    items: List[TelegramContactChatFilterDTO]
    total: int


class TelegramContactsPageDTO(BaseModel):
    items: List[TelegramContactDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class TelegramContactMessagesPageDTO(BaseModel):
    items: List[TelegramContactMessageDTO]
    total: int
    page: int
    page_size: int
    total_pages: int


class RouteGeocodePayload(BaseModel):
    address_key: str
    lat: float
    lon: float


class SendPayload(BaseModel):
    chat_id: str
    message: str


class LlmRunPayload(BaseModel):
    chat_id: str
    filename: str
    prompt_id: Optional[str] = None


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    from_: Literal["me","lead"] = Field(default="lead", alias="from")
    text: str = ""
    when: Optional[str] = None
    channel: Optional[str] = None

    class Config:
        populate_by_name = True


class LeadDTO(BaseModel):
    name: str
    file: str
    count: int
    last_date_utc: Optional[str] = None
    last_text_preview: Optional[str] = None
    last_text_full: Optional[str] = None
    in_source: bool = False
    has_jsonl: bool = True
    sync_status: Literal["active", "pending", "archived"] = "archived"
    source_selector: Optional[str] = None
    chat_type: Literal["channel", "group", "private", "bot"] = "channel"
    is_archived: bool = False
    telegram_status: Optional[str] = None
    retry_after: Optional[str] = None
    last_sync_at: Optional[str] = None
    last_error: Optional[str] = None
    scan_group: str = "C"
    scan_group_label: Optional[str] = None
    scan_group_frequency: Optional[str] = None
    scan_group_interval_minutes: Optional[int] = None
    import_history_months: int = 1
    import_message_limit: int = 1000
    import_max_history_months: int = 1
    import_max_message_limit: int = 1000
    telegram_active: bool = False
    telegram_active_stage: Optional[str] = None
    last_live_update_at: Optional[str] = None
    live_connected: bool = False
    backfill_running: bool = False
    setup_running: bool = False
    paused: bool = False
    cooldown: bool = False
    waiting_schedule: bool = False
    read_messages_count: int = 0
    total_messages_estimate: int = 0
    remaining_messages_estimate: int = 0
    read_progress_percent: float = 0.0
    source_policy_mode: Literal["own", "allowed", "public", "unknown", "blocked"] = "unknown"
    source_scan_allowed: bool = True
    source_policy_reason: Optional[str] = None


class ChatTokenSenderDTO(BaseModel):
    sender_key: str
    sender_name: str = ""
    sender_username: str = ""
    messages_count: int = 0
    tokens: int = 0


class BackgroundTaskStatusDTO(BaseModel):
    kind: str
    label: str
    status: Literal["idle", "running", "error", "disabled", "stale"]
    running: bool = False
    enabled: bool = True
    cache_ready: bool = False
    total_rows: int = 0
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    current_item: Optional[str] = None
    summary: str
    last_refresh_at: Optional[str] = None
    next_refresh_at: Optional[str] = None
    last_error: Optional[str] = None


class SystemMetricPointDTO(BaseModel):
    ts: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    process_cpu_percent: float = 0.0
    process_memory_mb: float = 0.0


class SourcePolicyDTO(BaseModel):
    selector_key: str
    lead: str
    selector: Optional[str] = None
    mode: Literal["own", "allowed", "public", "unknown", "blocked"] = "unknown"
    scan_allowed: bool = True
    reason: str = ""
    updated_at: Optional[str] = None
    source: str = "manual"


class TelegramDialogDTO(BaseModel):
    id: int
    title: str
    username: Optional[str] = None
    selector: str
    chat_type: Literal["channel", "group", "private", "bot"]
    is_archived: bool = False
    is_already_added: bool = False
    unread_count: int = 0
    last_date_utc: Optional[str] = None
    last_text_preview: Optional[str] = None
    last_text_full: Optional[str] = None
    import_history_months: int = 1
    import_message_limit: int = 1000
    import_max_history_months: int = 1
    import_max_message_limit: int = 1000


class ImageAssetDTO(BaseModel):
    lead: str
    file_name: str
    media_path: str
    text_path: Optional[str] = None
    image_exists: bool = True
    recognized: bool = False
    ocr_preview: Optional[str] = None
    modified_at: Optional[str] = None
    size_bytes: int = 0


class OpenRouterModelDTO(BaseModel):
    id: str
    name: str
    context_length: Optional[int] = None
    free: bool = False
    pricing_prompt: Optional[str] = None
    pricing_completion: Optional[str] = None


class XFilesLicenseMenuItemDTO(BaseModel):
    key: str
    href: str
    label: str
    group: str
    allowed: bool = True
    disabled: bool = False


class JurEntityFileDTO(BaseModel):
    file_key: str
    message_id: int
    channel: str
    file_name: str
    file_path: str
    size_bytes: int = 0
    message_date_utc: Optional[str] = None
    caption_preview: Optional[str] = None
    parser_enabled: bool = False
    downloaded_at: Optional[str] = None
    structure_common: bool = False
    structure_label: Optional[str] = None
    structure_tone: Optional[str] = None
    structure_summary: Optional[str] = None
    structure_group_count: int = 0


class EventMessageDTO(BaseModel):
    lead: str
    source_selector: Optional[str] = None
    message_id: int
    date_utc: str
    event_date: Optional[str] = None
    event_date_confidence: Optional[float] = None
    event_date_source: Optional[str] = None
    text: str
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    matched_keywords: List[str] = Field(default_factory=list)


class SearchMessageDTO(BaseModel):
    lead: str
    source_selector: Optional[str] = None
    message_id: int
    date_utc: str
    text: str
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronymic: Optional[str] = None
    job_title: Optional[str] = None
    companies: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    city: Optional[str] = None
    match_sources: List[str] = Field(default_factory=list)


class CrmContactDTO(BaseModel):
    lead: str
    source_selector: Optional[str] = None
    message_id: int
    date_utc: str
    text: str
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    patronymic: Optional[str] = None
    name_components_count: int = 0
    job_title: Optional[str] = None
    companies: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    emails: List[str] = Field(default_factory=list)
    city: Optional[str] = None
    match_sources: List[str] = Field(default_factory=list)
    field_provenance: Dict[str, List[str]] = Field(default_factory=dict)


class OutreachCrmFieldDTO(BaseModel):
    id: str
    field_type: str
    field_label: str
    value: str
    contact_key: Optional[str] = None
    lead: Optional[str] = None
    source_selector: Optional[str] = None
    message_id: Optional[int] = None
    date_utc: Optional[str] = None
    text: Optional[str] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    status: str = "new"
    created_at: str
    deal_id: Optional[str] = None
    deal_title: Optional[str] = None
    deal_stage: Optional[str] = None
    deal_stage_label: Optional[str] = None


class XFilesOutreachTouchDTO(BaseModel):
    touch_key: str
    label: str
    goal: str
    message: str
    status: OutreachTouchStatus = "draft"
    updated_at: Optional[str] = None


class XFilesOutreachSequenceDTO(BaseModel):
    id: str
    stable_key: Optional[str] = None
    title: str
    source_item_id: Optional[str] = None
    contact_name: str = ""
    lead: Optional[str] = None
    source_selector: Optional[str] = None
    need: str = ""
    product_match: str = ""
    variants: Dict[str, str] = Field(default_factory=dict)
    selected_variant: str = "soft"
    template_key: str = "manual_ab"
    template_label: str = "Ручные A/B варианты"
    touches: List[XFilesOutreachTouchDTO] = Field(default_factory=list)
    status: OutreachTouchStatus = "draft"
    created_at: str
    updated_at: str


class XFilesOutreachReplyRateDTO(BaseModel):
    key: str
    label: str
    total: int = 0
    sent: int = 0
    replies: int = 0
    reply_rate_percent: float = 0.0


class XFilesDealDTO(BaseModel):
    id: str
    stable_key: Optional[str] = None
    title: str
    stage: DealStage = "lead"
    score: int = 0
    expected_value: float = 0.0
    probability: float = 0.0
    margin: float = 1.0
    expected_profit: float = 0.0
    contact_key: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = None
    source_chat: Optional[str] = None
    source_message_id: Optional[str] = None
    need: Optional[str] = None
    product_match: Optional[str] = None
    next_action: Optional[str] = None
    next_action_at: Optional[str] = None
    owner: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str
    sla_hours: int = 0
    sla_status: Literal["green", "yellow", "red", "done"] = "green"
    sla_reason: str = ""
    sla_deadline_at: Optional[str] = None
    stale_hours: float = 0.0


class XFilesDealsKanbanColumnDTO(BaseModel):
    stage: DealStage
    label: str
    items: List[XFilesDealDTO]
    total: int = 0
    expected_profit: float = 0.0
    overdue: int = 0
    due_soon: int = 0


class XFilesContractTemplateDTO(BaseModel):
    id: str
    kind: XFilesContractTemplateKind
    title: str
    description: str = ""
    body: str = ""


class XFilesEventSalesWindowDTO(BaseModel):
    key: str
    label: str
    action: str = ""
    action_at: Optional[str] = None
    tone: Literal["green", "yellow", "red"] = "yellow"


class XFilesRouteMeetingDayDTO(BaseModel):
    address_key: str
    address: str
    messages_count: int = 0
    leads_count: int = 0
    events_count: int = 0
    contacts_count: int = 0
    gps_ready: bool = False
    lat: Optional[float] = None
    lon: Optional[float] = None
    suggested_day: Optional[str] = None
    action: str = ""
    examples: List[Dict[str, Any]] = Field(default_factory=list)


class XFilesEventSalesPlanItemDTO(BaseModel):
    id: str
    lead: str = ""
    source_selector: Optional[str] = None
    message_id: Optional[int] = None
    event_date: Optional[str] = None
    message_date: Optional[str] = None
    place: str = ""
    topic: str = ""
    participants: List[str] = Field(default_factory=list)
    who_to_write: str = ""
    contact_key: str = ""
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    matched_keywords: List[str] = Field(default_factory=list)
    message: str = ""
    message_preview: str = ""
    offer: str = ""
    product_match: str = ""
    score: int = 0
    probability: float = 0.0
    margin: float = 1.0
    sales_window_label: str = ""
    next_action_at: Optional[str] = None
    next_action: str = ""
    sales_windows: List[XFilesEventSalesWindowDTO] = Field(default_factory=list)
    route_address: Optional[str] = None
    route_address_key: Optional[str] = None
    related_contacts_count: int = 0
    group_outreach_plan: Optional[str] = None
    has_deal: bool = False
    deal_id: Optional[str] = None
    deal_title: Optional[str] = None


class XFilesDealAuditDTO(BaseModel):
    id: str
    ts: str
    action: str
    deal_id: str
    deal_title: str = ""
    actor: str = "user"
    source: str = "ui"
    before_stage: Optional[str] = None
    after_stage: Optional[str] = None
    changes: Dict[str, Any] = Field(default_factory=dict)


class XFilesFunnelStepDTO(BaseModel):
    key: str
    label: str
    count: int = 0
    conversion_percent: float = 0.0
    tone: Literal["green", "yellow", "red"] = "yellow"


class XFilesDashboardInsightDTO(BaseModel):
    tone: Literal["green", "yellow", "red"] = "yellow"
    title: str
    metric: str = ""
    action: str = ""


class XFilesDailyPlanBucketDTO(BaseModel):
    key: str
    label: str
    target: int = 0
    count: int = 0
    tone: Literal["green", "yellow", "red"] = "yellow"
    items: List[Dict[str, Any]] = Field(default_factory=list)


class XFilesDealReminderDTO(BaseModel):
    deal_id: str
    title: str = ""
    stage: DealStage = "lead"
    stage_label: str = ""
    contact_key: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    source_chat: Optional[str] = None
    next_action: str = ""
    next_action_at: Optional[str] = None
    sla_status: Literal["green", "yellow", "red", "done"] = "green"
    sla_reason: str = ""
    sla_deadline_at: Optional[str] = None
    stale_hours: float = 0.0
    expected_profit: float = 0.0
    urgency: int = 0
    reminder_text: str = ""


class XFilesTemplateModelBenchmarkDTO(BaseModel):
    key: str
    kind: str = "unknown"
    template_id: str = "default"
    model: str = "unknown"
    prompt_hash: str = ""
    requests: int = 0
    ready: int = 0
    errors: int = 0
    success_rate_percent: float = 0.0
    avg_duration_sec: float = 0.0
    cost_estimate_usd: float = 0.0
    avg_cost_usd: float = 0.0
    cost_per_ready_usd: float = 0.0
    quality_proxy_score: int = 0
    recommendation: str = "watch"
    reason: str = ""


class XFilesDealOpportunityDTO(BaseModel):
    id: str
    rank: int = 0
    opportunity_type: Literal["deal", "need_signal"] = "deal"
    priority_score: int = 0
    title: str = ""
    stage: DealStage = "lead"
    stage_label: str = ""
    score: int = 0
    expected_value: float = 0.0
    expected_profit: float = 0.0
    probability: float = 0.0
    margin: float = 1.0
    attention_hours: float = 0.0
    profit_per_user_hour: float = 0.0
    urgency_score: int = 0
    who: str = ""
    contact_key: Optional[str] = None
    contact_name: Optional[str] = None
    company: Optional[str] = None
    source: Optional[str] = None
    source_chat: Optional[str] = None
    source_message_id: Optional[str] = None
    source_date: Optional[str] = None
    need: str = ""
    offer: str = ""
    when_to_write: str = ""
    next_action: str = ""
    next_action_at: Optional[str] = None
    first_message: str = ""
    why_now: str = ""
    has_deal: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class XFilesFunctionImpactDTO(BaseModel):
    key: str
    label: str
    value_type: Literal["money", "time", "risk", "speed"] = "speed"
    metric: str = ""
    current_value: float = 0.0
    unit: str = ""
    saved_time_minutes: float = 0.0
    earned_money: float = 0.0
    risk_reduction: str = ""
    speed_gain: str = ""
    recommendation: str = ""
    source: str = ""


class XFilesMetricHistoryPointDTO(BaseModel):
    date: str
    pipeline_profit: float = 0.0
    profit_per_user_hour: float = 0.0
    qualified_leads_per_day: float = 0.0
    cost_per_qualified_lead_usd: float = 0.0
    next_action_ready: int = 0
    active_deals: int = 0
    source_roi_count: int = 0


class XFilesDailyContactDTO(BaseModel):
    contact_key: str
    display_name: str = ""
    sender_username: Optional[str] = None
    latest_lead: Optional[str] = None
    total_messages: int = 0
    qualification_count: int = 0
    first_message_at: Optional[str] = None
    last_message_at: Optional[str] = None
    latest_message_preview: Optional[str] = None
    fit_score: int = 0
    intent_score: int = 0
    urgency_score: int = 0
    ability_to_pay_score: int = 0
    deal_score: int = 0
    why: str = ""
    qualification_card: str = ""
    topics: List[str] = Field(default_factory=list)
    pains: List[str] = Field(default_factory=list)
    buying_signals: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    best_product_hint: str = ""
    product_match_score: int = 0
    offer_recommendation: str = ""
    missing_qualification: str = ""
    lead_temperature: str = "needs_data"
    lead_temperature_label: str = "Нужно больше данных"
    score_explanation: str = ""
    why_now: str = ""
    next_action: str = ""
    first_message: str = ""
    has_deal: bool = False
    deal_id: Optional[str] = None
    deal_title: Optional[str] = None


class XFilesNeedSignalDTO(BaseModel):
    id: str
    stable_key: Optional[str] = None
    source: str = "message"
    source_label: str = "Сообщение"
    lead: Optional[str] = None
    source_selector: Optional[str] = None
    contact_key: Optional[str] = None
    contact_name: str = ""
    company: Optional[str] = None
    sender_username: Optional[str] = None
    message_id: Optional[int] = None
    date_utc: Optional[str] = None
    text: str = ""
    need: str = ""
    pain: str = ""
    task: str = ""
    budget: str = ""
    deadline: str = ""
    role: str = ""
    buying_context: str = ""
    objection: str = ""
    tags: List[str] = Field(default_factory=list)
    tag_labels: List[str] = Field(default_factory=list)
    urgency_label: str = ""
    product_match: str = ""
    product_match_score: int = 0
    product_match_probability: float = 0.0
    product_expected_value_hint: float = 0.0
    product_expected_profit_rank: float = 0.0
    product_margin: float = 1.0
    alternative_product: str = ""
    offer_recommendation: str = ""
    do_not_sell_reason: str = ""
    pitch: str = ""
    first_touch: str = ""
    score: int = 0
    has_deal: bool = False
    deal_id: Optional[str] = None
    deal_title: Optional[str] = None


class TelegramContactMessageDTO(BaseModel):
    lead: str
    source_selector: Optional[str] = None
    message_id: int
    date_utc: str
    text: str
    sender_id: Optional[int] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    has_media: bool = False


class TelegramContactDTO(BaseModel):
    contact_key: str
    sender_id: Optional[int] = None
    sender_username: Optional[str] = None
    sender_name: Optional[str] = None
    display_name: str
    total_messages: int = 0
    first_message_at: Optional[str] = None
    last_message_at: Optional[str] = None
    latest_lead: Optional[str] = None
    latest_message_preview: Optional[str] = None
    latest_message_text: Optional[str] = None
    related_messages_count: int = 0
    leads: List[str] = Field(default_factory=list)
    source_selectors: List[str] = Field(default_factory=list)
    related_messages: List[TelegramContactMessageDTO] = Field(default_factory=list)
    qualification_count: int = 0
    qualified_template_ids: List[str] = Field(default_factory=list)
    latest_qualification_at: Optional[str] = None
    lead_temperature: str = "needs_data"
    lead_temperature_label: str = "Нужно больше данных"
    fit_score: int = 0
    intent_score: int = 0
    urgency_score: int = 0
    ability_to_pay_score: int = 0
    deal_score: int = 0
    score_explanation: str = ""
    why_now: str = ""
    best_product_hint: str = ""
    missing_qualification: str = ""
    first_message_suggestion: str = ""
    first_message_updated_at: Optional[str] = None
    first_message_model: str = ""
    product_offer_suggestion: str = ""
    product_offer_updated_at: Optional[str] = None
    product_offer_model: str = ""
    do_not_contact: bool = False
    do_not_contact_reason: str = ""
    do_not_contact_updated_at: Optional[str] = None
    has_contact_data: bool = False
    has_phone: bool = False
    has_email: bool = False
    has_need: bool = False
    has_event: bool = False
    has_company: bool = False
    has_city: bool = False
    signal_tags: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)


class ContactQualificationPromptDTO(BaseModel):
    id: str
    title: str
    prompt: str


class TelegramContactChatFilterDTO(BaseModel):
    value: str
    label: str
    selector: Optional[str] = None
    total_contacts: int = 0


__all__ = [
    "AnalysisActionDTO",
    "AnalysisConfigPayload",
    "AnalysisStatusDTO",
    "AppSettingsDTO",
    "AppSettingsPayload",
    "BackgroundTaskStatusDTO",
    "ChatAnalysisHistoryDTO",
    "ChatAnalysisPayload",
    "ChatAnalysisRunDTO",
    "ChatTokenSenderDTO",
    "ChatTokenStatsDTO",
    "ContactDoNotContactActionDTO",
    "ContactDoNotContactPayload",
    "ContactQualificationDTO",
    "ContactQualificationPromptDTO",
    "ContactQualificationPromptsDTO",
    "ContactQualificationRequestDTO",
    "ContactQualificationsDTO",
    "CrmContactDTO",
    "CrmContactsPageDTO",
    "Deal",
    "DuckDbActionDTO",
    "DuckDbExportDTO",
    "DuckDbLegacyCacheCleanupDTO",
    "DuckDbParquetSidecarsDTO",
    "DuckDbStatusDTO",
    "EventKeywordsDTO",
    "EventKeywordsPayload",
    "EventMessageDTO",
    "EventMessageDeleteDTO",
    "EventMessageDeletePayload",
    "EventMessagesPageDTO",
    "ImageAssetDTO",
    "ImageAssetTextDTO",
    "ImageAssetsPageDTO",
    "ImageOcrActionDTO",
    "ImportSyncActionDTO",
    "ImportSyncStatusDTO",
    "JurEntityActionDTO",
    "JurEntityActionPayload",
    "JurEntityFileDTO",
    "JurEntityFilesPageDTO",
    "JurEntitySyncDTO",
    "Lead",
    "LeadActionDTO",
    "LeadActionPayload",
    "LeadDTO",
    "LeadGroupActionDTO",
    "LeadGroupPayload",
    "LeadsPageDTO",
    "SourceStatsSummaryDTO",
    "SourceStatsPageDTO",
    "LlmRunPayload",
    "MediaClearDTO",
    "MediaConfigDTO",
    "MediaLeadPayload",
    "MediaLeadsPayload",
    "MediaStatusDTO",
    "Message",
    "MessageDTO",
    "MessageIn",
    "MessageOut",
    "OpenRouterModelDTO",
    "OpenRouterModelsDTO",
    "OutreachCrmFieldActionDTO",
    "OutreachCrmFieldDTO",
    "OutreachCrmFieldPayload",
    "OutreachCrmFieldsPageDTO",
    "Profile",
    "RouteGeocodePayload",
    "RuntimeLogDTO",
    "RuntimeStatusDTO",
    "SearchContextDTO",
    "SearchMessageDTO",
    "SearchMessagesPageDTO",
    "SendPayload",
    "ServerRuntimeDTO",
    "SourceEditDTO",
    "SourcePolicyActionDTO",
    "SourcePolicyDTO",
    "SourcePolicyPageDTO",
    "SourcePolicyPayload",
    "SourceSelectorPayload",
    "Stage",
    "SystemMetricPointDTO",
    "SystemMetricsDTO",
    "TelegramApiCredentialsPayload",
    "TelegramAuthActionDTO",
    "TelegramAuthCodePayload",
    "TelegramAuthPasswordPayload",
    "TelegramAuthPhonePayload",
    "TelegramAuthPhoneResendPayload",
    "TelegramContactChatFilterDTO",
    "TelegramContactChatFiltersDTO",
    "TelegramContactDTO",
    "TelegramContactMessageDTO",
    "TelegramContactMessagesPageDTO",
    "TelegramContactsPageDTO",
    "TelegramDialogDTO",
    "TelegramDialogSettingsDTO",
    "TelegramDialogSettingsPayload",
    "TelegramDialogsImportDTO",
    "TelegramDialogsImportPayload",
    "TelegramDialogsPageDTO",
    "TelegramDialogsRemoveAddedDTO",
    "TelegramDialogsRemoveAddedPayload",
    "XFilesContractMetricsDTO",
    "XFilesContractTemplateDTO",
    "XFilesContractTemplatesPageDTO",
    "XFilesDailyContactDTO",
    "XFilesDailyContactsDTO",
    "XFilesDailyPlanBucketDTO",
    "XFilesDashboardInsightDTO",
    "XFilesDealActionDTO",
    "XFilesDealAssistantDTO",
    "XFilesDealAuditDTO",
    "XFilesDealAuditPageDTO",
    "XFilesDealContractKitDTO",
    "XFilesDealContractStatusPayload",
    "XFilesDealConversionDTO",
    "XFilesDealDTO",
    "XFilesDealOpportunitiesDTO",
    "XFilesDealOpportunityDTO",
    "XFilesDealPatchPayload",
    "XFilesDealPayload",
    "XFilesDealReminderDTO",
    "XFilesDealRemindersDTO",
    "XFilesDealsKanbanColumnDTO",
    "XFilesDealsKanbanDTO",
    "XFilesDealsPageDTO",
    "XFilesDealsStatusDTO",
    "XFilesEventSalesPlanDTO",
    "XFilesEventSalesPlanItemDTO",
    "XFilesEventSalesWindowDTO",
    "XFilesFunctionImpactDTO",
    "XFilesFunnelStepDTO",
    "XFilesLicenseActionDTO",
    "XFilesLicenseActivatePayload",
    "XFilesLicenseAuditDTO",
    "XFilesLicenseEmailImportDTO",
    "XFilesLicenseMenuCheckDTO",
    "XFilesLicenseMenuCheckPayload",
    "XFilesLicenseMenuItemDTO",
    "XFilesLicenseMenusDTO",
    "XFilesLicenseStatusDTO",
    "XFilesMetricHistoryPointDTO",
    "XFilesNeedSignalDTO",
    "XFilesNeedSignalsPageDTO",
    "XFilesNegotiationBriefDTO",
    "XFilesNorthStarDTO",
    "XFilesOutreachReplyRateDTO",
    "XFilesOutreachSequenceActionDTO",
    "XFilesOutreachSequenceDTO",
    "XFilesOutreachSequencePatchPayload",
    "XFilesOutreachSequencePayload",
    "XFilesOutreachSequencesPageDTO",
    "XFilesOutreachStatsDTO",
    "XFilesOutreachTouchDTO",
    "XFilesOutreachTouchStatusPayload",
    "XFilesProductMarginDTO",
    "XFilesProductMarginPayload",
    "XFilesProductMarginsPageDTO",
    "XFilesProfitOptimizationDTO",
    "XFilesRouteMeetingDayDTO",
    "XFilesTemplateModelBenchmarkDTO",
]

for _model_name in __all__:
    _model = globals().get(_model_name)
    if hasattr(_model, "model_rebuild"):
        _model.model_rebuild(_types_namespace=globals())
