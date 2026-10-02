"""Redaction precision benchmark gate.

Turns `benchmarks/redaction_precision.py` into a REGRESSION gate for the
charter's 20% redaction-precision weight.

The assertions are ordered by what actually hurts a user. A leaked value is
unforgivable; a marginally imprecise mask is a quality problem. So the
irreversibility and leakage assertions are hard, and the IoU/utility assertions
gate the declared thresholds.

There is also a MUTATION test. A benchmark that cannot go red is decoration, so
`test_the_benchmark_detects_a_non_erasing_redactor` deliberately breaks the
redactor and asserts the harness catches it. Without this, every number below is
unfalsifiable.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from redaction_precision import (  # noqa: E402
    build_corpus,
    evaluate,
    render,
    to_dict,
)
from app.privacy.pixels import (  # noqa: E402
    MINIMUM_IOU,
    MINIMUM_UTILITY,
    PixelFrame,
    PixelRedactor,
)
from app.contracts.geometry import BoundingBox  # noqa: E402


@pytest.fixture(scope="module")
def corpus() -> dict:
    return build_corpus()


@pytest.fixture(scope="module")
def report(corpus: dict):
    return evaluate(corpus)


# -- the unforgivable ones -----------------------------------------------------


def test_no_value_survives_redaction(report) -> None:
    """A raw value still present in the output is a disclosure."""
    assert not report.raw_value_survivors, report.raw_value_survivors


def test_nothing_re_is_detectable_in_the_output(report) -> None:
    """Re-scanning the sanitised text must find nothing (V-1)."""
    assert not report.residual_detections, report.residual_detections


def test_no_vault_tokens_residual(report) -> None:
    assert not report.token_residuals, report.token_residuals


def test_no_pixel_survives_its_mask(report) -> None:
    """V-10, checked per pixel across every mask in the corpus."""
    assert report.pixel_survivors == 0, report.failed_cases


def test_redactor_never_returns_an_unverified_artefact(report) -> None:
    assert not report.failed_cases, report.failed_cases


# -- declared thresholds -------------------------------------------------------


def test_mask_geometry_meets_the_iou_floor(report) -> None:
    assert report.worst_iou >= MINIMUM_IOU, (
        f"worst IoU {report.worst_iou:.4f} < {MINIMUM_IOU} in {report.worst_iou_case!r}"
    )


def test_every_ground_truth_box_is_masked(report) -> None:
    assert report.masks_applied == report.boxes, (
        f"{report.masks_applied} masks for {report.boxes} boxes"
    )


def test_utility_is_preserved(report) -> None:
    assert report.worst_utility >= MINIMUM_UTILITY, (
        f"worst utility {report.worst_utility:.4f} < {MINIMUM_UTILITY}"
    )


def test_prose_is_not_redacted(report) -> None:
    """Redaction PRECISION: masking text that held nothing sensitive is a bug."""
    assert not report.over_redactions, report.over_redactions


# -- guards on the harness itself ---------------------------------------------


def test_corpus_contains_a_prose_only_case(report) -> None:
    """Without a negative case, redaction precision is unmeasurable."""
    assert report.prose_cases >= 1, "no prose-only case to prove non-over-redaction"


def test_iou_metric_is_not_vacuous(report) -> None:
    """Worst IoU of exactly 1.0 everywhere means the metric measures nothing.

    The out-of-bounds case exists to keep this honest. If a future change makes
    every box land in-bounds, this fails rather than quietly reporting a
    meaningless perfect score.
    """
    assert report.worst_iou < 1.0, (
        "every box was applied exactly; the geometry metric has stopped "
        "discriminating and needs an out-of-bounds fixture"
    )


def test_scorecard_is_serialisable(report) -> None:
    payload = json.dumps(to_dict(report))
    assert json.loads(payload)["benchmark"] == "redaction_precision"


def test_report_renders_without_error(report) -> None:
    assert "REDACTION PRECISION BENCHMARK" in render(report)


# -- mutation: prove the harness can fail --------------------------------------


def test_the_benchmark_detects_a_non_erasing_redactor(corpus: dict) -> None:
    """A redactor that copies the frame instead of masking must go red.

    This is the test that gives every number in this file its meaning.
    """

    class NoOpRedactor(PixelRedactor):
        def redact(self, frame, boxes, entity_ids=None, fill=(0, 0, 0)):  # type: ignore[override]
            # Returns the frame untouched, claiming success.
            return SimpleNamespace(
                frame=frame,
                masks=(),
                changed_pixels=0,
                utility_preservation=1.0,
                failures=(),
            )

    import redaction_precision as rp

    original = rp.PixelRedactor
    try:
        rp.PixelRedactor = NoOpRedactor
        broken = rp.evaluate(corpus)
    finally:
        rp.PixelRedactor = original

    # Sanity: the harness still scored the same corpus.
    assert broken.planted_values == 7
    # The untouched frame now carries original pixels inside every box, so the
    # geometry metric must collapse.
    assert broken.masks_applied == 0, "mutation should have removed every mask"
    assert broken.mask_recall == 0.0
