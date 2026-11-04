# Learn harness engineering with MA-PMO

**English | [한국어](README.ko.md)**

A hands-on course on building multi-agent systems that are **dependable, measurable and safe
to run in an organization**. The model is only one part of an agent system. The rest — the
contracts between agents, the fallbacks, the approval gates, the measurements, the experiments
and the integrations — is the *harness*. This course teaches that harness on a real, working
system: MA-PMO, seven agents that run a project management office.

Every lecture points at real code in this repository. Every lab has starter files, a reference
solution and automatic checks, so you get feedback without a teacher. No API key is needed:
everything runs offline.

## Who it is for

Developers who can read Python and want to move from "an LLM demo" to "an agent system a
PMO can trust". Project managers who want to understand what to ask of such a system will get
the most from lectures 1, 4 and 5.

## Setup (5 minutes)

```bash
pip install ma-pmo          # or, from a clone: make dev
ma-pmo init-db              # demo portfolio + lessons learned
ma-pmo learn list           # the six labs
```

Labs are copied to `./learn/labN` and checked with `ma-pmo learn check N`. Labs never touch
your own database: lab 3 uses its own SQLite file.

## Course map

| # | Lecture | You learn | Lab |
|---|---|---|---|
| 1 | [Why agents fail, and what a harness is](01-why-harness.md) | the failure modes a harness exists to catch | — |
| 2 | [Structured messages as contracts](02-structured-messages.md) | schemas, versions, an append-only audit log | — |
| 3 | [Deterministic fallbacks: offline first](03-offline-fallbacks.md) | how every LLM step keeps working without an LLM | — |
| 4 | [Human-in-the-loop gates](04-human-in-the-loop.md) | which decisions wait for a person, and how | — |
| 5 | [Measuring agents](05-measuring-agents.md) | KPIs, hypotheses, baselines, ground truth | [Lab 2](../../ma_pmo/learn/labs/lab2_dataset/README.md): repair a dataset |
| 6 | [Experiments, ablations and tests](06-experiments.md) | turning claims into reproducible runs | [Lab 3](../../ma_pmo/learn/labs/lab3_ablation/README.md): ablation |
| 7 | [Integrations and failure isolation](07-integrations.md) | plugins that can fail without breaking agents | [Lab 1](../../ma_pmo/learn/labs/lab1_notifier/README.md): notifier · [Lab 4](../../ma_pmo/learn/labs/lab4_tracker/README.md): tracker · [Lab 5](../../ma_pmo/learn/labs/lab5_mcp_tool/README.md): MCP tool |
| 8 | [Operating agents: identity, traces, calibration](08-operating-agents.md) | who did what, why a run behaved so, whether the gate filters risk | [Lab 6](../../ma_pmo/learn/labs/lab6_calibration/README.md): calibrate the gate |

Suggested order: lectures 1–4, then 7 with Lab 1 (the gentlest lab), then 5 with Lab 2, 6 with
Lab 3, Lab 4, then Lab 5 (needs `pip install "ma-pmo[mcp]"`), and finish with lecture 8 and
Lab 6. Plan about one hour per lecture and one to two hours per lab.

## How the labs work

```bash
ma-pmo learn start 1              # copy the starter files to ./learn/lab1
# edit learn/lab1/file_notifier.py, guided by learn/lab1/README.md
ma-pmo learn check 1              # ✓/✗ per requirement, with a hint for each ✗
ma-pmo learn start 1 --solution   # stuck? the reference solution goes to ./learn/lab1-solution
```

Teachers: `ma-pmo learn check N --solution` proves the reference solution passes, and the
repository's CI checks that every solution passes and every untouched starter fails.

## Credits

The lecture-plus-lab format is inspired by
[walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering)
(MIT License). The lectures, labs and code here are original and specific to MA-PMO.
