"""Telegram synchronization runtime extracted from the legacy backend."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone


def refresh_legacy_globals() -> None:
    runtime = sys.modules.get("app.legacy_runtime")
    legacy_back = sys.modules.get("back")
    for source in (runtime, legacy_back):
        if source is None:
            continue
        for name, value in vars(source).items():
            if not name.startswith("__"):
                globals().setdefault(name, value)


refresh_legacy_globals()

from app.services.telegram_sync.backfill import backfill_stop_reason, build_backfill_limits
from app.services.telegram_sync.client import session_file_paths as telegram_session_file_paths
from app.services.telegram_sync.live import forget_completed_task
from app.services.telegram_sync.rate_limits import flood_wait_seconds, rate_limit_state
from app.services.telegram_sync.selectors import (
    load_selected_chats_from_state,
    parse_selector_line,
    selector_key,
)
from app.services.telegram_sync.state import existing_jsonl_message_bounds, normalize_chat_state
from app.core.state import StateRepository, load_json_object

TELEGRAM_AUTH_CODE_STATE_KEY = "_telegram_auth_code"

class TelegramSync:
    def __init__(
        self,
        api_id: Optional[int],
        api_hash: str,
        session: str,
        out_dir: Path,
        state_path: Path,
        source_path: Optional[Path] = None,
    ):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self._ensure_session_parent_dir()
        self.client: Optional[TelegramClient] = None
        self._client_init_error: Optional[str] = None
        self.out_dir = out_dir
        self.state_path = state_path
        self._state_repository = StateRepository(state_path)
        self.source_path = source_path

        self.state: Dict[str, Any] = {}
        self.selected_chats: List[Union[str, int]] = self._load_selected_chats()
        self.entities_by_chat_key: Dict[str, Any] = {}
        self._live_handlers_installed: set[str] = set()
        self._desired_selector_keys: set[str] = set()
        self._enabled_chat_keys: set[str] = set()
        self._selector_to_chat_key: Dict[str, str] = {}
        self._chat_setup_tasks: Dict[str, asyncio.Task] = {}
        self._chat_backfill_tasks: Dict[str, asyncio.Task] = {}
        self._chat_media_backfill_tasks: Dict[str, asyncio.Task] = {}
        self._source_poll_interval = float(os.environ.get("PAYME_SOURCE_POLL_SEC", "5"))
        self._connect_retry_sec = float(os.environ.get("PAYME_CONNECT_RETRY_SEC", "5"))
        self._connect_timeout_sec = float(os.environ.get("PAYME_TELEGRAM_CONNECT_TIMEOUT_SEC", "12"))
        self._activity_log_interval_sec = float(os.environ.get("PAYME_ACTIVITY_LOG_SEC", "2"))
        self._setup_concurrency = 1
        self._backfill_concurrency = 1
        self._media_backfill_concurrency = 1
        self._telegram_429_retry_sec = max(30.0, float(os.environ.get("PAYME_TELEGRAM_429_RETRY_SEC", "60")))
        self._last_activity_log_at: Dict[str, float] = {}
        self._global_flood_wait_until_mono: float = 0.0
        self._global_flood_wait_until_iso: Optional[str] = None
        self._global_flood_wait_reason: str = ""
        self._global_flood_wait_last_log_at: float = 0.0
        self._source_reload_event = asyncio.Event()

        self._startup_lock = asyncio.Lock()
        self._auth_lock = asyncio.Lock()
        self._setup_lock = asyncio.Semaphore(self._setup_concurrency)
        self._backfill_lock = asyncio.Semaphore(self._backfill_concurrency)
        self._media_backfill_lock = asyncio.Semaphore(self._media_backfill_concurrency)
        self._dialogs_lock = asyncio.Semaphore(1)
        self._sync_task: Optional[asyncio.Task] = None
        self._connection_watch_task: Optional[asyncio.Task] = None
        self._started = False
        self._auth_phone: Optional[str] = None
        self._auth_phone_code_hash: Optional[str] = None
        self._auth_code_delivery_type: Optional[str] = None
        self._auth_code_next_type: Optional[str] = None
        self._auth_code_timeout_sec: Optional[int] = None
        self._auth_code_requested_at: Optional[str] = None
        self._auth_code_message: Optional[str] = None
        self._auth_code_hash_present: bool = False
        self._auth_pause_previous_status: Optional[Dict[str, Any]] = None
        self._auth_step: Literal["api", "phone", "code", "password", "done"] = (
            "phone" if self.has_api_credentials() else "api"
        )
        self._auth_last_error: Optional[str] = None
        self._ensure_client_available()

    @staticmethod
    def _import_limit_int(value: Any, default: int) -> int:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except Exception:
            return default

    def has_api_credentials(self) -> bool:
        return bool(self.api_id and self.api_hash)

    def _new_client(self) -> TelegramClient:
        if not self.has_api_credentials():
            raise RuntimeError("Telegram api_id/api_hash are not configured")
        self._ensure_session_parent_dir()
        return TelegramClient(
            self.session,
            int(self.api_id or 0),
            self.api_hash,
            connection_retries=1,
            retry_delay=1,
            timeout=max(3, int(self._connect_timeout_sec)),
        )

    def _ensure_client_available(self) -> bool:
        if self.client is not None:
            return True
        if not self.has_api_credentials():
            self.client = None
            self._client_init_error = "Telegram api_id/api_hash не указаны"
            self._auth_step = "api"
            return False
        try:
            self.client = self._new_client()
            self._client_init_error = None
            return True
        except Exception as exc:
            self.client = None
            self._client_init_error = str(exc)
            print(f"[telegram-sync] client init error: {exc!r}")
            return False

    def _ensure_session_parent_dir(self) -> None:
        session_path = Path(self.session)
        if session_path.parent and str(session_path.parent) not in ("", "."):
            session_path.parent.mkdir(parents=True, exist_ok=True)

    def _session_file_paths(self) -> List[Path]:
        return telegram_session_file_paths(self.session)

    def _clear_auth_progress(self, *, keep_phone: bool = False) -> None:
        if not keep_phone:
            self._auth_phone = None
        self._auth_phone_code_hash = None
        self._clear_auth_code_delivery()
        self._auth_step = "phone" if self.has_api_credentials() else "api"
        self._auth_last_error = None

    def _clear_auth_code_delivery(self) -> None:
        self._auth_code_delivery_type = None
        self._auth_code_next_type = None
        self._auth_code_timeout_sec = None
        self._auth_code_requested_at = None
        self._auth_code_message = None
        self._auth_code_hash_present = False
        if isinstance(getattr(self, "state", None), dict) and TELEGRAM_AUTH_CODE_STATE_KEY in self.state:
            self.state.pop(TELEGRAM_AUTH_CODE_STATE_KEY, None)
            try:
                self.save_state()
            except Exception as exc:
                print(f"[telegram-auth] auth code state cleanup skipped: {exc!r}")

    def _ensure_state_loaded(self) -> None:
        if not isinstance(getattr(self, "state", None), dict) or not self.state:
            try:
                self.state = self.load_state()
            except Exception:
                self.state = {}

    def _persist_auth_code_status(self) -> None:
        self._ensure_state_loaded()
        self.state[TELEGRAM_AUTH_CODE_STATE_KEY] = {
            "delivery_type": self._auth_code_delivery_type,
            "next_type": self._auth_code_next_type,
            "timeout_sec": self._auth_code_timeout_sec,
            "requested_at": self._auth_code_requested_at,
            "message": self._auth_code_message,
            "hash_present": bool(self._auth_phone_code_hash or self._auth_code_hash_present),
            "phone": self._auth_phone,
            "auth_step": self._auth_step,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.save_state()
        except Exception as exc:
            print(f"[telegram-auth] auth code state persist skipped: {exc!r}")

    def _hydrate_auth_code_status_from_state(self) -> None:
        if self._auth_code_message or self._auth_code_requested_at:
            return
        self._ensure_state_loaded()
        current = self.state.get(TELEGRAM_AUTH_CODE_STATE_KEY)
        if not isinstance(current, dict):
            return
        self._auth_code_delivery_type = current.get("delivery_type") or None
        self._auth_code_next_type = current.get("next_type") or None
        try:
            timeout = int(current.get("timeout_sec") or 0)
        except Exception:
            timeout = 0
        self._auth_code_timeout_sec = timeout if timeout > 0 else None
        self._auth_code_requested_at = current.get("requested_at") or None
        self._auth_code_message = current.get("message") or None
        self._auth_code_hash_present = bool(current.get("hash_present"))

    @staticmethod
    def _sent_code_type_name(value: Any) -> Optional[str]:
        if value is None:
            return None
        name = type(value).__name__
        if name and name != "str":
            return name
        text = str(value).strip()
        return text or None

    @staticmethod
    def _sent_code_timeout(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _delivery_human_message(
        delivery_type: Optional[str],
        next_type: Optional[str],
        timeout_sec: Optional[int],
        *,
        force_sms: bool = False,
    ) -> str:
        delivery = (delivery_type or "").lower()
        next_delivery = (next_type or "").lower()
        if "sms" in delivery:
            base = "Telegram отправил SMS-код."
        elif "call" in delivery:
            base = "Telegram отправляет код звонком."
        elif "app" in delivery:
            base = "Telegram отправил код в приложение Telegram на этом аккаунте."
        elif force_sms:
            base = "Запрошена повторная отправка кода через SMS/другой способ."
        else:
            base = "Telegram принял запрос кода."
        if next_type and timeout_sec:
            base += f" Следующий способ ({next_type}) можно запросить примерно через {timeout_sec} сек."
        elif next_type:
            base += f" Следующий способ доставки: {next_type}."
        elif timeout_sec:
            base += f" Повторный запрос обычно доступен примерно через {timeout_sec} сек."
        if "app" in delivery and ("sms" in next_delivery or "call" in next_delivery) and timeout_sec:
            base += " Если код не виден в Telegram, дождитесь таймера и запросите SMS/звонок."
        return base

    def _record_auth_sent_code(self, sent_code: Any, *, force_sms: bool = False) -> str:
        delivery_type = self._sent_code_type_name(getattr(sent_code, "type", None))
        next_type = self._sent_code_type_name(getattr(sent_code, "next_type", None))
        timeout_sec = self._sent_code_timeout(getattr(sent_code, "timeout", None))
        self._auth_code_delivery_type = delivery_type
        self._auth_code_next_type = next_type
        self._auth_code_timeout_sec = timeout_sec
        self._auth_code_requested_at = datetime.now(timezone.utc).isoformat()
        self._auth_code_hash_present = bool(getattr(sent_code, "phone_code_hash", None))
        self._auth_code_message = self._delivery_human_message(
            delivery_type,
            next_type,
            timeout_sec,
            force_sms=force_sms,
        )
        message = (
            "Telegram auth code requested: "
            f"delivery={delivery_type or 'unknown'}, next={next_type or '-'}, "
            f"timeout={timeout_sec if timeout_sec is not None else '-'}, "
            f"hash_present={self._auth_code_hash_present}"
        )
        print(f"[telegram-auth] {message}")
        append_runtime_log = globals().get("_append_runtime_log")
        if callable(append_runtime_log):
            append_runtime_log("telegram-auth", message)
        self._persist_auth_code_status()
        return self._auth_code_message

    def auth_code_status(self) -> Dict[str, Any]:
        self._hydrate_auth_code_status_from_state()
        return {
            "auth_code_delivery_type": self._auth_code_delivery_type,
            "auth_code_next_type": self._auth_code_next_type,
            "auth_code_timeout_sec": self._auth_code_timeout_sec,
            "auth_code_requested_at": self._auth_code_requested_at,
            "auth_code_message": self._auth_code_message,
            "auth_code_hash_present": bool(self._auth_phone_code_hash or self._auth_code_hash_present),
        }

    def _remaining_auth_code_timeout_sec(self) -> int:
        self._hydrate_auth_code_status_from_state()
        if not self._auth_code_timeout_sec or not self._auth_code_requested_at:
            return 0
        try:
            requested_at = datetime.fromisoformat(str(self._auth_code_requested_at))
            if requested_at.tzinfo is None:
                requested_at = requested_at.replace(tzinfo=timezone.utc)
        except Exception:
            return 0
        until = requested_at + timedelta(seconds=int(self._auth_code_timeout_sec))
        remaining = int((until - datetime.now(timezone.utc)).total_seconds())
        return max(0, remaining)

    def _set_auth_error(
        self,
        message: str,
        step: Optional[Literal["api", "phone", "code", "password"]] = None,
    ) -> None:
        self._auth_last_error = message
        if step:
            self._auth_step = step

    async def apply_api_credentials(self, api_id: Optional[int], api_hash: str) -> bool:
        normalized_id = int(api_id) if api_id else None
        normalized_hash = _normalize_telegram_api_hash(api_hash)
        changed = normalized_id != self.api_id or normalized_hash != self.api_hash
        if not changed:
            if self.has_api_credentials() and self.client is None:
                self._ensure_client_available()
            return False

        await self.stop()
        self._sync_task = None
        self._connection_watch_task = None

        self.api_id = normalized_id
        self.api_hash = normalized_hash
        self.client = None
        self._client_init_error = None
        self._started = False
        self._clear_auth_progress()
        self._ensure_client_available()
        return True

    async def _reset_client(self, *, drop_session: bool = False) -> None:
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        self._sync_task = None

        if self._connection_watch_task and not self._connection_watch_task.done():
            self._connection_watch_task.cancel()
            try:
                await self._connection_watch_task
            except asyncio.CancelledError:
                pass
        self._connection_watch_task = None

        for selector_key, task in list(self._chat_setup_tasks.items()):
            if not task.done():
                task.cancel()
            self._chat_setup_tasks.pop(selector_key, None)
        for chat_key, task in list(self._chat_backfill_tasks.items()):
            if not task.done():
                task.cancel()
            self._chat_backfill_tasks.pop(chat_key, None)

        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass

        self.entities_by_chat_key.clear()
        self._live_handlers_installed.clear()
        self._desired_selector_keys.clear()
        self._enabled_chat_keys.clear()
        self._selector_to_chat_key.clear()
        self._chat_backfill_tasks.clear()

        if drop_session:
            for path in self._session_file_paths():
                path.unlink(missing_ok=True)

        self.client = None
        self._ensure_client_available()

    async def _release_session_handles_for_pause(self, reason: str = "sync paused") -> None:
        """Disconnect Telethon and cancel child tasks without deleting the shared session.

        Telethon stores auth/update state in a SQLite ``.session`` file. The backend
        setup wizard and the celery Telegram worker share that file through the
        Docker volume, so every long-running sync task must release it before the
        setup wizard requests a new auth code. Otherwise SQLite may surface the
        conflict as ``disk I/O error`` or ``attempt to write a readonly database``.
        """

        current_task = asyncio.current_task()
        connection_watch_task = getattr(self, "_connection_watch_task", None)
        if connection_watch_task and connection_watch_task is not current_task and not connection_watch_task.done():
            connection_watch_task.cancel()
            try:
                await connection_watch_task
            except asyncio.CancelledError:
                pass
        self._connection_watch_task = None

        for task_map in (
            getattr(self, "_chat_setup_tasks", {}),
            getattr(self, "_chat_backfill_tasks", {}),
            getattr(self, "_chat_media_backfill_tasks", {}),
        ):
            for key, task in list(task_map.items()):
                if task is current_task:
                    continue
                if not task.done():
                    task.cancel()
                task_map.pop(key, None)

        if getattr(self, "client", None) is not None:
            try:
                await self.client.disconnect()
            except Exception as exc:
                print(f"[telegram-sync] session release disconnect skipped: {exc!r}")

        self.client = None
        self._started = False
        getattr(self, "entities_by_chat_key", {}).clear()
        getattr(self, "_live_handlers_installed", set()).clear()
        getattr(self, "_enabled_chat_keys", set()).clear()
        getattr(self, "_selector_to_chat_key", {}).clear()
        print(f"[telegram-sync] session handles released: {reason}")

    async def _pause_sync_for_auth(self) -> None:
        current = self.get_sync_control_status()
        if self._auth_pause_previous_status is None:
            self._auth_pause_previous_status = dict(current)
        if not bool(current.get("paused")):
            self.set_sync_paused(True, reason="telegram authorization")
            self.request_source_reload()
        await self._release_session_handles_for_pause("telegram authorization")
        grace_sec = max(0.0, float(os.environ.get("PAYME_AUTH_SESSION_RELEASE_GRACE_SEC", "6")))
        if grace_sec:
            await asyncio.sleep(grace_sec)

    async def _resume_sync_after_auth_if_needed(self) -> None:
        previous = self._auth_pause_previous_status
        self._auth_pause_previous_status = None
        if previous is not None and not bool(previous.get("paused")):
            self.set_sync_paused(False, reason="telegram authorization complete")
            self.request_source_reload()

    async def _ensure_connected_for_auth(self) -> None:
        if not self._ensure_client_available() or self.client is None:
            raise RuntimeError(
                f"Telegram session is unavailable: {self._client_init_error or 'client init failed'}"
            )
        try:
            await self.client.connect()
        except AuthKeyUnregisteredError:
            await self._reset_client(drop_session=True)
            if self.client is None:
                raise RuntimeError(
                    f"Telegram session is unavailable: {self._client_init_error or 'client init failed'}"
                )
            await self.client.connect()

    async def start_web_auth(self, phone: str, *, force_sms: bool = False, reset_session: bool = True) -> str:
        normalized_phone = (phone or "").strip()
        if not normalized_phone:
            raise ValueError("Введите номер телефона")

        async with self._auth_lock:
            same_pending_phone = self._auth_phone == normalized_phone
            if (
                same_pending_phone
                and self._auth_step == "code"
                and self._auth_phone_code_hash
                and not force_sms
            ):
                delivery_message = self._auth_code_message or self._delivery_human_message(
                    self._auth_code_delivery_type,
                    self._auth_code_next_type,
                    self._auth_code_timeout_sec,
                )
                return f"Код уже запрошен для номера {normalized_phone}. {delivery_message}"

            cooldown_remaining = self._remaining_auth_code_timeout_sec()
            if cooldown_remaining > 0 and not self._auth_phone_code_hash:
                raise ValueError(
                    "Telegram временно ограничил повторную отправку кода. "
                    f"Повторите примерно через {cooldown_remaining} сек."
                )

            await self._pause_sync_for_auth()
            if force_sms:
                remaining = self._remaining_auth_code_timeout_sec()
                if remaining > 0:
                    raise ValueError(f"Повторный способ доставки будет доступен примерно через {remaining} сек.")
            if reset_session:
                await self._reset_client(drop_session=True)
            await self._ensure_connected_for_auth()

            try:
                append_runtime_log = globals().get("_append_runtime_log")
                if callable(append_runtime_log):
                    append_runtime_log("telegram-auth", "Telegram auth phone request started")
                sent_code = await self.client.send_code_request(normalized_phone, force_sms=force_sms)
            except FloodWaitError as exc:
                seconds = int(getattr(exc, "seconds", 0) or 0)
                message = f"Telegram временно ограничил повторную отправку кода. Повторите примерно через {seconds} сек."
                self._set_auth_error(message, step="phone")
                self._auth_phone_code_hash = None
                self._auth_code_hash_present = False
                self._auth_code_timeout_sec = seconds if seconds > 0 else None
                self._auth_code_requested_at = datetime.now(timezone.utc).isoformat()
                self._auth_code_message = message
                self._persist_auth_code_status()
                await self._resume_sync_after_auth_if_needed()
                raise ValueError(message) from exc
            except PhoneNumberInvalidError as exc:
                self._clear_auth_progress()
                await self._resume_sync_after_auth_if_needed()
                raise ValueError("Неверный формат номера телефона") from exc
            except Exception as exc:
                self._set_auth_error(f"Не удалось отправить код: {exc}", step="phone")
                await self._resume_sync_after_auth_if_needed()
                raise

            self._auth_phone = normalized_phone
            self._auth_phone_code_hash = sent_code.phone_code_hash
            self._auth_step = "code"
            self._auth_last_error = None
            delivery_message = self._record_auth_sent_code(sent_code, force_sms=force_sms)
            return f"Код запрошен для номера {normalized_phone}. {delivery_message}"

    async def submit_web_auth_code(self, code: str) -> str:
        normalized_code = re.sub(r"\s+", "", code or "")
        if not normalized_code:
            raise ValueError("Введите код из Telegram")

        async with self._auth_lock:
            if not self._auth_phone or not self._auth_phone_code_hash:
                self._set_auth_error("Сначала введите номер телефона", step="phone")
                raise ValueError("Сначала запросите код по номеру телефона")

            await self._ensure_connected_for_auth()

            try:
                await self.client.sign_in(
                    phone=self._auth_phone,
                    code=normalized_code,
                    phone_code_hash=self._auth_phone_code_hash,
                )
            except SessionPasswordNeededError:
                self._auth_step = "password"
                self._auth_last_error = None
                return "Нужен пароль двухфакторной защиты"
            except PhoneCodeInvalidError as exc:
                self._set_auth_error("Неверный код подтверждения", step="code")
                raise ValueError("Неверный код подтверждения") from exc
            except PhoneCodeExpiredError as exc:
                self._set_auth_error("Код истёк. Запросите новый код", step="phone")
                self._auth_phone_code_hash = None
                raise ValueError("Код истёк. Запросите новый код") from exc
            except Exception as exc:
                self._set_auth_error(f"Не удалось подтвердить код: {exc}", step="code")
                raise

            self._auth_step = "done"
            self._auth_last_error = None
            self._auth_phone_code_hash = None
            await self._resume_sync_after_auth_if_needed()
            await self.start(sync_in_background=True)
            self.request_source_reload()
            return "Telegram успешно авторизован"

    async def submit_web_auth_password(self, password: str) -> str:
        normalized_password = password or ""
        if not normalized_password:
            raise ValueError("Введите пароль двухфакторной защиты")

        async with self._auth_lock:
            await self._ensure_connected_for_auth()

            try:
                await self.client.sign_in(password=normalized_password)
            except PasswordHashInvalidError as exc:
                self._set_auth_error("Неверный пароль двухфакторной защиты", step="password")
                raise ValueError("Неверный пароль двухфакторной защиты") from exc
            except Exception as exc:
                self._set_auth_error(f"Не удалось подтвердить пароль: {exc}", step="password")
                raise

            self._auth_step = "done"
            self._auth_last_error = None
            self._auth_phone_code_hash = None
            await self._resume_sync_after_auth_if_needed()
            await self.start(sync_in_background=True)
            self.request_source_reload()
            return "Telegram успешно авторизован"

    async def connect_once(self) -> bool:
        if not self._ensure_client_available() or self.client is None:
            print(
                f"[telegram-sync] client unavailable: {self._client_init_error or 'client init failed'}"
            )
            return False

        if self.client.is_connected():
            return True

        try:
            await asyncio.wait_for(
                self.client.connect(),
                timeout=max(3.0, float(self._connect_timeout_sec)),
            )
        except AuthKeyUnregisteredError:
            self._set_auth_error(
                "Сохраненная сессия Telegram недействительна. Авторизуйтесь заново через интерфейс.",
                step="phone",
            )
            await self._reset_client(drop_session=True)
            return False
        except asyncio.TimeoutError:
            self._auth_last_error = (
                "Telegram не ответил за отведённое время. Проверьте интернет/VPN и повторите подключение."
            )
            print(f"[telegram-sync] connect timeout after {self._connect_timeout_sec}s")
            await self._reset_client(drop_session=False)
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[telegram-sync] connect error: {exc!r}")
            return False

        if self.client.is_connected():
            return True

        try:
            await asyncio.wait_for(
                self.client.start(),
                timeout=max(3.0, float(self._connect_timeout_sec)),
            )
        except AuthKeyUnregisteredError:
            self._set_auth_error(
                "Сохраненная сессия Telegram недействительна. Авторизуйтесь заново через интерфейс.",
                step="phone",
            )
            await self._reset_client(drop_session=True)
            return False
        except asyncio.TimeoutError:
            self._auth_last_error = (
                "Telegram-авторизация не ответила за отведённое время. Проверьте интернет/VPN и повторите подключение."
            )
            print(f"[telegram-sync] start/connect timeout after {self._connect_timeout_sec}s")
            await self._reset_client(drop_session=False)
            return False
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[telegram-sync] start/connect error: {exc!r}")
            return False

        return self.client.is_connected()

    async def ensure_connected(self) -> None:
        while not await self.connect_once():
            print(f"[telegram-sync] waiting for internet/telegram connection, retry in {self._connect_retry_sec}s")
            await asyncio.sleep(self._connect_retry_sec)

    async def maintain_connection(self) -> None:
        while True:
            try:
                if not self.client.is_connected():
                    await self.ensure_connected()
                await asyncio.sleep(self._connect_retry_sec)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[telegram-sync] connection watchdog error: {exc!r} - retry in {self._connect_retry_sec}s")
                await asyncio.sleep(self._connect_retry_sec)

    def _parse_line(self, line: str) -> Union[str, int]:
        return parse_selector_line(line)

    def _selector_key(self, chat_selector: Union[str, int]) -> str:
        return selector_key(chat_selector)

    def _selector_cache_state(self) -> Dict[str, Any]:
        current = self.state.get(TELEGRAM_SELECTOR_CACHE_STATE_KEY)
        if not isinstance(current, dict):
            current = {}
        self.state[TELEGRAM_SELECTOR_CACHE_STATE_KEY] = current
        return current

    def _selector_cache_entry(self, selector_key: str) -> Optional[Dict[str, Any]]:
        entry = self._selector_cache_state().get(selector_key)
        if not isinstance(entry, dict):
            return None
        chat_key = str(entry.get("chat_key") or "").strip()
        if not chat_key:
            return None
        return entry

    def _hydrate_selector_cache_from_state(self) -> None:
        for selector_key, entry in self._selector_cache_state().items():
            if not isinstance(entry, dict):
                continue
            chat_key = str(entry.get("chat_key") or "").strip()
            if chat_key:
                self._selector_to_chat_key.setdefault(str(selector_key), chat_key)

    def _selector_setup_failures_state(self) -> Dict[str, Any]:
        current = self.state.get("_telegram_selector_setup_failures")
        if not isinstance(current, dict):
            current = {}
        self.state["_telegram_selector_setup_failures"] = current
        return current

    def _selector_setup_failure_entry(self, selector_key: str) -> Optional[Dict[str, Any]]:
        entry = self._selector_setup_failures_state().get(selector_key)
        return entry if isinstance(entry, dict) else None

    def _selector_setup_is_blocked(self, selector_key: str) -> bool:
        entry = self._selector_setup_failure_entry(selector_key)
        if not entry:
            return False
        status = str(entry.get("status") or "").strip().lower()
        if status == "unresolvable":
            return True
        retry_after = self._parse_state_datetime(entry.get("retry_after"))
        if retry_after and retry_after > _utc_now():
            return True
        if retry_after and retry_after <= _utc_now():
            entry["active"] = False
            entry["status"] = "expired"
            entry["cleared_at"] = _utc_now().isoformat()
            self.save_state()
        return False

    def _is_unresolvable_selector_error(self, exc: Exception) -> bool:
        message = str(exc or "").lower()
        return (
            "could not find the input entity" in message
            or "cannot find any entity corresponding to" in message
            or "no user has" in message
        )

    def _mark_selector_setup_failed(
        self,
        selector_key: str,
        chat_selector: Union[str, int],
        exc: Exception,
    ) -> None:
        failures = self._selector_setup_failures_state()
        permanent = self._is_unresolvable_selector_error(exc)
        previous = failures.get(selector_key) if isinstance(failures.get(selector_key), dict) else {}
        attempts = int(previous.get("attempts", 0) or 0) + 1
        retry_after = None
        if not permanent:
            retry_after = (_utc_now() + timedelta(minutes=min(60, 5 * attempts))).isoformat()
        failures[selector_key] = {
            "active": True,
            "status": "unresolvable" if permanent else "setup_error",
            "selector": str(chat_selector),
            "error_type": type(exc).__name__,
            "reason": str(exc),
            "attempts": attempts,
            "retry_after": retry_after,
            "updated_at": _utc_now().isoformat(),
        }
        message = (
            f"Telegram setup skipped selector={chat_selector!r}: "
            f"{type(exc).__name__}: {exc}"
        )
        print(f"[telegram-sync] {message}")
        append_runtime_log = globals().get("_append_runtime_log")
        if callable(append_runtime_log):
            append_runtime_log("telegram", message)
        self.save_state()

    def _persist_selector_resolution(self, selector_key: str, chat_key: str, entity: Any) -> None:
        if not selector_key or not chat_key:
            return
        cache = self._selector_cache_state()
        cache[selector_key] = {
            "chat_key": chat_key,
            "resolved_entity_id": getattr(entity, "id", None),
            "access_hash": getattr(entity, "access_hash", None),
            "username": getattr(entity, "username", None),
            "title": getattr(entity, "title", None) or getattr(entity, "first_name", None),
            "resolved_at": _utc_now().isoformat(),
        }
        self._selector_setup_failures_state().pop(selector_key, None)
        self._selector_to_chat_key[selector_key] = chat_key

    def get_sync_control_status(self) -> Dict[str, Any]:
        current = self.state.get(TELEGRAM_SYNC_CONTROL_STATE_KEY)
        if not isinstance(current, dict):
            current = {}
        current.setdefault("paused", False)
        current.setdefault("paused_at", None)
        current.setdefault("resumed_at", None)
        current.setdefault("reason", None)
        self.state[TELEGRAM_SYNC_CONTROL_STATE_KEY] = current
        return {
            "paused": bool(current.get("paused")),
            "paused_at": current.get("paused_at"),
            "resumed_at": current.get("resumed_at"),
            "reason": current.get("reason"),
        }

    def is_sync_paused(self) -> bool:
        return bool(self.get_sync_control_status().get("paused"))

    def set_sync_paused(self, paused: bool, reason: Optional[str] = None) -> Dict[str, Any]:
        current = self.state.get(TELEGRAM_SYNC_CONTROL_STATE_KEY)
        if not isinstance(current, dict):
            current = {}
        now = _utc_now().isoformat()
        current["paused"] = bool(paused)
        current["reason"] = str(reason or "").strip() or ("manual pause" if paused else None)
        if paused:
            current["paused_at"] = now
        else:
            current["resumed_at"] = now
        self.state[TELEGRAM_SYNC_CONTROL_STATE_KEY] = current
        self.save_state()
        _append_runtime_log(
            "telegram-sync",
            f"Telegram sync {'paused' if paused else 'resumed'}: {current.get('reason') or 'manual'}",
        )
        return self.get_sync_control_status()

    def refresh_runtime_control_from_disk(self) -> bool:
        """Refresh external control/source keys without overwriting live chat progress."""
        try:
            latest = self.load_state()
        except Exception as exc:
            print(f"[telegram-sync] state refresh skipped: {exc!r}")
            return False
        if not isinstance(latest, dict):
            return False

        control_key = globals().get("TELEGRAM_SYNC_CONTROL_STATE_KEY", "_telegram_sync_control")
        source_key = globals().get("SOURCE_SELECTORS_STATE_KEY", "_source_selectors")
        keys = {
            control_key,
            source_key,
            globals().get("TELEGRAM_SOURCE_POLICY_STATE_KEY", "_telegram_source_policy"),
            globals().get("TELEGRAM_SELECTOR_CACHE_STATE_KEY", "_telegram_selector_cache"),
            "_app_settings",
            "_import_dialog_settings",
            "_import_sync",
            "_known_selectors",
        }
        changed = False
        for key in keys:
            if not key:
                continue
            if key in latest:
                next_value = latest.get(key)
                if self.state.get(key) != next_value:
                    self.state[key] = next_value
                    changed = True
            elif key in {control_key, source_key, "_import_sync"} and key in self.state:
                self.state.pop(key, None)
                changed = True
        if changed:
            self.request_source_reload()
        return changed

    def _selector_scan_priority_key(self, selector: Union[str, int]) -> tuple[int, str]:
        selector_text = str(selector or "").strip()
        group_id = "C"
        try:
            fields = _lead_scan_group_fields(_selector_to_lead_name(selector), selector_text)
            group_id = str(fields.get("scan_group") or "C").strip().upper() or "C"
        except Exception:
            group_id = "C"
        priority = {"A": 0, "B": 1, "C": 2, "D": 3}.get(group_id, 9)
        return (priority, selector_text.lower())

    def sort_selected_chats_for_scan(self, selectors: List[Union[str, int]]) -> List[Union[str, int]]:
        return sorted(list(selectors or []), key=self._selector_scan_priority_key)

    async def _wait_if_sync_paused(self, context: str) -> None:
        released = False
        while self.is_sync_paused():
            self.refresh_runtime_control_from_disk()
            if not released:
                await self._release_session_handles_for_pause(f"paused before {context}")
                released = True
            status = self.get_sync_control_status()
            print(
                f"[telegram-sync] paused: context={context}, "
                f"paused_at={status.get('paused_at')}, reason={status.get('reason') or 'manual'}"
            )
            await asyncio.sleep(max(5, self._source_poll_interval))

    def _is_chat_enabled(self, chat_key: str) -> bool:
        if chat_key not in self._enabled_chat_keys:
            return False
        try:
            return bool(_source_policy_for_lead(chat_key).scan_allowed)
        except Exception:
            return True

    def _selector_scan_allowed(self, selector: Union[str, int]) -> bool:
        try:
            selector_text = str(selector).strip()
            lead_name = _selector_to_lead_name(selector)
            policy = _source_policy_for_lead(lead_name, selector_text)
            if not policy.scan_allowed:
                print(
                    f"[telegram-sync] skipped by source policy: selector={selector_text!r}, "
                    f"mode={policy.mode}, reason={policy.reason or 'manual'}"
                )
                return False
        except Exception:
            return True
        return True

    def _disable_selector(self, selector_key: str) -> None:
        task = self._chat_setup_tasks.pop(selector_key, None)
        if task and not task.done():
            task.cancel()

        chat_key = self._selector_to_chat_key.get(selector_key)
        if chat_key and chat_key in self._enabled_chat_keys:
            self._enabled_chat_keys.discard(chat_key)
            print(f"[{chat_key}] disabled by selected source registry")

    def request_source_reload(self) -> None:
        self._source_reload_event.set()

    def get_import_sync_state(self) -> Dict[str, Any]:
        current = self.state.get("_import_sync")
        if not isinstance(current, dict):
            current = {}
        current.setdefault("enabled", False)
        current.setdefault("selectors", [])
        current.setdefault("started_at", None)
        current.setdefault("updated_at", None)
        self.state["_import_sync"] = current
        return current

    def is_import_sync_enabled(self) -> bool:
        return bool(self.get_import_sync_state().get("enabled"))

    def get_import_sync_selectors(self) -> List[Union[str, int]]:
        state = self.get_import_sync_state()
        if not state.get("enabled"):
            return []

        selected_keys = {
            self._selector_key(selector)
            for selector in self._load_selected_chats()
        }
        if not selected_keys:
            return []

        selectors: List[Union[str, int]] = []
        for item in state.get("selectors", []):
            if item is None:
                continue
            selector = self._parse_line(str(item).strip())
            if self._selector_key(selector) not in selected_keys:
                continue
            selectors.append(selector)
        return selectors

    def combined_selected_chats(self) -> List[Union[str, int]]:
        combined: List[Union[str, int]] = []
        seen: set[str] = set()

        for selector in [*self._load_selected_chats(), *self.get_import_sync_selectors()]:
            key = self._selector_key(selector)
            if key in seen:
                continue
            seen.add(key)
            combined.append(selector)

        return combined

    def _load_selected_chats(self) -> List[Union[str, int]]:
        if not self.state:
            try:
                self.state = self.load_state()
            except Exception:
                self.state = {}
        key = globals().get("SOURCE_SELECTORS_STATE_KEY", "_source_selectors")
        return load_selected_chats_from_state(self.state, state_key=key, parse_line=self._parse_line)

    def load_state(self) -> Dict[str, Any]:
        try:
            if not hasattr(self, "_state_repository") or getattr(self._state_repository, "path", None) != self.state_path:
                self._state_repository = StateRepository(self.state_path)
            return self._state_repository.load()
        except json.JSONDecodeError:
            print(f"[telegram-sync] invalid JSON in {self.state_path}, fallback to empty state")
            return {}

    def save_state(self) -> None:
        if not hasattr(self, "_state_repository") or getattr(self._state_repository, "path", None) != self.state_path:
            self._state_repository = StateRepository(self.state_path)
        self.state = self._state_repository.save(self.state)

    def get_chat_state(self, chat_key: str) -> Dict[str, Any]:
        return normalize_chat_state(self.state, chat_key)

    def _existing_jsonl_message_bounds(self, path: Path) -> Dict[str, int]:
        return existing_jsonl_message_bounds(path)

    def recover_chat_state_from_existing_jsonl(self, chat_key: str, out_path: Path) -> None:
        chat_state = self.get_chat_state(chat_key)
        needs_backfill_offset = int(chat_state.get("backfill_offset_id", 0) or 0) <= 0 and not bool(chat_state.get("backfill_done"))
        needs_max_saved = int(chat_state.get("max_saved_id", 0) or 0) <= 0
        if not (needs_backfill_offset or needs_max_saved):
            return

        bounds = self._existing_jsonl_message_bounds(out_path)
        min_id = int(bounds.get("min_id") or 0)
        max_id = int(bounds.get("max_id") or 0)
        total = int(bounds.get("total") or 0)
        if total <= 0:
            return

        changed = False
        if needs_backfill_offset and min_id > 0:
            chat_state["backfill_offset_id"] = min_id
            chat_state["backfill_items_processed"] = max(
                int(chat_state.get("backfill_items_processed", 0) or 0),
                total,
            )
            chat_state["backfill_recovered_from_jsonl_at"] = _utc_now().isoformat()
            changed = True
        if needs_max_saved and max_id > 0:
            chat_state["max_saved_id"] = max_id
            chat_state["max_saved_recovered_from_jsonl_at"] = _utc_now().isoformat()
            changed = True

        if changed:
            now = _utc_now().isoformat()
            chat_state["cursor_state_version"] = 1
            chat_state["cursor_resume_strategy"] = "jsonl_bounds_then_forward_min_id"
            chat_state["cursor_state_updated_at"] = now
            chat_state["state_recovered_from_jsonl"] = True
            chat_state["state_recovered_jsonl_rows"] = total
            chat_state["state_recovered_jsonl_min_id"] = min_id
            chat_state["state_recovered_jsonl_max_id"] = max_id
            self.save_state()
            print(
                f"[{chat_key}] state recovered from existing jsonl: "
                f"rows={total}, min_id={min_id}, max_id={max_id}"
            )

    def _resume_backfill_if_limits_expanded(self, chat_key: str) -> bool:
        chat_state = self.get_chat_state(chat_key)
        stop_reason = str(chat_state.get("backfill_stop_reason") or "").strip()
        if not chat_state.get("backfill_done") or stop_reason not in {"history_months", "message_limit"}:
            return False
        effective_limits = globals().get("_effective_import_limits_for_selector")
        if not callable(effective_limits):
            return False
        try:
            limits = effective_limits(chat_key)
        except Exception:
            return False

        def _limit(value: Any, default: int) -> int:
            if value is None or value == "":
                return default
            try:
                return int(value)
            except Exception:
                return default

        current_history = _limit(limits.get("import_history_months"), 1)
        current_messages = _limit(limits.get("import_message_limit"), 1000)
        previous_history = _limit(chat_state.get("import_history_months"), 1)
        previous_messages = _limit(chat_state.get("import_message_limit"), 1000)
        expanded_by_history = stop_reason == "history_months" and (
            current_history == 0 or current_history > previous_history
        )
        expanded_by_messages = stop_reason == "message_limit" and (
            current_messages == 0 or current_messages > previous_messages
        )
        if not (expanded_by_history or expanded_by_messages):
            return False

        chat_state["backfill_done"] = False
        chat_state["backfill_stop_reason"] = "limits_expanded"
        chat_state["backfill_resumed_at"] = _utc_now().isoformat()
        chat_state["import_history_months"] = current_history
        chat_state["import_message_limit"] = current_messages
        self.save_state()
        return True

    def update_chat_message_cursors(self, chat_key: str, obj: Dict[str, Any]) -> None:
        if not chat_key:
            return
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        try:
            message_id = int(message.get("id") or 0)
        except (TypeError, ValueError):
            message_id = 0
        if message_id <= 0:
            return

        chat_state = self.get_chat_state(chat_key)
        current_min = int(chat_state.get("min_saved_id", 0) or 0)
        current_max = int(chat_state.get("max_saved_id", 0) or 0)
        chat_state["min_saved_id"] = message_id if current_min <= 0 else min(current_min, message_id)
        chat_state["max_saved_id"] = max(current_max, message_id)
        chat_state["last_message_id"] = max(int(chat_state.get("last_message_id", 0) or 0), message_id)
        chat_state["last_seen_at"] = _utc_now().isoformat()
        chat_state["last_sync_at"] = chat_state["last_seen_at"]
        chat_state["cursor_state_version"] = 1
        chat_state["cursor_state_updated_at"] = chat_state["last_seen_at"]
        chat_state["cursor_resume_strategy"] = "jsonl_bounds_then_forward_min_id"
        if str(chat_state.get("telegram_status") or "") in {"", "pending", "cooldown", "active"}:
            chat_state["telegram_status"] = "active"
        date_utc = str(message.get("date_utc") or "").strip()
        if date_utc:
            chat_state["last_message_date_utc"] = date_utc

    def chat_key_from_entity(self, entity: Any) -> str:
        username = getattr(entity, "username", None)
        if username:
            return username.lower()

        title = getattr(entity, "title", None)
        if title:
            return title.replace("/", "_")

        first_name = getattr(entity, "first_name", None) or ""
        last_name = getattr(entity, "last_name", None) or ""
        name = (first_name + " " + last_name).strip()
        if name:
            return name.replace("/", "_")

        return f"id_{getattr(entity, 'id', 'unknown')}"

    def record_from_message(self, msg: TelegramMessage, chat: Any, sender: Any) -> Dict[str, Any]:
        chat_id = getattr(chat, "id", None)
        chat_username = getattr(chat, "username", None)
        if hasattr(chat, "title") and chat.title:
            chat_title = chat.title
        else:
            first_name = getattr(chat, "first_name", None) or ""
            last_name = getattr(chat, "last_name", None) or ""
            chat_title = (first_name + " " + last_name).strip() or None

        sender_id = getattr(sender, "id", None) if sender else None
        sender_username = getattr(sender, "username", None) if sender else None
        if sender:
            if hasattr(sender, "title") and sender.title:
                sender_name = sender.title
            else:
                first_name = getattr(sender, "first_name", None) or ""
                last_name = getattr(sender, "last_name", None) or ""
                sender_name = (first_name + " " + last_name).strip() or None
        else:
            sender_name = None

        return {
            "chat": {
                "id": chat_id,
                "username": chat_username,
                "title": chat_title,
            },
            "sender": {
                "id": sender_id,
                "username": sender_username,
                "name": sender_name,
            },
            "message": {
                "id": msg.id,
                "text": msg.message or "",
                "date_utc": msg.date.astimezone(timezone.utc).isoformat(),
                "reply_to_msg_id": getattr(msg, "reply_to_msg_id", None),
                "has_media": msg.media is not None,
                "media_path": None,
            },
        }

    def append_jsonl(self, path: Path, obj: Dict[str, Any], chat_key: Optional[str] = None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if chat_key:
            self.update_chat_message_cursors(chat_key, obj)
            _publish_lead_event(chat_key, obj)
        _schedule_duckdb_live_sync_debounced()

    def _message_preview(self, msg: TelegramMessage) -> str:
        text = re.sub(r"\s+", " ", (msg.message or "").strip())
        if text:
            if len(text) > 180:
                return text[:177] + "..."
            return text
        if getattr(msg, "photo", None):
            return "[photo]"
        if getattr(msg, "document", None):
            return "[document]"
        if getattr(msg, "media", None):
            return "[media]"
        return "[empty]"

    def _message_has_downloadable_image(self, msg: TelegramMessage) -> bool:
        if getattr(msg, "photo", None):
            return True
        file_info = getattr(msg, "file", None)
        if file_info is None:
            return False
        mime_type = str(getattr(file_info, "mime_type", "") or "").lower()
        if mime_type.startswith("image/"):
            return True
        ext = str(getattr(file_info, "ext", "") or "").lower()
        if ext in _IMAGE_EXTENSIONS:
            return True
        file_name = str(getattr(file_info, "name", "") or "")
        if Path(file_name).suffix.lower() in _IMAGE_EXTENSIONS:
            return True
        return False

    def log_channel_activity(self, chat_key: str, stage: str, msg: TelegramMessage, force: bool = False) -> None:
        key = f"{chat_key}:{stage}"
        now_ts = _utc_now().timestamp()
        if not force and now_ts - self._last_activity_log_at.get(key, 0.0) < self._activity_log_interval_sec:
            return

        self._last_activity_log_at[key] = now_ts
        print(
            f"[{chat_key}] {stage}: "
            f"message_id={msg.id} "
            f"last_message=\"{self._message_preview(msg)}\""
        )

    def _operation_from_context(self, context: str) -> str:
        text = str(context or "").lower()
        if "dialog" in text or "import" in text or "xlsx" in text:
            return "dialogs"
        if "media" in text or "ocr" in text:
            return "media"
        if "setup" in text or "entity" in text or "resolve" in text:
            return "setup"
        if "live" in text:
            return "live"
        if "backfill" in text or "catch-up" in text or "history" in text or "forward" in text:
            return "history"
        return "telegram"

    def _is_transient_telegram_rate_limit(self, exc: Exception) -> bool:
        text = str(exc or "").lower()
        return any(
            token in text
            for token in (
                "http code 429",
                " 429",
                "too many requests",
                "invalid response buffer",
                "connection throttling",
                "retry after",
                "try again later",
            )
        )

    def _operation_cooldowns_state(self) -> Dict[str, Any]:
        rate_state = self._rate_limit_state()
        current = rate_state.get("operation_cooldowns")
        if not isinstance(current, dict):
            current = {}
        rate_state["operation_cooldowns"] = current
        return current

    def _operation_cooldown_remaining(self, operation: str) -> float:
        cooldowns = self._operation_cooldowns_state()
        entry = cooldowns.get(operation)
        if not isinstance(entry, dict):
            return 0.0
        retry_after = self._parse_state_datetime(entry.get("retry_after") or entry.get("until"))
        if retry_after is None:
            return 0.0
        remaining = (retry_after - _utc_now()).total_seconds()
        if remaining <= 0:
            if entry.get("active"):
                entry["active"] = False
                entry["status"] = "ok"
                entry["cleared_at"] = _utc_now().isoformat()
                self.save_state()
            return 0.0
        return float(remaining)

    def _register_telegram_transient_limit(
        self,
        exc: Exception,
        context: str,
        *,
        chat_key: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> float:
        operation_key = operation or self._operation_from_context(context)
        cooldowns = self._operation_cooldowns_state()
        previous = cooldowns.get(operation_key) if isinstance(cooldowns.get(operation_key), dict) else {}
        attempts = int(previous.get("attempts", 0) or 0) + 1
        multiplier = 2 ** min(max(attempts - 1, 0), 5)
        jitter = random.uniform(0.5, min(5.0, 0.5 + attempts))
        delay_sec = min(3600.0, float(self._telegram_429_retry_sec) * multiplier) + jitter
        retry_after = (_utc_now() + timedelta(seconds=delay_sec)).isoformat()
        status = "risk_rate_limited" if attempts >= 3 else "cooldown"
        error_type = type(exc).__name__

        cooldowns[operation_key] = {
            "active": True,
            "status": status,
            "scope": "operation",
            "operation": operation_key,
            "context": context,
            "error_type": error_type,
            "reason": str(exc),
            "retry_after": retry_after,
            "can_fetch_after": retry_after,
            "retry_after_seconds": int(max(1, round(delay_sec))),
            "attempts": attempts,
            "updated_at": _utc_now().isoformat(),
        }

        if chat_key:
            chat_state = self.get_chat_state(chat_key)
            chat_state["telegram_status"] = status
            chat_state["last_error"] = f"{error_type}: {exc}"
            chat_state["retry_after"] = retry_after
            chat_state["last_error_at"] = _utc_now().isoformat()

        message = (
            f"Telegram rate-limit/backoff: operation={operation_key}, "
            f"retry_after={retry_after}, attempts={attempts}, context={context}, error={error_type}: {exc}"
        )
        print(f"[telegram-sync] {message}")
        _append_runtime_log("telegram", message)
        self.save_state()
        return delay_sec

    def _clear_operation_cooldown(
        self,
        operation: str,
        *,
        context: Optional[str] = None,
        chat_key: Optional[str] = None,
    ) -> None:
        cooldowns = self._operation_cooldowns_state()
        entry = cooldowns.get(operation)
        if isinstance(entry, dict) and entry.get("active"):
            entry["active"] = False
            entry["status"] = "ok"
            entry["cleared_at"] = _utc_now().isoformat()
            if context:
                entry["clear_context"] = context
            self.save_state()
        if chat_key:
            chat_state = self.get_chat_state(chat_key)
            if str(chat_state.get("telegram_status") or "") in {"cooldown", "risk_rate_limited"}:
                chat_state["telegram_status"] = "active"
                chat_state["retry_after"] = None
                self.save_state()

    def _is_operation_cooldown_active(self, operation: str, context: str = "") -> bool:
        remaining = self._operation_cooldown_remaining(operation)
        if remaining <= 0:
            return False
        print(
            f"[telegram-sync] operation cooldown active: operation={operation}, "
            f"remaining={remaining:.0f}s, context={context}"
        )
        return True

    async def _sleep_operation_cooldown(self, operation: str, context: str) -> None:
        remaining = self._operation_cooldown_remaining(operation)
        if remaining <= 0:
            return
        jitter = random.uniform(0.25, 2.5)
        print(
            f"[telegram-sync] waiting operation cooldown: operation={operation}, "
            f"sleep={remaining + jitter:.1f}s, context={context}"
        )
        await asyncio.sleep(remaining + jitter)

    def get_rate_limit_status(self) -> Dict[str, Any]:
        rate_state = self._rate_limit_state()
        cooldowns = self._operation_cooldowns_state()
        normalized_cooldowns: Dict[str, Any] = {}
        for operation, entry in cooldowns.items():
            if not isinstance(entry, dict):
                continue
            remaining = self._operation_cooldown_remaining(str(operation))
            normalized = dict(entry)
            normalized["active"] = remaining > 0
            normalized["remaining_sec"] = int(remaining + 0.999) if remaining > 0 else 0
            normalized_cooldowns[str(operation)] = normalized
        return {
            "global_flood_wait": self.get_global_flood_wait_status(),
            "operation_cooldowns": normalized_cooldowns,
            "risks": rate_state.get("risks") if isinstance(rate_state.get("risks"), dict) else {},
        }

    def _telegram_retry_delay(
        self,
        exc: Exception,
        context: str = "",
        *,
        chat_key: Optional[str] = None,
        operation: Optional[str] = None,
    ) -> float:
        if self._is_transient_telegram_rate_limit(exc):
            return self._register_telegram_transient_limit(
                exc,
                context or "telegram request",
                chat_key=chat_key,
                operation=operation,
            )
        return 5.0

    def _flood_wait_seconds(self, exc: Exception) -> int:
        return flood_wait_seconds(exc)

    def _rate_limit_state(self) -> Dict[str, Any]:
        return rate_limit_state(self.state, TELEGRAM_RATE_LIMIT_STATE_KEY)

    def _parse_state_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _restore_global_flood_wait_from_state(self) -> None:
        if not self.state and self.state_path.exists():
            self.state = self.load_state()

        rate_state = self._rate_limit_state()
        flood_state = rate_state.get("global_flood_wait")
        if not isinstance(flood_state, dict):
            return

        until_dt = self._parse_state_datetime(flood_state.get("until"))
        if until_dt is None:
            return

        remaining = (until_dt - _utc_now()).total_seconds()
        if remaining <= 0:
            if flood_state.get("active"):
                flood_state["active"] = False
                flood_state["status"] = "ok"
                flood_state["cleared_at"] = _utc_now().isoformat()
                self.save_state()
            if self._global_flood_wait_remaining() <= 0:
                self._global_flood_wait_until_mono = 0.0
                self._global_flood_wait_until_iso = None
                self._global_flood_wait_reason = ""
            return

        until_mono = time.monotonic() + float(remaining)
        if until_mono > self._global_flood_wait_until_mono:
            self._global_flood_wait_until_mono = until_mono
            self._global_flood_wait_until_iso = until_dt.isoformat()
            self._global_flood_wait_reason = str(flood_state.get("reason") or "restored FloodWait")

    def _persist_global_flood_wait(self, *, wait_seconds: float, context: str, until_iso: str) -> None:
        rate_state = self._rate_limit_state()
        rate_state["global_flood_wait"] = {
            "active": True,
            "status": "cooldown",
            "scope": "global_account",
            "operation": context,
            "reason": context,
            "until": until_iso,
            "can_fetch_after": until_iso,
            "retry_after_seconds": int(max(1, round(wait_seconds))),
            "updated_at": _utc_now().isoformat(),
        }
        self.save_state()

    def _mark_telegram_risk_blocked(self, exc: Exception, context: str, *, chat_key: Optional[str] = None) -> None:
        error_type = type(exc).__name__
        status = "blocked_privacy" if isinstance(exc, UserPrivacyRestrictedError) else "risk_blocked"
        rate_state = self._rate_limit_state()
        risks = rate_state.get("risks")
        if not isinstance(risks, dict):
            risks = {}
            rate_state["risks"] = risks
        key = chat_key or context or "global"
        risks[key] = {
            "status": status,
            "error_type": error_type,
            "reason": str(exc),
            "context": context,
            "updated_at": _utc_now().isoformat(),
        }
        if chat_key:
            chat_state = self.get_chat_state(chat_key)
            chat_state["telegram_status"] = status
            chat_state["last_error"] = f"{error_type}: {exc}"
            chat_state["retry_after"] = None
            chat_state["last_error_at"] = _utc_now().isoformat()
            _set_source_policy(
                chat_key,
                chat_key,
                "blocked",
                f"{status}: {error_type}: {exc}",
                source="telegram_risk",
            )
        print(f"[telegram-sync] {status}: context={context}; error={error_type}: {exc}")
        self.save_state()

    def _global_flood_wait_remaining(self) -> float:
        return max(0.0, float(self._global_flood_wait_until_mono or 0.0) - time.monotonic())

    def get_global_flood_wait_status(self) -> Dict[str, Any]:
        self._restore_global_flood_wait_from_state()
        remaining = self._global_flood_wait_remaining()
        active = remaining > 0
        rate_state = self._rate_limit_state()
        flood_state = rate_state.get("global_flood_wait") if isinstance(rate_state.get("global_flood_wait"), dict) else {}
        return {
            "active": active,
            "status": "cooldown" if active else "ok",
            "remaining_sec": int(remaining + 0.999) if active else 0,
            "until": self._global_flood_wait_until_iso if active else None,
            "reason": self._global_flood_wait_reason if active else None,
            "can_fetch_after": self._global_flood_wait_until_iso if active else None,
            "scope": str(flood_state.get("scope") or "global_account"),
            "operation": str(flood_state.get("operation") or self._global_flood_wait_reason or ""),
        }

    def _log_global_flood_wait_active(self, context: str, *, force: bool = False) -> None:
        remaining = self._global_flood_wait_remaining()
        if remaining <= 0:
            return
        now_mono = time.monotonic()
        if not force and now_mono - self._global_flood_wait_last_log_at < 60.0:
            return
        self._global_flood_wait_last_log_at = now_mono
        until = self._global_flood_wait_until_iso or "unknown"
        reason = self._global_flood_wait_reason or "Telegram API"
        print(
            f"[telegram-sync] global FloodWait active: pause {remaining:.0f}s until {until}; "
            f"context={context}; reason={reason}"
        )

    def _activate_global_flood_wait(self, exc: FloodWaitError, context: str) -> float:
        seconds = self._flood_wait_seconds(exc)
        wait_seconds = float(seconds + 1)
        until_mono = time.monotonic() + wait_seconds
        if until_mono >= self._global_flood_wait_until_mono:
            self._global_flood_wait_until_mono = until_mono
            self._global_flood_wait_until_iso = (_utc_now() + timedelta(seconds=wait_seconds)).isoformat()
            self._global_flood_wait_reason = context
            self._persist_global_flood_wait(
                wait_seconds=wait_seconds,
                context=context,
                until_iso=self._global_flood_wait_until_iso,
            )
            self._log_global_flood_wait_active(context, force=True)
        return wait_seconds

    def _is_global_flood_wait_active(self, context: str = "") -> bool:
        self._restore_global_flood_wait_from_state()
        remaining = self._global_flood_wait_remaining()
        if remaining <= 0:
            return False
        self._log_global_flood_wait_active(context or "telegram request")
        return True

    async def _sleep_global_flood_wait(self, context: str) -> None:
        self._restore_global_flood_wait_from_state()
        remaining = self._global_flood_wait_remaining()
        if remaining <= 0:
            return
        self._log_global_flood_wait_active(context, force=True)
        await asyncio.sleep(remaining)

    async def download_message_media(self, msg: TelegramMessage, chat_key: str) -> Optional[str]:
        if msg.media is None:
            return None
        if not _is_media_enabled_for_chat(chat_key):
            return None
        if self.is_sync_paused():
            return None
        if not self._message_has_downloadable_image(msg):
            return None
        if self._is_global_flood_wait_active(f"{chat_key} media download"):
            return None
        if self._is_operation_cooldown_active("media", f"{chat_key} media download"):
            return None

        media_dir = self.out_dir / chat_key / "media"
        media_dir.mkdir(parents=True, exist_ok=True)

        try:
            saved_path = await self.client.download_media(msg, file=str(media_dir / f"{msg.id}"))
        except FloodWaitError as exc:
            self._activate_global_flood_wait(exc, f"{chat_key} media download")
            print(f"[{chat_key}] media download FloodWait {self._flood_wait_seconds(exc)}s - global pause enabled")
            return None
        except (PeerFloodError, UserPrivacyRestrictedError) as exc:
            self._mark_telegram_risk_blocked(exc, f"{chat_key} media download", chat_key=chat_key)
            return None
        except Exception as exc:
            if self._is_transient_telegram_rate_limit(exc):
                self._register_telegram_transient_limit(
                    exc,
                    f"{chat_key} media download",
                    chat_key=chat_key,
                    operation="media",
                )
                return None
            print(f"[{chat_key}] media download error for message {msg.id}: {exc!r}")
            return None

        if not saved_path:
            return None

        saved_path_obj = Path(saved_path).resolve()
        try:
            return str(saved_path_obj.relative_to(APP_DIR))
        except ValueError:
            return str(saved_path_obj)

    async def export_backfill(self, entity: Any, chat_key: str) -> None:
        out_path = self.out_dir / f"{chat_key}.jsonl"
        await self._wait_if_sync_paused(f"{chat_key} backfill")
        self.recover_chat_state_from_existing_jsonl(chat_key, out_path)
        chat_state = self.get_chat_state(chat_key)
        offset_id = int(chat_state.get("backfill_offset_id", 0) or 0)
        total = int(chat_state.get("backfill_items_processed", 0) or 0)
        import_limits = _effective_import_limits_for_selector(chat_key)
        limits = build_backfill_limits(
            history_months=self._import_limit_int(import_limits.get("import_history_months"), 1),
            message_limit=self._import_limit_int(import_limits.get("import_message_limit"), 1000),
            now=_utc_now(),
        )
        import_history_months = limits.history_months
        import_message_limit = limits.message_limit
        cutoff_dt = limits.cutoff_dt

        chat_state["backfill_done"] = False
        chat_state["backfill_started_at"] = chat_state.get("backfill_started_at") or _utc_now().isoformat()
        chat_state["backfill_updated_at"] = _utc_now().isoformat()
        chat_state["backfill_items_processed"] = int(chat_state.get("backfill_items_processed", 0) or 0)
        chat_state["backfill_batch_size"] = min(1000, max(1, import_message_limit))
        chat_state["import_history_months"] = import_history_months
        chat_state["import_message_limit"] = import_message_limit
        chat_state["import_cutoff_date_utc"] = cutoff_dt.isoformat() if cutoff_dt is not None else ""

        if backfill_stop_reason(
            total=total,
            message_limit=import_message_limit,
            message_date=None,
            cutoff_dt=cutoff_dt,
        ) == "message_limit":
            chat_state["backfill_done"] = True
            chat_state["backfill_stop_reason"] = "message_limit"
            chat_state["backfill_updated_at"] = _utc_now().isoformat()
            chat_state["backfill_completed_at"] = _utc_now().isoformat()
            self.save_state()
            print(f"[{chat_key}] backfill skipped: message limit {import_message_limit} already reached")
            return

        latest_id = int(chat_state.get("backfill_latest_id", 0) or chat_state.get("max_saved_id", 0) or 0)
        if latest_id <= 0:
            try:
                await self._sleep_operation_cooldown("history", f"{chat_key} latest message")
                latest = await self.client.get_messages(entity, limit=1)
                if latest and latest[0]:
                    latest_id = int(latest[0].id)
                    self._clear_operation_cooldown("history", context=f"{chat_key} latest message", chat_key=chat_key)
            except FloodWaitError as exc:
                self._activate_global_flood_wait(exc, f"{chat_key} latest message")
                latest_id = 0
            except (PeerFloodError, UserPrivacyRestrictedError) as exc:
                self._mark_telegram_risk_blocked(exc, f"{chat_key} latest message", chat_key=chat_key)
                return
            except Exception as exc:
                if self._is_transient_telegram_rate_limit(exc):
                    self._register_telegram_transient_limit(
                        exc,
                        f"{chat_key} latest message",
                        chat_key=chat_key,
                        operation="history",
                    )
                latest_id = 0
        if latest_id > 0:
            chat_state["backfill_latest_id"] = latest_id

        print(
            f"[{chat_key}] backfill start: offset_id={offset_id or 'latest'}, "
            f"history_months={import_history_months or 'unlimited'}, "
            f"message_limit={import_message_limit or 'unlimited'}"
        )

        while True:
            if not self._is_chat_enabled(chat_key):
                print(f"[{chat_key}] backfill stopped: removed from selected source registry")
                return
            await self._wait_if_sync_paused(f"{chat_key} backfill")
            await self._sleep_global_flood_wait(f"{chat_key} backfill")
            await self._sleep_operation_cooldown("history", f"{chat_key} backfill")
            try:
                await self.ensure_connected()
                batch_count = 0
                stop_reason: Optional[str] = None
                remaining_limit = max(1, import_message_limit - total) if import_message_limit > 0 else 1000
                batch_limit = min(1000, remaining_limit)
                async for msg in self.client.iter_messages(entity, limit=batch_limit, offset_id=offset_id):
                    if not self._is_chat_enabled(chat_key):
                        print(f"[{chat_key}] backfill stopped: removed from selected source registry")
                        return
                    offset_id = msg.id
                    msg_date = getattr(msg, "date", None)
                    message_stop_reason = backfill_stop_reason(
                        total=total,
                        message_limit=0,
                        message_date=msg_date,
                        cutoff_dt=cutoff_dt,
                    )
                    if message_stop_reason == "history_months":
                        stop_reason = message_stop_reason
                        print(
                            f"[{chat_key}] backfill stop: message {msg.id} older than "
                            f"{import_history_months} month(s)"
                        )
                        break
                    chat = await self.client.get_entity(msg.peer_id) if msg.peer_id else entity
                    sender = await msg.get_sender()
                    record = self.record_from_message(msg, chat, sender)
                    record["message"]["media_path"] = await self.download_message_media(msg, chat_key)
                    record["message"]["has_media"] = bool(record["message"]["media_path"]) or msg.media is not None
                    self.append_jsonl(out_path, record, chat_key=chat_key)
                    if record["message"]["media_path"]:
                        _ensure_pending_image_ocr_task(force=False)
                    self.log_channel_activity(chat_key, "backfill updating", msg)

                    batch_count += 1
                    total += 1
                    chat_state["backfill_offset_id"] = offset_id
                    chat_state["backfill_items_processed"] = total
                    chat_state["backfill_updated_at"] = _utc_now().isoformat()
                    chat_state["oldest_processed_id"] = offset_id
                    newest_processed_id = int(chat_state.get("newest_processed_id", 0) or 0)
                    chat_state["newest_processed_id"] = max(newest_processed_id, int(msg.id))

                    if total % 5000 == 0:
                        self.save_state()
                        print(f"[{chat_key}] backfill checkpoint: written={total}, offset_id={offset_id}")

                    limit_stop_reason = backfill_stop_reason(
                        total=total,
                        message_limit=import_message_limit,
                        message_date=None,
                        cutoff_dt=cutoff_dt,
                    )
                    if limit_stop_reason == "message_limit":
                        stop_reason = limit_stop_reason
                        break

                if batch_count > 0:
                    self._clear_operation_cooldown("history", context=f"{chat_key} backfill", chat_key=chat_key)
                    self.save_state()
                    print(f"[{chat_key}] backfill batch checkpoint: written={total}, offset_id={offset_id}")

                if stop_reason or batch_count == 0:
                    chat_state["backfill_done"] = True
                    chat_state["backfill_offset_id"] = offset_id
                    chat_state["backfill_stop_reason"] = stop_reason or "telegram_end"
                    chat_state["backfill_updated_at"] = _utc_now().isoformat()
                    chat_state["backfill_completed_at"] = _utc_now().isoformat()
                    self.save_state()
                    print(
                        f"[{chat_key}] backfill done: total={total}, "
                        f"last_offset_id={offset_id}, reason={chat_state['backfill_stop_reason']}"
                    )
                    break

            except FloodWaitError as exc:
                self._activate_global_flood_wait(exc, f"{chat_key} backfill")
                print(f"[{chat_key}] FloodWait {self._flood_wait_seconds(exc)}s - global pause enabled")
                await self._sleep_global_flood_wait(f"{chat_key} backfill")
            except (PeerFloodError, UserPrivacyRestrictedError) as exc:
                self._mark_telegram_risk_blocked(exc, f"{chat_key} backfill", chat_key=chat_key)
                return
            except ConnectionError as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} backfill", chat_key=chat_key, operation="history")
                print(f"[{chat_key}] backfill disconnected: {exc!r} - reconnect in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)
            except Exception as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} backfill", chat_key=chat_key, operation="history")
                print(f"[{chat_key}] backfill error: {exc!r} - retry in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)

    async def forward_catch_up(self, entity: Any, chat_key: str) -> None:
        out_path = self.out_dir / f"{chat_key}.jsonl"
        await self._wait_if_sync_paused(f"{chat_key} forward catch-up")
        self.recover_chat_state_from_existing_jsonl(chat_key, out_path)
        chat_state = self.get_chat_state(chat_key)
        max_saved_id = int(chat_state.get("max_saved_id", 0) or 0)

        if not self._is_chat_enabled(chat_key):
            print(f"[{chat_key}] forward stopped: removed from selected source registry")
            return

        if max_saved_id <= 0:
            try:
                await self._wait_if_sync_paused(f"{chat_key} forward init")
                await self.ensure_connected()
                await self._sleep_operation_cooldown("history", f"{chat_key} forward init")
                latest = await self.client.get_messages(entity, limit=1)
                if latest and latest[0]:
                    chat_state["max_saved_id"] = int(latest[0].id)
                    self.save_state()
                    print(f"[{chat_key}] forward init: set max_saved_id={latest[0].id}")
                    self._clear_operation_cooldown("history", context=f"{chat_key} forward init", chat_key=chat_key)
            except FloodWaitError as exc:
                self._activate_global_flood_wait(exc, f"{chat_key} forward init")
            except (PeerFloodError, UserPrivacyRestrictedError) as exc:
                self._mark_telegram_risk_blocked(exc, f"{chat_key} forward init", chat_key=chat_key)
            except Exception as exc:
                if self._is_transient_telegram_rate_limit(exc):
                    self._register_telegram_transient_limit(
                        exc,
                        f"{chat_key} forward init",
                        chat_key=chat_key,
                        operation="history",
                    )
                print(f"[{chat_key}] forward init error: {exc!r}")
            return

        print(f"[{chat_key}] forward catch-up from max_saved_id={max_saved_id + 1}")

        got = 0
        while True:
            if not self._is_chat_enabled(chat_key):
                print(f"[{chat_key}] forward stopped: removed from selected source registry")
                break
            await self._wait_if_sync_paused(f"{chat_key} forward catch-up")
            await self._sleep_global_flood_wait(f"{chat_key} forward catch-up")
            await self._sleep_operation_cooldown("history", f"{chat_key} forward catch-up")
            try:
                await self.ensure_connected()
                batch_count = 0
                async for msg in self.client.iter_messages(entity, limit=1000, min_id=max_saved_id, reverse=True):
                    if not self._is_chat_enabled(chat_key):
                        print(f"[{chat_key}] forward stopped: removed from selected source registry")
                        self.save_state()
                        return
                    if int(msg.id) <= int(chat_state.get("max_saved_id", 0) or 0):
                        continue
                    chat = await self.client.get_entity(msg.peer_id) if msg.peer_id else entity
                    sender = await msg.get_sender()
                    record = self.record_from_message(msg, chat, sender)
                    record["message"]["media_path"] = await self.download_message_media(msg, chat_key)
                    record["message"]["has_media"] = bool(record["message"]["media_path"]) or msg.media is not None
                    self.append_jsonl(out_path, record, chat_key=chat_key)
                    if record["message"]["media_path"]:
                        _ensure_pending_image_ocr_task(force=False)
                    self.log_channel_activity(chat_key, "catch-up updating", msg)

                    current_max = int(chat_state.get("max_saved_id", 0) or 0)
                    if msg.id > current_max:
                        chat_state["max_saved_id"] = int(msg.id)
                        max_saved_id = int(msg.id)

                    got += 1
                    batch_count += 1
                    if got % 2000 == 0:
                        self.save_state()
                        print(f"[{chat_key}] forward checkpoint: got={got}, max_saved_id={chat_state['max_saved_id']}")

                if batch_count > 0:
                    self._clear_operation_cooldown("history", context=f"{chat_key} forward catch-up", chat_key=chat_key)
                    self.save_state()
                    print(f"[{chat_key}] forward batch checkpoint: got={got}, max_saved_id={chat_state.get('max_saved_id')}")

                if batch_count == 0:
                    break
            except FloodWaitError as exc:
                self._activate_global_flood_wait(exc, f"{chat_key} forward catch-up")
                print(f"[{chat_key}] forward FloodWait {self._flood_wait_seconds(exc)}s - global pause enabled")
                await self._sleep_global_flood_wait(f"{chat_key} forward catch-up")
            except (PeerFloodError, UserPrivacyRestrictedError) as exc:
                self._mark_telegram_risk_blocked(exc, f"{chat_key} forward catch-up", chat_key=chat_key)
                return
            except ConnectionError as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} forward catch-up", chat_key=chat_key, operation="history")
                print(f"[{chat_key}] forward disconnected: {exc!r} - reconnect in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)
            except Exception as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} forward catch-up", chat_key=chat_key, operation="history")
                print(f"[{chat_key}] forward error: {exc!r} - retry in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)

        self.save_state()
        print(f"[{chat_key}] forward done: got={got}, max_saved_id={chat_state.get('max_saved_id')}")

    def install_live_handler(self, entity: Any, chat_key: str) -> None:
        if chat_key in self._live_handlers_installed:
            return

        out_path = self.out_dir / f"{chat_key}.jsonl"
        self.recover_chat_state_from_existing_jsonl(chat_key, out_path)
        chat_state = self.get_chat_state(chat_key)
        chat_state.setdefault("max_saved_id", int(chat_state.get("max_saved_id", 0) or 0))

        @self.client.on(events.NewMessage(chats=entity))
        async def _handler(event):
            try:
                if self.is_sync_paused():
                    return
                if self._is_global_flood_wait_active(f"{chat_key} live handler"):
                    return
                if self._is_operation_cooldown_active("live", f"{chat_key} live handler"):
                    return
                if not self._is_chat_enabled(chat_key):
                    return
                msg = event.message
                if int(msg.id) <= int(chat_state.get("max_saved_id", 0) or 0):
                    return

                chat = await event.get_chat()
                sender = await event.get_sender()
                record = self.record_from_message(msg, chat, sender)
                record["message"]["media_path"] = await self.download_message_media(msg, chat_key)
                record["message"]["has_media"] = bool(record["message"]["media_path"]) or msg.media is not None
                self.append_jsonl(out_path, record, chat_key=chat_key)
                if record["message"]["media_path"]:
                    _ensure_pending_image_ocr_task(force=False)
                self.log_channel_activity(chat_key, "live update", msg, force=True)

                current_max = int(chat_state.get("max_saved_id", 0) or 0)
                if msg.id > current_max:
                    chat_state["max_saved_id"] = int(msg.id)
                self.save_state()
            except Exception as exc:
                if isinstance(exc, FloodWaitError):
                    self._activate_global_flood_wait(exc, f"{chat_key} live handler")
                    print(f"[{chat_key}] live handler FloodWait {self._flood_wait_seconds(exc)}s - global pause enabled")
                    return
                if isinstance(exc, (PeerFloodError, UserPrivacyRestrictedError)):
                    self._mark_telegram_risk_blocked(exc, f"{chat_key} live handler", chat_key=chat_key)
                    return
                if self._is_transient_telegram_rate_limit(exc):
                    self._register_telegram_transient_limit(
                        exc,
                        f"{chat_key} live handler",
                        chat_key=chat_key,
                        operation="live",
                    )
                    return
                print(f"[{chat_key}] live handler error: {exc!r}")

        self._live_handlers_installed.add(chat_key)
        print(f"[{chat_key}] live handler installed")

    async def _backfill_chat_history_task(self, entity: Any, chat_key: str) -> None:
        try:
            async with self._backfill_lock:
                await self.export_backfill(entity, chat_key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[{chat_key}] background backfill error: {exc!r}")
        finally:
            forget_completed_task(self._chat_backfill_tasks, chat_key, asyncio.current_task())

    def start_backfill_in_background(self, entity: Any, chat_key: str) -> None:
        if not self._is_chat_enabled(chat_key):
            return
        chat_state = self.get_chat_state(chat_key)
        if chat_state.get("backfill_done") and not self._resume_backfill_if_limits_expanded(chat_key):
            return
        task = self._chat_backfill_tasks.get(chat_key)
        if task and not task.done():
            return
        self._chat_backfill_tasks[chat_key] = asyncio.create_task(
            self._backfill_chat_history_task(entity, chat_key)
        )
        print(f"[{chat_key}] backfill scheduled in background")

    async def export_media_backfill(self, entity: Any, chat_key: str) -> None:
        if not _is_media_enabled_for_chat(chat_key):
            return

        await self._wait_if_sync_paused(f"{chat_key} media backfill")
        chat_state = self.get_chat_state(chat_key)
        offset_id = int(chat_state.get("media_backfill_offset_id", 0) or 0)
        total_checked = int(chat_state.get("media_backfill_items_checked", 0) or 0)
        total_downloaded = int(chat_state.get("media_backfill_images_downloaded", 0) or 0)

        chat_state["media_backfill_done"] = False
        chat_state["media_backfill_started_at"] = chat_state.get("media_backfill_started_at") or _utc_now().isoformat()
        chat_state["media_backfill_updated_at"] = _utc_now().isoformat()
        self.save_state()
        print(f"[{chat_key}] media backfill start: offset_id={offset_id or 'latest'}")

        while True:
            if not self._is_chat_enabled(chat_key) or not _is_media_enabled_for_chat(chat_key):
                print(f"[{chat_key}] media backfill stopped: media disabled")
                self.save_state()
                return
            await self._wait_if_sync_paused(f"{chat_key} media backfill")
            await self._sleep_global_flood_wait(f"{chat_key} media backfill")
            await self._sleep_operation_cooldown("media", f"{chat_key} media backfill")
            try:
                await self.ensure_connected()
                batch_count = 0
                async for msg in self.client.iter_messages(entity, limit=1000, offset_id=offset_id):
                    if not self._is_chat_enabled(chat_key) or not _is_media_enabled_for_chat(chat_key):
                        self.save_state()
                        print(f"[{chat_key}] media backfill stopped: media disabled")
                        return

                    offset_id = int(msg.id)
                    batch_count += 1
                    total_checked += 1
                    chat_state["media_backfill_offset_id"] = offset_id
                    chat_state["media_backfill_items_checked"] = total_checked
                    chat_state["last_media_check_id"] = offset_id
                    chat_state["media_checked_count"] = total_checked
                    chat_state["media_backfill_updated_at"] = _utc_now().isoformat()

                    if not self._message_has_downloadable_image(msg):
                        continue

                    media_path = await self.download_message_media(msg, chat_key)
                    if media_path:
                        total_downloaded += 1
                        chat_state["media_backfill_images_downloaded"] = total_downloaded
                        chat_state["media_downloaded_count"] = total_downloaded
                        _image_ocr_progress_log(f"Скачано изображение для OCR: {chat_key} #{msg.id}")
                        _ensure_pending_image_ocr_task(force=False)

                    if total_checked % 500 == 0:
                        self.save_state()
                        print(
                            f"[{chat_key}] media backfill checkpoint: "
                            f"checked={total_checked}, images={total_downloaded}, offset_id={offset_id}"
                        )

                if batch_count > 0:
                    self._clear_operation_cooldown("media", context=f"{chat_key} media backfill", chat_key=chat_key)
                    self.save_state()

                if batch_count == 0:
                    chat_state["media_backfill_done"] = True
                    chat_state["media_backfill_offset_id"] = offset_id
                    chat_state["media_backfill_items_checked"] = total_checked
                    chat_state["media_backfill_images_downloaded"] = total_downloaded
                    chat_state["media_checked_count"] = total_checked
                    chat_state["media_downloaded_count"] = total_downloaded
                    chat_state["media_backfill_updated_at"] = _utc_now().isoformat()
                    chat_state["media_backfill_completed_at"] = _utc_now().isoformat()
                    self.save_state()
                    print(f"[{chat_key}] media backfill done: checked={total_checked}, images={total_downloaded}")
                    break
            except FloodWaitError as exc:
                self._activate_global_flood_wait(exc, f"{chat_key} media backfill")
                print(f"[{chat_key}] media backfill FloodWait {self._flood_wait_seconds(exc)}s - global pause enabled")
                await self._sleep_global_flood_wait(f"{chat_key} media backfill")
            except (PeerFloodError, UserPrivacyRestrictedError) as exc:
                self._mark_telegram_risk_blocked(exc, f"{chat_key} media backfill", chat_key=chat_key)
                return
            except ConnectionError as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} media backfill", chat_key=chat_key, operation="media")
                print(f"[{chat_key}] media backfill disconnected: {exc!r} - reconnect in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)
            except Exception as exc:
                retry_sec = self._telegram_retry_delay(exc, f"{chat_key} media backfill", chat_key=chat_key, operation="media")
                print(f"[{chat_key}] media backfill error: {exc!r} - retry in {retry_sec:.0f}s")
                await asyncio.sleep(retry_sec)

    async def _media_backfill_chat_history_task(self, entity: Any, chat_key: str) -> None:
        try:
            async with self._media_backfill_lock:
                await self.export_media_backfill(entity, chat_key)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[{chat_key}] background media backfill error: {exc!r}")
        finally:
            forget_completed_task(self._chat_media_backfill_tasks, chat_key, asyncio.current_task())

    def start_media_backfill_in_background(self, entity: Any, chat_key: str, force: bool = False) -> None:
        if not self._is_chat_enabled(chat_key) or not _is_media_enabled_for_chat(chat_key):
            return
        chat_state = self.get_chat_state(chat_key)
        if chat_state.get("media_backfill_done") and not force:
            return
        task = self._chat_media_backfill_tasks.get(chat_key)
        if task and not task.done():
            return
        self._chat_media_backfill_tasks[chat_key] = asyncio.create_task(
            self._media_backfill_chat_history_task(entity, chat_key)
        )
        print(f"[{chat_key}] media backfill scheduled in background")

    async def _resolve_entity(self, chat_selector: Union[str, int], selector_key: Optional[str] = None) -> Any:
        await self.ensure_connected()
        await self._sleep_operation_cooldown("setup", f"setup {chat_selector!r}")
        entity = await self.client.get_entity(chat_selector)
        chat_key = self.chat_key_from_entity(entity)
        selector_key = selector_key or self._selector_key(chat_selector)
        self._persist_selector_resolution(selector_key, chat_key, entity)
        self._clear_operation_cooldown("setup", context=f"setup {chat_selector!r}", chat_key=chat_key)
        self.save_state()
        return entity

    async def setup_chat(self, chat_selector: Union[str, int], selector_key: Optional[str] = None) -> None:
        await self._wait_if_sync_paused(f"setup {chat_selector!r}")
        if self._is_global_flood_wait_active(f"setup {chat_selector!r}"):
            return
        if self._is_operation_cooldown_active("setup", f"setup {chat_selector!r}"):
            return
        if not self._selector_scan_allowed(chat_selector):
            return
        entity = await self._resolve_entity(chat_selector, selector_key=selector_key)
        chat_key = self.chat_key_from_entity(entity)
        selector_key = selector_key or self._selector_key(chat_selector)
        policy = _source_policy_for_lead(chat_key, str(chat_selector))
        if not policy.scan_allowed:
            print(
                f"[{chat_key}] skipped by source policy after resolve: "
                f"mode={policy.mode}, reason={policy.reason or 'manual'}"
            )
            return
        if selector_key not in self._desired_selector_keys:
            print(f"[{chat_key}] skipped: removed from selected source registry before setup")
            return

        self._enabled_chat_keys.add(chat_key)
        self.entities_by_chat_key[chat_key] = entity
        print(f"[{chat_key}] resolved")

        self.recover_chat_state_from_existing_jsonl(chat_key, self.out_dir / f"{chat_key}.jsonl")
        self.install_live_handler(entity, chat_key)
        await self.forward_catch_up(entity, chat_key)
        self.start_backfill_in_background(entity, chat_key)
        self.start_media_backfill_in_background(entity, chat_key)

    async def _setup_chat_task(self, chat_selector: Union[str, int], selector_key: str) -> None:
        try:
            await self._wait_if_sync_paused(f"setup {chat_selector!r}")
            if self._is_global_flood_wait_active(f"setup {chat_selector!r}"):
                return
            async with self._setup_lock:
                if self._is_global_flood_wait_active(f"setup {chat_selector!r}"):
                    return
                await self.setup_chat(chat_selector, selector_key=selector_key)
        except asyncio.CancelledError:
            raise
        except FloodWaitError as exc:
            self._activate_global_flood_wait(exc, f"setup {chat_selector!r}")
            print(
                f"[telegram-sync] setup FloodWait for {chat_selector!r}: "
                f"{self._flood_wait_seconds(exc)}s - global pause enabled"
            )
        except (PeerFloodError, UserPrivacyRestrictedError) as exc:
            self._mark_telegram_risk_blocked(exc, f"setup {chat_selector!r}", chat_key=self._selector_key(chat_selector))
        except Exception as exc:
            if self._is_transient_telegram_rate_limit(exc):
                self._register_telegram_transient_limit(
                    exc,
                    f"setup {chat_selector!r}",
                    operation="setup",
                )
                return
            if _should_emit_telegram_setup_error(chat_selector, exc):
                print(f"[telegram-sync] setup error for {chat_selector!r}: {exc!r}")
            self._mark_selector_setup_failed(selector_key, chat_selector, exc)
        finally:
            current = self._chat_setup_tasks.get(selector_key)
            if current is asyncio.current_task():
                self._chat_setup_tasks.pop(selector_key, None)

    async def sync_selected_chats(self) -> None:
        announced_live = False
        empty_reported = False

        while True:
            self.refresh_runtime_control_from_disk()
            if self.is_sync_paused():
                await self._release_session_handles_for_pause("sync control pause")
                try:
                    await asyncio.wait_for(
                        self._source_reload_event.wait(),
                        timeout=max(5, self._source_poll_interval),
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._source_reload_event.clear()
                continue

            if self.client is None or not self.client.is_connected():
                await self.ensure_connected()

            self.selected_chats = [
                selector
                for selector in self.combined_selected_chats()
                if self._selector_scan_allowed(selector)
            ]
            self.selected_chats = self.sort_selected_chats_for_scan(self.selected_chats)
            desired = {self._selector_key(chat_selector): chat_selector for chat_selector in self.selected_chats}
            desired_keys = set(desired)

            removed_keys = self._desired_selector_keys - desired_keys
            self._desired_selector_keys = desired_keys

            for selector_key in removed_keys:
                self._disable_selector(selector_key)

            if not desired_keys:
                if not empty_reported:
                    print("[telegram-sync] selected source registry is empty, no chats selected")
                    empty_reported = True
                await asyncio.sleep(self._source_poll_interval)
                continue

            empty_reported = False

            if self._is_global_flood_wait_active("setup scheduler"):
                try:
                    await asyncio.wait_for(
                        self._source_reload_event.wait(),
                        timeout=self._source_poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._source_reload_event.clear()
                continue
            if self._is_operation_cooldown_active("setup", "setup scheduler"):
                try:
                    await asyncio.wait_for(
                        self._source_reload_event.wait(),
                        timeout=self._source_poll_interval,
                    )
                except asyncio.TimeoutError:
                    pass
                finally:
                    self._source_reload_event.clear()
                continue

            scheduled_this_tick = 0
            for selector_key, chat_selector in desired.items():
                task = self._chat_setup_tasks.get(selector_key)
                if task and not task.done():
                    continue
                if self._selector_setup_is_blocked(selector_key):
                    continue

                cache_entry = self._selector_cache_entry(selector_key)
                if cache_entry:
                    cached_chat_key = str(cache_entry.get("chat_key") or "").strip()
                    if cached_chat_key:
                        self._selector_to_chat_key.setdefault(selector_key, cached_chat_key)

                chat_key = self._selector_to_chat_key.get(selector_key)
                if chat_key and self._is_chat_enabled(chat_key):
                    continue
                if chat_key:
                    chat_state = self.get_chat_state(chat_key)
                    retry_after = self._parse_state_datetime(chat_state.get("retry_after"))
                    if retry_after and retry_after > _utc_now():
                        continue
                    if str(chat_state.get("telegram_status") or "") in {"risk_blocked", "blocked_privacy"}:
                        continue

                if scheduled_this_tick >= 1:
                    break
                self._chat_setup_tasks[selector_key] = asyncio.create_task(
                    self._setup_chat_task(chat_selector, selector_key)
                )
                scheduled_this_tick += 1

            if not announced_live:
                print("[telegram-sync] live sync is running")
                announced_live = True

            if self._source_reload_event.is_set():
                self._source_reload_event.clear()
                continue

            try:
                await asyncio.wait_for(
                    self._source_reload_event.wait(),
                    timeout=self._source_poll_interval,
                )
            except asyncio.TimeoutError:
                pass
            finally:
                self._source_reload_event.clear()

    async def start(self, sync_in_background: bool = True) -> None:
        async with self._startup_lock:
            if not self._started:
                self.state = self.load_state()
                self._restore_global_flood_wait_from_state()
                self._hydrate_selector_cache_from_state()

            if self.is_sync_paused():
                status = self.get_sync_control_status()
                print(
                    "[telegram-sync] start skipped: sync paused; "
                    f"paused_at={status.get('paused_at')}, reason={status.get('reason') or 'manual'}"
                )
                return

            if not self.has_api_credentials():
                self._set_auth_error(
                    "Укажите Telegram api_id и api_hash из my.telegram.org → API development tools.",
                    step="api",
                )
                return

            if sync_in_background:
                connected = await self.connect_once()
                if not connected:
                    print("[telegram-sync] background start skipped: Telegram is not reachable yet")
                    return
            else:
                await self.ensure_connected()

            if not self._started:
                self._started = True

            self.selected_chats = self.combined_selected_chats()

            if self._connection_watch_task is None or self._connection_watch_task.done():
                self._connection_watch_task = asyncio.create_task(self.maintain_connection())

            if self._sync_task is None or self._sync_task.done():
                if sync_in_background:
                    self._sync_task = asyncio.create_task(self.sync_selected_chats())
                else:
                    await self.sync_selected_chats()

    async def stop(self) -> None:
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        if self._connection_watch_task and not self._connection_watch_task.done():
            self._connection_watch_task.cancel()
            try:
                await self._connection_watch_task
            except asyncio.CancelledError:
                pass
        for selector_key, task in list(self._chat_setup_tasks.items()):
            if not task.done():
                task.cancel()
            self._chat_setup_tasks.pop(selector_key, None)
        for chat_key, task in list(self._chat_backfill_tasks.items()):
            if not task.done():
                task.cancel()
            self._chat_backfill_tasks.pop(chat_key, None)
        for chat_key, task in list(self._chat_media_backfill_tasks.items()):
            if not task.done():
                task.cancel()
            self._chat_media_backfill_tasks.pop(chat_key, None)
        if self.client is not None:
            await self.client.disconnect()

    async def send_message(self, chat_id: str, message: str) -> None:
        chat = (chat_id or "").strip()
        if not chat:
            raise ValueError("chat_id is empty")
        if not message:
            raise ValueError("message is empty")

        await self.start(sync_in_background=True)
        if self.client is None:
            raise RuntimeError("Telegram client is unavailable")

        entity = self.entities_by_chat_key.get(chat.lower()) or self.entities_by_chat_key.get(chat)
        target = entity or chat
        await self.client.send_message(target, message)

    async def run_forever(self) -> None:
        await self.start(sync_in_background=True)
        if self.client is None:
            raise RuntimeError("Telegram client is unavailable")
        await self.client.run_until_disconnected()

if {"API_ID", "API_HASH", "SESSION", "PAYME_OUT_DIR", "STATE_PATH"}.issubset(globals()):
    telegram_sync = TelegramSync(
        api_id=API_ID,
        api_hash=API_HASH,
        session=SESSION,
        out_dir=PAYME_OUT_DIR,
        state_path=STATE_PATH,
    )
else:
    telegram_sync = None

__all__ = ["TelegramSync", "telegram_sync", "refresh_legacy_globals"]
