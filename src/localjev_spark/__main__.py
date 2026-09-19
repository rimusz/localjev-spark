from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _fetch(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                body = {"raw": raw}
            return int(resp.status), body if isinstance(body, dict) else {"raw": body}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"error": raw}
        return int(exc.code), body if isinstance(body, dict) else {"error": raw}
    except OSError as exc:
        return 0, {"error": str(exc)}


def status() -> int:
    judge_port = os.environ.get("LOCALJEV_JUDGE_PORT", "8090")
    proxy_port = os.environ.get("LOCALJEV_PROXY_PORT", "8091")
    j_code, j_body = _fetch(f"http://127.0.0.1:{judge_port}/health")
    p_code, p_body = _fetch(f"http://127.0.0.1:{proxy_port}/health")
    print(f"judge  :{judge_port}  HTTP {j_code or 'down'}  {j_body.get('status', j_body.get('error', ''))}")
    if j_body.get("backend") or j_body.get("model"):
        print(f"        backend={j_body.get('backend')}  model={j_body.get('model')}")
    print(f"proxy  :{proxy_port}  HTTP {p_code or 'down'}  {p_body.get('status', p_body.get('error', ''))}")
    print(f"        spark={p_body.get('spark')}")
    print()
    print("Add one chat model (keep existing Spark / Grok / GPT rows):")
    print("  Base URL   http://127.0.0.1:8091/v1")
    print("  API key    not-needed")
    print("  Model id   spark-via-localjev")
    print("  Protocol   Chat Completions  (not :8090)")
    ok = j_code == 200 and p_code == 200
    return 0 if ok else 1


def uninstall(purge: bool) -> int:
    home = Path(os.environ.get("LOCALJEV_HOME", Path.home() / ".localjev-spark"))
    config = Path.home() / ".config/localjev-spark"
    uname = os.uname().sysname
    if uname == "Darwin":
        uid = os.getuid()
        for label in ("ai.localjev.spark", "ai.localjev.sidecar", "ai.laya.sidecar"):
            subprocess.run(
                ["launchctl", "bootout", f"gui/{uid}/{label}"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            plist = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
            plist.unlink(missing_ok=True)
        print("stopped launchd ai.localjev.spark")
    elif uname == "Linux":
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", "localjev-spark.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        unit = Path.home() / ".config/systemd/user/localjev-spark.service"
        unit.unlink(missing_ok=True)
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("stopped systemd --user localjev-spark")
    else:
        print(f"stop the process on {uname} yourself", file=sys.stderr)

    if not purge:
        print(f"left {home} (pass --purge to delete venv, config, and localjev skills)")
        return 0

    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(config, ignore_errors=True)
    log = Path.home() / "logs" / "localjev-spark.log"
    log.unlink(missing_ok=True)
    for tree in (".cursor", ".claude", ".agents", ".codex", ".grok"):
        for name in ("localjev-spark", "localjev-auto"):
            shutil.rmtree(Path.home() / tree / "skills" / name, ignore_errors=True)
    print(f"purged {home}, {config}, localjev skills (jev-auto / Jev MCP left alone)")
    return 0


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
    sub.add_parser("status", help="print health and the chat client row")
    un = sub.add_parser("uninstall", help="stop the user service (keeps the venv)")
    un.add_argument(
        "--purge",
        action="store_true",
        help="also delete ~/.localjev-spark, config, and localjev skills (not jev-auto)",
    )
    args = parser.parse_args(argv)
    if args.cmd == "status":
        sys.exit(status())
    if args.cmd == "uninstall":
        sys.exit(uninstall(purge=args.purge))
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
