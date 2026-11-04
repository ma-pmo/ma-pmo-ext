"""Lab 3: does the knowledge agent (A7) add evidence? (H4)

Fill in the TODOs, then run `ma-pmo learn check 3`. The lab guide is README.md.
`ma-pmo learn scenarios` lists every scenario and the agents it uses.
"""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment("h4_knowledge", "TODO: one sentence on what this experiment measures")
    # TODO (step 1): .with_scenarios(...) — 2 to 5 scenarios that actually use A7
    # TODO (step 2): .ablate(...) — the agent to remove
    # TODO (step 3): .repeat(...) — 1 to 3 is enough for a deterministic (offline) run
)
