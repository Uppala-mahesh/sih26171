"""Effort profiles and Ask mode are contract-level behaviour, not UI copy.

Fast/Balanced/Deep change how long the loop may run and whether the visual
reasoner runs. Ask mode is read-only: only reading verbs may reach execution.
"""
from server.loop import ANSWER_ONLY_ACTIONS, Task, _effort_profile


def test_effort_profiles_are_bounded_and_vision_aware():
    fast = _effort_profile("fast")
    balanced = _effort_profile("balanced")
    deep = _effort_profile("deep")

    assert fast["max_steps"] < balanced["max_steps"] < deep["max_steps"]
    assert fast["vision"] is False
    assert balanced["vision"] is True
    assert deep["vision"] is True
    assert fast["screenshot_every"] == 0
    assert deep["screenshot_every"] >= 1


def test_ask_mode_allows_reading_but_not_page_changes():
    for verb in ("scroll", "wait", "extract", "note", "finish", "fail"):
        assert verb in ANSWER_ONLY_ACTIONS
    for verb in ("click", "type", "submit", "navigate", "open_tab", "upload_file"):
        assert verb not in ANSWER_ONLY_ACTIONS


def test_task_snapshot_reports_effort_and_answer_only():
    task = Task("summarize this page", effort="deep", answer_only=True)
    snap = task.snapshot()

    assert snap["effort"] == "deep"
    assert snap["answer_only"] is True
    assert task.effort_profile["max_steps"] == 90
