"""Every GET response of the API on seeded demo data, to check that a change keeps behaviour.

    DB_URL=sqlite:///before.db python tests/golden/api_snapshot.py capture before.json
    (make the change; use a new database)
    DB_URL=sqlite:///after.db python tests/golden/api_snapshot.py capture after.json
    python tests/golden/api_snapshot.py compare before.json after.json

`capture` seeds the demo data (docs/capture_seed.py), runs every scenario and a goal, then reads
every GET route in English and Korean, with path parameters filled from what exists. Ids and
times are normalized, and a zip is compared by the contents of its files. `compare` also ignores
what differs between two identical runs (measured durations, thread ids, timing KPIs, the order
of rows written in the same instant) and exits non-zero when anything else differs.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
UUID = re.compile(r"\b[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}\b")
HEX_ID = re.compile(r"\b(RPT|RISK|run)-[0-9a-f]{6,}\b|\bsandbox-[0-9a-f]{12}\b")
TIME = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d(:\d\d(\.\d+)?)?(\+00:00|Z| UTC)?")
VOLATILE = {"elapsed_ms", "ms", "duration_ms", "report_cycle_time_sec", "latency", "value_sec"}
THREAD = re.compile(r"thread-[0-9a-f]{8}")
DURATION = re.compile(r"\d+(\.\d+)?(s\b|초)")  # measured times in findings, as capture.py does
TIMED = {"latency_ms", "automated_avg_sec", "avg", "sum", "p50", "p95", "max", "min", "value"}


def capture(out: str) -> None:
    from fastapi.testclient import TestClient

    from ma_pmo.core import llm
    from ma_pmo.core.goals import run_goal
    from ma_pmo.core.scenarios import SCENARIOS, run_scenario
    from ma_pmo.core.scope import DEFAULT_SCOPE
    from ma_pmo.db.init import main as init_db

    init_db()
    sys.path.insert(0, str(ROOT / "docs"))
    import capture_seed

    capture_seed.main()
    llm.litellm.completion = capture_seed.completion
    for scenario_id in sorted(SCENARIOS):
        run_scenario(scenario_id)
    run_goal("risk review and report", DEFAULT_SCOPE)

    from ma_pmo.api.main import app

    client = TestClient(app)
    runs = [r["run_id"] for r in client.get("/runs", params={"limit": 50}).json()]
    flows = [w["id"] for w in client.get("/workflows").json()["workflows"]]
    fill = {"run_id": runs[:6], "workflow_id": flows[:5], "version": ["1", "2"],
            "portfolio_id": [DEFAULT_SCOPE.replace("#", "%23")]}
    query = {"/knowledge/search": {"q": "lesson risk schedule"}}
    results: dict[str, Any] = {}
    for path, ops in sorted(client.get("/openapi.json").json()["paths"].items()):
        if "get" not in ops:
            continue
        urls = [path]
        for name in re.findall(r"{(\w+)}", path):
            urls = [u.replace("{" + name + "}", v) for u in urls for v in fill.get(name, ["x"])]
        for url in urls:
            for lang in ("en", "ko"):
                r = client.get(url, params={**query.get(path, {}), "lang": lang})
                results[f"{lang} {_url_key(url, runs)}"] = [r.status_code, _body(r)]
    text = json.dumps(results, ensure_ascii=False, sort_keys=True, default=str)
    Path(out).write_text(json.dumps(_normalize(json.loads(text)), ensure_ascii=False,
                                    sort_keys=True, indent=1), encoding="utf-8")


def _body(response: Any) -> Any:
    if response.headers.get("content-type", "").startswith("application/zip"):
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:  # contents, not file times
            return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
    try:
        return response.json()
    except ValueError:
        return response.text


def _url_key(url: str, runs: list[str]) -> str:
    for i, run_id in enumerate(runs):
        url = url.replace(run_id, f"<run{i}>")
    return url


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("<v>" if k in VOLATILE else _normalize(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, str):
        return TIME.sub("<time>", HEX_ID.sub("<id>", UUID.sub("<id>", obj)))
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def _clean(obj: Any, timed: bool = False) -> Any:
    if isinstance(obj, dict):
        return {k: ("<t>" if timed and k in TIMED and isinstance(v, float) else _clean(v, timed))
                for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_clean(v, timed) for v in obj]
        # rows written in the same instant come back in either order
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    if isinstance(obj, str):
        return DURATION.sub("<time>", THREAD.sub("<thread>", obj))
    return obj


def compare(a_path: str, b_path: str) -> int:
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    keys = sorted(set(a) | set(b))
    differ = []
    for key in keys:
        timed = key.split(" ", 1)[1] in ("/kpi", "/eval")
        if _clean(a.get(key), timed) != _clean(b.get(key), timed):
            differ.append(key)
    print(f"{len(keys)} responses compared, {len(differ)} differ")
    for key in differ[:30]:
        print("  ", key)
    return 1 if differ else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "capture":
        capture(sys.argv[2])
    elif len(sys.argv) == 4 and sys.argv[1] == "compare":
        sys.exit(compare(sys.argv[2], sys.argv[3]))
    else:
        sys.exit(__doc__)
