---
name: localjev-spark
description: >
  Install, run, health-check, and wire localjev-spark (local System One on
  :8090 plus soft OpenAI chat proxy to a live Spark slot on :8091). Use when
  the user mentions localjev, LocalJev, Laya on Mini/Mac/Linux, spark-via-localjev,
  POST /v1/systemone, or pointing AGNT / Grok Build / CodexGateway at :8091.
---

# localjev-spark

Upstream: https://github.com/rimusz/localjev-spark

Python service. Keep it Python (Laya/transformers). Do **not** rewrite in Rust unless the user drops the Laya backend.

## What it is

| Port | Role |
|------|------|
| `8090` | Judge: `GET /health`, `POST /v1/systemone` |
| `8091` | OpenAI `/v1` proxy → whichever Spark port is already up |

Not TypeSafe Jev (hosted MCP stays on typesafe.ai). Not a chat model on `:8090`. Does **not** run `sm start` or switch Spark slots. If the classifier is down, chat still proxies (`x-localjev-status: bypass`).

## Install (macOS or Linux)

```bash
git clone https://github.com/rimusz/localjev-spark.git
cd localjev-spark
./scripts/install.sh
```

Foreground:

```bash
export USE_TF=0
uv pip install --python ~/.localjev-spark/.venv/bin/python \
  "localjev-spark[laya] @ git+https://github.com/rimusz/localjev-spark.git"
~/.localjev-spark/.venv/bin/localjev-spark serve
```

User services: macOS launchd `ai.localjev.spark`; Linux systemd `--user` `localjev-spark.service`.  
Opt-out autostart: `touch ~/.config/localjev-spark/disable` (install script) or stack flag `~/.config/ai-stack/localjev.disable`.

## Health (required after install or restart)

```bash
curl -sf http://127.0.0.1:8090/health
curl -sf http://127.0.0.1:8091/health
# remote Mini / Tailscale:
curl -sf http://ai-stack:8090/health
curl -sf http://ai-stack:8091/health
```

Expect JSON `service=localjev-spark`, `status=OK`, and proxy `spark=` pointing at a live slot.

Logs: `~/logs/localjev-spark.log`

## Config

`~/.config/localjev-spark/localjev.env` (OSS) or `~/.config/ai-stack/localjev.env` (private-ai-stack Mini):

```bash
LOCALJEV_BACKEND=laya
LOCALJEV_REPO=convaiinnovations/laya
# LOCALJEV_SUBFOLDER=
LOCALJEV_SPARK_HOSTS=spark-local,spark,localhost
LOCALJEV_SPARK_PORTS=8000,8001,8002
# LOCALJEV_SPARK_UPSTREAM=http://spark:8001/v1
```

Re-run `./scripts/install.sh` or `~/bin/setup-localjev.sh` after edits.

## Wire chat clients (use :8091 only)

| Client | Base URL | Key |
|--------|----------|-----|
| AGNT on same host | `http://127.0.0.1:8091/v1` | `not-needed` |
| MacBook → Mini | `http://ai-stack:8091/v1` (LAN: `ai-stack.local`) | `not-needed` |
| Grok Build Settings → Models | same URL, Chat Completions | `not-needed` |
| CodexGateway custom provider | same URL; Gateway does Responses ⇄ Chat | dummy key |

Provider name: `spark-via-localjev`. Keep direct Spark rows (`spark:8000/8001/8002`) as fallbacks.

Do **not** point Codex’s whole gateway or TypeSafe Jev MCP at `:8090`.

## Judge API

```bash
curl -s http://127.0.0.1:8090/v1/systemone -H 'content-type: application/json' -d '{
  "state": "Summarize this error log",
  "questions": {
    "slot": {
      "type": "choice",
      "instructions": "Which Spark slot fits?",
      "criteria": {"qwen": "general", "deepseek": "hard reasoning", "ling": "fast"}
    }
  }
}'
```

## Agent rules

- After install or config change: wait for `:8090` health, then report backend + live Spark URL.
- Do not claim LocalJev replaced TypeSafe Jev or started a Spark slot.
- Do not commit API keys. Dummy `not-needed` is fine for the proxy.
