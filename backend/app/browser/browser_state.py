from dataclasses import dataclass
from playwright.async_api import Browser, BrowserContext, Page


@dataclass
class BrowserState:
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
