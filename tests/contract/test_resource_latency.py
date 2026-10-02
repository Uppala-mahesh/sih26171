"""Resource and latency gate — the 20% resources + 15% latency weights.

Two things are asserted, and the second is the point.

A latency gate on Node numbers is a *proxy*. So the harness exists, budgets are
enforced, and every stage is measured in isolation - but the assertions that
carry the weight are the ones about HONESTY:

  * the scorecard still declares Chrome-process, inference and Range-layout
    costs as NOT MEASURED, so this file cannot quietly become a claim that the
    client's resource use is known;
  * every stage is present, so a stage cannot be dropped because it was slow;
  * the dominant stage is identified, because "everything is fast enough" is not
    the same as knowing where the budget actually goes.

Budgets are generous on purpose. They catch an order-of-magnitude regression.
They do not certify a target that was never baselined on real hardware.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))

from resource_latency import (  # noqa: E402
    BUDGET_E2E_P95_MS,
    BUDGET_ENVELOPE_KB,
    BUDGET_FRAME_KB,
    BUDGET_STAGE_P95_MS,
    run_harness,
    to_scorecard,
)

REQUIRED_STAGES = {
    "detect_text",
    "sanitize_text",
    "redact_pixels",
    "guard_revalidate",
}


@pytest.fixture(scope="module")
def card() -> dict:
    return to_scorecard(run_harness())


# -- budgets -------------------------------------------------------------------


def test_end_to_end_p95_is_within_budget(card: dict) -> None:
    for rung, sample in card["end_to_end"].items():
        assert sample["p95_ms"] <= BUDGET_E2E_P95_MS, (
            f"{rung} p95 {sample['p95_ms']}ms exceeds {BUDGET_E2E_P95_MS}ms"
        )


def test_no_single_stage_exceeds_budget(card: dict) -> None:
    for name, sample in card["stages"].items():
        assert sample["p95_ms"] <= BUDGET_STAGE_P95_MS, (
            f"{name} p95 {sample['p95_ms']}ms exceeds {BUDGET_STAGE_P95_MS}ms"
        )


def test_envelope_and_frame_stay_within_budget(card: dict) -> None:
    assert card["footprint"]["envelope_kb"] <= BUDGET_ENVELOPE_KB
    assert card["footprint"]["frame_buffer_kb"] <= BUDGET_FRAME_KB


# -- the honesty assertions ----------------------------------------------------


def test_every_stage_is_measured(card: dict) -> None:
    """A stage cannot be dropped because it turned out to be slow."""
    assert REQUIRED_STAGES <= set(card["stages"]), (
        f"missing stages: {sorted(REQUIRED_STAGES - set(card['stages']))}"
    )


def test_the_dominant_stage_is_identified(card: dict) -> None:
    """Knowing where the budget goes is the point of per-stage timing."""
    dominant = card["dominant_stage"]
    assert dominant["stage"] in card["stages"]
    assert dominant["p95_ms"] == max(
        s["p95_ms"] for s in card["stages"].values()
    )


def test_pixel_work_dominates_and_that_is_stated(card: dict) -> None:
    """The measured shape of this system: pixels cost orders of magnitude more
    than text. If that ever flips, the measurement is suspect."""
    pixel = card["stages"]["redact_pixels"]["median_ms"]
    text = card["stages"]["detect_text"]["median_ms"]
    assert pixel > text, "expected the pixel path to dominate on a CPU-only core"


def test_unmeasured_routes_are_still_declared(card: dict) -> None:
    routes = {item["route"] for item in card["not_measured"]}
    assert routes == {
        "chrome_extension_process",
        "inference_latency",
        "dom_and_range_cost",
    }, (
        "the declared gaps changed. These three are what keeps this scorecard "
        "from reading as a claim about the real client."
    )


def test_the_scorecard_cannot_claim_chrome_numbers(card: dict) -> None:
    """The footprint is Node heap. If a future edit reports it as Chrome heap,
    this fails."""
    chrome = next(
        i for i in card["not_measured"] if i["route"] == "chrome_extension_process"
    )
    assert "Node" in chrome["why"] or "node" in chrome["why"]
    assert "20%" in chrome["affects"], (
        "the Chrome gap must say it invalidates the whole resources weight"
    )


def test_no_model_weights_are_claimed(card: dict) -> None:
    """CR-003 ships no weights, so the figure must be exactly zero."""
    assert card["footprint"]["model_weights_bytes"] == 0


def test_scorecard_is_serialisable(card: dict) -> None:
    assert json.loads(json.dumps(card))["benchmark"] == "resource_latency"
