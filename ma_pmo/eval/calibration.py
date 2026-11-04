"""Confidence calibration — does an agent's stated confidence match how often it is right?

The HITL gate sends messages below `HITL_CONFIDENCE_THRESHOLD` to a person. That only works if
confidence means something: among messages sent at 0.8, about 80% should be right. This module
measures it from two sources of ground truth:

- **risk alerts** (A4 `risk_alert.v1`) against the risk labels used by H3: right when the alert
  and the label agree on whether the project is at risk (medium or worse);
- **resolved approvals**: approved = right, rejected = wrong. Only gated messages are ever
  approved or rejected, so this sample is biased towards low confidence — reported separately.

Metrics: expected calibration error (ECE, equal-width bins), Brier score, reliability bins, and
the number of distinct confidence values (one value means confidence cannot separate good from
bad outputs, whatever its calibration). `threshold_table` shows, per candidate threshold, how many
messages would wait for a person and how many wrong ones would slip through.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select

from ma_pmo.core.i18n import tr

POSITIVE = {"medium", "high", "critical"}
MIN_SAMPLES = 5
DEFAULT_THRESHOLDS = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)


@dataclass(frozen=True)
class Pair:
    confidence: float
    correct: bool
    source: str
    # sent to a person whatever its confidence (e.g. high-severity risk, failed gate)
    always_reviewed: bool = False


def calibration(pairs: Sequence[Pair], bins: int = 10) -> dict:
    """ECE, Brier score and reliability bins. `verdict` is insufficient below MIN_SAMPLES."""
    n = len(pairs)
    if n < MIN_SAMPLES:
        return {"n": n, "verdict": "insufficient", "ece": None, "brier": None, "bins": [],
                "distinct_confidences": len({p.confidence for p in pairs})}
    rows = []
    ece = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        last = b == bins - 1
        members = [p for p in pairs if lo <= p.confidence < hi or (last and p.confidence == 1.0)]
        if not members:
            continue
        conf = sum(p.confidence for p in members) / len(members)
        acc = sum(p.correct for p in members) / len(members)
        ece += len(members) / n * abs(acc - conf)
        rows.append({"range": f"{lo:.1f}–{hi:.1f}", "n": len(members),
                     "mean_confidence": round(conf, 3), "accuracy": round(acc, 3)})
    brier = sum((p.confidence - p.correct) ** 2 for p in pairs) / n
    distinct = len({p.confidence for p in pairs})
    accuracy = sum(p.correct for p in pairs) / n
    if distinct < 2:
        verdict = "uninformative"
    elif ece <= 0.1:
        verdict = "calibrated"
    elif accuracy < sum(p.confidence for p in pairs) / n:
        verdict = "overconfident"
    else:
        verdict = "underconfident"
    return {"n": n, "verdict": verdict, "ece": round(ece, 3), "brier": round(brier, 3),
            "accuracy": round(accuracy, 3), "distinct_confidences": distinct, "bins": rows}


def threshold_table(pairs: Sequence[Pair],
                    thresholds: Iterable[float] = DEFAULT_THRESHOLDS) -> list[dict]:
    """Per threshold: messages that would wait for a person, and wrong ones that would not.

    Messages flagged `human_gate_required` are reviewed at every threshold."""
    out = []
    for t in thresholds:
        gated = [p for p in pairs if p.always_reviewed or p.confidence < t]
        missed = [p for p in pairs if not (p.always_reviewed or p.confidence < t)
                  and not p.correct]
        out.append({"threshold": t, "to_review": len(gated), "wrong_not_reviewed": len(missed),
                    "wrong_caught": sum(not p.correct for p in gated)})
    return out


def collect_pairs(scope: str, labels: dict[str, str]) -> list[Pair]:
    """(confidence, correct) for this portfolio's risk alerts and for all resolved approvals."""
    from ma_pmo.db.models import AgentMessageRow, Approval
    from ma_pmo.db.session import get_session

    pairs: list[Pair] = []
    with get_session() as s:
        alerts = s.scalars(select(AgentMessageRow).where(
            AgentMessageRow.task_ref.like(f"{scope}/%"))).all()
        for m in alerts:
            data = (m.payload or {}).get("data") or {}
            if (m.payload or {}).get("schema") != "risk_alert.v1" or "severity" not in data:
                continue
            project = m.task_ref.rsplit("/", 1)[-1]
            if project not in labels:
                continue
            predicted = data["severity"] in POSITIVE
            actual = labels[project] in POSITIVE
            pairs.append(Pair(m.confidence, predicted == actual, "risk_alert",
                              m.human_gate_required))
        resolved = s.execute(select(Approval.decision, AgentMessageRow.confidence,
                                    AgentMessageRow.human_gate_required).join(
            AgentMessageRow, Approval.message_id == AgentMessageRow.message_id).where(
            Approval.decision.in_(("approve", "reject")))).all()
        pairs += [Pair(conf, decision == "approve", "approval", flagged)
                  for decision, conf, flagged in resolved]
    return pairs


def calibration_report(scope: str, labels: dict[str, str]) -> dict:
    pairs = collect_pairs(scope, labels)
    by_source = {src: [p for p in pairs if p.source == src] for src in ("risk_alert", "approval")}
    return {
        "hypothesis": tr("Confidence calibration (HITL threshold)", "확신도 보정 (HITL 기준값)"),
        "overall": calibration(pairs),
        "by_source": {src: calibration(ps) for src, ps in by_source.items()},
        "thresholds": threshold_table(pairs),
        "note": tr(
            "Approvals only cover gated messages (low confidence or flagged), so that sample is "
            "biased; risk alerts need A4 runs (scenarios) and risk labels.",
            "승인 데이터는 게이트에 걸린 메시지(확신도 낮음 또는 승인 필수)만 포함하므로 표본이 "
            "치우쳐 있습니다. 리스크 경보는 A4 실행(시나리오)과 리스크 레이블이 있어야 집계됩니다.",
        ),
    }
