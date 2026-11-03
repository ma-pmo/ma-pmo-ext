"""Experiment template — scaffold a new experiment (and its test) with one command.

    ma-pmo harness new risk_focus --hypothesis H3 --repeat 3
    ma-pmo harness new kickoff_check --scenarios knowledge_kickoff,baseline_planning --ablate A7

Files go to the experiments folder (`MA_PMO_EXPERIMENTS_DIR`, default `./experiments`) and are
picked up automatically by `ma-pmo harness list` / `ma-pmo harness <name>`.
"""
from __future__ import annotations

import keyword
import re
from pathlib import Path

from ma_pmo.core.scenarios import SCENARIOS
from ma_pmo.harness.experiments import discover, experiments_dir

HYPOTHESES = ("H1", "H2", "H3", "H4", "H5")
AGENTS = ("A2", "A3", "A4", "A5", "A6", "A7")
RESERVED = {"new", "list", "help"}
_NAME = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

_EXPERIMENT = '''"""{description}

Created with `ma-pmo harness new`. Run it with `ma-pmo harness {name}`.
"""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment({name!r}, {description!r})
    .with_scenarios(
{scenarios}
    )
    .repeat({repeat}){ablate}
)
'''

_TEST = '''"""Smoke test for the {name} experiment (created with `ma-pmo harness new`)."""
from pathlib import Path

from ma_pmo.harness import run_experiment
from ma_pmo.harness.experiments import load_experiment_file

EXPERIMENT = Path(__file__).resolve().parent{rel} / "{name}.py"


def test_{name}_runs():
    spec = load_experiment_file(EXPERIMENT).repeat(1)
    result = run_experiment(spec)
    assert result["runs"], "every scenario should produce a run"
    assert all(r["n_outputs"] > 0 for r in result["runs"])
'''


def _validate(name: str, scenarios: list[str], ablate: list[str], hypothesis: str | None,
              repeat: int) -> None:
    if not _NAME.match(name) or keyword.iskeyword(name) or name in RESERVED:
        raise ValueError(f"invalid experiment name '{name}': use lowercase letters, digits "
                         "and _ (start with a letter), not a reserved word")
    unknown = [s for s in scenarios if s not in SCENARIOS]
    if unknown:
        raise ValueError(f"unknown scenarios: {', '.join(unknown)} "
                         f"(see GET /scenarios for ids)")
    bad = [a for a in ablate if a not in AGENTS]
    if bad:
        raise ValueError(f"can only ablate {', '.join(AGENTS)}; got {', '.join(bad)}")
    if hypothesis and hypothesis not in HYPOTHESES:
        raise ValueError(f"hypothesis must be one of {', '.join(HYPOTHESES)}")
    if not 1 <= repeat <= 50:
        raise ValueError("repeat must be between 1 and 50")


def scenarios_for(hypothesis: str) -> list[str]:
    """Scenario ids that test a hypothesis, in catalog order."""
    return [sid for sid, s in SCENARIOS.items() if hypothesis in s["hypotheses"]]


def new_experiment(name: str, *, description: str = "", scenarios: list[str] | None = None,
                   hypothesis: str | None = None, repeat: int = 1,
                   ablate: list[str] | None = None, directory: str | Path | None = None,
                   tests_dir: str | Path | None = None, with_test: bool = True,
                   force: bool = False) -> list[Path]:
    """Write `<directory>/<name>.py` (and a test). Returns the written paths."""
    scenarios = list(scenarios or [])
    ablate = list(ablate or [])
    _validate(name, scenarios, ablate, hypothesis, repeat)
    if not scenarios:
        scenarios = scenarios_for(hypothesis) if hypothesis else []
    if not scenarios:
        raise ValueError("give --scenarios or --hypothesis so the experiment has scenarios")
    used = {a for sid in scenarios for a, _ in SCENARIOS[sid]["steps"]}
    unused = [a for a in ablate if a not in used]
    if unused:
        raise ValueError(f"ablating {', '.join(unused)} changes nothing: no selected scenario "
                         "uses it")

    folder = Path(directory) if directory is not None else experiments_dir()
    target = folder / f"{name}.py"
    if not force:
        if target.exists():
            raise FileExistsError(f"{target} already exists (use --force)")
        if name in discover(folder):
            raise FileExistsError(f"an experiment named '{name}' already exists")

    description = description or (
        f"{hypothesis} check" if hypothesis else f"Experiment {name}"
    )
    folder.mkdir(parents=True, exist_ok=True)
    target.write_text(
        _EXPERIMENT.format(
            name=name,
            description=description,
            scenarios="\n".join(f"        {s!r}," for s in scenarios),
            repeat=repeat,
            ablate=f"\n    .ablate({', '.join(repr(a) for a in ablate)})" if ablate else "",
        ),
        encoding="utf-8",
    )
    written = [target]

    if with_test:
        tdir = Path(tests_dir) if tests_dir is not None else folder
        tdir.mkdir(parents=True, exist_ok=True)
        rel = _relative(tdir, folder)
        test_path = tdir / f"test_{name}.py"
        if test_path.exists() and not force:
            raise FileExistsError(f"{test_path} already exists (use --force)")
        test_path.write_text(_TEST.format(name=name, rel=rel), encoding="utf-8")
        written.append(test_path)
    return written


def _relative(tests_dir: Path, folder: Path) -> str:
    """Path expression from the test file's folder to the experiment folder."""
    t, f = tests_dir.resolve(), folder.resolve()
    if t == f:
        return ""
    common = Path(*[a for a, b in zip(t.parts, f.parts, strict=False) if a == b])
    ups = len(t.parts) - len(common.parts)
    downs = f.parts[len(common.parts):]
    return ".parent" * ups + "".join(f" / {p!r}" for p in downs)
