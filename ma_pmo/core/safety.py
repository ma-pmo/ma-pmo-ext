"""Input and execution guardrails, and the stop switch (roadmap 10, step 3).

Input (what reaches an LLM call, a goal, a webhook). `pii_mask` is enforced by default since round
2 of the evaluation; `injection_check` stays in `observe` (docs/GUARDRAILS-EVAL.md).

- `injection_check` looks for instructions hidden in data, such as tracker text that says
  "ignore the previous instructions" (OWASP Agentic Top 10: goal hijack). Enforced, it blocks the
  LLM call, so the agent falls back to its rules, and refuses the goal or webhook. Besides those
  phrases it looks for text addressed to the model ("note to the AI", "as the model reading
  this", "모델에게", "AI 검토자는 ... 할 것"), for orders that override the task ("whatever your
  instructions say", "your real task is", "pretend you are", "do not mention"), and it reads each
  string inside JSON as its own text, so a role label such as "system:" counts there as well.
  It is a list of patterns: an instruction worded some other way still gets through.
- `pii_mask` masks personal data before an LLM call: e-mail addresses, phone numbers (also in
  international form without the leading 0), Korean resident registration numbers (with a
  hyphen, a space or none, the birth date checked) and card numbers (Luhn-checked). The log
  keeps only how many of each kind, never the values.

Execution (what leaves MA-PMO), `enforce` by default since the evaluation
(docs/GUARDRAILS-EVAL.md); with the default lists (`["*"]`) it only records:

- `execution_allowlist` checks each notification against the notifiers and hosts the policy
  allows (`["*"]`: any) and records what is sent: event, notifier and host, never the URL's
  secret part. MA-PMO's connectors only read trackers today, so notifications are the writes.

The stop switch (`policy` document `stop`) pauses autonomous actions while reads and dry runs
go on: with `all`, no notification is sent and no decision commits (each is held for a person);
listed `agents` are skipped in runs and listed `notifiers` are not used. Turning it on or off is
a policy version and a decision record.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from ma_pmo.core.guardrails import ALLOW, BLOCK, ENFORCE, MODIFY, OBSERVE, Result, register

# who an instruction to the model is addressed to (EN, KO)
_TO_MODEL = (r"(?:ai|a\.i\.|assistant|chat ?bot|bot|llm|(?:large |the )?language model|model"
             r"|automated (?:reviewer|analy[sz]er|system|agent|assistant))")
_TO_MODEL_KO = (r"(?:AI|인공지능|언어 ?모델|모델|챗봇|어시스턴트|비서"
                r"|자동 ?(?:분석기|검토자|평가기)|AI ?(?:검토자|분석기|비서))")
# phrases that address the model rather than describe the project (EN, KO)
_INJECTION = [
    r"ignore (?:all |any |the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)",
    r"disregard (?:all |any |the )?(?:previous|prior|above|earlier) (?:instructions|rules)",
    r"forget (?:all |your )?(?:previous |prior )?instructions",
    r"you are now (?:a|an|the) ",
    r"new instructions?\s*:",
    r"(?:reveal|print|show) (?:your |the )?system prompt",
    r"<\|(?:im_start|im_end|system)\|>",
    r"^\s*(?:system|assistant)\s*:",
    r"(?:이전|앞의|위의) (?:모든 )?(?:지시|지침|명령)(?:을|를)? (?:무시|잊)",
    r"지시(?:를|사항을)? 무시하고",
    r"시스템 프롬프트(?:를|을)? (?:보여|출력|공개)",
    r"너는 이제 ",
    # addressed to the model
    rf"\b(?:hey|hi|dear|attention|note to|message to|instructions? (?:to|for)|for)"
    rf"\s*,?\s+(?:the |an? |this )?(?:\w+ )?{_TO_MODEL}\b",
    rf"\b(?:as|you are) (?:the|an?) (?:\w+ )?{_TO_MODEL} (?:reading|processing|reviewing)",
    rf"{_TO_MODEL_KO}\s*(?:에게|한테|께)",
    rf"{_TO_MODEL_KO}(?:는|은) .*(?:할 것|하세요|하십시오|하지 마|해라|하라)",
    # orders that override the task
    r"whatever (?:your|the) (?:instructions|rules|prompt) (?:say|says)",
    r"regardless of (?:your |the |any )?(?:instructions|rules|data|evidence|findings)",
    r"(?:your|the) (?:real|actual|true|new) (?:task|job|goal|instructions?) (?:is|are)",
    r"pretend (?:you are|to be|you're)",
    r"^\s*override\s*:",
    r"\bdo not (?:mention|flag|disclose) ",
    r"(?:지금까지|기존|앞에서 받은|이전)(?:의)? (?:규칙|지침|지시|안내|명령)(?:은|는|을|를)? .*"
    r"(?:적용하지 말|무시|잊|신경 쓰지 말)",
    r"새로운 (?:임무|지시|명령)\s*[:：]",
    r"(?:지금부터|이제부터) 너는 ",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION), re.IGNORECASE | re.MULTILINE)

_PII = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    # Korean resident registration number: birth date YYMMDD, then a digit 1-4 and six more
    "rrn": re.compile(r"\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[- ]?[1-4]\d{6}\b"),
    "card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone": re.compile(r"(?<![\w-])(?:(?:\+\d{1,3}[ -]?)?(?:0\d{1,2}|\(\d{2,3}\))"
                        r"|\+\d{1,3}[ -]?\(?\d{1,4}\)?)"  # international: no leading 0
                        r"[ -]?\d{3,4}[ -]?\d{4}\b"),
}


def _luhn(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


_JSON_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _strings(text: str) -> list[str]:
    """Each JSON string literal in the text, decoded: data sent as JSON is read value by value."""
    import json

    found = []
    for m in _JSON_STRING.finditer(text):
        try:
            found.append(json.loads(f'"{m.group(1)}"'))
        except ValueError:
            continue
    return found


def find_injection(text: str) -> list[str]:
    text = text or ""
    seen: list[str] = []
    for part in [text, *(_strings(text) if '"' in text else [])]:
        for m in _INJECTION_RE.finditer(part):
            if m.group(0)[:80] not in seen:
                seen.append(m.group(0)[:80])
    return seen


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """(masked text, how many of each kind were masked)."""
    counts: dict[str, int] = {}

    def sub(kind: str) -> Any:
        def replace(m: re.Match) -> str:
            if kind == "card" and not _luhn(m.group(0)):
                return m.group(0)
            counts[kind] = counts.get(kind, 0) + 1
            return f"[{kind}]"
        return replace

    for kind in ("email", "rrn", "card", "phone"):  # card before phone: long digit runs
        text = _PII[kind].sub(sub(kind), text)
    return text, counts


@register("injection_check", "input", OBSERVE,
          "Block LLM calls, goals and webhooks whose text carries instructions to the model")
def _injection(context: dict[str, Any], params: dict[str, Any]) -> Result:
    found = find_injection(context.get("text") or "")
    if not found:
        return Result(ALLOW, "no instructions found")
    return Result(BLOCK, f"instructions in {context.get('source', 'input')}: {found[0]!r}",
                  detail={"source": context.get("source"), "matches": found[:5]})


@register("pii_mask", "input", ENFORCE,
          "Mask personal data (e-mail, phone, resident and card numbers) before LLM calls")
def _pii(context: dict[str, Any], params: dict[str, Any]) -> Result:
    masked, counts = mask_pii(context.get("text") or "")
    if not counts:
        return Result(ALLOW, "no personal data found")
    return Result(MODIFY, "masked " + ", ".join(f"{n} {k}" for k, n in counts.items()),
                  detail={"source": context.get("source"), "masked": counts}, value=masked)


@register("execution_allowlist", "execution", ENFORCE,
          "Send notifications only through allowed notifiers and hosts; record what leaves",
          notifiers=["*"], hosts=["*"])
def _allowlist(context: dict[str, Any], params: dict[str, Any]) -> Result:
    notifier, event = context["notifier"], context["event"]
    url = getattr(notifier, "url", None) or getattr(notifier, "webhook_url", None) or ""
    host = urlparse(url).hostname or ""
    sent = {"event": event.type.value, "notifier": notifier.name, "host": host or None,
            "title": event.title[:200]}
    names, hosts = params.get("notifiers") or ["*"], params.get("hosts") or ["*"]
    if "*" not in names and notifier.name not in names:
        return Result(BLOCK, f"notifier {notifier.name} is not allowed", detail=sent)
    if host and "*" not in hosts and not any(host == h or host.endswith("." + h)
                                             for h in hosts):
        return Result(BLOCK, f"host {host} is not allowed", detail=sent)
    return Result(ALLOW, f"{event.type.value} via {notifier.name}", detail=sent)


# ── checks callers use ────────────────────────────────────────────────────────────────

class InputBlocked(RuntimeError):
    """An input guardrail refused the text; the caller falls back or refuses the request."""


def guard_input(text: str, source: str) -> str:
    """The text to use: unchanged, masked (pii_mask enforced), or InputBlocked raised
    (injection_check enforced)."""
    from ma_pmo.core import guardrails

    checked = guardrails.run("injection_check", {"text": text, "source": source})
    if checked.decision == BLOCK:
        raise InputBlocked(checked.reason)
    masked = guardrails.run("pii_mask", {"text": text, "source": source})
    return masked.value if masked.decision == MODIFY and masked.value is not None else text


# ── the stop switch ───────────────────────────────────────────────────────────────────

def stop() -> dict[str, Any]:
    from ma_pmo.core import policy

    row = policy._latest()
    return ((row.document if row else {}).get("stop") or {})


def stopped(*, agent: str | None = None, notifier: str | None = None) -> bool:
    """Whether autonomous action is paused: all of it, this agent, or this notifier."""
    switch = stop()
    if agent is not None:
        return agent in (switch.get("agents") or [])
    if notifier is not None:
        return bool(switch.get("all")) or notifier in (switch.get("notifiers") or [])
    return bool(switch.get("all"))
