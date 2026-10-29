"""Hypothesis coverage matrix — which scenarios test H1–H5, measured over 3 repetitions."""
from ma_pmo.harness.spec import Experiment

spec = (
    Experiment("hypothesis_matrix", "H1–H5 hypothesis coverage and variance (3 repetitions)")
    .all_scenarios()
    .repeat(3)
)
