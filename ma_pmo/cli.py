"""`ma-pmo` command-line entry point (installed via `pip install ma-pmo`).

Examples:
    ma-pmo init-db                          # create SQLite schema + load demo fixtures
    ma-pmo db upgrade                       # bring the database to the latest schema
    ma-pmo db status                        # current and latest schema revision
    ma-pmo serve --port 8000                # start the FastAPI server
    ma-pmo agents                           # worker agents, including installed plugins
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


def _cmd_workspace(ns: argparse.Namespace) -> int:
    from ma_pmo.core.i18n import tr
    from ma_pmo.db import workspaces

    try:
        if ns.action == "create":
            workspaces.create(ns.id, ns.name)
            print(tr(f"✓ workspace '{ns.id}' created", f"✓ 워크스페이스 '{ns.id}' 생성"))
        elif ns.action == "list":
            for w in workspaces.list_all():
                print(f"{w['id']:<24}{w['name']}")
        elif ns.action == "members":
            for m in workspaces.members(ns.id):
                print(f"{m['principal']:<24}{m['role']}")
        elif ns.action == "grant":
            added = workspaces.grant(ns.id, ns.principal, ns.role)
            note = "" if added else tr(" (already)", " (이미 있음)")
            print(tr(f"✓ {ns.principal} is {ns.role} in '{ns.id}'{note}",
                     f"✓ {ns.principal}: '{ns.id}'에서 {ns.role}{note}"))
        elif ns.action == "revoke":
            if not workspaces.revoke(ns.id, ns.principal, ns.role):
                print(tr("nothing to revoke", "회수할 권한이 없습니다"))
                return 1
            print(tr(f"✓ revoked {ns.role} from {ns.principal} in '{ns.id}'",
                     f"✓ {ns.principal}: '{ns.id}'의 {ns.role} 회수"))
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    return 0


def _cmd_agents() -> int:
    from ma_pmo.agents import registry
    from ma_pmo.core.i18n import tr

    print(f"{'id':<16}{tr('name', '이름'):<14}{tr('version', '버전'):<9}{tr('source', '출처')}")
    for spec in registry.specs().values():
        print(f"{spec.id:<16}{spec.title:<14}{spec.version:<9}{spec.source}")
    problems = registry.problems()
    for problem in problems:
        print(tr(f"✗ not loaded: {problem}", f"✗ 불러오지 못함: {problem}"))
    return 1 if problems else 0


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


def _cmd_workflow(ns: argparse.Namespace) -> int:
    """Workflow versions in this workspace (MA_PMO_WORKSPACE), with the API's validator."""
    import json
    from pathlib import Path

    from ma_pmo.core import workflow_store
    from ma_pmo.core.i18n import tr

    try:
        if ns.action in ("validate", "draft"):
            data = json.loads(Path(ns.file).read_text(encoding="utf-8"))
            if ns.action == "validate":
                _, found = workflow_store.problems(data)
                for problem in found:
                    print(f"✗ {problem}")
                if not found:
                    print(tr("✓ valid", "✓ 문제 없음"))
                return 1 if found else 0
            saved = workflow_store.save_draft(data, "cli", ns.note)
            print(tr(f"✓ draft v{saved['version']} of '{data.get('id')}' saved",
                     f"✓ '{data.get('id')}' 초안(v{saved['version']}) 저장"))
        elif ns.action == "versions":
            for v in workflow_store.versions(ns.id):
                mark = "*" if v["in_use"] else " "
                print(f"{mark} v{v['version']:<4}{v['status']:<11}{v['created_by'] or '':<16}"
                      f"{v['note']}")
        elif ns.action == "publish":
            workflow_store.publish(ns.id, ns.version, "cli")
            print(tr(f"✓ '{ns.id}' v{ns.version} is now in use",
                     f"✓ 이제 '{ns.id}'의 v{ns.version} 버전을 사용합니다"))
    except workflow_store.Invalid as e:
        for problem in e.problems:
            print(f"✗ {problem}")
        return 1
    except (KeyError, OSError, ValueError) as e:
        print(f"✗ {e}")
        return 1
    return 0


