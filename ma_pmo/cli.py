"""`ma-pmo` command-line entry point (installed via `pip install ma-pmo`).

Examples:
    ma-pmo init-db                 # create SQLite schema + load demo fixtures
    ma-pmo serve --port 8000       # start the FastAPI server
    ma-pmo eval                    # run the H1–H5 evaluation harness
    ma-pmo harness full_suite      # run an experiment from the harness
"""
from __future__ import annotations

import argparse
import sys

from ma_pmo import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ma-pmo", description="MA-PMO multi-agent PMO orchestration"
    )
    parser.add_argument("--version", action="version", version=f"ma-pmo {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create the schema and load demo fixtures")

    serve = sub.add_parser("serve", help="start the FastAPI server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")

    sub.add_parser("eval", help="run the H1–H5 evaluation harness")

    harness = sub.add_parser("harness", help="run an experiment (use 'list' to see all)")
    harness.add_argument("args", nargs=argparse.REMAINDER)

    ns = parser.parse_args(argv)

    if ns.command == "init-db":
        from ma_pmo.db.init import main as init_main

        init_main()
    elif ns.command == "serve":
        import uvicorn

        uvicorn.run("ma_pmo.api.main:app", host=ns.host, port=ns.port, reload=ns.reload)
    elif ns.command == "eval":
        from ma_pmo.eval.run import main as eval_main

        eval_main()
    elif ns.command == "harness":
        from ma_pmo.harness.cli import main as harness_main

        return harness_main(ns.args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
