#!/usr/bin/env python3
"""Stdlib-only smoke tests (no FastAPI / Laya)."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from localjev_spark.util import (
    DROP_RESPONSE_EXTRA,
    LoopBoundLock,
    filter_hop_headers,
    last_user_text,
    parse_upstream,
    resolve_backend,
    truncate,
)


class ParseUpstreamTests(unittest.TestCase):
    def test_plain_host_port(self) -> None:
        self.assertEqual(parse_upstream("spark-local:8001"), "http://spark-local:8001/v1")

    def test_http_with_v1(self) -> None:
        self.assertEqual(
            parse_upstream("http://spark:8000/v1"),
            "http://spark:8000/v1",
        )

    def test_https_keeps_scheme(self) -> None:
        self.assertEqual(
            parse_upstream("https://spark.example:8443/v1"),
            "https://spark.example:8443/v1",
        )

    def test_https_default_port(self) -> None:
        self.assertEqual(parse_upstream("https://spark.example/v1"), "https://spark.example:443/v1")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError):
            parse_upstream("  ")


class HeaderTests(unittest.TestCase):
    def test_strips_hop_by_hop(self) -> None:
        out = filter_hop_headers(
            {
                "Host": "localhost:8091",
                "Content-Type": "application/json",
                "Transfer-Encoding": "chunked",
                "Connection": "keep-alive",
                "Authorization": "Bearer x",
            }
        )
        self.assertEqual(out, {"Content-Type": "application/json", "Authorization": "Bearer x"})

    def test_strips_date_server_on_response(self) -> None:
        out = filter_hop_headers(
            {"Date": "Sat", "Server": "uvicorn", "Content-Type": "application/json"},
            extra=DROP_RESPONSE_EXTRA,
        )
        self.assertEqual(out, {"Content-Type": "application/json"})


class MessageTests(unittest.TestCase):
    def test_last_user_string(self) -> None:
        body = {
            "messages": [
                {"role": "system", "content": "x"},
                {"role": "user", "content": " first "},
                {"role": "assistant", "content": "ok"},
                {"role": "user", "content": " second "},
            ]
        }
        self.assertEqual(last_user_text(body), "second")

    def test_last_user_parts(self) -> None:
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "image_url", "image_url": {"url": "x"}},
                    ],
                }
            ]
        }
        self.assertEqual(last_user_text(body), "hello")

    def test_truncate(self) -> None:
        self.assertEqual(truncate("abc", 10), "abc")
        self.assertTrue(truncate("x" * 20, 10).endswith("…"))


async def _contend(lock: asyncio.Lock) -> None:
    """Force asyncio.Lock to bind via a waiting acquire."""
    release = asyncio.Event()

    async def hold() -> None:
        async with lock:
            await release.wait()

    holder = asyncio.create_task(hold())
    await asyncio.sleep(0)
    waiter = asyncio.create_task(lock.acquire())
    await asyncio.sleep(0)
    release.set()
    await waiter
    lock.release()
    await holder


class LoopBoundLockTests(unittest.TestCase):
    def test_module_level_lock_raises_on_later_loop(self) -> None:
        lock = asyncio.Lock()
        asyncio.run(_contend(lock))
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(_contend(lock))
        self.assertIn("different event loop", str(ctx.exception))

    def test_same_loop_reuses_lock(self) -> None:
        holder = LoopBoundLock()

        async def inner() -> None:
            first = holder.get()
            self.assertIs(holder.get(), first)
            await _contend(first)

        asyncio.run(inner())

    def test_new_loop_gets_fresh_lock(self) -> None:
        holder = LoopBoundLock()
        seen: list[asyncio.Lock] = []

        async def inner() -> None:
            lock = holder.get()
            seen.append(lock)
            await _contend(lock)

        asyncio.run(inner())
        asyncio.run(inner())
        self.assertEqual(len(seen), 2)
        self.assertIsNot(seen[0], seen[1])

    def test_invalidate_after_in_flight_write(self) -> None:
        """Unlocked clear can be overwritten by a probe still inside the lock."""
        holder = LoopBoundLock()
        cache: dict[str, str | None] = {"base": "stale"}

        async def race(*, locked: bool) -> str | None:
            cache["base"] = "stale"
            started = asyncio.Event()
            release = asyncio.Event()

            async def probe() -> None:
                async with holder.get():
                    started.set()
                    await release.wait()
                    cache["base"] = "http://dead:8000/v1"

            async def clear() -> None:
                await started.wait()
                if locked:
                    release.set()
                    async with holder.get():
                        cache["base"] = None
                else:
                    cache["base"] = None
                    release.set()

            await asyncio.gather(probe(), clear())
            return cache["base"]

        self.assertEqual(asyncio.run(race(locked=False)), "http://dead:8000/v1")
        self.assertIsNone(asyncio.run(race(locked=True)))


class BackendResolveTests(unittest.TestCase):
    def test_auto_darwin_is_laya_mlx(self) -> None:
        self.assertEqual(resolve_backend("auto", "darwin"), "laya-mlx")
        self.assertEqual(resolve_backend("", "darwin"), "laya-mlx")

    def test_auto_linux_is_laya(self) -> None:
        self.assertEqual(resolve_backend("auto", "linux"), "laya")

    def test_explicit(self) -> None:
        self.assertEqual(resolve_backend("torch", "darwin"), "laya")
        self.assertEqual(resolve_backend("laya-mlx", "darwin"), "laya-mlx")

    def test_mlx_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_backend("mlx", "darwin")


if __name__ == "__main__":
    unittest.main()
