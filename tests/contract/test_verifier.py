"""Completion verifier gate (FR-VER-1…5).

FR-VER-4 sets a measurable acceptance criterion: **0.00% false completions**
against a ground-truth task set. This suite exists to hold that line.

── Why the suite is adversarial rather than flattering ───────────────────────
Every case in `run-verifier.cjs` is one where the actor CLAIMS SUCCESS. The
verifier is the only thing that can dissent, so a suite of easy tasks would
report 100% and prove nothing. The hard cases — stale perception, a value that
survived redaction, a region never masked — are the measurement.

── The defect this suite caught ───────────────────────────────────────────────
Its first run reported a FALSE COMPLETION. The page still displayed
"4532 0151 1283 0366" while the postcondition looked for the unspaced
"4532015112830366"; a literal substring match missed it and the task reported
COMPLETED with the card number on screen. That is precisely the failure FR-VER
exists to prevent, living inside the module written to prevent it.

The fix normalises punctuation on both sides. The regression test for it is
`test_a_value_is_found_however_it_is_punctuated`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "vision" / "run-verifier.cjs"
VERIFIER_JS = ROOT / "dist" / "packages" / "agent" / "verifier.js"


@pytest.fixture(scope="module")
def results() -> list[dict]:
    if not VERIFIER_JS.exists():
        pytest.fail(f"{VERIFIER_JS} is missing. Run: npm run build:parity")
    completed = subprocess.run(
        ["node", str(RUNNER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"Node verifier runner failed:\n{completed.stderr}")
    return json.loads(completed.stdout)["results"]


def _case(results: list[dict], name: str) -> dict:
    return next(c for c in results if c["name"] == name)


# -- FR-VER-4: the headline criterion -----------------------------------------


def test_false_completion_rate_is_zero(results: list[dict]) -> None:
    false_completions = [c["name"] for c in results if c["falseCompletion"]]
    assert not false_completions, (
        f"the verifier agreed with a false success claim on: {false_completions}"
    )


def test_every_case_produced_the_expected_verdict(results: list[dict]) -> None:
    wrong = [
        f"{c['name']}: {c['actual']} != {c['expected']}"
        for c in results
        if not c["matches"]
    ]
    assert not wrong, wrong


# -- FR-VER-2: determinism ------------------------------------------------------


def test_verification_is_deterministic(results: list[dict]) -> None:
    """Same input, same verdict — twice, in the same process.

    A verifier that can be talked into agreeing is not a verifier, and a
    non-deterministic one cannot be reasoned about when it dissents.
    """
    unstable = [c["name"] for c in results if not c["deterministic"]]
    assert not unstable, unstable


# -- FR-VER-3: freshness, the v1 defect ----------------------------------------


def test_stale_perception_cannot_verify_anything(results: list[dict]) -> None:
    """The core v1 shape: success claimed against a pre-action snapshot."""
    case = _case(results, "stale-perception-claimed-success")
    assert case["actual"] == "FAILED"
    assert case["fresh"] is False
    assert case["checksRun"] == 0, (
        "stale perception must be rejected BEFORE any postcondition runs; "
        "running checks against the wrong moment in time reports a verdict "
        "about the past as a verdict about the present"
    )


# -- FR-VER-5: positive verification only ---------------------------------------


def test_blocked_and_bounded_are_not_successes(results: list[dict]) -> None:
    """A timeout is a failure, never a success (FR-EXE-4 by the same logic)."""
    assert _case(results, "blocked-before-execution")["actual"] == "BLOCKED"
    assert _case(results, "execution-bound-elapsed")["actual"] == "BOUNDED_OUT"


def test_a_goal_without_postconditions_cannot_complete(results: list[dict]) -> None:
    """Completion must never be inferred from an absent criterion."""
    assert _case(results, "goal-without-postconditions")["actual"] == "FAILED"


# -- the regression this suite earned ------------------------------------------


def test_a_value_is_found_however_it_is_punctuated(results: list[dict]) -> None:
    """Caught by the first run of this very suite.

    The page displayed "4532 0151 1283 0366"; the postcondition named
    "4532015112830366". A literal substring check passed, the verifier reported
    COMPLETED, and the card number was still on screen — a false completion in
    the module written to prevent false completions.
    """
    assert _case(results, "value-still-present")["actual"] == "FAILED", (
        "a spaced, dashed or dotted rendering of a sensitive value must still be "
        "found; a verifier defeated by a space is not a verifier"
    )
    assert _case(results, "value-present-different-case")["actual"] == "FAILED"


def test_a_never_masked_region_fails_verification(results: list[dict]) -> None:
    assert _case(results, "region-never-masked")["actual"] == "FAILED"


# -- harness integrity ----------------------------------------------------------


def test_the_suite_contains_cases_that_must_be_rejected(results: list[dict]) -> None:
    """Guards the opposite failure.

    If every case were an honest completion, the 0.00% figure would be
    meaningless: a verifier that always agrees scores perfectly.
    """
    rejected = [c for c in results if c["actual"] != "COMPLETED"]
    assert len(rejected) >= 7, (
        f"only {len(rejected)} rejecting cases; the suite cannot demonstrate "
        f"that the verifier dissents"
    )
    assert [c for c in results if c["actual"] == "COMPLETED"], (
        "no case completes, so the verifier cannot be shown to work at all"
    )


def test_sensitive_presence_does_not_satisfy_a_presence_check(results: list[dict]) -> None:
    """A field still flagged sensitive is not a clean input to interact with."""
    assert _case(results, "sensitive-element-is-not-a-clean-presence")["actual"] == "FAILED"
