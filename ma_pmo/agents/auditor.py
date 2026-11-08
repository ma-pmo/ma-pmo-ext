"""A8 Auditor — the dedicated reviewer: checks other agents' decisions against the board.

A8 has no task of its own and decides nothing. Placed after the decisions of a run (a workflow
with `"review": true` does this, see `WorkflowSpec.with_review`), it reads the board and posts a
review.v1 verdict with `role: dedicated` on every decision it can check:

- each gate_review.v1: the gate cross-checks (agents/cross_checks.py), on the project's facts
  from the tracker;
- each report.v1: whether it covers the risks A4 raised;
- for each gate decision it challenges, the alternatives a person could take instead
  (`ALTERNATIVE` verdicts, see `cross_checks.alternatives`): at least one alternative for every
  challenged decision, as ArcticSwarm requires before a commit.

It uses the same rules as the builders but comes to them without having made the decision, and
it reads only decisions and their sources, never the builders' verdicts, so the two reviews stay
independent. Where they differ, both stay on the board. A dedicated reviewer next to the
builders follows ArcticSwarm (Yoon et al., 2026, arXiv:2609.01870, Appendix G.1), implemented
independently and without an LLM: a verdict can only rest on what is on the board.
"""
from __future__ import annotations

from ma_pmo.agents import cross_checks
from ma_pmo.agents.base import BaseAgent
from ma_pmo.connectors.base import IssueTrackerConnector
from ma_pmo.core.schemas.payloads.review_v1 import ReviewV1
from ma_pmo.core.scope import DEFAULT_SCOPE
from ma_pmo.core.state.blackboard import PortfolioState
from ma_pmo.integrations.registry import get_tracker

_ROLE = """You are the PMO auditor. Check other agents' decisions against the evidence on the
board; you make no decision yourself."""


class AuditorAgent(BaseAgent[ReviewV1]):
    agent_id = "A8"
    function = "Auditor (dedicated review)"
    role_prompt = _ROLE
    output_schema = ReviewV1

    def __init__(self, tracker: IssueTrackerConnector | None = None) -> None:
        self.tracker = tracker or get_tracker()

    def run(self, state: PortfolioState) -> dict:
        if "board" not in state:  # isolated: nothing to review
            return {"outputs": []}
        board, steps = state["board"], state.get("board_steps", [])
        scope = state.get("task_ref", DEFAULT_SCOPE)
        projects = {p["project_id"]: p
                    for p in self.tracker.get_portfolio_status(scope).get("projects", [])}
        outputs = []
        for post in board:
            if post["schema"] == "gate_review.v1":
                project = projects.get(post["data"].get("project_id"))
                verdicts = cross_checks.gate_checks(project, board, steps) if project else []
                verdicts += [alt for v in verdicts if v.verdict == "CHALLENGE"
                             for alt in cross_checks.alternatives(v, project or {}, board, steps)]
            elif post["schema"] == "report.v1":
                check = cross_checks.covers_risks(post["data"].get("key_risks", []), board, steps)
                verdicts = [check] if check else []
            else:
                continue
            outputs += [cross_checks.publish_review(self.agent_id, v, post["message_id"],
                                                    post["task_ref"], role="dedicated")
                        for v in verdicts]
        return {"outputs": outputs}
