from fastapi.testclient import TestClient

from server import main
from server.runtime import RuntimeManager


TOKEN = "H" * 43


def test_health_reports_the_live_extension_runtime(monkeypatch):
    manager = RuntimeManager()
    runtime = manager.get(TOKEN)
    runtime.bridge._socket = object()
    runtime.registry.active_task_id = "task-live"
    manager.mark_agent_connected(runtime.key)
    monkeypatch.setattr(main, "runtimes", manager)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["browser_connected"] is True
    assert response.json()["active_task"] == "task-live"


def test_health_reports_no_browser_when_no_extension_is_connected(monkeypatch):
    monkeypatch.setattr(main, "runtimes", RuntimeManager())

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    assert response.json()["browser_connected"] is False
    assert response.json()["active_task"] is None
