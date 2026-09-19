# Point chat clients at `:8091`

```
App  →  http://127.0.0.1:8091/v1  →  localjev-spark  →  one live Spark port
```

Key `not-needed`. Chat Completions. Not `:8090`. Remote box: `http://HOST:8091/v1`. The proxy binds `0.0.0.0` with no auth unless `LOCALJEV_BIND=127.0.0.1`.

Upstream Spark (one live): `:8000` Qwen, `:8001` DeepSeek, `:8002` Ling.

| App | Repo |
|-----|------|
| AGNT | https://github.com/agnt-gg/agnt |
| GrokBuild Desktop | https://github.com/rimusz/grok-build-desktop |
| Codex + CodexGateway | https://github.com/openai/codex · https://github.com/rimusz/codex-gateway |

**AGNT** — Settings → Providers → OpenAI-compatible `spark-via-localjev`.

**GrokBuild** — Settings → Models → custom provider, Chat Completions, id `spark-via-localjev` (do not reuse `grok-4.6`). Writes `~/.grok/config.toml`.

**Codex** — Desktop/CLI talk Responses to CodexGateway (`http://127.0.0.1:8765`). In Gateway, add **one** custom provider to `:8091`. Do not set the whole gateway `openai_base_url` to localjev-spark. Leave TypeSafe Jev MCP unchanged.
