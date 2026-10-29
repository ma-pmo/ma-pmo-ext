"""Harness CLI — `python -m ma_pmo.harness.cli <experiment> [--save]` (or `ma-pmo harness`).

Examples:
    python -m ma_pmo.harness.cli list
    python -m ma_pmo.harness.cli full_suite
    python -m ma_pmo.harness.cli a7_ablation --save
"""
from __future__ import annotations

import sys

from ma_pmo.core.i18n import tr
from ma_pmo.core.obs import configure_logging
from ma_pmo.harness import render_markdown, run_experiment, write_report
from ma_pmo.harness.experiments import EXPERIMENTS


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(tr("usage: ma-pmo harness <experiment> [--save]",
                 "사용법: ma-pmo harness <experiment> [--save]"))
        print(tr("experiments: ma-pmo harness list", "실험 목록: ma-pmo harness list"))
        return 0

    name = argv[0]
    if name == "list":
        for k, s in EXPERIMENTS.items():
            print(f"  {k:20} {s.build().description}")
        return 0

    if name not in EXPERIMENTS:
        print(tr(f"unknown experiment: {name}. See 'list'.",
                 f"알 수 없는 실험: {name}. 목록은 'list'."))
        return 1

    configure_logging()
    result = run_experiment(EXPERIMENTS[name])
    print(render_markdown(result))
    if "--save" in argv:
        paths = write_report(result)
        print(tr("\nsaved:", "\n저장:"), ", ".join(paths.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
