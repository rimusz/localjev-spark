"""Judge API (:8090) + soft Spark OpenAI chat proxy (:8091)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

LOG = logging.getLogger("localjev-spark")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value != "":
            return value
    return default


BIND = _env("LOCALJEV_BIND", default="0.0.0.0")
JUDGE_PORT = int(_env("LOCALJEV_JUDGE_PORT", "LOCALJEV_SIDECAR_PORT", default="8090"))
PROXY_PORT = int(_env("LOCALJEV_PROXY_PORT", default="8091"))
BACKEND = _env("LOCALJEV_BACKEND", default="laya").strip().lower()
MODEL_REPO = _env("LOCALJEV_REPO", default="convaiinnovations/laya")
MODEL_SUBFOLDER = _env("LOCALJEV_SUBFOLDER").strip() or None
SPARK_HOSTS = [
    h.strip()
    for h in _env("LOCALJEV_SPARK_HOSTS", default="spark-local,spark,localhost").split(",")
    if h.strip()
]
SPARK_PORTS = tuple(
    int(p)
    for p in _env("LOCALJEV_SPARK_PORTS", default="8000,8001,8002").split(",")
    if p.strip()
)
SLOT_FOR_PORT = {8000: "qwen", 8001: "deepseek", 8002: "ling"}
UPSTREAM_OVERRIDE = _env("LOCALJEV_SPARK_UPSTREAM").rstrip("/")

CLASSIFY_QUESTIONS: dict[str, Any] = {
    "slot": {
        "type": "choice",
        "instructions": "Which handler should serve this user request?",
        "criteria": {
            "qwen": "General chat, coding help, summarization",
            "deepseek": "Hard reasoning, long context, or math",
            "ling": "Fast or Chinese-first chat",
            "local_code": "Should stay on local coding CLIs, not Spark",
            "human": "Needs a human, not an LLM",
        },
    },
    "needs_trade_confirm": {
        "type": "noul",
        "instructions": "Does this request ask to place or confirm a financial trade?",
        "criteria": {
            "true": "Asks to buy, sell, or confirm a trade",
            "false": "No trade execution requested",
        },
    },
}

_agent: Any = None
_agent_error: str | None = None


def _load_backend() -> None:
    global _agent, _agent_error
    os.environ.setdefault("USE_TF", "0")
    try:
        if BACKEND in {"laya", "localjev"}:
            import laya

            kwargs: dict[str, Any] = {}
            if MODEL_SUBFOLDER:
                kwargs["subfolder"] = MODEL_SUBFOLDER
            _agent = laya.load(MODEL_REPO, **kwargs)
        else:
            raise RuntimeError(f"unknown LOCALJEV_BACKEND={BACKEND!r} (supported: laya)")
        _agent_error = None
        LOG.info("loaded backend=%s repo=%s subfolder=%s", BACKEND, MODEL_REPO, MODEL_SUBFOLDER)
    except Exception as exc:  # noqa: BLE001
        _agent = None
        _agent_error = str(exc)
        LOG.exception("backend load failed: %s", exc)


def _last_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages") or []
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ]
            return " ".join(parts).strip()
    return ""


def _truncate(text: str, limit: int = 480) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def classify(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    if _agent is None:
        raise RuntimeError(_agent_error or "localjev backend not loaded")
    return _agent.predict(state, questions)


judge = FastAPI(title="localjev-spark-judge")
proxy = FastAPI(title="localjev-spark-proxy")


@judge.get("/health")
def judge_health() -> dict[str, Any]:
    ok = _agent is not None
    return {
        "status": "OK" if ok else "DEGRADED",
        "service": "localjev-spark",
        "backend": BACKEND,
        "model": MODEL_REPO,
        "subfolder": MODEL_SUBFOLDER,
        "error": _agent_error,
    }


@judge.post("/v1/systemone")
async def systemone(request: Request) -> JSONResponse:
    body = await request.json()
    state = body.get("state")
    questions = body.get("questions")
    if questions is None or not isinstance(questions, dict):
        return JSONResponse({"error": "questions map required"}, status_code=422)
    if state is None:
        return JSONResponse({"error": "state required"}, status_code=422)
    try:
        raw = await asyncio.to_thread(classify, state, questions)
    except Exception as exc:  # noqa: BLE001
        LOG.exception("predict failed")
        return JSONResponse({"error": str(exc)}, status_code=503)
    answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
    return JSONResponse(
        {
            "service": "localjev-spark",
            "backend": BACKEND,
            "model": MODEL_REPO,
            "answers": answers,
        }
    )


async def _probe_spark() -> tuple[str, int] | None:
    if UPSTREAM_OVERRIDE:
        rest = UPSTREAM_OVERRIDE.replace("http://", "").replace("https://", "")
        hostport = rest.split("/")[0]
        host, _, port_s = hostport.partition(":")
        return host, int(port_s or "8000")
    timeout = httpx.Timeout(3.0, connect=2.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for host in SPARK_HOSTS:
            for port in SPARK_PORTS:
                url = f"http://{host}:{port}/v1/models"
                try:
                    r = await client.get(url)
                    if r.status_code < 500 and r.content:
                        return host, port
                except httpx.HTTPError:
                    continue
    return None


def _classify_chat(text: str) -> tuple[dict[str, Any] | None, str]:
    if not text or _agent is None:
        return None, "bypass"
    try:
        raw = classify(_truncate(text), CLASSIFY_QUESTIONS)
        answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
        LOG.info("classify %s", json.dumps(answers, default=str)[:800])
        return answers if isinstance(answers, dict) else None, "ok"
    except Exception as exc:  # noqa: BLE001
        LOG.warning("classify bypass: %s", exc)
        return None, "bypass"


@proxy.get("/health")
async def proxy_health() -> dict[str, Any]:
    live = await _probe_spark()
    return {
        "status": "OK" if live else "DEGRADED",
        "service": "localjev-spark",
        "backend": BACKEND,
        "localjev": _agent is not None,
        "spark": f"http://{live[0]}:{live[1]}/v1" if live else None,
    }


@proxy.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def openai_passthrough(path: str, request: Request) -> Response:
    live = await _probe_spark()
    if live is None:
        return JSONResponse({"error": "no Spark slot is up"}, status_code=503)
    host, port = live
    upstream = f"http://{host}:{port}/v1/{path}"
    raw = await request.body()
    jev_status = "skip"
    if path.rstrip("/") == "chat/completions" and request.method == "POST":
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}
        text = _last_user_text(body if isinstance(body, dict) else {})
        answers, jev_status = await asyncio.to_thread(_classify_chat, text)
        live_slot = SLOT_FOR_PORT.get(port, str(port))
        if answers:
            slot = answers.get("slot") or {}
            choice = slot.get("choice") if isinstance(slot, dict) else None
            if choice and choice != live_slot:
                LOG.info("slot mismatch choice=%s live=%s (no slot switch)", choice, live_slot)

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length"}
    }
    timeout = httpx.Timeout(600.0, connect=5.0)
    client = httpx.AsyncClient(timeout=timeout)
    req = client.build_request(request.method, upstream, content=raw, headers=headers)
    try:
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        return JSONResponse({"error": str(exc)}, status_code=502)

    out_headers = dict(resp.headers)
    out_headers["x-localjev-status"] = jev_status
    out_headers["x-localjev-spark"] = f"{host}:{port}"
    out_headers["x-localjev-backend"] = BACKEND

    async def stream():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    ctype = resp.headers.get("content-type", "application/json")
    return StreamingResponse(
        stream(), status_code=resp.status_code, media_type=ctype, headers=out_headers
    )


async def run() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _load_backend)
    cfg_a = uvicorn.Config(judge, host=BIND, port=JUDGE_PORT, log_level="info")
    cfg_b = uvicorn.Config(proxy, host=BIND, port=PROXY_PORT, log_level="info")
    await asyncio.gather(uvicorn.Server(cfg_a).serve(), uvicorn.Server(cfg_b).serve())
