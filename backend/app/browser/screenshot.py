from app.browser.browser_manager import BrowserManager


class ScreenshotManager:
    def __init__(self, browser_manager: BrowserManager) -> None:
        self.browser_manager = browser_manager

    async def capture(self) -> bytes:
        return await self.browser_manager.screenshot()
