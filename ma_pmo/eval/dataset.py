"""Evaluation data template — run H1–H5 on your organization's own data.

    ma-pmo template data ./my-org        # write fill-in CSV/JSON files (with example rows)
    ma-pmo template validate ./my-org    # check them, line by line
    ma-pmo eval --data ./my-org          # load into an isolated DB and run H1–H5

Files (CSV so they open in any spreadsheet; UTF-8):

| file                | one row per          | columns                                                   |
|---------------------|----------------------|-----------------------------------------------------------|
| portfolio.csv       | the portfolio (1 row)| id, name, period                                          |
| projects.csv        | project              | id, skill, planned_start, planned_finish, deadline, status|
| tasks.csv           | task                 | id, project_id, wbs, effort_hours, deps, percent_complete |
| resources.csv       | person / team        | id, skill, capacity_hours_per_week                        |
| risk_labels.csv     | project              | project_id, actual_severity                               |
| baselines.json      | —                    | manual report time, target utilization, ...               |
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ma_pmo.agents.gates import _has_cycle

COLUMNS: dict[str, list[str]] = {
    "portfolio.csv": ["id", "name", "period"],
    "projects.csv": ["id", "skill", "planned_start", "planned_finish", "deadline", "status"],
    "tasks.csv": ["id", "project_id", "wbs", "effort_hours", "deps", "percent_complete"],
    "resources.csv": ["id", "skill", "capacity_hours_per_week"],
    "risk_labels.csv": ["project_id", "actual_severity"],
}
BASELINE_KEYS = {
    "manual_report_cycle_time_sec": "seconds a person needs to produce one status report",
    "target_utilization_pct": "resource utilization the PMO aims for (%)",
    "manual_risk_lead_time_days": "days of warning a manual process gives before risks hit",
    "manual_estimation_error_pct": "typical estimation error without lessons learned (%)",
}
STATUSES = {"green", "amber", "red"}
SEVERITIES = {"none", "low", "medium", "high", "critical"}

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

README = """# MA-PMO evaluation data / 평가 데이터 입력 양식

Fill in these files with your organization's data, then:
아래 파일에 우리 조직의 데이터를 채운 뒤 실행하세요.

```bash
ma-pmo template validate .     # check / 검사
ma-pmo eval --data .           # run H1–H5 / 평가 실행
ma-pmo template report --data . --format html --out report.html   # report / 보고서
```

| File / 파일 | One row per / 한 줄에 | Notes / 설명 |
|---|---|---|
| portfolio.csv | portfolio (1 row) / 포트폴리오(1줄) | `id` is the scope name, e.g. `PORTFOLIO#2027-Q1` |
| projects.csv | project / 프로젝트 | dates `YYYY-MM-DD`; status `green`/`amber`/`red` |
| tasks.csv | task / 태스크 | `effort_hours` = planned hours; `deps` = task ids separated by `;`; `percent_complete` 0–100 |
| resources.csv | person or team / 사람·팀 | `skill` must match project skills; weekly capacity in hours |
| risk_labels.csv | project / 프로젝트 | what **actually** happened: `none`/`low`/`medium`/`high`/`critical` (H3 ground truth) |
| baselines.json | — | manual-process numbers to compare against (H1, H2) |

