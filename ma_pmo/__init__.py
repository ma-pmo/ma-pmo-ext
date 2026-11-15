"""MA-PMO: LLM-backed supervisor-worker multi-agent PMO orchestration."""
from importlib.metadata import PackageNotFoundError, version

try:  # the installed distribution's version, so it cannot drift from pyproject.toml
    __version__ = version("ma-pmo")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"
