"""Observability — structured logging setup.

Prints agent behavior (messages, KPI records, scenario phases) to the console as
human-readable key-value logs. A lightweight entry point to paper §5 observability
(OTel/Langfuse).
"""
from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    # logs go to stderr (stdout is reserved for data/reports -> clean CLI output)
    logging.basicConfig(
        format="%(message)s", level=getattr(logging, level, logging.INFO), stream=sys.stderr
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str = "ma-pmo"):
    return structlog.get_logger(name)
