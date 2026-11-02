"""Experiments — discovered automatically, run by name from the CLI.

Any module in this package, or any `.py` file in the experiments folder
(`MA_PMO_EXPERIMENTS_DIR`, default `./experiments`), that defines a module-level
`spec = Experiment(...)` is registered under its file name. Create one with:

    ma-pmo harness new my_experiment --hypothesis H3
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import pkgutil
from pathlib import Path
from types import ModuleType

from ma_pmo.core.obs import get_logger
from ma_pmo.harness.spec import Experiment

_log = get_logger("harness")


def experiments_dir() -> Path:
    return Path(os.environ.get("MA_PMO_EXPERIMENTS_DIR", "experiments"))


def _spec_of(module: ModuleType) -> Experiment | None:
    spec = getattr(module, "spec", None)
    return spec if isinstance(spec, Experiment) else None


def load_experiment_file(path: str | Path) -> Experiment:
    """Load the `spec` defined in a standalone experiment file."""
    path = Path(path)
    mod_spec = importlib.util.spec_from_file_location(f"ma_pmo_user_exp_{path.stem}", path)
    if mod_spec is None or mod_spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(module)
    spec = _spec_of(module)
    if spec is None:
        raise ImportError(f"{path} has no module-level `spec = Experiment(...)`")
    return spec


def _builtin() -> dict[str, Experiment]:
    found = {}
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        spec = _spec_of(importlib.import_module(f"{__name__}.{info.name}"))
        if spec is not None:
            found[info.name] = spec
    return found


def discover(directory: str | Path | None = None) -> dict[str, Experiment]:
    """Built-in experiments plus those in the user experiments folder."""
    found = _builtin()
    folder = Path(directory) if directory is not None else experiments_dir()
    if folder.is_dir():
        for path in sorted(folder.glob("*.py")):
            if path.name.startswith(("_", "test_")):
                continue
            try:
                found.setdefault(path.stem, load_experiment_file(path))
            except Exception as e:  # one broken file must not hide the others
                _log.warning("experiment_load_failed", file=str(path), error=str(e))
    return found


# built-in experiments, kept for backwards compatibility
EXPERIMENTS: dict[str, Experiment] = _builtin()

__all__ = ["EXPERIMENTS", "discover", "experiments_dir", "load_experiment_file"]
