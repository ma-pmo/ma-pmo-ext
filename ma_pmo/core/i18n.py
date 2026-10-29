"""Output language for user-facing text (English by default, Korean optional).

The active language is stored in a context variable so each API request can pick
its own language (`?lang=ko` or `Accept-Language: ko`) without global state.
The process-wide default comes from `MA_PMO_LANG` (see `core/config.py`).
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

SUPPORTED = ("en", "ko")

_lang: ContextVar[str | None] = ContextVar("ma_pmo_lang", default=None)


def normalize(lang: str | None) -> str | None:
    """Map 'ko-KR', 'KO', 'en_US' … to a supported code, or None if unsupported."""
    if not lang:
        return None
    code = lang.strip().lower().replace("_", "-").split("-")[0]
    return code if code in SUPPORTED else None


def default_lang() -> str:
    from ma_pmo.core.config import get_settings

    return normalize(get_settings().default_lang) or "en"


def get_lang() -> str:
    return _lang.get() or default_lang()


def set_lang(lang: str | None) -> None:
    _lang.set(normalize(lang))


@contextmanager
def use_lang(lang: str | None) -> Iterator[None]:
    token = _lang.set(normalize(lang))
    try:
        yield
    finally:
        _lang.reset(token)


def tr(en: str, ko: str) -> str:
    """Return the string for the active language."""
    return ko if get_lang() == "ko" else en


def from_accept_language(header: str | None) -> str | None:
    """Pick the first supported language from an Accept-Language header."""
    for part in (header or "").split(","):
        code = normalize(part.split(";")[0])
        if code:
            return code
    return None
