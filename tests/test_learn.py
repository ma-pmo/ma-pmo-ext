"""Course labs: every reference solution passes its checks and every untouched starter fails.

Labs without a database are checked in-process. Labs that run agents (3, 5) are checked through
the CLI in a subprocess with their own SQLite file, keeping the shared test database untouched.
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ma_pmo.learn import LABS
from ma_pmo.learn.checks import run_checks
from ma_pmo.learn.cli import main as learn_main

ROOT = Path(__file__).resolve().parents[1]
IN_PROCESS = [n for n, lab in LABS.items() if not lab.needs_db]
THROUGH_CLI = [
    pytest.param(n, marks=pytest.mark.skipif(
        bool(lab.needs_extra) and importlib.util.find_spec(lab.needs_extra) is None,
        reason=f"needs the {lab.needs_extra} extra"))
    for n, lab in LABS.items() if lab.needs_db
]


def _cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("DB_URL", "CHECKPOINT_DB")}
    env["PYTHONPATH"] = str(ROOT)
    env["MA_PMO_LANG"] = "en"
    return subprocess.run([sys.executable, "-m", "ma_pmo.cli", "learn", *args], cwd=cwd,
                          env=env, capture_output=True, text=True, timeout=300)


@pytest.mark.smoke
def test_list_and_start(tmp_path, capsys):
    assert learn_main(["list"]) == 0
    assert learn_main(["scenarios"]) == 0
    assert learn_main(["start", "1", "--dir", str(tmp_path)]) == 0
    lab = tmp_path / "lab1"
    assert {"file_notifier.py", "README.md", "README.ko.md"} <= {p.name for p in lab.iterdir()}
    # a second start must not overwrite the learner's work
    assert learn_main(["start", "1", "--dir", str(tmp_path)]) == 1
    assert learn_main(["start", "1", "--dir", str(tmp_path), "--force"]) == 0
    assert learn_main(["start", "9"]) == 2


@pytest.mark.parametrize("number", IN_PROCESS)
def test_solution_passes(number):
    results = run_checks(number, LABS[number].solution)
    assert results and all(r.ok for r in results), [(r.name, r.hint) for r in results if not r.ok]


@pytest.mark.parametrize("number", IN_PROCESS)
def test_starter_fails(number, tmp_path):
    assert learn_main(["start", str(number), "--dir", str(tmp_path)]) == 0
    results = run_checks(number, tmp_path / f"lab{number}")
    assert not all(r.ok for r in results)
    assert all(r.hint for r in results if not r.ok), "every failed check needs a hint"
    assert learn_main(["check", str(number), "--dir", str(tmp_path)]) == 1


@pytest.mark.parametrize("number", THROUGH_CLI)
def test_db_labs_through_cli(number, tmp_path):
    ok = _cli("check", str(number), "--solution", "--dir", str(tmp_path), cwd=tmp_path)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "lab complete" in ok.stdout
    assert _cli("start", str(number), "--dir", str(tmp_path), cwd=tmp_path).returncode == 0
    bad = _cli("check", str(number), "--dir", str(tmp_path), cwd=tmp_path)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert "→" in bad.stdout  # failed checks come with hints


def test_lab2_starter_has_the_seven_documented_errors():
    from ma_pmo.eval.dataset import load_dataset

    _, issues = load_dataset(LABS[2].starter / "data")
    assert len([i for i in issues if i.level == "error"]) == 7


def test_course_files_and_links_exist():
    learn = ROOT / "docs" / "learn"
    for lab in LABS.values():
        for guide in ("README.md", "README.ko.md"):
            assert (lab.folder / guide).is_file()
        assert (learn / lab.lecture).is_file()
        assert (learn / lab.lecture.replace(".md", ".ko.md")).is_file()
    # every relative link in the course points at a file that exists
    pages = list(learn.glob("*.md")) + [p for lab in LABS.values() for p in lab.folder.glob("*.md")]
    for page in pages:
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", page.read_text(encoding="utf-8")):
            assert (page.parent / target).resolve().exists(), f"{page.name}: broken link {target}"