Example rows come from the bundled demo portfolio; replace or delete them.
예시 행은 데모 포트폴리오입니다. 지우고 실제 값으로 바꿔 주세요.
Open the CSV files in Excel / Google Sheets and save as **CSV UTF-8**.
엑셀·구글 시트로 열어 편집한 뒤 **CSV UTF-8** 형식으로 저장하세요.
"""


# ── generate ─────────────────────────────────────────────────────
def _example_rows() -> dict[str, list[list[str]]]:
    demo = json.loads((_FIXTURES / "sample_portfolio.json").read_text(encoding="utf-8"))
    labels = json.loads((_FIXTURES / "risk_ground_truth.json").read_text(encoding="utf-8"))
    p = demo["portfolio"]
    rows: dict[str, list[list[str]]] = {
        "portfolio.csv": [[p["id"], p["name"], p["period"]]],
        "projects.csv": [],
        "tasks.csv": [],
        "resources.csv": [[r["id"], r["skill"], str(r["capacity"])] for r in demo["resources"]],
        "risk_labels.csv": [[pid, sev] for pid, sev in labels["labels"].items()],
    }
    for proj in demo["projects"]:
        rows["projects.csv"].append([proj["id"], proj["skill"], proj["planned_start"],
                                     proj["planned_finish"], proj["deadline"], proj["status"]])
        for t in proj["tasks"]:
            rows["tasks.csv"].append([t["id"], proj["id"], t["wbs"], str(t["effort"]),
                                      ";".join(t["deps"]), str(t["percent_complete"])])
    return rows


def generate_data_template(out_dir: str | Path, *, examples: bool = True,
                           overwrite: bool = False) -> list[Path]:
    """Write the template files. Refuses to overwrite existing files unless asked."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    targets = [*COLUMNS, "baselines.json", "README.md"]
    existing = [n for n in targets if (out / n).exists()]
    if existing and not overwrite:
        raise FileExistsError(f"already exists: {', '.join(existing)} (use --force)")

    rows = _example_rows() if examples else {name: [] for name in COLUMNS}
    written = []
    for name, cols in COLUMNS.items():
        path = out / name
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows[name])
        written.append(path)

    demo_base = json.loads((_FIXTURES / "baselines.json").read_text(encoding="utf-8"))
    baselines = {
        "_help": {k: v for k, v in BASELINE_KEYS.items()},
        **{k: (demo_base.get(k) if examples else None) for k in BASELINE_KEYS},
    }
    (out / "baselines.json").write_text(json.dumps(baselines, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    (out / "README.md").write_text(README, encoding="utf-8")
    written += [out / "baselines.json", out / "README.md"]
    return written


# ── load + validate ──────────────────────────────────────────────
@dataclass
class Issue:
    level: str  # "error" | "warning"
    file: str
    line: int | None
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"[{self.level}] {where} — {self.message}"


@dataclass
class Dataset:
    portfolio: dict = field(default_factory=dict)
    projects: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    baselines: dict = field(default_factory=dict)

    @property
    def scope(self) -> str:
        return str(self.portfolio.get("id", ""))


def _read_csv(path: Path, issues: list[Issue]) -> list[tuple[int, dict[str, str]]]:
    name = path.name
    if not path.exists():
        issues.append(Issue("error", name, None, "file is missing"))
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in COLUMNS[name] if c not in header]
        if missing:
            issues.append(Issue("error", name, 1, f"missing columns: {', '.join(missing)}"))
            return []
        rows = []
        for i, raw in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
            if any(row.values()):
                rows.append((i, row))
        return rows


def _date(value: str, file: str, line: int, col: str, issues: list[Issue],
          required: bool = True) -> str | None:
    if not value:
        if required:
            issues.append(Issue("error", file, line, f"{col} is empty"))
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        issues.append(Issue("error", file, line, f"{col} '{value}' is not YYYY-MM-DD"))
        return None
    return value


def _number(value: str, file: str, line: int, col: str, issues: list[Issue],
            lo: float = 0, hi: float | None = None) -> float | None:
    try:
        n = float(value)
    except ValueError:
        issues.append(Issue("error", file, line, f"{col} '{value}' is not a number"))
        return None
    if n < lo or (hi is not None and n > hi):
        rng = f"{lo}–{hi}" if hi is not None else f"≥ {lo}"
        issues.append(Issue("error", file, line, f"{col} {value} is out of range ({rng})"))
        return None
    return n


def load_dataset(data_dir: str | Path) -> tuple[Dataset, list[Issue]]:
    """Parse and check a data folder. Returns the dataset and all problems found."""
    d = Path(data_dir)
    issues: list[Issue] = []
    ds = Dataset()

    port = _read_csv(d / "portfolio.csv", issues)
    if len(port) != 1 and (d / "portfolio.csv").exists():
        issues.append(Issue("error", "portfolio.csv", None,
                            f"needs exactly 1 row, found {len(port)}"))
    if port:
        line, row = port[0]
        if not row["id"]:
            issues.append(Issue("error", "portfolio.csv", line, "id is empty"))
        ds.portfolio = {"id": row["id"], "name": row["name"] or row["id"],
                        "period": row["period"]}

    projects: dict[str, dict] = {}
    for line, row in _read_csv(d / "projects.csv", issues):
        pid = row["id"]
        if not pid:
            issues.append(Issue("error", "projects.csv", line, "id is empty"))
            continue
        if pid in projects:
            issues.append(Issue("error", "projects.csv", line, f"duplicate project id {pid}"))
            continue
        start = _date(row["planned_start"], "projects.csv", line, "planned_start", issues)
        finish = _date(row["planned_finish"], "projects.csv", line, "planned_finish", issues)
        deadline = _date(row["deadline"], "projects.csv", line, "deadline", issues)
        if start and finish and finish < start:
            issues.append(Issue("error", "projects.csv", line,
                                "planned_finish is before planned_start"))
        status = row["status"].lower() or "green"
        if status not in STATUSES:
            issues.append(Issue("error", "projects.csv", line,
                                f"status '{row['status']}' must be green/amber/red"))
        projects[pid] = {"id": pid, "skill": row["skill"], "planned_start": start,
                         "planned_finish": finish, "deadline": deadline, "status": status,
                         "tasks": []}

    task_ids: dict[str, str] = {}
    task_lines: dict[str, int] = {}
    for line, row in _read_csv(d / "tasks.csv", issues):
        tid, pid = row["id"], row["project_id"]
        if not tid:
            issues.append(Issue("error", "tasks.csv", line, "id is empty"))
            continue
        if tid in task_ids:
            issues.append(Issue("error", "tasks.csv", line, f"duplicate task id {tid}"))
            continue
        if pid not in projects:
            issues.append(Issue("error", "tasks.csv", line,
                                f"project_id '{pid}' is not in projects.csv"))
            continue
        effort = _number(row["effort_hours"], "tasks.csv", line, "effort_hours", issues)
        pct = _number(row["percent_complete"] or "0", "tasks.csv", line, "percent_complete",
                      issues, 0, 100)
        deps = [x.strip() for x in row["deps"].replace(",", ";").split(";") if x.strip()]
        task_ids[tid] = pid
        task_lines[tid] = line
        projects[pid]["tasks"].append({"id": tid, "wbs": row["wbs"] or tid,
                                       "effort": effort or 0.0, "deps": deps,
                                       "percent_complete": pct or 0.0})

    for pid, proj in projects.items():
        for t in proj["tasks"]:
            for dep in t["deps"]:
                if dep not in task_ids:
                    issues.append(Issue("error", "tasks.csv", task_lines[t["id"]],
                                        f"dep '{dep}' of {t['id']} is not a task id"))
                elif task_ids[dep] != pid:
                    issues.append(Issue("warning", "tasks.csv", task_lines[t["id"]],
                                        f"dep '{dep}' belongs to another project"))
        if not proj["tasks"]:
            issues.append(Issue("warning", "tasks.csv", None, f"project {pid} has no tasks"))
        elif _has_cycle([{"task_id": t["id"], "wbs": t["wbs"], "effort": t["effort"],
                          "deps": [x for x in t["deps"] if task_ids.get(x) == pid]}
                         for t in proj["tasks"]]):
            issues.append(Issue("error", "tasks.csv", None,
                                f"project {pid} has a dependency cycle"))
    ds.projects = list(projects.values())

    seen_res: set[str] = set()
    for line, row in _read_csv(d / "resources.csv", issues):
        rid = row["id"]
        if not rid or rid in seen_res:
            issues.append(Issue("error", "resources.csv", line,
                                "id is empty" if not rid else f"duplicate resource id {rid}"))
            continue
        cap = _number(row["capacity_hours_per_week"], "resources.csv", line,
                      "capacity_hours_per_week", issues, 0, 168)
        seen_res.add(rid)
        ds.resources.append({"id": rid, "skill": row["skill"], "capacity": cap or 0.0})
    skills = {r["skill"] for r in ds.resources}
    for p in ds.projects:
        if p["skill"] and p["skill"] not in skills:
            issues.append(Issue("warning", "resources.csv", None,
                                f"no resource has skill '{p['skill']}' (project {p['id']})"))

    for line, row in _read_csv(d / "risk_labels.csv", issues):
        pid, sev = row["project_id"], row["actual_severity"].lower()
        if pid not in projects:
            issues.append(Issue("error", "risk_labels.csv", line,
                                f"project_id '{pid}' is not in projects.csv"))
        elif sev not in SEVERITIES:
            issues.append(Issue("error", "risk_labels.csv", line,
                                f"actual_severity '{row['actual_severity']}' must be one of "
                                f"{'/'.join(sorted(SEVERITIES))}"))
        else:
            ds.labels[pid] = "low" if sev == "none" else sev
    unlabeled = sorted(set(projects) - set(ds.labels))
    if unlabeled:
        issues.append(Issue("warning", "risk_labels.csv", None,
                            f"no label for {', '.join(unlabeled)} — counted as low for H3"))

    bpath = d / "baselines.json"
    if not bpath.exists():
        issues.append(Issue("error", "baselines.json", None, "file is missing"))
    else:
        try:
            raw = json.loads(bpath.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            issues.append(Issue("error", "baselines.json", e.lineno, f"invalid JSON: {e.msg}"))
            raw = {}
        for key in BASELINE_KEYS:
            value = raw.get(key)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                issues.append(Issue("error", "baselines.json", None,
                                    f"{key} must be a number ≥ 0 ({BASELINE_KEYS[key]})"))
            else:
                ds.baselines[key] = value
    return ds, issues


def import_dataset(ds: Dataset) -> None:
    """Write a validated dataset into the current database (merge by id)."""
    from ma_pmo.db.models import Portfolio, Project, Resource, Task
    from ma_pmo.db.session import create_all, get_session

    create_all()
    with get_session() as s:
        p = ds.portfolio
        s.merge(Portfolio(id=p["id"], name=p["name"], period=p["period"]))
        for r in ds.resources:
            s.merge(Resource(id=r["id"], skill=r["skill"], capacity=r["capacity"]))
        for proj in ds.projects:
            s.merge(Project(id=proj["id"], portfolio_id=p["id"], skill=proj["skill"],
                            planned_start=proj["planned_start"],
                            planned_finish=proj["planned_finish"], deadline=proj["deadline"],
                            status=proj["status"]))
            for t in proj["tasks"]:
                s.merge(Task(id=t["id"], project_id=proj["id"], wbs=t["wbs"],
                             effort=t["effort"], deps=t["deps"],
                             percent_complete=t["percent_complete"]))
