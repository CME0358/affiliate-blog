"""
night_factory_browser_pool.py — Shared Playwright browser for Night Factory LW (bounded concurrency).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

_POOL: "NightFactoryBrowserPool | None" = None


class NightFactoryBrowserPool:
    def __init__(self, *, max_contexts: int = 2) -> None:
        self._max_contexts = max_contexts
        self._sem = asyncio.Semaphore(max_contexts)
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()
        self.launch_count = 0
        self.context_count = 0

    async def start(self) -> None:
        async with self._lock:
            if self._browser:
                return
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self.launch_count += 1

    async def close(self) -> None:
        async with self._lock:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

    @asynccontextmanager
    async def context(self):
        await self.start()
        await self._sem.acquire()
        ctx = None
        try:
            ctx = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="ja-JP",
            )
            self.context_count += 1
            yield ctx
        finally:
            if ctx:
                await ctx.close()
            self._sem.release()


def get_browser_pool(*, max_contexts: int = 2) -> NightFactoryBrowserPool:
    global _POOL
    if _POOL is None:
        _POOL = NightFactoryBrowserPool(max_contexts=max_contexts)
    return _POOL


async def shutdown_browser_pool() -> None:
    global _POOL
    if _POOL:
        await _POOL.close()
        _POOL = None
