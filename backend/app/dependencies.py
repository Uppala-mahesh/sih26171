from pathlib import Path

from app.browser.browser_manager import BrowserManager
from app.browser.screenshot import ScreenshotManager
from app.config.settings import get_settings

settings = get_settings()

browser_manager = BrowserManager(
    headless=settings.browser_headless,
    screenshot_dir=Path("screenshots/raw"),
)
screenshot_manager = ScreenshotManager(browser_manager)


def get_browser_manager() -> BrowserManager:
    return browser_manager


def get_screenshot_manager() -> ScreenshotManager:
    return screenshot_manager
