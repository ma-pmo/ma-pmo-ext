"""`ma-pmo` command-line entry point (installed via `pip install ma-pmo`).

Examples:
    ma-pmo init-db                          # create SQLite schema + load demo fixtures
    ma-pmo db upgrade                       # bring the database to the latest schema
    ma-pmo db status                        # current and latest schema revision
    ma-pmo serve --port 8000                # start the FastAPI server
    ma-pmo eval                             # run the H1–H5 evaluation on the demo data
    ma-pmo eval --retrieval                 # A7 retrieval quality: lexical vs. vector search
    ma-pmo template data ./my-org           # write the evaluation data template
    ma-pmo template validate ./my-org       # check the filled-in data
    ma-pmo eval --data ./my-org             # evaluate H1–H5 on your own data
    ma-pmo template report --format html    # evaluation report (Markdown/HTML)
    ma-pmo harness full_suite               # run an experiment from the harness
    ma-pmo harness new my_exp --hypothesis H3   # scaffold a new experiment
    ma-pmo learn start 1                    # course lab: copy the starter files
    ma-pmo learn check 1                    # course lab: check your work
    ma-pmo mcp                              # MCP server over stdio (pip install "ma-pmo[mcp]")
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ma_pmo import __version__


def _print_issues(issues: list) -> None:
    for issue in issues:
        print(f"  {issue}")


def _cmd_template(ns: argparse.Namespace) -> int:
    from ma_pmo.core.i18n import tr

    if ns.kind == "data":
        from ma_pmo.eval.dataset import generate_data_template

        try:
            paths = generate_data_template(ns.dir, examples=not ns.empty, overwrite=ns.force)
        except FileExistsError as e:
            print(f"✗ {e}")
            return 1
        print(tr(f"✓ evaluation data template written to {ns.dir}:",
                 f"✓ 평가 데이터 양식을 {ns.dir}에 만들었습니다:"))
        for p in paths:
            print(f"  - {p.name}")
        print(tr(f"\nNext: fill them in, then `ma-pmo template validate {ns.dir}`",
                 f"\n다음: 내용을 채운 뒤 `ma-pmo template validate {ns.dir}` 실행"))
        return 0

    if ns.kind == "validate":
        from ma_pmo.eval.dataset import load_dataset

        ds, issues = load_dataset(ns.dir)
        errors = [i for i in issues if i.level == "error"]
        _print_issues(issues)
        if errors:
            print(tr(f"✗ {len(errors)} error(s) — fix them and run again",
                     f"✗ 오류 {len(errors)}건 — 고친 뒤 다시 실행하세요"))
            return 1
        n_tasks = sum(len(p["tasks"]) for p in ds.projects)
        print(tr(
            f"✓ valid: {len(ds.projects)} projects, {n_tasks} tasks, {len(ds.resources)} "
            f"resources, {len(ds.labels)} risk labels ({len(issues)} warning(s))",
            f"✓ 정상: 프로젝트 {len(ds.projects)}개, 태스크 {n_tasks}개, 자원 "
            f"{len(ds.resources)}개, 리스크 레이블 {len(ds.labels)}개 (경고 {len(issues)}건)",
        ))
        return 0

    # report
    from ma_pmo.eval import workflow

    if ns.data:
        workflow.use_isolated_db(ns.data)
    from ma_pmo.core.obs import configure_logging
    from ma_pmo.eval.report import build_report, render

    configure_logging()
    if ns.data:
        try:
            results, ds, _ = workflow.evaluate_dataset(ns.data)
        except workflow.DatasetError as e:
            _print_issues(e.issues)
            print(f"✗ {e}")
            return 1
        scope, source = ds.scope, workflow.dataset_source(ns.data)
    else:
        results = workflow.evaluate_demo()
        scope, source = workflow.DEMO_SCOPE, workflow.demo_source()
    text = render(build_report(results, scope=scope, source=source), ns.format)
    if ns.out:
        Path(ns.out).write_text(text, encoding="utf-8")
        print(tr(f"✓ report written to {ns.out}", f"✓ 보고서를 {ns.out}에 저장했습니다"))
    else:
        print(text)
    return 0


def _cmd_db(action: str) -> int:
    from ma_pmo.core.i18n import tr
    from ma_pmo.db import migrate

    if action == "upgrade":
        print(tr(f"✓ schema at {migrate.upgrade()}", f"✓ 스키마 버전: {migrate.upgrade()}"))
        return 0
    now, latest = migrate.current(), migrate.head()
    print(tr(f"current: {now or 'none'} · latest: {latest}",
             f"현재: {now or '없음'} · 최신: {latest}"))
    return 0 if now == latest else 1


def _cmd_retrieval() -> int:
    from ma_pmo.connectors.vectordb import LiteLLMEmbedder, Retriever, VectorStore
    from ma_pmo.core.config import get_settings
    from ma_pmo.core.i18n import tr
    from ma_pmo.eval.retrieval import compare

    model = get_settings().embedding_model.strip()
    extra: dict[str, Retriever] = {}
    if model:
        extra[f"vector ({model})"] = VectorStore(
            LiteLLMEmbedder(model, get_settings().embedding_api_base))
    results = compare(extra=extra)
    print(tr("A7 retrieval on the labeled query set (ma_pmo/fixtures/retrieval_eval.json)",
             "라벨링된 질의 세트로 본 A7 검색 품질 (ma_pmo/fixtures/retrieval_eval.json)"))
    print(f"{'':26}{'recall@1':>10}{'recall@3':>10}{'MRR':>8}   by kind")
    for name, r in results.items():
        kinds = ", ".join(f"{k} {v}" for k, v in r["by_kind"].items())
        if r["fallbacks"]:
            print(f"{name:26}  " + tr(
                f"model unreachable — {r['fallbacks']}/{r['n']} searches fell back to lexical",
                f"모델 연결 안 됨 — {r['n']}건 중 {r['fallbacks']}건이 어휘 검색으로 대체됨"))
            continue
        print(f"{name:26}{r['recall_at_1']:>10}{r['recall_at_3']:>10}{r['mrr']:>8}   {kinds}")
        for miss in r["misses"]:
            print(f"{'':28}{tr('missed', '놓침')}: {miss}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ma-pmo", description="MA-PMO multi-agent PMO orchestration"
    )
    parser.add_argument("--version", action="version", version=f"ma-pmo {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the schema and load demo fixtures")

    db = sub.add_parser("db", help="database schema: upgrade | status")
    db.add_argument("action", choices=["upgrade", "status"])

    serve = sub.add_parser("serve", help="start the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    ev = sub.add_parser("eval", help="run the H1–H5 evaluation harness")
    ev.add_argument("--data", help="folder made with `ma-pmo template data` (default: demo data)")
    ev.add_argument("--retrieval", action="store_true",
                    help="A7 retrieval quality (recall@k, MRR): lexical vs. vector search")

    tpl = sub.add_parser("template", help="evaluation templates: data | validate | report")
    tsub = tpl.add_subparsers(dest="kind", required=True)
    t_data = tsub.add_parser("data", help="write the evaluation data template (CSV/JSON)")
    t_data.add_argument("dir", help="folder to create")
    t_data.add_argument("--empty", action="store_true", help="headers only, no example rows")
    t_data.add_argument("--force", action="store_true", help="overwrite existing files")
    t_val = tsub.add_parser("validate", help="check a filled-in data folder")
    t_val.add_argument("dir")
    t_rep = tsub.add_parser("report", help="evaluation report (Markdown or HTML)")
    t_rep.add_argument("--format", choices=["md", "html"], default="md")
    t_rep.add_argument("--data", help="evaluate this data folder instead of the demo data")
    t_rep.add_argument("--out", help="write to a file instead of stdout")

    harness = sub.add_parser(
        "harness", help="run an experiment ('list' to see all, 'new' to create one)"
    )
    harness.add_argument("args", nargs=argparse.REMAINDER)

    sub.add_parser("mcp", help='MCP server over stdio for AI assistants (needs "ma-pmo[mcp]")')

    learn = sub.add_parser("learn", help="course labs: list | start N | check N")
    learn.add_argument("args", nargs=argparse.REMAINDER)

    ns = parser.parse_args(argv)

    from ma_pmo.core.tracing import configure_tracing

    configure_tracing()  # no-op unless OTEL_ENABLED=true

    if ns.command == "init-db":
        from ma_pmo.db.init import main as init_main

        init_main()
    elif ns.command == "db":
        return _cmd_db(ns.action)
    elif ns.command == "serve":
        import uvicorn

        uvicorn.run("ma_pmo.api.main:app", host=ns.host, port=ns.port, reload=ns.reload)
    elif ns.command == "eval" and ns.retrieval:
        return _cmd_retrieval()
    elif ns.command == "eval":
        if ns.data:
            from ma_pmo.eval.workflow import use_isolated_db

            use_isolated_db(ns.data)
        from ma_pmo.eval.run import main as eval_main

        return eval_main(ns.data)
    elif ns.command == "template":
        return _cmd_template(ns)
    elif ns.command == "harness":
        from ma_pmo.harness.cli import main as harness_main

        return harness_main(ns.args)
    elif ns.command == "mcp":
        from ma_pmo.mcp_server import main as mcp_main

        try:
            return mcp_main()
        except ImportError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
    elif ns.command == "learn":
        from ma_pmo.learn.cli import main as learn_main

        return learn_main(ns.args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
