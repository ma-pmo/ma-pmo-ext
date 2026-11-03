"""Evaluation template generator: data template, validation, dataset evaluation, report,
experiment scaffold, and their CLI/API entry points."""
from __future__ import annotations

import csv
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from ma_pmo.api.main import app
from ma_pmo.cli import main as cli
from ma_pmo.core.i18n import use_lang
from ma_pmo.eval.dataset import COLUMNS, generate_data_template, import_dataset, load_dataset
from ma_pmo.eval.harness import run_all
from ma_pmo.eval.report import build_report, render, summarize
from ma_pmo.harness import run_experiment
from ma_pmo.harness.experiments import discover, load_experiment_file
from ma_pmo.harness.scaffold import new_experiment, scenarios_for

client = TestClient(app)


def _rewrite(path, transform):
    rows = list(csv.reader(path.open(encoding="utf-8")))
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(transform(rows))


# ── data template ────────────────────────────────────────────────
@pytest.mark.smoke
def test_generated_template_is_valid(tmp_path):
    paths = generate_data_template(tmp_path)
    assert {p.name for p in paths} == {*COLUMNS, "baselines.json", "README.md"}
    ds, issues = load_dataset(tmp_path)
    assert issues == []
    assert ds.scope == "PORTFOLIO#2026-Q1"
    assert len(ds.projects) == 3 and sum(len(p["tasks"]) for p in ds.projects) == 7


def test_template_refuses_to_overwrite(tmp_path):
    generate_data_template(tmp_path)
    with pytest.raises(FileExistsError):
        generate_data_template(tmp_path)
    generate_data_template(tmp_path, overwrite=True)


def test_empty_template_reports_what_is_missing(tmp_path):
    generate_data_template(tmp_path, examples=False)
    _, issues = load_dataset(tmp_path)
    messages = [str(i) for i in issues]
    assert any("portfolio.csv" in m and "exactly 1 row" in m for m in messages)
    assert any("baselines.json" in m and "manual_report_cycle_time_sec" in m for m in messages)


@pytest.mark.regression
def test_validation_points_to_file_and_line(tmp_path):
    generate_data_template(tmp_path)

    def break_tasks(rows):
        rows[2][3] = "abc"        # effort_hours of T-1402 (line 3)
        rows[2][4] = "T-9999"     # unknown dependency
        rows[2][5] = "160"        # percent out of range
        return rows

    _rewrite(tmp_path / "tasks.csv", break_tasks)
    _rewrite(tmp_path / "projects.csv", lambda r: [r[0], [*r[1][:3], "2026-13-40", *r[1][4:]],
                                                   *r[2:]])
    _rewrite(tmp_path / "risk_labels.csv", lambda r: [r[0], r[1], [r[2][0], "unknown"], *r[3:]])
    _, issues = load_dataset(tmp_path)
    errors = {(i.file, i.line, i.message.split(" ")[0]) for i in issues if i.level == "error"}
    assert ("tasks.csv", 3, "effort_hours") in errors
    assert ("tasks.csv", 3, "percent_complete") in errors
    assert ("tasks.csv", 3, "dep") in errors
    assert ("projects.csv", 2, "planned_finish") in errors
    assert ("risk_labels.csv", 3, "actual_severity") in errors


def test_dependency_cycle_is_an_error(tmp_path):
    generate_data_template(tmp_path)
    _rewrite(tmp_path / "tasks.csv",
             lambda r: [r[0], [*r[1][:4], "T-1403", r[1][5]], *r[2:]])  # T-1401 needs T-1403
    _, issues = load_dataset(tmp_path)
    assert any("dependency cycle" in i.message for i in issues)


@pytest.mark.smoke
def test_dataset_import_and_evaluation_use_its_labels(tmp_path):
    generate_data_template(tmp_path)
    (tmp_path / "portfolio.csv").write_text("id,name,period\nPORTFOLIO#TEST-DS,Test DS,2027\n",
                                            encoding="utf-8")
    _rewrite(tmp_path / "projects.csv",
             lambda r: [r[0]] + [[f"DS-{x[0]}", *x[1:]] for x in r[1:]])
    _rewrite(tmp_path / "tasks.csv",
             lambda r: [r[0]] + [[f"DS-{x[0]}", f"DS-{x[1]}", x[2], x[3],
                                  ";".join(f"DS-{d}" for d in x[4].split(";") if d), x[5]]
                                 for x in r[1:]])
    # say PROJ-22 actually went badly: the rule-based detector called it low -> one miss
    _rewrite(tmp_path / "risk_labels.csv",
             lambda r: [r[0]] + [[f"DS-{x[0]}", "high" if x[0] == "PROJ-22" else x[1]]
                                 for x in r[1:]])
    ds, issues = load_dataset(tmp_path)
    assert not [i for i in issues if i.level == "error"]
    import_dataset(ds)
    results = run_all(scope=ds.scope, baselines=ds.baselines, labels=ds.labels)
    assert results["H3"]["recall"] == pytest.approx(0.667, abs=1e-3)
    assert {d["project_id"] for d in results["H3"]["detail"]} == {
        "DS-PROJ-14", "DS-PROJ-22", "DS-PROJ-31"}


