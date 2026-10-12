"""The agent must land in a tab it can drive, not always spawn a new one.

Opening a fresh tab for every task is what makes the browser feel hijacked: you
ask for something on the page you are already looking at and a new tab appears,
steals focus, and your own tab is left stranded behind it.

These tests pin the tab-selection rule, including the exclusions that keep the
agent away from the operator's cockpit.
"""
import pytest

from server.loop import Task


@pytest.fixture
def task(monkeypatch):
    t = Task("open example.com and read the heading")
    return t


def _tabs(*items):
    """Mirror BrowserBridge.request, which already unwraps the ``result`` key."""
    return {"tabs": list(items), "active_tab_id": items[0]["id"] if items else None}


class TestLandingReusesAnExistingTab:
    @pytest.mark.asyncio
    async def test_reuses_the_active_http_tab(self, task, monkeypatch):
        from server import loop as loop_mod

        calls = []

        async def fake_request(op, args, task_id=None, **kw):
            calls.append((op, args))
            if op == "tabs":
                return _tabs(
                    {"id": 7, "url": "https://example.com/page"},
                    {"id": 8, "url": "https://other.test/"},
                )
            return {"ok": True, "result": {"to": args.get("url"), "tab_id": args.get("tab_id")}}

        async def fake_emit(*a, **kw):
            return None

        monkeypatch.setattr(loop_mod.bridge, "request", fake_request)
        monkeypatch.setattr(loop_mod.bus, "emit", fake_emit)

        await task._land_on("https://example.com/next")

        navs = [c for c in calls if c[0] == "navigate"]
        assert navs, "expected the agent to navigate an existing tab"
        assert navs[0][1]["tab_id"] == 7
        assert not [c for c in calls if c[0] == "open_tab"], "must not also open a tab"


class TestLandingNeverStealsTheCockpit:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("tab_url", [
        "http://127.0.0.1:8787/cockpit",
        "http://localhost:8787/cockpit",
        "chrome-extension://abcdef/index.html",
        "about:blank",
        "chrome://settings",
    ])
    async def test_opens_a_new_tab_when_nothing_is_reusable(self, task, monkeypatch, tab_url):
        from server import loop as loop_mod

        calls = []

        async def fake_request(op, args, task_id=None, **kw):
            calls.append((op, args))
            if op == "tabs":
                return _tabs({"id": 7, "url": tab_url})
            return {"ok": True, "result": {}}

        async def fake_emit(*a, **kw):
            return None

        monkeypatch.setattr(loop_mod.bridge, "request", fake_request)
        monkeypatch.setattr(loop_mod.bus, "emit", fake_emit)

        await task._land_on("https://example.com/")

        opens = [c for c in calls if c[0] == "open_tab"]
        assert opens, "a non-reusable tab must not be navigated; open a new one"
        assert not [c for c in calls if c[0] == "navigate"]


class TestLandingDegradesSafely:
    @pytest.mark.asyncio
    async def test_no_tab_list_still_opens_one(self, task, monkeypatch):
        from server.browser_bridge import BridgeError
        from server import loop as loop_mod

        calls = []

        async def fake_request(op, args, task_id=None, **kw):
            calls.append(op)
            if op == "tabs":
                raise BridgeError("no tab list")
            return {"ok": True, "result": {}}

        async def fake_emit(*a, **kw):
            return None

        monkeypatch.setattr(loop_mod.bridge, "request", fake_request)
        monkeypatch.setattr(loop_mod.bus, "emit", fake_emit)

        await task._land_on("https://example.com/")
        assert "open_tab" in calls

    @pytest.mark.asyncio
    async def test_a_failed_navigate_falls_back_to_opening(self, task, monkeypatch):
        from server.browser_bridge import BridgeError
        from server import loop as loop_mod

        calls = []

        async def fake_request(op, args, task_id=None, **kw):
            calls.append(op)
            if op == "tabs":
                return _tabs({"id": 7, "url": "https://example.com/"})
            if op == "navigate":
                raise BridgeError("tab vanished")
            return {"ok": True, "result": {}}

        async def fake_emit(*a, **kw):
            return None

        monkeypatch.setattr(loop_mod.bridge, "request", fake_request)
        monkeypatch.setattr(loop_mod.bus, "emit", fake_emit)

        await task._land_on("https://example.com/next")
        assert "open_tab" in calls, "a failed reuse must not lose the task"

    @pytest.mark.asyncio
    async def test_no_url_is_a_no_op(self, task, monkeypatch):
        from server import loop as loop_mod

        calls = []

        async def fake_request(op, args, task_id=None, **kw):
            calls.append(op)
            return {"ok": True, "result": {}}

        monkeypatch.setattr(loop_mod.bridge, "request", fake_request)

        await task._land_on("")
        assert calls == []