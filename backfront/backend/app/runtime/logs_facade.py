"""Runtime logs facade."""

from app.services import monitoring

api_payme_runtime_logs = monitoring.api_payme_runtime_logs
api_payme_runtime_logs_stream = monitoring.api_payme_runtime_logs_stream

__all__ = ["api_payme_runtime_logs", "api_payme_runtime_logs_stream"]

