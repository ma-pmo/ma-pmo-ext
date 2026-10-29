"""A7 (knowledge) ablation — outputs and evidence with vs. without the knowledge agent (H4)."""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment("a7_ablation", "A7 knowledge agent ablation — measures citation contribution")
    .with_scenarios("knowledge_kickoff", "new_project_intake", "estimation_review",
                    "lessons_learned_closure", "estimation_calibration")
    .ablate("A7")
)
