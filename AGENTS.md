# AGENTS.md

Operating contract for [localjev-spark](https://github.com/rimusz/localjev-spark).

## What this repo is

Python service: local System One judge on `:8090` and a soft OpenAI chat proxy to a live Spark (or any `/v1`) on `:8091`. Default backend is Laya. Keep Python while that is true. Product and install narrative: `README.md`.

## Skill copies (must stay identical)

`localjev-spark` (install) and `localjev-auto` (use beside TypeSafe Jev). Copy **both** trees.

| Client | Repo path | User-global install |
|--------|-----------|---------------------|
| Cursor | `.cursor/skills/localjev-*` | `~/.cursor/skills/` |
| Claude Code | `.claude/skills/` and `.agents/skills/` | `~/.claude/skills/` |
| Codex | `.codex/skills/` | `~/.codex/skills/` |
| Grok | `.grok/skills/` | `~/.grok/skills/` |

TypeSafe Jev stays `[mcp_servers.jev]` + `jev-auto`. Agents must label which Jev ran.

## Do

- Install with `./scripts/install.sh` (or the curl-pipe installer from any directory); wait for `:8090` **HTTP 200** (Laya loaded) and `:8091` **HTTP 200** (process up). `:8090` is 503 while loading or if load failed. `:8091` stays 200 even when Spark is missing.
- Chat clients → `:8091/v1` only. Print the provider row; do **not** write AGNT / Grok / Codex / CodexGateway config.
- Uninstall: `localjev-spark uninstall` (keep venv) or `uninstall --purge`. Never delete TypeSafe `jev-auto` or Jev MCP.
- Default bind is `0.0.0.0` with no auth. Trusted LAN/VPN only, or `LOCALJEV_BIND=127.0.0.1`.
- `LOCALJEV_REPO` must be Laya-compatible. Soft fail is judge-predict-fail, not process-down.
- macOS installs `[laya-mlx]`. Linux installs `[laya]` (torch). `LOCALJEV_BACKEND=auto` picks `laya-mlx` or `laya`. Force torch on a Mac with `torch`.

## Do not

- Treat `:8090` as chat.
- Run `sm start` or switch Spark slots from this process.
- Replace hosted TypeSafe Jev MCP.
- Rewrite Laya in Rust unless the user drops that backend.