# ── report ───────────────────────────────────────────────────────
@pytest.mark.regression
def test_verdicts_on_demo_results():
    verdicts = {r["id"]: r["verdict"] for r in summarize(run_all())}
    assert verdicts["H2"] == "partial"     # 45.1% utilization vs. 80% target
    assert verdicts["H3"] == "supported"   # F1 = 1.0 on the fixtures
    assert verdicts["H4"] == "supported"


@pytest.mark.smoke
@pytest.mark.parametrize("fmt", ["md", "html"])
def test_report_renders_in_both_languages(fmt):
    results = run_all(populate=False)
    en = render(build_report(results, scope="S", source="demo"), fmt)
    with use_lang("ko"):
        ko = render(build_report(results, scope="S", source="demo"), fmt)
    assert "MA-PMO evaluation report" in en and "MA-PMO 평가 보고서" in ko
    for h in ("H1", "H2", "H3", "H4", "H5"):
        assert h in en
    if fmt == "html":
        assert en.lstrip().startswith("<!doctype html>") and "</html>" in en
    with pytest.raises(ValueError):
        render(build_report(results, scope="S", source="demo"), "pdf")


# ── experiment scaffold ──────────────────────────────────────────
@pytest.mark.smoke
def test_scaffolded_experiment_is_discovered_and_runs(tmp_path):
    exp_dir, test_dir = tmp_path / "experiments", tmp_path / "tests"
    paths = new_experiment("kickoff_check", scenarios=["knowledge_kickoff"], ablate=["A7"],
                           directory=exp_dir, tests_dir=test_dir)
    assert [p.name for p in paths] == ["kickoff_check.py", "test_kickoff_check.py"]
    assert "kickoff_check" in discover(exp_dir)
    spec = load_experiment_file(exp_dir / "kickoff_check.py").build()
    assert spec.scenarios == ["knowledge_kickoff"] and spec.ablate_agents == ["A7"]
    result = run_experiment(load_experiment_file(exp_dir / "kickoff_check.py"))
    assert result["runs"] and "A7" in result["ablation"]
    # the generated test points at the experiment file through a relative path
    assert "parent.parent / 'experiments'" in (test_dir / "test_kickoff_check.py").read_text()


def test_scaffold_by_hypothesis_uses_matching_scenarios(tmp_path):
    new_experiment("h4_only", hypothesis="H4", directory=tmp_path, with_test=False)
    spec = load_experiment_file(tmp_path / "h4_only.py").build()
    assert spec.scenarios == scenarios_for("H4") and spec.scenarios


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "Bad-Name", "hypothesis": "H3"}, "invalid experiment name"),
        ({"name": "list", "hypothesis": "H3"}, "invalid experiment name"),
        ({"name": "ok_name", "scenarios": ["nope"]}, "unknown scenarios"),
        ({"name": "ok_name", "hypothesis": "H9"}, "hypothesis must be"),
        ({"name": "ok_name", "hypothesis": "H3", "ablate": ["A1"]}, "can only ablate"),
        ({"name": "ok_name", "scenarios": ["weekly_status"], "ablate": ["A7"]}, "changes nothing"),
        ({"name": "ok_name"}, "give --scenarios or --hypothesis"),
    ],
)
def test_scaffold_rejects_bad_input(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        new_experiment(directory=tmp_path, **kwargs)


def test_scaffold_refuses_existing_names(tmp_path):
    new_experiment("dup", hypothesis="H1", directory=tmp_path, with_test=False)
    with pytest.raises(FileExistsError):
        new_experiment("dup", hypothesis="H1", directory=tmp_path, with_test=False)
    with pytest.raises(FileExistsError):  # clashes with a built-in experiment
        new_experiment("full_suite", hypothesis="H1", directory=tmp_path, with_test=False)


# ── CLI + API ────────────────────────────────────────────────────
@pytest.mark.smoke
def test_cli_template_flow(tmp_path, capsys):
    folder = tmp_path / "org"
    assert cli(["template", "data", str(folder)]) == 0
    assert cli(["template", "validate", str(folder)]) == 0
    (folder / "baselines.json").write_text("{}", encoding="utf-8")
    assert cli(["template", "validate", str(folder)]) == 1
    assert "baselines.json" in capsys.readouterr().out


@pytest.mark.smoke
def test_api_eval_report_and_templates():
    assert client.get("/eval/report?format=html").text.lstrip().startswith("<!doctype html>")
    md = client.get("/eval/report?format=md")
    assert md.status_code == 200 and md.text.startswith("# MA-PMO evaluation report")
    assert client.get("/eval/report?format=pdf").status_code == 400
    assert len(client.get("/eval").json()["summary"]) == 5

    resp = client.get("/templates/data.zip")
    assert resp.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert "ma-pmo-eval-data/tasks.csv" in names and "ma-pmo-eval-data/README.md" in names

    ok = client.post("/templates/validate", content=resp.content).json()
    assert ok["valid"] is True and ok["counts"]["tasks"] == 7


@pytest.mark.regression
def test_api_validate_rejects_bad_uploads():
    assert client.post("/templates/validate", content=b"").status_code == 400
    assert client.post("/templates/validate", content=b"not a zip").status_code == 400
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil/portfolio.csv", "id,name,period\nP,P,2027\n")
        zf.writestr("baselines.json", json.dumps({"target_utilization_pct": "high"}))
    body = client.post("/templates/validate", content=buf.getvalue()).json()
    assert body["valid"] is False
    assert any(i["file"] == "baselines.json" for i in body["issues"])