def _cmd_budget(ns: argparse.Namespace) -> int:
    """Budgets of this workspace (MA_PMO_WORKSPACE); see docs/COSTS.md."""
    from ma_pmo.core import budgets
    from ma_pmo.core.i18n import tr

    def money(v: float | None) -> str:
        return "–" if v is None else f"${v:.2f}"

    try:
        if ns.action == "set":
            if ns.warn is None and ns.limit is None:
                print(tr("✗ give --warn, --limit or both",
                         "✗ --warn, --limit 중 하나 이상을 주세요"))
                return 1
            budgets.set_budget(ns.kind, ns.warn, ns.limit, "cli")
        elif ns.action == "clear":
            budgets.set_budget(ns.kind, None, None, "cli")
    except ValueError as e:
        print(f"✗ {e}")
        return 1
    now = budgets.status()
    month, run = now["month"], now["run"]
    print(tr(f"month {now['period']}: spent {money(month['spent_usd'])} · "
             f"warn {money(month['warn_usd'])} · limit {money(month['limit_usd'])}",
             f"{now['period']} 월: 사용 {money(month['spent_usd'])} · "
             f"경고 {money(month['warn_usd'])} · 한도 {money(month['limit_usd'])}"))
    print(tr(f"per run: warn {money(run['warn_usd'])} · limit {money(run['limit_usd'])}",
             f"실행 1회: 경고 {money(run['warn_usd'])} · 한도 {money(run['limit_usd'])}"))
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

    sub.add_parser("agents", help="list worker agents, including installed plugins")

    ws = sub.add_parser("workspace", help="workspaces and memberships")
    wsub = ws.add_subparsers(dest="action", required=True)
    w_create = wsub.add_parser("create", help="create a workspace")
    w_create.add_argument("id")
    w_create.add_argument("--name", default="")
    wsub.add_parser("list", help="list workspaces")
    w_members = wsub.add_parser("members", help="who has which role in a workspace")
    w_members.add_argument("id")
    for verb in ("grant", "revoke"):
        w_verb = wsub.add_parser(verb, help=f"{verb} a role (viewer, operator, approver, admin)")
        w_verb.add_argument("id")
        w_verb.add_argument("principal", help="an API key name or an authenticator subject")
        w_verb.add_argument("role")

    wf = sub.add_parser("workflow", help="workflow versions: validate | draft | versions | publish")
    wfsub = wf.add_subparsers(dest="action", required=True)
    wf_validate = wfsub.add_parser("validate", help="check a workflow JSON file; saves nothing")
    wf_validate.add_argument("file")
    wf_draft = wfsub.add_parser("draft", help="save a workflow JSON file as a new draft version")
    wf_draft.add_argument("file")
    wf_draft.add_argument("--note", default="")
    wf_versions = wfsub.add_parser("versions", help="list a workflow's versions (* = in use)")
    wf_versions.add_argument("id")
    wf_publish = wfsub.add_parser("publish", help="put a draft version in use")
    wf_publish.add_argument("id")
    wf_publish.add_argument("version", type=int)

    bud = sub.add_parser("budget", help="LLM spending limits: show | set | clear")
    budsub = bud.add_subparsers(dest="action", required=True)
    budsub.add_parser("show", help="budgets and this month's spend")
    b_set = budsub.add_parser("set", help="set a warning and/or hard limit in USD")
    b_set.add_argument("kind", choices=["month", "run"])
    b_set.add_argument("--warn", type=float, default=None)
    b_set.add_argument("--limit", type=float, default=None)
    b_clear = budsub.add_parser("clear", help="remove a budget")
    b_clear.add_argument("kind", choices=["month", "run"])

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
    elif ns.command == "agents":
        return _cmd_agents()
    elif ns.command == "workspace":
        return _cmd_workspace(ns)
    elif ns.command == "workflow":
        return _cmd_workflow(ns)
    elif ns.command == "budget":
        return _cmd_budget(ns)
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
