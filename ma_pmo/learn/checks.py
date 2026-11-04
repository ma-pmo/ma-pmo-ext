"""Automatic checks for the labs.

Each `check_labN(workdir)` returns one `Result` per requirement. A check never raises: an
exception inside the learner's code becomes a failed result with the error message, so one
broken step does not hide the feedback for the others.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from ma_pmo.core.i18n import tr


@dataclass
class Result:
    name: str
    ok: bool
    hint: str = ""


class _Fail(AssertionError):
    """A failed requirement; the message is the hint shown to the learner."""


def _require(cond: bool, hint: str) -> None:
    if not cond:
        raise _Fail(hint)


def _run(results: list[Result], name: str, fn: Callable[[], None]) -> None:
    try:
        fn()
        results.append(Result(name, True))
    except _Fail as e:
        results.append(Result(name, False, str(e)))
    except NotImplementedError:
        results.append(Result(name, False, tr("not implemented yet (TODO)",
                                              "아직 구현되지 않았습니다 (TODO)")))
    except Exception as e:  # learner code may raise anything
        results.append(Result(name, False, f"{type(e).__name__}: {e}"[:300]))


def _load_module(path: Path) -> ModuleType:
    if not path.is_file():
        raise _Fail(tr(f"{path} not found — run `ma-pmo learn start` first",
                       f"{path} 파일이 없습니다 — 먼저 `ma-pmo learn start`를 실행하세요"))
    spec = importlib.util.spec_from_file_location(f"ma_pmo_lab_{path.stem}_{id(path)}", path)
    if spec is None or spec.loader is None:
        raise _Fail(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Lab 1: notifier plugin ─────────────────────────────────────────────────────────

def check_lab1(workdir: Path) -> list[Result]:
    from ma_pmo.core.config import Settings
    from ma_pmo.integrations.base import Event, EventType, Notifier
    from ma_pmo.integrations.dispatch import emit

    results: list[Result] = []
    state: dict[str, Any] = {}
    tmp = Path(tempfile.mkdtemp(prefix="ma-pmo-lab1-"))

    def event(severity: str = "info") -> Event:
        return Event(EventType.TEST, f"{severity} event", "lab 1", severity=severity)  # type: ignore[arg-type]

    def lines(path: Path) -> list[dict]:
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]

    def imports() -> None:
        state["m"] = _load_module(workdir / "file_notifier.py")
        _require(hasattr(state["m"], "FileNotifier") and hasattr(state["m"], "SPEC"),
                 tr("file_notifier.py must define FileNotifier and SPEC",
                    "file_notifier.py에 FileNotifier와 SPEC이 있어야 합니다"))

    def spec() -> None:
        s = state["m"].SPEC
        _require(s.name == "file", tr("SPEC.name should be 'file'", "SPEC.name은 'file'이어야 합니다"))
        _require(s.kind == "notifier", tr("a notifier delivers events: SPEC.kind = 'notifier'",
                                          "이벤트를 보내는 연동이므로 SPEC.kind = 'notifier'"))

    def writes_json_lines() -> None:
        path = tmp / "events.jsonl"
        n = state["m"].FileNotifier(path)
        _require(isinstance(n, Notifier), tr("FileNotifier must have `name` and `send(event)`",
                                             "FileNotifier에 `name`과 `send(event)`가 있어야 합니다"))
        n.send(event("warning"))
        n.send(event("critical"))
        rows = lines(path)
        _require(len(rows) == 2, tr(f"expected 2 lines after 2 events, got {len(rows)}",
                                    f"이벤트 2개를 보냈으니 2줄이어야 하는데 {len(rows)}줄입니다"))
        _require(all({"type", "title", "severity", "occurred_at"} <= r.keys() for r in rows),
                 tr("each line should be event.as_dict() as JSON",
                    "각 줄은 event.as_dict()를 JSON으로 쓴 것이어야 합니다"))

    def severity_filter() -> None:
        path = tmp / "filtered.jsonl"
        n = state["m"].FileNotifier(path, min_severity="warning")
        for sev in ("info", "warning", "critical"):
            n.send(event(sev))
        got = [r["severity"] for r in lines(path)]
        _require(got == ["warning", "critical"],
                 tr(f"with min_severity='warning' expected [warning, critical], got {got}",
                    f"min_severity='warning'이면 [warning, critical]만 기록해야 하는데 {got}"))
        try:
            state["m"].FileNotifier(path, min_severity="loud")
        except ValueError:
            return
        raise _Fail(tr("an unknown min_severity should raise ValueError",
                       "알 수 없는 min_severity는 ValueError를 내야 합니다"))

    def from_settings() -> None:
        target = tmp / "from-env.jsonl"
        old = os.environ.get("MA_PMO_NOTIFY_FILE")
        os.environ["MA_PMO_NOTIFY_FILE"] = str(target)
        try:
            n = state["m"].SPEC.factory(Settings())
        finally:
            if old is None:
                os.environ.pop("MA_PMO_NOTIFY_FILE", None)
            else:
                os.environ["MA_PMO_NOTIFY_FILE"] = old
        _require(Path(n.path) == target, tr("from_settings should read MA_PMO_NOTIFY_FILE",
                                            "from_settings는 MA_PMO_NOTIFY_FILE을 읽어야 합니다"))

    def failure_isolated() -> None:
        ok_path = tmp / "isolated.jsonl"
        rows = emit([event("critical")], notifiers=[state["m"].FileNotifier(ok_path)],
                    settings=Settings())
        _require(bool(rows) and rows[0]["ok"] is True and len(lines(ok_path)) == 1,
                 tr("a working FileNotifier should deliver through emit() first",
                    "먼저 정상 경로에서 emit()으로 전달이 되어야 합니다"))
        broken = state["m"].FileNotifier(tmp / "missing-dir" / "events.jsonl")
        rows = emit([event("critical")], notifiers=[broken], settings=Settings())
        _require(len(rows) == 1 and rows[0]["ok"] is False,
                 tr("send() must raise when it cannot write (do not swallow errors); "
                    "the dispatcher records the failure",
                    "기록할 수 없으면 send()가 예외를 내야 합니다(오류를 삼키지 마세요). "
                    "실패 기록은 디스패처가 합니다"))

    _run(results, tr("module defines FileNotifier and SPEC", "FileNotifier와 SPEC 정의"), imports)
    if not results[-1].ok:
        return results
    _run(results, tr("SPEC describes a notifier named 'file'", "SPEC: 이름 'file', 종류 notifier"), spec)
    _run(results, tr("send() appends one JSON line per event", "send()가 이벤트마다 JSON 한 줄 추가"),
         writes_json_lines)
    _run(results, tr("min_severity filters and is validated", "min_severity 필터와 값 검사"),
         severity_filter)
    _run(results, tr("factory reads MA_PMO_NOTIFY_FILE", "factory가 MA_PMO_NOTIFY_FILE을 읽음"),
         from_settings)
    _run(results, tr("a failing notifier cannot break dispatch", "실패한 알림이 전체를 멈추지 않음"),
         failure_isolated)
    return results


# ── Lab 2: repair a dataset ────────────────────────────────────────────────────────

LAB2_TASKS = {"T-101", "T-102", "T-103", "T-201", "T-202",
              "T-301", "T-302", "T-303", "T-401", "T-402"}


def check_lab2(workdir: Path) -> list[Result]:
    from ma_pmo.eval.dataset import load_dataset

    results: list[Result] = []
    data = workdir / "data"
    state: dict[str, Any] = {}

    def no_errors() -> None:
        _require(data.is_dir(), tr(f"{data} not found", f"{data} 폴더가 없습니다"))
        ds, issues = load_dataset(data)
        state["ds"] = ds
        errors = [str(i) for i in issues if i.level == "error"]
        _require(not errors, tr(f"{len(errors)} error(s) left — run `ma-pmo template validate "
                                f"{data}`: " + "; ".join(errors[:3]),
                                f"오류 {len(errors)}건 남음 — `ma-pmo template validate {data}`로 "
                                f"확인하세요: " + "; ".join(errors[:3])))

    def nothing_deleted() -> None:
        ds = state["ds"]
        tasks = {t["id"] for p in ds.projects for t in p["tasks"]}
        _require(len(ds.projects) == 4, tr("keep all 4 projects", "프로젝트 4개를 모두 유지하세요"))
        _require(tasks == LAB2_TASKS,
                 tr(f"fix rows instead of deleting them; expected tasks {sorted(LAB2_TASKS)}",
                    f"행을 지우지 말고 고치세요. 기대 태스크: {sorted(LAB2_TASKS)}"))
        _require(len(ds.resources) == 4, tr("keep all 4 resources", "자원 4개를 모두 유지하세요"))

    def labels_complete() -> None:
        ds = state["ds"]
        missing = {p["id"] for p in ds.projects} - set(ds.labels)
        _require(not missing, tr(f"every project needs a risk label; missing {sorted(missing)}",
                                 f"모든 프로젝트에 리스크 레이블이 필요합니다. 누락: {sorted(missing)}"))
        _require(ds.labels.get("ACME-3") == "high",
                 tr("ACME-3 was labeled 'severe' — the closest allowed severity is 'high'",
                    "ACME-3의 'severe'에 가장 가까운 허용 값은 'high'입니다"))

    def plausible_values() -> None:
        ds = state["ds"]
        by_id = {t["id"]: t for p in ds.projects for t in p["tasks"]}
        _require(by_id["T-201"]["deps"] == [],
                 tr("T-201 is the first task of ACME-2: it should not depend on T-202",
                    "T-201은 ACME-2의 첫 태스크이므로 T-202에 의존하면 안 됩니다"))
        _require(by_id["T-303"]["deps"] == ["T-302"],
                 tr("T-303 follows T-302 (T-320 is a typo)", "T-303은 T-302 다음입니다 (T-320은 오타)"))
        _require(by_id["T-103"]["deps"] == ["T-102"],
                 tr("the second T-102 row is T-103 and depends on T-102",
                    "두 번째 T-102 행은 T-103이며 T-102에 의존합니다"))

    _run(results, tr("validation passes with no errors", "검사 오류 0건"), no_errors)
    if not results[-1].ok:
        return results
    _run(results, tr("no project, task or resource was deleted", "프로젝트·태스크·자원 삭제 없음"),
         nothing_deleted)
    _run(results, tr("every project has a valid risk label", "모든 프로젝트에 올바른 레이블"),
         labels_complete)
    _run(results, tr("dependencies were repaired, not removed", "의존 관계를 지우지 않고 고침"),
         plausible_values)
    return results


# ── Lab 3: ablation experiment ─────────────────────────────────────────────────────

def check_lab3(workdir: Path) -> list[Result]:
    from ma_pmo.core.scenarios import SCENARIOS
    from ma_pmo.harness.experiments import load_experiment_file

    results: list[Result] = []
    state: dict[str, Any] = {}
    path = workdir / "experiments" / "h4_knowledge.py"

    def loads() -> None:
        _require(path.is_file(), tr(f"{path} not found", f"{path} 파일이 없습니다"))
        state["spec"] = load_experiment_file(path).build()
        _require(state["spec"].name == "h4_knowledge",
                 tr("keep the experiment name 'h4_knowledge'", "실험 이름은 'h4_knowledge'로 두세요"))

    def described() -> None:
        _require(state["spec"].description and "TODO" not in state["spec"].description,
                 tr("write a one-sentence description", "설명을 한 문장으로 써 주세요"))

    def ablates_a7() -> None:
        _require(state["spec"].ablate_agents == ["A7"],
                 tr("H4 is about the knowledge agent: .ablate('A7')",
                    "H4는 지식 에이전트에 관한 가설입니다: .ablate('A7')"))

    def scenarios_use_a7() -> None:
        ids = state["spec"].scenarios
        _require(2 <= len(ids) <= 5, tr("choose 2 to 5 scenarios (an empty list means all 20)",
                                        "시나리오를 2~5개 고르세요 (빈 목록은 20개 전체)"))
        unknown = [s for s in ids if s not in SCENARIOS]
        _require(not unknown, tr(f"unknown scenario ids: {unknown}", f"없는 시나리오: {unknown}"))
        unused = [s for s in ids if "A7" not in {a for a, _ in SCENARIOS[s]["steps"]}]
        _require(not unused, tr(f"{unused} never call A7, so removing A7 there measures nothing",
                                f"{unused}는 A7을 쓰지 않아서 A7을 빼도 아무것도 측정되지 않습니다"))

    def repeat_small() -> None:
        _require(1 <= state["spec"].repeat <= 3,
                 tr("offline runs are deterministic: repeat 1–3 is enough",
                    "오프라인 실행은 결정론적이므로 반복 1~3회면 충분합니다"))

    def shows_effect() -> None:
        from ma_pmo.harness.runner import run_experiment

        rows = run_experiment(state["spec"]).get("ablation", {}).get("A7", [])
        delta = sum(r["delta_findings"] for r in rows)
        _require(rows and delta > 0,
                 tr("the ablation should show fewer findings without A7",
                    "A7을 뺐을 때 발견 사항이 줄어드는 결과가 나와야 합니다"))

    _run(results, tr("experiment file loads", "실험 파일 로드"), loads)
    if not results[-1].ok:
        return results
    _run(results, tr("says what it measures", "무엇을 측정하는지 설명"), described)
    _run(results, tr("removes the knowledge agent (A7)", "지식 에이전트(A7) 제거"), ablates_a7)
    _run(results, tr("every scenario actually uses A7", "모든 시나리오가 A7을 사용"), scenarios_use_a7)
    _run(results, tr("repeat count fits a deterministic run", "반복 횟수 적절"), repeat_small)
    if all(r.ok for r in results):
        _run(results, tr("experiment runs and shows A7's effect", "실험 실행 및 A7 효과 확인"),
             shows_effect)
    return results


# ── Lab 4: custom tracker ──────────────────────────────────────────────────────────

def check_lab4(workdir: Path) -> list[Result]:
    from ma_pmo.agents.cpm import compute_cpm

    results: list[Result] = []
    state: dict[str, Any] = {}
    scope = "PORTFOLIO#2026-Q1"

    def imports() -> None:
        state["m"] = _load_module(workdir / "csv_tracker.py")
        state["t"] = state["m"].CsvTracker(workdir / "data")

    def spec() -> None:
        _require(state["m"].SPEC.kind == "tracker",
                 tr("agents read data from it: SPEC.kind = 'tracker'",
                    "에이전트가 데이터를 읽어 오는 연동이므로 SPEC.kind = 'tracker'"))

    def unknown_portfolio() -> None:
        got = state["t"].get_portfolio_status("PORTFOLIO#NOPE")
        _require(got == {"portfolio_id": "PORTFOLIO#NOPE", "found": False, "projects": []},
                 tr("an unknown portfolio returns found=False and no projects",
                    "없는 포트폴리오는 found=False, projects=[]를 돌려줘야 합니다"))

    def shape() -> None:
        got = state["t"].get_portfolio_status(scope)
        state["status"] = got
        _require(got.get("found") is True and got.get("name"),
                 tr("found=True with the portfolio name", "found=True와 포트폴리오 이름이 필요합니다"))
        projects = {p["project_id"]: p for p in got.get("projects", [])}
        _require(set(projects) == {"PROJ-14", "PROJ-22", "PROJ-31"},
                 tr("expected projects PROJ-14, PROJ-22, PROJ-31", "프로젝트 3개가 나와야 합니다"))
        t = projects["PROJ-14"]["tasks"][1]
        _require(isinstance(t["effort"], float) and isinstance(t["percent_complete"], float),
                 tr("effort and percent_complete must be numbers (float)",
                    "effort와 percent_complete는 숫자(float)여야 합니다"))
        _require(t["deps"] == ["T-1401"] and projects["PROJ-14"]["tasks"][0]["deps"] == [],
                 tr("deps is a list of task ids ([] when empty)",
                    "deps는 태스크 id 목록이어야 합니다 (없으면 [])"))
        state["projects"] = projects

    def weighted_progress() -> None:
        p = state["projects"]["PROJ-14"]["percent_complete"]
        _require(p == 54.0, tr(f"PROJ-14 progress weighted by effort is 54.0, got {p}",
                               f"PROJ-14의 공수 가중 진척률은 54.0이어야 하는데 {p}입니다"))

    def agents_can_plan() -> None:
        cpm = compute_cpm(state["projects"]["PROJ-14"]["tasks"])
        _require(cpm.critical_path == ["T-1401", "T-1402", "T-1403"],
                 tr(f"A2's CPM should find T-1401 → T-1402 → T-1403, got {cpm.critical_path}",
                    f"A2의 CPM 결과가 T-1401 → T-1402 → T-1403이어야 하는데 {cpm.critical_path}"))

    _run(results, tr("module defines CsvTracker and SPEC", "CsvTracker와 SPEC 정의"), imports)
    if not results[-1].ok:
        return results
    _run(results, tr("SPEC describes a tracker", "SPEC 종류가 tracker"), spec)
    _run(results, tr("unknown portfolio is reported, not crashed", "없는 포트폴리오 처리"),
         unknown_portfolio)
    _run(results, tr("returns the shape agents expect", "에이전트가 기대하는 형태로 반환"), shape)
    if results[-1].ok:
        _run(results, tr("progress is weighted by effort", "진척률을 공수로 가중"), weighted_progress)
        _run(results, tr("the planning agent (A2) can schedule it", "계획 에이전트(A2)가 일정 계산 가능"),
             agents_can_plan)
    return results


CHECKS: dict[int, Callable[[Path], list[Result]]] = {
    1: check_lab1, 2: check_lab2, 3: check_lab3, 4: check_lab4,
}


def run_checks(number: int, workdir: str | Path) -> list[Result]:
    return CHECKS[number](Path(workdir))
