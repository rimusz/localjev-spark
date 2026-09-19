"""Judge API (:8090) + soft Spark OpenAI chat proxy (:8091)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from localjev_spark.util import (
    DROP_RESPONSE_EXTRA,
    LoopBoundLock,
    filter_hop_headers,
    last_user_text,
    parse_upstream,
    truncate,
)

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
UPSTREAM_OVERRIDE = _env("LOCALJEV_SPARK_UPSTREAM").rstrip("/")
PROBE_TTL = float(_env("LOCALJEV_PROBE_TTL", default="5"))

# Chat hop only — slot routing is noise on Laya; callers still send any questions to :8090.
CLASSIFY_QUESTIONS: dict[str, Any] = {
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
_load_done = False
_classify_lock = threading.Lock()
_cached_base: str | None = None
_cached_at = 0.0
_probe_lock = LoopBoundLock()


def _load_backend() -> None:
    global _agent, _agent_error, _load_done
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
    finally:
        _load_done = True


def classify(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
    if _agent is None:
        raise RuntimeError(_agent_error or "localjev backend not loaded")
    with _classify_lock:
        return _agent.predict(state, questions)


judge = FastAPI(title="localjev-spark-judge")
proxy = FastAPI(title="localjev-spark-proxy")


def _judge_payload() -> dict[str, Any]:
    if _agent is not None:
        status = "OK"
    elif not _load_done:
        status = "loading"
    else:
        status = "DEGRADED"
    return {
        "status": status,
        "service": "localjev-spark",
        "backend": BACKEND,
        "model": MODEL_REPO,
        "subfolder": MODEL_SUBFOLDER,
        "error": _agent_error,
    }


@judge.get("/health")
def judge_health() -> JSONResponse:
    payload = _judge_payload()
    code = 200 if payload["status"] == "OK" else 503
    return JSONResponse(payload, status_code=code)


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


async def _models_ok(client: httpx.AsyncClient, base: str) -> bool:
    try:
        r = await client.get(f"{base.rstrip('/')}/models")
        return r.status_code < 500 and bool(r.content)
    except httpx.HTTPError:
        return False


def _clear_spark_cache() -> None:
    """Drop cached Spark base. Caller must already hold ``_probe_lock``."""
    global _cached_base, _cached_at
    _cached_base = None
    _cached_at = 0.0


async def _invalidate_spark_cache() -> None:
    async with _probe_lock.get():
        _clear_spark_cache()


async def _probe_spark() -> str | None:
    """Return live OpenAI base (`http://host:port/v1`) or None. Cached for PROBE_TTL seconds."""
    global _cached_base, _cached_at
    now = time.monotonic()
    async with _probe_lock.get():
        if _cached_base and (now - _cached_at) < PROBE_TTL:
            return _cached_base
        timeout = httpx.Timeout(3.0, connect=2.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if UPSTREAM_OVERRIDE:
                try:
                    base = parse_upstream(UPSTREAM_OVERRIDE)
                except ValueError:
                    _clear_spark_cache()
                    return None
                if await _models_ok(client, base):
                    _cached_base = base
                    _cached_at = time.monotonic()
                    return base
                _clear_spark_cache()
                return None
            for host in SPARK_HOSTS:
                for port in SPARK_PORTS:
                    base = f"http://{host}:{port}/v1"
                    if await _models_ok(client, base):
                        _cached_base = base
                        _cached_at = time.monotonic()
                        return base
        _clear_spark_cache()
        return None


def _classify_chat(text: str) -> tuple[dict[str, Any] | None, str]:
    if not text or _agent is None:
        return None, "bypass"
    try:
        raw = classify(truncate(text), CLASSIFY_QUESTIONS)
        answers = raw.get("answers", raw) if isinstance(raw, dict) else raw
        LOG.info("classify %s", json.dumps(answers, default=str)[:800])
        return answers if isinstance(answers, dict) else None, "ok"
    except Exception as exc:  # noqa: BLE001
        LOG.warning("classify bypass: %s", exc)
        return None, "bypass"


@proxy.get("/health")
async def proxy_health() -> JSONResponse:
    live = await _probe_spark()
    payload = {
        "status": "OK" if live else "DEGRADED",
        "service": "localjev-spark",
        "backend": BACKEND,
        "localjev": _agent is not None,
        "spark": live,
    }
    # Process-up is 200 even with no Spark — that is not a localjev outage.
    return JSONResponse(payload, status_code=200)


@proxy.api_route("/v1/{path:path}", methods=["GET", "POST"])
async def openai_passthrough(path: str, request: Request) -> Response:
    live = await _probe_spark()
    if live is None:
        return JSONResponse({"error": "no Spark slot is up"}, status_code=503)
    upstream = f"{live.rstrip('/')}/{path}"
    raw = await request.body()
    jev_status = "skip"
    if path.rstrip("/") == "chat/completions" and request.method == "POST":
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}
        text = last_user_text(body if isinstance(body, dict) else {})
        _answers, jev_status = await asyncio.to_thread(_classify_chat, text)

    headers = filter_hop_headers(request.headers)
    timeout = httpx.Timeout(600.0, connect=5.0)
    client = httpx.AsyncClient(timeout=timeout)
    req = client.build_request(request.method, upstream, content=raw, headers=headers)
    try:
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        await _invalidate_spark_cache()
        return JSONResponse({"error": str(exc)}, status_code=502)

    out_headers = filter_hop_headers(resp.headers, extra=DROP_RESPONSE_EXTRA)
    out_headers["x-localjev-status"] = jev_status
    out_headers["x-localjev-spark"] = live
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
    load_fut = loop.run_in_executor(None, _load_backend)
    cfg_a = uvicorn.Config(judge, host=BIND, port=JUDGE_PORT, log_level="info")
    cfg_b = uvicorn.Config(proxy, host=BIND, port=PROXY_PORT, log_level="info")
    await asyncio.gather(
        uvicorn.Server(cfg_a).serve(),
        uvicorn.Server(cfg_b).serve(),
        load_fut,
    )
