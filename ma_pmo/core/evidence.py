"""The evidence pack: what governed the agents in a period, and what happened (roadmap 10).

For one workspace and period it collects the policy versions, the guardrail results (counted,
with every one that did not simply allow), the tolerance exceptions and who decided them, and
the approvals with their reasons. It lists which guardrails relate to which items of NIST AI
RMF 1.0 (Govern, Map, Measure, Manage), ISO/IEC 42001 Annex A objectives (area names from
secondary summaries) and EU AI Act Articles 9, 12 and 14. That mapping is a starting point for
the organisation's own assessment. It does not claim conformity with any of them.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select

from ma_pmo.core import guardrails
from ma_pmo.core.times import iso
from ma_pmo.db.models import Approval, GuardrailCheck, Policy
from ma_pmo.db.session import get_session

DISCLAIMER = ("A starting point for your own assessment. MA-PMO does not claim conformity with "
              "NIST AI RMF, ISO/IEC 42001 or the EU AI Act.")
# guardrail -> (NIST AI RMF functions, ISO/IEC 42001 Annex A areas, EU AI Act articles)
MAPPING: dict[str, tuple[list[str], list[str], list[str]]] = {
    "schema": (["MEASURE"], ["A.6 AI system life cycle"], ["Art. 9 risk management"]),
    "budget": (["MANAGE"], ["A.4 Resources for AI systems"], []),
    "tolerance": (["MANAGE", "GOVERN"], ["A.9 Use of AI systems"],
                  ["Art. 14 human oversight"]),
    "injection_check": (["MEASURE", "MANAGE"], ["A.6 AI system life cycle"],
                        ["Art. 9 risk management"]),
    "pii_mask": (["MAP", "MANAGE"], ["A.7 Data for AI systems"], ["Art. 9 risk management"]),
    "execution_allowlist": (["MANAGE"], ["A.10 Third-party and customer relationships"],
                            ["Art. 9 risk management"]),
    "segregation": (["GOVERN"], ["A.3 Internal organization"], ["Art. 14 human oversight"]),
}
RECORDS = [  # what the pack itself is evidence of
    ("policy versions", ["GOVERN"], ["A.2 Policies related to AI"], ["Art. 12 record-keeping"]),
    ("guardrail log", ["MEASURE"], ["A.6 AI system life cycle"], ["Art. 12 record-keeping"]),
    ("approvals with reasons", ["GOVERN", "MANAGE"], ["A.9 Use of AI systems"],
     ["Art. 14 human oversight"]),
]


def _period(since: date | None, until: date | None) -> tuple[datetime, datetime]:
    end = datetime.combine(until or date.today(), datetime.min.time()) + timedelta(days=1)
    start = datetime.combine(since, datetime.min.time()) if since else end - timedelta(days=31)
    return start, end


def build(since: date | None = None, until: date | None = None) -> dict[str, Any]:
    """The pack for this workspace from `since` to `until` (inclusive; default: 31 days)."""
    from ma_pmo.core import policy, workspace

    start, end = _period(since, until)
    with get_session() as s:
        versions = s.scalars(select(Policy).where(Policy.created_at >= start,
                                                  Policy.created_at < end)
                             .order_by(Policy.version)).all()
        checks = s.scalars(select(GuardrailCheck).where(GuardrailCheck.created_at >= start,
                                                        GuardrailCheck.created_at < end)
                           .order_by(GuardrailCheck.id)).all()
        approvals = s.scalars(select(Approval).where(Approval.decided_at >= start,
                                                     Approval.decided_at < end)
                              .order_by(Approval.decided_at)).all()
        pending = s.scalars(select(Approval).where(Approval.decision == "pending")).all()
        counted = Counter((c.name, c.mode, c.outcome, c.decision) for c in checks)
        flagged = [guardrails.as_dict(c) for c in checks if c.outcome != guardrails.ALLOW]
        decided = [{"approval_id": a.id, "message_id": a.message_id, "decision": a.decision,
                    "approver": a.approver, "decided_at": iso(a.decided_at),
                    "rationale": a.rationale, "reason": (a.reason or {}).get("kind"),
                    "signoffs": a.signoffs or []} for a in approvals]
        exceptions = [{**d, "breaches": (a.reason or {}).get("breaches", [])}
                      for d, a in zip(decided, approvals, strict=True)
                      if (a.reason or {}).get("kind") == "exception"]
        exceptions += [{"approval_id": a.id, "message_id": a.message_id, "decision": "pending",
                        "breaches": (a.reason or {}).get("breaches", [])} for a in pending
                       if (a.reason or {}).get("kind") == "exception"]
        version_rows = [{"version": v.version, "created_by": v.created_by,
                         "created_at": iso(v.created_at), "note": v.note,
                         "document": v.document} for v in versions]
    in_force = policy.current()
    return {
        "workspace": workspace.current(),
        "period": {"from": start.date().isoformat(),
                   "to": (end - timedelta(days=1)).date().isoformat()},
        "generated_at": iso(datetime.now()),
        "disclaimer": DISCLAIMER,
        "policy_in_force": {"version": in_force["version"],
                            "guardrails": {g["name"]: g["mode"] for g in in_force["guardrails"]},
                            "tolerances": in_force["tolerances"], "stop": in_force["stop"]},
        "policy_versions": version_rows,
        "guardrail_counts": [{"guardrail": n, "mode": m, "outcome": o, "decision": d,
                              "count": k} for (n, m, o, d), k in sorted(counted.items())],
        "flagged": flagged,
        "exceptions": exceptions,
        "approvals": decided,
        "mapping": [{"guardrail": name, "nist_ai_rmf": nist, "iso_iec_42001": iso_areas,
                     "eu_ai_act": eu} for name, (nist, iso_areas, eu) in MAPPING.items()]
        + [{"record": name, "nist_ai_rmf": nist, "iso_iec_42001": iso_areas, "eu_ai_act": eu}
           for name, nist, iso_areas, eu in RECORDS],
    }


def to_markdown(pack: dict[str, Any]) -> str:
    p = pack["period"]
    lines = [f"# Evidence pack: {pack['workspace']}, {p['from']} to {p['to']}", "",
             f"_{pack['disclaimer']}_", "", "## Policy in force", "",
             f"Version {pack['policy_in_force']['version']}. Guardrails: "
             + ", ".join(f"`{n}` {m}" for n, m in pack["policy_in_force"]["guardrails"].items())
             + ".", ""]
    stop = pack["policy_in_force"]["stop"]
    if stop.get("all") or stop.get("agents") or stop.get("notifiers"):
        lines += [f"Stop switch: {stop}", ""]
    lines += ["## Policy changes in the period", ""]
    lines += [f"- v{v['version']} by {v['created_by']} at {v['created_at']}: {v['note'] or '-'}"
              for v in pack["policy_versions"]] or ["- none"]
    lines += ["", "## Guardrail results", "", "| guardrail | mode | found | took effect | count |",
              "|---|---|---|---|---:|"]
    lines += [f"| {c['guardrail']} | {c['mode']} | {c['outcome']} | {c['decision']} | "
              f"{c['count']} |" for c in pack["guardrail_counts"]] or ["| none | | | | 0 |"]
    lines += ["", f"{len(pack['flagged'])} results did not simply allow; they are listed in "
              "the JSON pack.", "", "## Tolerance exceptions", ""]
    lines += [f"- approval {e['approval_id']}: {e['decision']}"
              + (f" by {e.get('approver')}" if e.get("approver") else "")
              + "; " + "; ".join(f"{b['project']} {b['dimension']} {b['forecast']} past "
                                 f"{b['tolerance']}" for b in e["breaches"])
              for e in pack["exceptions"]] or ["- none"]
    lines += ["", "## Approvals", "", f"{len(pack['approvals'])} decided in the period, "
              f"{sum(1 for a in pack['approvals'] if a['rationale'])} with a written reason.",
              "", "## How the guardrails relate to frameworks", "",
              "| item | NIST AI RMF | ISO/IEC 42001 Annex A | EU AI Act |", "|---|---|---|---|"]
    for m in pack["mapping"]:
        name = f"`{m['guardrail']}`" if "guardrail" in m else m["record"]
        lines.append(f"| {name} | {', '.join(m['nist_ai_rmf'])} | "
                     f"{', '.join(m['iso_iec_42001'])} | {', '.join(m['eu_ai_act']) or '-'} |")
    return "\n".join(lines) + "\n"
