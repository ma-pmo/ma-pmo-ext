# Guardrails and policy

**English | [한국어](GUARDRAILS.ko.md)**

Roadmap 10 ([#84](https://github.com/ma-pmo/ma-pmo-ext/issues/84)) puts MA-PMO's checks behind
one policy and one record, so a PMO can say in one place how much the agents may do alone, and
show afterwards what was checked.

## Guardrails

A guardrail is a check at a control point, after the rail types of NeMo Guardrails and the
guardrails of the OpenAI Agents SDK:

| point | where |
|---|---|
| `input` | a goal or request reaching A1, a webhook payload |
| `retrieval` | lessons and tracker data agents read |
| `execution` | connector writes, notifiers, plugins |
| `output` | each agent payload |
| `decision` | the commit gate and approvals |
| `spend` | LLM calls |

It answers `allow`, `modify`, `ask` or `block`, with a reason. Its **mode** comes from the
policy:

- `off`: not run.
- `observe`: run and recorded, but `allow` takes effect, so you see what it would have done
  before turning it on.
- `enforce`: its answer takes effect.

| guardrail | point | default | what it does |
|---|---|---|---|
| `schema` | output | enforce | rejects an agent payload that does not match its registered schema |
| `budget` | spend | enforce | stops LLM calls past a hard budget ([COSTS.md](COSTS.md#budgets)); agents fall back to their rules |

Both existed before roadmap 10 and behave as they did. Guardrails added later start in
`observe`.

## Policy

The policy is data, versioned per workspace: `{"guardrails": {name: {"mode", "params"}}}`.

- `GET /policy` returns the policy in force, with every guardrail's point, mode and
  parameters.
- `PUT /policy` `{guardrails, note}` creates a new version. It needs the admin role.
- `GET /policy/versions` lists every version, with who changed it and why.

Each change is also a decision record (kind `policy`). Every run stores the version it ran
under (`policy_version` in its state).

## The guardrail log

Every result is a `guardrail.v1` entry (`GET /guardrails`, filter by `name`, `point`,
`decision`, `outcome`, `run`). An entry holds:
- the mode;
- what the check found (`outcome`) and what took effect (`decision`);
- the reason and the details (for example the invalid fields);
- the policy version;
- the run and the message.

`outcome=block` with `decision=allow` is what observe mode would have blocked. The entries
sit next to the communication log, not in it, so notification counts are unchanged.

On the demo data the 20 built-in scenarios leave about 270 entries (every payload's schema
check, every LLM attempt's budget check), with no measurable added run time.
