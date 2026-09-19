---
name: localjev-auto
description: >
  Use localjev-spark (:8090 judgments, :8091 Spark chat) automatically when
  it is healthy, without replacing TypeSafe Jev MCP. Use when localjev,
  LocalJev, Laya, spark-via-localjev, or slot-routing comes up, and when both
  Jevs are installed. Always say which Jev ran.
---

# localjev-auto (beside TypeSafe Jev)

Two **integrations** for the same agent. TypeSafe Jev is hosted (MCP client only on this machine). localjev-spark is the local HTTP process. **Keep both.** Never point `TYPESAFE_API_KEY` or `[mcp_servers.jev]` at localjev-spark.

| Name | How you call it | What it is |
|------|-----------------|------------|
| **TypeSafe Jev** | MCP `jev_*` / Grok `jev__*` ([jkudish/jev-mcp](https://github.com/jkudish/jev-mcp)) | Hosted System One on typesafe.ai |
| **localjev-spark** | `POST http://127.0.0.1:8090/v1/systemone` or chat model `spark-via-localjev` → `:8091` | Local Laya + Spark proxy |

## Which one to use

| Situation | Use |
|-----------|-----|
| Untrusted paste, verify claims, review a diff, **gate “done”** | **TypeSafe Jev** (`jev_screen`, `jev_verify`, `jev_review`, `jev_gate`) — follow `jev-auto` if that skill is present |
| Cheap local classify (trade flag, custom questions) | **localjev** `:8090` if `GET /health` is HTTP 200 (`status=OK`) |
| Coding chat that should go through Spark | Chat client model **spark-via-localjev** (`:8091`), not Jev MCP |
| Judge predict fails, process still up | Chat via `:8091` still works (`bypass`). TypeSafe Jev unchanged |
| Process / both ports down | Skip localjev. TypeSafe Jev still fine. Chat Spark directly |
| User says “use TypeSafe” / “use local Jev” | Honor that for the rest of the turn |

If both could apply, prefer TypeSafe for safety/trust, localjev for Spark routing. You may run **both** and label each result.

## Prove which Jev ran

Say it in the reply, every time:

- TypeSafe: `Jev: TypeSafe MCP` + tool name (`jev_gate`, …). Do not print the API key.
- Local judge: `Jev: localjev-spark :8090` + `backend` / `model` from the JSON (`service` should be `localjev-spark`).
- Spark chat via proxy: `Chat: spark-via-localjev :8091` + `x-localjev-status` / `x-localjev-spark` if you have them.

If you cannot tell, say **unknown** and do not claim Jev ran.

## Local judge call

Only after `curl -sf http://127.0.0.1:8090/health` (or `http://HOST:8090/health`).

```bash
curl -s http://127.0.0.1:8090/v1/systemone -H 'content-type: application/json' -d '{
  "state": "<user request or last user message>",
  "questions": {
    "slot": {
      "type": "choice",
      "instructions": "Which Spark slot fits?",
      "criteria": {"qwen": "general", "deepseek": "hard reasoning", "ling": "fast"}
    }
  }
}'
```

Do not start Spark slots. Do not treat `:8090` as a chat Base URL.

## How this skill is loaded

Same as `localjev-spark`: copy `.grok/skills/localjev-auto` → `~/.grok/skills/`, and the Codex/Cursor/Claude twins. Install the **service** with the `localjev-spark` skill first.
