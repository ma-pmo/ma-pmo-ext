"""`ma-pmo learn` — list, start and check the course labs."""
from __future__ import annotations

import argparse
import logging
import os
import shutil
from pathlib import Path

from ma_pmo.core.i18n import get_lang, tr
from ma_pmo.learn import LABS, Lab, get_lab


def _title(lab: Lab) -> str:
    return tr(*lab.title)


DOCS_URL = "https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn"


def _doc(name: str) -> str:
    """Link to a course page in the reader's language (docs are not shipped in the wheel)."""
    return f"{DOCS_URL}/{name.replace('.md', '.ko.md') if get_lang() == 'ko' else name}"


def _workdir(base: str, lab: Lab) -> Path:
    return Path(base) / f"lab{lab.number}"


def _cmd_list() -> int:
    print(tr("Labs", "실습 목록"))
    for lab in LABS.values():
        print(f"  {lab.number}. {_title(lab)}")
        print(f"     {tr('lecture', '강의')}: {_doc(lab.lecture)}")
    print(tr(f"\nCourse map: {_doc('README.md')}", f"\n과정 지도: {_doc('README.md')}"))
    print(tr("\nStart one with `ma-pmo learn start 1`.", "\n`ma-pmo learn start 1`로 시작하세요."))
    return 0


def _cmd_scenarios() -> int:
    """Scenario ids with the agents each one calls (lab 3 picks scenarios that use A7)."""
    from ma_pmo.core.scenarios import SCENARIOS

    print(tr("scenario id                agents", "시나리오 id                에이전트"))
    for sid, scen in SCENARIOS.items():
        agents = sorted({a for a, _ in scen["steps"]})
        print(f"  {sid:<25}{', '.join(agents)}")
    return 0


def _cmd_start(lab: Lab, base: str, *, force: bool, solution: bool) -> int:
    dest = _workdir(base, lab) if not solution else Path(base) / f"lab{lab.number}-solution"
    if dest.exists() and any(dest.iterdir()) and not force:
        print(tr(f"✗ {dest} already exists — use --force to overwrite it",
                 f"✗ {dest} 폴더가 이미 있습니다 — 덮어쓰려면 --force를 붙이세요"))
        return 1
    if dest.exists() and force:
        shutil.rmtree(dest)
    shutil.copytree(lab.solution if solution else lab.starter, dest)
    for guide in ("README.md", "README.ko.md"):
        shutil.copy(lab.folder / guide, dest / guide)
    print(tr(f"✓ Lab {lab.number} — {_title(lab)}: files copied to {dest}",
             f"✓ 실습 {lab.number} — {_title(lab)}: {dest}에 파일을 복사했습니다"))
    for path in sorted(p for p in dest.rglob("*") if p.is_file()):
        print(f"  - {path.relative_to(dest)}")
    if not solution:
        guide = "README.ko.md" if get_lang() == "ko" else "README.md"
        print(tr(f"\nRead {dest / guide}, then run `ma-pmo learn check {lab.number}`.",
                 f"\n{dest / guide}를 읽고 `ma-pmo learn check {lab.number}`를 실행하세요."))
    return 0


def _prepare_db(workdir: Path) -> None:
    """Labs that run agents get their own SQLite file, never the learner's real database."""
    if not os.environ.get("DB_URL"):
        workdir.mkdir(parents=True, exist_ok=True)
        path = workdir.resolve() / ".ma-pmo-learn.db"
        os.environ["DB_URL"] = f"sqlite:///{path}"
        os.environ.setdefault("CHECKPOINT_DB", str(path.with_suffix(".ckpt.sqlite")))
    from ma_pmo.db.init import load_fixtures, load_lessons
    from ma_pmo.db.session import ensure_schema

    ensure_schema()
    load_fixtures()
    load_lessons()


def _quiet_logs() -> None:
    """Show only check results: expected failures (lab 1) and LLM fallbacks are not news here."""
    import litellm
    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    litellm.suppress_debug_info = True


def _cmd_check(lab: Lab, base: str, *, solution: bool) -> int:
    from ma_pmo.learn.checks import run_checks

    if lab.needs_extra:
        import importlib.util

        if importlib.util.find_spec(lab.needs_extra) is None:
            print(tr(f'✗ lab {lab.number} needs the extra: pip install "ma-pmo[{lab.needs_extra}]"',
                     f'✗ 실습 {lab.number}에는 추가 설치가 필요합니다: pip install "ma-pmo[{lab.needs_extra}]"'))
            return 1
    workdir = lab.solution if solution else _workdir(base, lab)
    if not workdir.is_dir():
        print(tr(f"✗ {workdir} not found — run `ma-pmo learn start {lab.number}` first",
                 f"✗ {workdir} 폴더가 없습니다 — 먼저 `ma-pmo learn start {lab.number}`를 실행하세요"))
        return 1
    _quiet_logs()
    if lab.needs_db:
        _prepare_db(workdir if not solution else Path(base))
    results = run_checks(lab.number, workdir)
    print(tr(f"Lab {lab.number} — {_title(lab)} ({workdir})",
             f"실습 {lab.number} — {_title(lab)} ({workdir})"))
    for r in results:
        print(f"  {'✓' if r.ok else '✗'} {r.name}")
        if not r.ok and r.hint:
            print(f"      → {r.hint}")
    passed = sum(r.ok for r in results)
    done = passed == len(results)
    print(tr(f"\n{passed}/{len(results)} checks passed" + (" — lab complete 🎉" if done else ""),
             f"\n{len(results)}개 중 {passed}개 통과" + (" — 실습 완료 🎉" if done else "")))
    return 0 if done else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ma-pmo learn", description="course labs")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="show the labs")
    sub.add_parser("scenarios", help="scenario ids and the agents each one uses")
    start = sub.add_parser("start", help="copy a lab's starter files")
    start.add_argument("lab", type=int)
    start.add_argument("--dir", default="learn", help="parent folder (default: ./learn)")
    start.add_argument("--force", action="store_true", help="overwrite an existing lab folder")
    start.add_argument("--solution", action="store_true",
                       help="copy the reference solution to lab<N>-solution instead")
    check = sub.add_parser("check", help="check your work on a lab")
    check.add_argument("lab", type=int)
    check.add_argument("--dir", default="learn", help="parent folder (default: ./learn)")
    check.add_argument("--solution", action="store_true", help="check the reference solution")
    ns = parser.parse_args(argv)

    if ns.action == "list":
        return _cmd_list()
    if ns.action == "scenarios":
        return _cmd_scenarios()
    try:
        lab = get_lab(ns.lab)
    except ValueError as e:
        print(f"✗ {e}")
        return 2
    if ns.action == "start":
        return _cmd_start(lab, ns.dir, force=ns.force, solution=ns.solution)
    return _cmd_check(lab, ns.dir, solution=ns.solution)
