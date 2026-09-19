---
name: localjev-spark
description: >
  Install and operate localjev-spark: local System One judge on :8090 and a
  soft OpenAI chat proxy to a live Spark slot on :8091. Use when the user
  says install localjev, LocalJev, localjev-spark, Laya proxy, spark-via-localjev,
  or wants Grok / Codex / Cursor / Claude / AGNT pointed at :8091. Also use
  when copying this skill into ~/.grok/skills, ~/.codex/skills, ~/.cursor/skills,
  or ~/.claude/skills.
---

# localjev-spark

Repo: https://github.com/rimusz/localjev-spark  
Read `README.md` in that repo for the full product story. This skill is the **install + verify + wire** runbook for agents (Grok, Codex, Cursor, Claude Code).

Users may paste the install prompt from the README. Treat that as: copy **this skill and `localjev-auto`** if needed, run `./scripts/install.sh`, health-check both ports, report Spark upstream, then give `:8091` client fields only if they use AGNT / GrokBuild / CodexGateway.

**Keep official Jev.** Copy `localjev-auto` beside `jev-auto`. Do **not** remove, rewrite, or retarget TypeSafe Jev MCP (`[mcp_servers.jev]`, `TYPESAFE_API_KEY`, `jev-mcp`).

Python + Laya. Do **not** rewrite in Rust unless the user drops the Laya backend.

## What you are installing

| Port | Role |
|------|------|
| `8090` | Judge only: `GET /health`, `POST /v1/systemone` |
| `8091` | Chat Completions proxy → live Spark (no `sm start`) |

Not TypeSafe Jev MCP. Not a chat model on `:8090`. Soft fail: if the **process is up** but Laya fails to load/predict, `:8091` still proxies (`x-localjev-status: bypass`). If the process is down, both ports are down. Default bind `0.0.0.0` has no auth — trusted network only, or `LOCALJEV_BIND=127.0.0.1`.

## 0. Install skills for every supported client

Always copy **both** `localjev-spark` and `localjev-auto` into **all** of these homes (not only the client you are in). `./scripts/install.sh` does this. If you installed some other way, run:

```bash
git clone --depth 1 https://github.com/rimusz/localjev-spark.git /tmp/localjev-spark
for tree in .cursor .claude .agents .codex .grok; do
  mkdir -p "${HOME}/${tree}/skills"
  rm -rf "${HOME}/${tree}/skills/localjev-spark" "${HOME}/${tree}/skills/localjev-auto"
  cp -R /tmp/localjev-spark/${tree}/skills/localjev-spark /tmp/localjev-spark/${tree}/skills/localjev-auto \
    "${HOME}/${tree}/skills/"
done
```

Do **not** delete `jev-auto` or any TypeSafe Jev MCP config. In a checkout of this repo, project skills already load from the same trees; keep those `SKILL.md` files identical.

## 1. Install the service (macOS or Linux)

Need network, a writable `$HOME`, and enough disk for torch + Laya.

```bash
git clone https://github.com/rimusz/localjev-spark.git
cd localjev-spark
chmod +x scripts/install.sh
./scripts/install.sh
```

Or from any directory (no local checkout):

```bash
curl -fsSL https://raw.githubusercontent.com/rimusz/localjev-spark/main/scripts/install.sh | bash
```

Foreground alternative:

```bash
export USE_TF=0
uv venv --python 3.12 ~/.localjev-spark/.venv
uv pip install --python ~/.localjev-spark/.venv/bin/python \
  "localjev-spark[laya] @ git+https://github.com/rimusz/localjev-spark.git"
~/.localjev-spark/.venv/bin/localjev-spark serve
```

Do **not** fire-and-forget. Stream installer output. First model download can take minutes.

## 2. Health (required)

```bash
curl -s -o /tmp/lj0.json -w "%{http_code}\n" http://127.0.0.1:8090/health
curl -s -o /tmp/lj1.json -w "%{http_code}\n" http://127.0.0.1:8091/health
```

