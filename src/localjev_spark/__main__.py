from __future__ import annotations

import argparse
import asyncio
import os
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="localjev-spark",
        description="Local System One API (:8090) and Spark chat proxy (:8091)",
    )
    sub = parser.add_subparsers(dest="cmd")
    serve = sub.add_parser("serve", help="run the judge API and Spark chat proxy")
    serve.add_argument("--bind", default=os.environ.get("LOCALJEV_BIND", "0.0.0.0"))
    serve.add_argument(
        "--judge-port",
        type=int,
        default=int(os.environ.get("LOCALJEV_JUDGE_PORT", os.environ.get("LOCALJEV_SIDECAR_PORT", "8090"))),
    )
    serve.add_argument(
        "--proxy-port",
        type=int,
        default=int(os.environ.get("LOCALJEV_PROXY_PORT", "8091")),
    )
    args = parser.parse_args(argv)
    if args.cmd != "serve":
        parser.print_help()
        sys.exit(2)
    os.environ["LOCALJEV_BIND"] = args.bind
    os.environ["LOCALJEV_JUDGE_PORT"] = str(args.judge_port)
    os.environ["LOCALJEV_PROXY_PORT"] = str(args.proxy_port)
    from localjev_spark.server import run

    asyncio.run(run())


if __name__ == "__main__":
    main()
