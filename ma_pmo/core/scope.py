"""The portfolio used when a caller does not name one (MA_PMO_DEFAULT_PORTFOLIO)."""
from __future__ import annotations

from ma_pmo.core.config import get_settings

DEFAULT_SCOPE = get_settings().default_portfolio
