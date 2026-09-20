# localjev-spark

A **local** [System One](https://docs.typesafe.ai/concepts/system-one.md) judge, plus an optional OpenAI chat hop in front of [NVIDIA DGX Spark](https://www.nvidia.com/en-us/products/workstations/dgx-spark/).

## Official Jev vs this repo

**[Jev](https://docs.typesafe.ai/introduction.md)** is TypeSafe’s hosted System One model — a decision model, not a chat model. You send `state` plus typed questions (`noul` / `choice` / `score`) to [`POST https://api.typesafe.ai/v1/systemone`](https://docs.typesafe.ai/api.md) and get calibrated probabilities back. Docs: [docs.typesafe.ai](https://docs.typesafe.ai). Agents usually call it through [jev-mcp](https://github.com/jkudish/jev-mcp) (`jev_verify`, `jev_gate`, …) with a `TYPESAFE_API_KEY`.

This repo is **not** official Jev and is **not** affiliated with TypeSafe. It is a local clone of that request shape, running [Laya](https://huggingface.co/convaiinnovations/laya) on your machine (`POST /v1/systemone` on `:8090`), plus a soft proxy so chat clients can reach Spark through `:8091`. Keep hosted Jev for trust, untrusted paste, and “are we done?”. Use this for an on-box judge and a classified hop onto Spark.

| Port | What |
|------|------|
| `8090` | Local System One — `GET /health`, `POST /v1/systemone` (not a chat model) |
| `8091` | OpenAI chat proxy → the Spark slot that is already up |

Spark writes the tokens (one live model). This process classifies the last user message, then forwards. Bind is `0.0.0.0` with **no auth** — trusted LAN/VPN only, or `LOCALJEV_BIND=127.0.0.1`. Needs macOS or Linux, [uv](https://docs.astral.sh/uv/), a few GB for Laya on first start, and Spark already serving if you want chat.

## Install

### Ask an agent to install

Copy into Grok, Codex, Cursor, or Claude:

```text
Install localjev-spark from https://github.com/rimusz/localjev-spark
Follow the localjev-spark skill. Run ./scripts/install.sh (or the curl | bash
installer). That also copies localjev-spark + localjev-auto into ~/.cursor/skills,
~/.claude/skills, ~/.codex/skills, and ~/.grok/skills. Wait until :8090 /health
is HTTP 200 (Laya loaded) and :8091 is HTTP 200, then tell me backend, model,
which Spark URL the proxy found, and which skill homes were written.
Chat base URL is http://127.0.0.1:8091/v1 — not :8090.
Do not start Spark models or change TypeSafe Jev MCP.
```

### Install yourself

```bash
git clone https://github.com/rimusz/localjev-spark.git
cd localjev-spark
./scripts/install.sh
```

Or, from any directory (installs the published GitHub tree):

```bash
curl -fsSL https://raw.githubusercontent.com/rimusz/localjev-spark/main/scripts/install.sh | bash
```

That puts a venv in `~/.localjev-spark` and a user service (macOS launchd `ai.localjev.spark`, Linux `systemd --user`). First run can take several minutes. The installer waits for `:8090` **HTTP 200** (Laya loaded) and `:8091` **HTTP 200** (process up); it warns if Spark is not found yet.

```bash
~/.localjev-spark/.venv/bin/localjev-spark status
```

`:8090` is **200** / `"OK"` when Laya loaded; **503** while `loading` or if load failed (`DEGRADED`). `:8091` is **200** whenever the process is up; `"spark"` is the live base URL or `null`.

Restart Grok / Codex / Cursor / Claude so the new skills load. Then add **one** chat model in the app UI (see [Use it](#use-it)). The installer does **not** write AGNT / Grok / Codex config.

Logs: `~/logs/localjev-spark.log`. Config: `~/.config/localjev-spark/localjev.env` (re-run `./scripts/install.sh` after edits). Foreground: `USE_TF=0 ~/.localjev-spark/.venv/bin/localjev-spark serve`.

Uninstall (stops the service, keeps the venv):

```bash
~/.localjev-spark/.venv/bin/localjev-spark uninstall
# or: curl -fsSL https://raw.githubusercontent.com/rimusz/localjev-spark/main/scripts/uninstall.sh | bash
```

`--purge` also deletes `~/.localjev-spark`, `~/.config/localjev-spark`, and the localjev skills. It does **not** touch TypeSafe `jev-auto` or Jev MCP.

## Use it

```
GrokBuild / AGNT / Codex  →  http://127.0.0.1:8091/v1  →  localjev-spark  →  Spark :8000|:8001|:8002
```

You add **one extra OpenAI-compatible model** named `spark-via-localjev` in the app UI (this repo never writes those settings). Chat still comes from Spark; localjev-spark only classifies, then forwards. Keep your existing Spark / Grok / GPT rows.

| App | Repo | What you do |
|-----|------|-------------|
| [AGNT](https://github.com/agnt-gg/agnt) | Settings → Providers → add custom OpenAI | Base `http://127.0.0.1:8091/v1`, key `not-needed` |
| [GrokBuild Desktop](https://github.com/rimusz/grok-build-desktop) | Settings → Models → custom provider | Same URL, **Chat Completions**, id `spark-via-localjev` (not `grok-4.6`) |
| [Codex](https://github.com/openai/codex) via [CodexGateway](https://github.com/rimusz/codex-gateway) | Gateway Settings → add **one** custom provider | Same URL. Codex itself stays on `http://127.0.0.1:8765` (Responses). Do not point the whole gateway at `:8091`. |

If localjev-spark runs on another machine, use `http://HOST:8091/v1` instead of localhost. Extra clicks: [docs/clients.md](docs/clients.md).

`:8090` is not a chat provider.

## How it behaves

**Laya failing is not an outage.** If the judge cannot load or predict, `:8091` still forwards to Spark (`x-localjev-status: bypass`). **If localjev-spark is stopped, both ports are dead** — point the client at Spark directly.

Spark is **one** live model. The proxy tries these ports in order and uses the first that answers (`GET /v1/models`):

| Spark port | Usual model (convention only) |
|------------|-------------------------------|
| `8000` | Qwen |
| `8001` | DeepSeek |
| `8002` | Ling |

Hosts tried: `spark-local`, `spark`, `localhost`. Pin: `LOCALJEV_SPARK_UPSTREAM=http://YOUR-SPARK:8001/v1`.

The **judge** is still Laya. On **macOS** the installer uses [laya-mlx](https://github.com/mizorewww/laya-mlx) (`LOCALJEV_BACKEND=laya-mlx`). On **Linux** it uses official torch [laya](https://pypi.org/project/laya/) (`LOCALJEV_BACKEND=laya`). `LOCALJEV_REPO` must be a Laya-compatible Hugging Face id (default `convaiinnovations/laya`). Force torch on a Mac with `LOCALJEV_BACKEND=torch`. Edit `~/.config/localjev-spark/localjev.env` and re-run `./scripts/install.sh`. To change the **Spark** slot, start that slot or set `LOCALJEV_SPARK_UPSTREAM` — do not change `LOCALJEV_REPO`.

## Same host as official Jev

Two **integrations** for the same agent — not two Jev servers on your box. Official Jev stays at typesafe.ai (MCP client only here). localjev-spark is the local HTTP process. **Keep both.** This process does **not** use MCP and does **not** replace [jev-mcp](https://github.com/jkudish/jev-mcp) / `jev-auto`.

```
Grok / Codex / Cursor / Claude  (same Mac or Linux box)
  ├─ MCP  jev_* / jev-auto     →  typesafe.ai          hosted Jev
  ├─ chat spark-via-localjev   →  127.0.0.1:8091  →  Spark
  └─ optional POST /v1/systemone →  127.0.0.1:8090    local judge
```

| | Hosted TypeSafe Jev | localjev-spark |
|--|---------------------|----------------|
| How | MCP client + `TYPESAFE_API_KEY` → typesafe.ai | Local HTTP on `:8090` / `:8091` |
| On this machine | MCP config only | The `localjev-spark` process |
| Use for | Trust, untrusted paste, “are we done?” | Spark hop + cheap local classify |
| Agent says | `Jev: TypeSafe MCP` | `Jev: localjev-spark :8090` or `Chat: spark-via-localjev :8091` |

Do not point `[mcp_servers.jev]` or `TYPESAFE_API_KEY` at `:8090`. No second Jev MCP is required.

## How to use the skills

Two skills, same copies under `.grok/skills`, `.codex/skills`, `.cursor/skills`, `.claude/skills`, `.agents/skills`:

| Skill | When |
|-------|------|
| `localjev-spark` | Install, health, wire `:8091` |
| `localjev-auto` | After install: use local `:8090` / `:8091` **next to** TypeSafe Jev MCP, and **say which Jev ran** |

**Load them**

`./scripts/install.sh` already copies both skills into `~/.cursor/skills`, `~/.claude/skills`, `~/.agents/skills`, `~/.codex/skills`, and `~/.grok/skills`. Restart the app or start a new session so they are rescanned. Opening this repo also loads the project copies. Some clients accept `$localjev-spark` / `$localjev-auto` when that skill is loaded.

## License

Apache-2.0. Not affiliated with TypeSafe, NVIDIA, or Laya.
