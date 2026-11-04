"""Hands-on course: harness engineering for multi-agent systems, taught on MA-PMO.

Lectures live in `docs/learn/`. Each lab ships a starter, a reference solution and automatic
checks, so learners get feedback without a teacher:

    ma-pmo learn list              # the six labs
    ma-pmo learn scenarios         # scenario ids and the agents they use (lab 3)
    ma-pmo learn start 1           # copy the starter files to ./learn/lab1
    ma-pmo learn check 1           # run the checks against ./learn/lab1
    ma-pmo learn check 1 --solution    # run them against the reference solution
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

LABS_DIR = Path(__file__).parent / "labs"


@dataclass(frozen=True)
class Lab:
    number: int
    slug: str
    title: tuple[str, str]  # (English, Korean)
    lecture: str  # lecture file in docs/learn/ this lab practices
    needs_db: bool = False
    needs_extra: str = ""  # optional dependency the lab needs, e.g. "mcp"

    @property
    def folder(self) -> Path:
        return LABS_DIR / f"lab{self.number}_{self.slug}"

    @property
    def starter(self) -> Path:
        return self.folder / "starter"

    @property
    def solution(self) -> Path:
        return self.folder / "solution"


LABS: dict[int, Lab] = {
    lab.number: lab
    for lab in (
        Lab(1, "notifier", ("Write a notifier plugin", "알림 플러그인 만들기"),
            "07-integrations.md"),
        Lab(2, "dataset", ("Repair an organization dataset", "조직 데이터 고치기"),
            "05-measuring-agents.md"),
        Lab(3, "ablation", ("Design an ablation experiment", "제거 실험(ablation) 설계하기"),
            "06-experiments.md", needs_db=True),
        Lab(4, "tracker", ("Build a custom tracker", "나만의 트래커 만들기"),
            "07-integrations.md"),
        Lab(5, "mcp_tool", ("Write an MCP tool", "MCP 도구 만들기"),
            "07-integrations.md", needs_db=True, needs_extra="mcp"),
        Lab(6, "calibration", ("Calibrate the approval gate", "승인 게이트 보정하기"),
            "08-operating-agents.md"),
    )
}


def get_lab(number: int) -> Lab:
    try:
        return LABS[number]
    except KeyError:
        raise ValueError(f"no lab {number}; choose one of {sorted(LABS)}") from None


__all__ = ["LABS", "LABS_DIR", "Lab", "get_lab"]
