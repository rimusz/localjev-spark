# AGENTS.md

Operating contract for [localjev-spark](https://github.com/rimusz/localjev-spark).

## What this repo is

Python service: local System One on `:8090` and a soft OpenAI chat proxy to a live NVIDIA DGX Spark (or any OpenAI `/v1`) on `:8091`. Backend default is Laya (`LOCALJEV_BACKEND`). Keep Python while Laya/HF is the classifier.

## Agent skill (keep copies in sync)

| Client | Path |
|--------|------|
| Cursor | `.cursor/skills/localjev-spark/` |
| Claude Code | `.claude/skills/localjev-spark/` and `.agents/skills/localjev-spark/` |
| Codex | `.codex/skills/localjev-spark/` |
| Grok | `.grok/skills/localjev-spark/` |

When you edit the skill, update **all** copies (same `SKILL.md`).

## Do

- Install via `./scripts/install.sh` or `localjev-spark serve`.
- Health-check `:8090` and `:8091` after install or config change.
- Point chat clients at `:8091/v1` only.

## Do not

- Treat `:8090` as a chat provider.
- Switch Spark slots or run `sm start` from this process.
- Replace hosted TypeSafe Jev MCP with this service.
- Rewrite the Laya path in Rust unless the user explicitly drops that backend.