`:8090` is **200** only when Laya loaded (`status=OK`). **503** means the process is up (`loading` or `DEGRADED`) — wait, do not reinstall. `:8091` is **200** when the process is bound even if Spark is missing.

From another machine: `http://HOST:8090/health` and `http://HOST:8091/health`.

Pass install only if `:8090` is 200 and `:8091` is 200. Report `:8090` `backend` / `model` and `:8091` `spark`. If `spark` is null, say Spark was not found (chat will 503 until a slot is up). On failure, tail `~/logs/localjev-spark.log` (20 lines) and stop claiming it is installed.

## 3. Config (only if they need a different Spark host)

`~/.config/localjev-spark/localjev.env`:

```bash
LOCALJEV_BACKEND=laya
# Laya-compatible Hugging Face id only (not an arbitrary chat model)
LOCALJEV_REPO=convaiinnovations/laya
# LOCALJEV_BIND=127.0.0.1
LOCALJEV_SPARK_HOSTS=spark-local,spark,localhost
# Probe order (one live slot): 8000 Qwen, 8001 DeepSeek, 8002 Ling.
# Or set LOCALJEV_SPARK_UPSTREAM=http://YOUR-SPARK:8001/v1
LOCALJEV_SPARK_PORTS=8000,8001,8002
```

Then re-run `./scripts/install.sh`.

## 4. Wire chat clients (`:8091` only)

```
GrokBuild / AGNT / Codex  →  http://127.0.0.1:8091/v1  →  localjev-spark  →  Spark :8000|:8001|:8002
```

Add **one** extra model `spark-via-localjev`. Same-host URL `http://127.0.0.1:8091/v1`. Other host: `http://HOST:8091/v1`. Key `not-needed`. Chat Completions. Keep existing Spark / Grok / GPT rows. Details: `docs/clients.md`.

| App | Repo | What you do |
|-----|------|-------------|
| AGNT | https://github.com/agnt-gg/agnt | Settings → Providers → custom OpenAI, that base URL |
| GrokBuild Desktop | https://github.com/rimusz/grok-build-desktop | Settings → Models → custom, Chat Completions, id `spark-via-localjev` (never `grok-4.6`). Writes `~/.grok/config.toml` |
| Codex via CodexGateway | https://github.com/openai/codex · https://github.com/rimusz/codex-gateway | Gateway Settings → **one** custom provider to `:8091`. Codex stays on `http://127.0.0.1:8765` (Responses). Do not set gateway `openai_base_url` or `[mcp_servers.jev]` to localjev-spark |

**Print the provider row. Do not write client config.** Do not edit `~/.grok/config.toml`, Codex `config.toml`, AGNT settings, or CodexGateway `openai_base_url`. The user adds `spark-via-localjev` in the app UI.

**If this session is Grok:** after a healthy install, **describe** the GrokBuild model row if they want Spark-via-localjev in the picker. Do not write `~/.grok/config.toml`. Installing the *service* is steps 1–2 even if they do not change models yet.

**If this session is Codex:** install the service (steps 0–2), then the Gateway Settings steps. Do not retarget all of Codex at `:8091`.

**Cursor / Claude:** use this skill to install and verify the service; they are not chat frontends for `:8091` unless the user also runs AGNT/GrokBuild/CodexGateway.

## 5. Agent rules

- After install: health both ports, then report which skill homes were written (`~/.cursor/skills`, `~/.claude/skills`, `~/.codex/skills`, `~/.grok/skills`).
- Leave TypeSafe Jev MCP and `jev-auto` in place. Install `localjev-auto` next to it in every client home.
- Do not say TypeSafe Jev was replaced or that a Spark slot was started.
- Dummy key `not-needed` only; no real secrets in git.
- `:8090` is never a chat Base URL.
- Uninstall: `~/.localjev-spark/.venv/bin/localjev-spark uninstall` (keep venv) or `uninstall --purge`. Never delete TypeSafe `jev-auto` or Jev MCP config.
