"""Lab 3 reference solution: does the knowledge agent (A7) add evidence? (H4)

Only scenarios that use A7 are listed: removing an agent from a scenario that never calls it
changes nothing, so it would only dilute the result.
"""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment("h4_knowledge", "H4: findings with vs. without the knowledge agent (A7)")
    .with_scenarios("knowledge_kickoff", "estimation_review", "lessons_learned_closure")
    .ablate("A7")
    .repeat(1)
)
