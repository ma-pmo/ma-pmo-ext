"""Predefined experiments — run by name from the CLI via the `EXPERIMENTS` registry.

To add one: create a spec in this directory and register it in EXPERIMENTS.
"""
from ma_pmo.harness.experiments.a7_ablation import spec as a7_ablation
from ma_pmo.harness.experiments.full_suite import spec as full_suite
from ma_pmo.harness.experiments.hypothesis_matrix import spec as hypothesis_matrix

EXPERIMENTS = {
    "full_suite": full_suite,
    "hypothesis_matrix": hypothesis_matrix,
    "a7_ablation": a7_ablation,
}

__all__ = ["EXPERIMENTS", "full_suite", "hypothesis_matrix", "a7_ablation"]
