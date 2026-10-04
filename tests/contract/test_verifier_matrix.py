"""Exhaustive completion-verifier matrix (FR-VER-1..5).

v1's central failure was a reasoning model asserting a task was done. When the vision
pipeline quietly returned a 1x1 frame, the model still reported success and the
success was believed (defects G-2, G-6).

The verifier exists to make that impossible: completion is a deterministic check over
FRESH post-action perception, and the actor's own report is not reachable from it.

Testing one postcondition at a time never establishes that TWO failing postconditions
behave the same as one, nor that an empty goal is special-cased. So every non-empty
subset of the five postcondition kinds is enumerated - once all satisfied, once with
exactly one violated.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "parity" / "run-verifier-matrix.cjs"
VERIFIER_JS = ROOT / "dist" / "packages" / "agent" / "verifier.js"

TERMINAL = {"COMPLETED", "FAILED", "BLOCKED", "BOUNDED_OUT"}


@pytest.fixture(scope="module")
def verifier_matrix() -> dict:
    if not VERIFIER_JS.exists():
        pytest.skip("dist/ not built; run: npm run build:parity")
    proc = subprocess.run(["node", str(RUNNER)], capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise AssertionError(f"verifier matrix runner failed: {proc.stderr}")
    return json.loads(proc.stdout)


def test_no_violated_postcondition_can_yield_completion(
    verifier_matrix: dict,
) -> None:
    """THE property. FR-VER-5 is positive verification only.

    One violated condition in a goal of any size must end the task as failed. If a
    goal of three could complete with one of them broken, then "COMPLETED" means only
    "most of it went well", which is the v1 shape restated.
    """
    violated = [c for c in verifier_matrix["cells"] if c["violated"] is not None]
    assert violated, "the matrix contains no cell with a violated postcondition"

    for c in violated:
        assert c["outcome"] != "COMPLETED", (
            f"{c['label']}: COMPLETED despite {c['violated']} being violated"
        )
        # And the failure must be attributed to the right number of checks, so a
        # verifier that silently dropped a check cannot look identical to one that
        # evaluated it.
        assert c["failedChecks"] == 1, (
            f"{c['label']}: {c['failedChecks']} failed checks, expected exactly 1"
        )
        assert c["totalChecks"] == c["count"], (
            f"{c['label']}: {c['totalChecks']} checks run for a goal of {c['count']}"
        )


def test_completion_is_exactly_the_fully_satisfied_goal(verifier_matrix: dict) -> None:
    """COMPLETED must mean every declared postcondition held, on fresh perception."""
    for c in verifier_matrix["cells"]:
        assert c["outcome"] in TERMINAL, f"{c['label']}: unknown outcome {c['outcome']}"
        if c["violated"] is None and c["count"] > 0 and c["fresh"]:
            assert c["outcome"] == "COMPLETED", (
                f"{c['label']}: every postcondition held yet the outcome was "
                f"{c['outcome']}"
            )
            assert c["failedChecks"] == 0, f"{c['label']}: COMPLETED with a failed check"


def test_a_goal_declaring_nothing_can_never_complete(verifier_matrix: dict) -> None:
    """Completing it would mean inventing a criterion at verification time."""
    empty = [c for c in verifier_matrix["cells"] if c["count"] == 0]
    assert empty, "the matrix never exercised an empty goal"
    for c in empty:
        assert c["outcome"] == "FAILED", f"{c['label']}: {c['outcome']}"
        assert c["fresh"] is True, (
            f"{c['label']}: the perception WAS fresh, so the failure must come from "
            "the absent postcondition and not from staleness"
        )


def test_stale_perception_never_completes(verifier_matrix: dict) -> None:
    """FR-VER-3: verifying against pre-action input produces a verdict about the
    wrong moment in time."""
    stale = [c for c in verifier_matrix["cells"] if c["fresh"] is False]
    assert stale, "the matrix never exercised stale perception"
    for c in stale:
        assert c["outcome"] != "COMPLETED", f"{c['label']}: stale perception completed"


def test_blocked_and_bounded_out_are_terminal(verifier_matrix: dict) -> None:
    """A refusal and a timeout are failures, never soft successes."""
    seen = {c["outcome"] for c in verifier_matrix["cells"]}
    assert {"BLOCKED", "BOUNDED_OUT"} <= seen, (
        f"the matrix never produced BLOCKED or BOUNDED_OUT; saw {sorted(seen)}"
    )
    for c in verifier_matrix["cells"]:
        if c["outcome"] in {"BLOCKED", "BOUNDED_OUT"}:
            assert c["outcome"] != "COMPLETED"


def test_the_matrix_enumerated_the_whole_space(verifier_matrix: dict) -> None:
    """2^5 - 1 = 31 all-satisfied subsets, plus one cell per (subset, violation).

    Asserted so a runner that silently skips a combination cannot pass while every
    invariant above stays green.
    """
    cells = verifier_matrix["cells"]
    assert verifier_matrix["cellCount"] == len(cells)

    # The three terminal cells (blocked, bounded out, stale) also carry
    # violated=None and a non-zero count, so they are excluded explicitly rather
    # than by heuristics - they are terminal states, not satisfied goals.
    terminal = {"blocked", "bounded out", "stale perception"}
    satisfied = [
        c
        for c in cells
        if c["violated"] is None and c["count"] > 0 and c["label"] not in terminal
    ]
    # One per non-empty subset of five kinds.
    assert len(satisfied) == 31, f"expected 31 all-satisfied cells, got {len(satisfied)}"
    assert len({tuple(c["kinds"]) for c in satisfied}) == 31, "duplicate subsets"

    # And COMPLETED appears exactly that many times: the count itself is a check.
    assert sum(1 for c in cells if c["outcome"] == "COMPLETED") == 31
    assert sum(1 for c in cells if c["violated"] is not None) == 80
    assert sum(1 for c in cells if c["label"] in terminal) == 3