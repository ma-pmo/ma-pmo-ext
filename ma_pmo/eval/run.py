"""`python -m ma_pmo.eval.run` (or `ma-pmo eval`) — run the H1–H5 harness and print a summary.

If the DB schema/fixtures are missing, run `ma-pmo init-db` first.
"""
from __future__ import annotations

import json

from ma_pmo.core.i18n import tr


def main(data_dir: str | None = None) -> int:
    """Print H1–H5 for the demo data, or for a data folder (see `ma-pmo template data`)."""
    from ma_pmo.eval import workflow

    if data_dir:
        try:
            results, ds, issues = workflow.evaluate_dataset(data_dir)
        except workflow.DatasetError as e:
            for issue in e.issues:
                print(f"  {issue}")
            print(f"✗ {e}")
            return 1
        for issue in issues:
            print(f"  {issue}")
        scope = ds.scope
    else:
        results = workflow.evaluate_demo()
        scope = workflow.DEMO_SCOPE
    print("=" * 60)
    print(tr(
        "MA-PMO hypothesis validation (H1–H5) — five-axis KPI measurement",
        "MA-PMO 가설 검증 (H1~H5) — 5축 KPI 실측",
    ))
    print(f"{scope}")
    print("=" * 60)
    for key, r in results.items():
        print(f"\n[{key}] {r['hypothesis']}")
        for k, v in r.items():
            if k in ("hypothesis", "detail"):
                continue
            print(f"  - {k}: {json.dumps(v, ensure_ascii=False)}")
    print(tr("\n(full JSON: GET /eval · report: ma-pmo template report)",
             "\n(전체 JSON: GET /eval · 보고서: ma-pmo template report)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
