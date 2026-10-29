"""`python -m ma_pmo.eval.run` (or `ma-pmo eval`) — run the H1–H5 harness and print a summary.

If the DB schema/fixtures are missing, run `ma-pmo init-db` first.
"""
from __future__ import annotations

import json

from ma_pmo.core.i18n import tr
from ma_pmo.eval.harness import run_all


def main() -> None:
    results = run_all(populate=True)
    print("=" * 60)
    print(tr(
        "MA-PMO hypothesis validation (H1–H5) — five-axis KPI measurement",
        "MA-PMO 가설 검증 (H1~H5) — 5축 KPI 실측",
    ))
    print("=" * 60)
    for key, r in results.items():
        print(f"\n[{key}] {r['hypothesis']}")
        for k, v in r.items():
            if k in ("hypothesis", "detail"):
                continue
            print(f"  - {k}: {json.dumps(v, ensure_ascii=False)}")
    print(tr("\n(full JSON: GET /eval)", "\n(전체 JSON 은 GET /eval 로 조회)"))


if __name__ == "__main__":
    main()
