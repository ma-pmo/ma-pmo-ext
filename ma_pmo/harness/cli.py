"""Harness CLI — `ma-pmo harness <experiment> [--save]` (or `python -m ma_pmo.harness.cli`).

Examples:
    ma-pmo harness list
    ma-pmo harness full_suite
    ma-pmo harness a7_ablation --save
    ma-pmo harness new risk_focus --hypothesis H3 --repeat 3
"""
from __future__ import annotations

import argparse
import sys

from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import configure_logging
from ma_pmo.harness import render_markdown, run_experiment, write_report
from ma_pmo.harness.experiments import discover


def _new(argv: list[str]) -> int:
    from ma_pmo.harness.scaffold import new_experiment

    p = argparse.ArgumentParser(prog="ma-pmo harness new",
                                description="scaffold a new experiment and its test")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--scenarios", default="", help="comma-separated scenario ids")
    p.add_argument("--hypothesis", choices=["H1", "H2", "H3", "H4", "H5"],
                   help="use every scenario that tests this hypothesis")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--ablate", default="", help="comma-separated agents, e.g. A7")
    p.add_argument("--dir",
                   help="experiments folder (default: $MA_PMO_EXPERIMENTS_DIR or ./experiments)")
    p.add_argument("--tests-dir", help="where to write the test (default: same folder)")
    p.add_argument("--no-test", action="store_true")
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    split = lambda v: [x.strip() for x in v.split(",") if x.strip()]  # noqa: E731
    try:
        paths = new_experiment(
            a.name, description=a.description, scenarios=split(a.scenarios),
            hypothesis=a.hypothesis, repeat=a.repeat, ablate=split(a.ablate),
            directory=a.dir, tests_dir=a.tests_dir, with_test=not a.no_test, force=a.force,
        )
    except (ValueError, FileExistsError) as e:
        print(f"✗ {e}")
        return 1
    print(tr("✓ created:", "✓ 생성했습니다:"))
    for path in paths:
        print(f"  - {path}")
    print(tr(f"\nRun it: ma-pmo harness {a.name}", f"\n실행: ma-pmo harness {a.name}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(tr("usage: ma-pmo harness <experiment> [--save] | list | new <name>",
                 "사용법: ma-pmo harness <experiment> [--save] | list | new <name>"))
        print(tr("experiments: ma-pmo harness list", "실험 목록: ma-pmo harness list"))
        return 0

    name = argv[0]
    if name == "new":
        return _new(argv[1:])
    experiments = discover()
    if name == "list":
        for k, s in experiments.items():
            print(f"  {k:20} {s.build().description}")
        return 0

    if name not in experiments:
        print(tr(f"unknown experiment: {name}. See 'list'.",
                 f"알 수 없는 실험: {name}. 목록은 'list'."))
        return 1

    configure_logging()
    result = run_experiment(experiments[name])
    print(render_markdown(result))
    if "--save" in argv:
        paths = write_report(result)
        print(tr("\nsaved:", "\n저장:"), ", ".join(paths.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
