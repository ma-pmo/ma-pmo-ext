"""Full scenario sweep — runs all 20 scenarios to measure collaboration, KPIs and coverage."""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment("full_suite", "Full sweep of 20 organizational project-lifecycle scenarios")
    .all_scenarios()
    .repeat(1)
)
