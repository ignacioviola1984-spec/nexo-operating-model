"""Structured JSON logging for Nexo v3.

Every record carries a run_id when one is bound. NO PII in log bodies: log
identifiers (cliente_id, poliza_id), never names/documents/emails/phones. The
audit trail (hash-chained, in the store) is separate from these operational logs.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog to emit JSON lines to stderr. Idempotent."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Bind run_id via bind_run_id() for correlation."""
    return structlog.get_logger(name)


def bind_run_id(run_id: str) -> None:
    """Bind a run_id to all subsequent log records in this context."""
    structlog.contextvars.bind_contextvars(run_id=run_id)


def clear_context() -> None:
    """Clear bound context vars (call at the end of a run)."""
    structlog.contextvars.clear_contextvars()
