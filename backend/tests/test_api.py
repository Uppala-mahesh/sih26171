from fastapi.testclient import TestClient

from app.dependencies import get_browser_manager, get_screenshot_manager
from app.main import app


class FakeBrowserManager:
    def __init__(self) -> None:
        self.is_running = False

    async def start(self, url: str) -> None:
        self.is_running = True

    async def stop(self) -> None:
        self.is_running = False


class FakeScreenshotManager:
    async def capture(self) -> bytes:
        return b"fakepng"


class BrokenScreenshotManager:
    async def capture(self) -> bytes:
        raise RuntimeError("Browser is not started")


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_browser_start_stop_and_screenshot() -> None:
    app.dependency_overrides[get_browser_manager] = lambda: FakeBrowserManager()
    app.dependency_overrides[get_screenshot_manager] = lambda: FakeScreenshotManager()
    client = TestClient(app)

    start_response = client.post("/api/browser/start", json={"url": "https://example.com"})
    assert start_response.status_code == 200
    assert start_response.json()["status"] == "started"

    screenshot_response = client.get("/api/browser/screenshot")
    assert screenshot_response.status_code == 200
    assert screenshot_response.content == b"fakepng"

    stop_response = client.post("/api/browser/stop")
    assert stop_response.status_code == 200
    assert stop_response.json()["status"] in {"stopped", "already_stopped"}

    app.dependency_overrides.clear()


def test_screenshot_requires_running_browser() -> None:
    app.dependency_overrides[get_screenshot_manager] = lambda: BrokenScreenshotManager()
    client = TestClient(app)

    response = client.get("/api/browser/screenshot")
    assert response.status_code == 409
    assert "Browser is not started" in response.text

    app.dependency_overrides.clear()
