import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, Playwright

from app.browser.browser_state import BrowserState


class BrowserManager:
    def __init__(self, headless: bool = False, screenshot_dir: Path | None = None) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._state = BrowserState()
        self._lock = asyncio.Lock()
        self._screenshot_dir = screenshot_dir or Path("screenshots/raw")
        self._screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def start(self, url: str) -> None:
        async with self._lock:
            if self._state.page:
                await self._state.page.goto(url)
                return

            self._playwright = await async_playwright().start()
            self._state.browser = await self._playwright.chromium.launch(headless=self._headless)
            self._state.context = await self._state.browser.new_context(accept_downloads=True)
            self._state.page = await self._state.context.new_page()
            await self._state.page.goto(url)

    async def stop(self) -> None:
        async with self._lock:
            if self._state.context:
                await self._state.context.close()
            if self._state.browser:
                await self._state.browser.close()
            if self._playwright:
                await self._playwright.stop()

            self._state = BrowserState()
            self._playwright = None

    async def screenshot(self) -> bytes:
        if not self._state.page:
            raise RuntimeError("Browser is not started")

        screenshot_bytes = await self._state.page.screenshot(full_page=True)
        latest_path = self._screenshot_dir / "latest.png"
        latest_path.write_bytes(screenshot_bytes)
        return screenshot_bytes

    @property
    def is_running(self) -> bool:
        return self._state.page is not None
