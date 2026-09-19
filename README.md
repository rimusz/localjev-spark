# localjev-spark

Local **System One** judgments plus a **soft** OpenAI-compatible chat proxy to a live [NVIDIA DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/) (or any OpenAI `/v1` slot).

It is **not** a hosted TypeSafe Jev replacement and it does **not** start Spark models. Chat always goes to whichever Spark port is already up. If the classifier is down, chat still works (`x-localjev-status: bypass`).

| Port | Role |
|------|------|
| `8090` | `GET /health`, `POST /v1/systemone` |
| `8091` | OpenAI `/v1` proxy → live Spark slot |

Runs on **macOS** and **Linux** (Apple Silicon or x86_64 with enough RAM for the classifier).

## Install

Needs [uv](https://docs.astral.sh/uv/) (or Python 3.11+). First start downloads the Laya weights.

```bash
git clone https://github.com/rimusz/localjev-spark.git
cd localjev-spark
./scripts/install.sh          # venv + localjev-spark[laya] + user service
# or one-shot, no clone:
curl -fsSL https://raw.githubusercontent.com/rimusz/localjev-spark/main/scripts/install.sh | bash
```

Foreground:

```bash
uv venv --python 3.12 ~/.localjev-spark/.venv
uv pip install --python ~/.localjev-spark/.venv/bin/python "localjev-spark[laya] @ git+https://github.com/rimusz/localjev-spark.git"
export USE_TF=0
~/.localjev-spark/.venv/bin/localjev-spark serve
```

Point AGNT, Grok Build, or CodexGateway (Chat Completions) at:

```text
http://127.0.0.1:8091/v1
```

API key can be `not-needed`.

## Config

Optional `~/.config/localjev-spark/localjev.env` (sourced by `install.sh`):

```bash
LOCALJEV_BACKEND=laya
LOCALJEV_REPO=convaiinnovations/laya
# LOCALJEV_SUBFOLDER=
LOCALJEV_SPARK_HOSTS=spark-local,spark,localhost
LOCALJEV_SPARK_PORTS=8000,8001,8002
# LOCALJEV_SPARK_UPSTREAM=http://spark:8001/v1
```

`install.sh` installs a **user** service:

- macOS: launchd `ai.localjev.spark`
- Linux: systemd `--user` `localjev-spark.service`

Disable autostart: `touch ~/.config/localjev-spark/disable`.

## Clients

Do **not** treat `:8090` as a chat model. That is judgments only.

| Client | How |
|--------|-----|
| OpenAI-compatible chat | Base URL `http://HOST:8091/v1` |
| TypeSafe-style evaluate | `POST http://HOST:8090/v1/systemone` |
| Hosted TypeSafe Jev MCP | Leave on typesafe.ai; this is a local clone API |

Example judge call:

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

## License

Apache-2.0. Not affiliated with TypeSafe, NVIDIA, or Laya beyond using their public packages/models.
