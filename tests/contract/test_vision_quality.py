"""Vision quality gate (CR-003) — the 25% "visual accuracy" weight.

Two things are asserted here, and the second matters more than the first.

A 100% scorecard is easy to produce with a small corpus and a classifier that
was tuned against it. So the gate asserts the SCORE **and** the properties that
make the score meaningful:

  * the corpus contains negative cases, so a classifier that answered
    TEXT_INPUT to everything would fail rather than look perfect;
  * every unbound span carries a stated reason, so an invisible failure cannot
    pass as a success;
  * the two unimplemented routes are still DECLARED in the scorecard, so this
    file cannot silently become a claim that the whole surface is covered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))

from vision_quality import (  # noqa: E402
    CORPUS,
    TARGET_BOX_RECALL,
    TARGET_MIN_IOU,
    TARGET_ROLE_ACCURACY,
    evaluate,
    run_node,
    to_dict,
)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def raw() -> dict:
    return run_node(CORPUS)


@pytest.fixture(scope="module")
def report(raw: dict):
    return evaluate(raw)


@pytest.fixture(scope="module")
def scorecard(report) -> dict:
    return to_dict(report)


# -- headline figures ----------------------------------------------------------


def test_role_accuracy_meets_the_target(report) -> None:
    assert report.role_accuracy >= TARGET_ROLE_ACCURACY, (
        f"role accuracy {report.role_accuracy:.4f} < {TARGET_ROLE_ACCURACY}"
    )


def test_every_expected_span_is_bound_to_pixels(report) -> None:
    """Under-binding is a privacy failure, not a quality metric."""
    assert report.box_recall >= TARGET_BOX_RECALL, (
        f"box recall {report.box_recall:.4f} < {TARGET_BOX_RECALL}"
    )


def test_bound_boxes_point_at_the_glyphs(report) -> None:
    """Returning a box is not the same as returning the RIGHT box."""
    assert report.worst_iou is not None, "no box was ever scored for IoU"
    assert report.worst_iou >= TARGET_MIN_IOU, report.worst_iou


# -- the honesty assertions ----------------------------------------------------


def test_every_unbound_span_states_a_reason(report) -> None:
    """An unbound span with no reason is a failure nobody can see."""
    assert report.unbound_missing_reason == 0


def test_unbound_spans_are_actually_exercised(report) -> None:
    """The corpus must contain a case the system cannot bind, or the
    declaration path is never tested."""
    assert report.unbound_declared >= 1, (
        "no case produces an unbound span, so the declare-don't-guess path is "
        "untested"
    )


def test_negative_cases_exist(corpus: dict) -> None:
    """Prose must produce zero boxes. Without that, a binder that boxes
    everything scores perfectly."""
    negatives = [d for d in corpus["documents"] if d["expectedBoxes"] == 0]
    assert len(negatives) >= 2, "corpus needs negative documents"


def test_the_classifier_refuses_to_guess(report, corpus: dict) -> None:
    """FR-VIS-4: below threshold is UNKNOWN, not a best guess."""
    unknown_cases = [e for e in corpus["elements"] if e["expectedRole"] == "UNKNOWN"]
    assert len(unknown_cases) >= 3, "corpus needs ambiguous elements to refuse"
    assert report.below_threshold >= len(unknown_cases) - 1, (
        "the classifier is answering confidently where it should have abstained"
    )


def test_password_inputs_are_never_misfiled(raw: dict) -> None:
    """A PASSWORD_INPUT misfiled as TEXT_INPUT invites a consumer to type into
    the wrong control, which is an ACTION bug rather than a labelling bug."""
    case = next(c for c in raw["roles"] if c["expected"] == "PASSWORD_INPUT")
    assert case["actual"] == "PASSWORD_INPUT", case
    # And it must be decided by the explicit declaration, not a shape guess.
    assert "password" in case["decidedBy"], case["decidedBy"]


def test_hidden_inputs_are_not_advertised_as_interactive(raw: dict) -> None:
    """A hidden input holds a value the page set. Reporting it as TEXT_INPUT
    would invite a consumer to type into something invisible."""
    case = next(c for c in raw["roles"] if c["name"] == "hidden-token")
    assert case["actual"] == "UNKNOWN", case


# -- the declared blind spots --------------------------------------------------


def test_unimplemented_routes_are_still_declared(scorecard: dict) -> None:
    """This file must never become a claim of full coverage."""
    routes = {item["route"] for item in scorecard["not_measured"]}
    assert "ocr_painted_text" in routes, (
        "the OCR gap was dropped from the scorecard; canvas and image text are "
        "still unhandled and must stay visible"
    )
    for item in scorecard["not_measured"]:
        assert item["status"]
        assert item["surface"]


def test_scorecard_is_serialisable(scorecard: dict) -> None:
    assert json.loads(json.dumps(scorecard))["benchmark"] == "vision_quality"
