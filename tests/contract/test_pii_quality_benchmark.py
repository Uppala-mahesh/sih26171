"""PII quality benchmark gate.

Turns `benchmarks/pii_quality.py` into a REGRESSION gate. A benchmark that is
only ever run by hand rots; a benchmark that fails the build when quality drops
is a control.

The assertions are deliberately asymmetric:

  * MISSED spans are a hard failure. A missed entity is a real disclosure.
  * A precision shortfall against the charter target is a hard failure, because
    precision is a scored criterion.
  * PROTECTIVE precision is NOT gated. Over-redaction is the declared,
    fail-closed direction (FR-PII-9); punishing it would push the system
    toward under-redaction, which is the dangerous direction.

The confusion-matrix count is cross-checked against the strict false-positive
count, because that is exactly the bug this harness shipped with: it
accumulated the matrix in both reading loops and produced 9 entries against
1 strict false positive.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from pii_quality import (  # noqa: E402
    CORPUS,
    TARGET_PRECISION,
    TARGET_RECALL,
    evaluate,
)

REQUIRED_ENTITY_ACCURACY = {
    "AADHAAR",
    "PAN",
    "UPI_VPA",
    "IFSC",
    "EMAIL",
    "MOBILE_IN",
    "CREDIT_CARD",
    "OTP",
    "API_KEY",
    "JWT",
    "BANK_ACCOUNT",
    "STUDENT_ID",
    "DOB",
    "POSTAL_CODE_IN",
    "SECRET_GENERIC",
}


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report(corpus: dict):
    return evaluate(corpus)


# -- headline figures against the charter ------------------------------------


def test_strict_precision_meets_the_charter_target(report) -> None:
    precision = report.strict.precision
    assert precision is not None
    assert precision >= TARGET_PRECISION, f"precision {precision:.4f} < {TARGET_PRECISION}"


def test_strict_recall_meets_the_charter_target(report) -> None:
    recall = report.strict.recall
    assert recall is not None
    assert recall >= TARGET_RECALL, f"recall {recall:.4f} < {TARGET_RECALL}"


# -- the disclosure-facing assertion -----------------------------------------


def test_no_labelled_entity_is_missed(report) -> None:
    """A missed entity is a real disclosure. This is the assertion that matters."""
    assert report.strict.false_negatives == 0, (
        f"missed spans: {report.missed}"
    )


def test_protective_recall_is_perfect(report) -> None:
    """Every planted value must be redacted one way or another."""
    assert report.protective.false_negatives == 0, (
        "a planted value escaped redaction entirely"
    )


# -- benchmark integrity ------------------------------------------------------


def test_confusion_matrix_is_not_double_counted(report) -> None:
    """Catches the bug this harness shipped with."""
    matrix_total = sum(report.confusion.values())
    assert matrix_total == report.strict.false_positives, (
        f"confusion has {matrix_total} entries but strict recorded "
        f"{report.strict.false_positives} false positives"
    )


def test_corpus_labels_point_at_the_values_they_claim(corpus: dict) -> None:
    """A wrong offset understates recall rather than failing loudly."""
    for case in corpus["cases"]:
        for span in case["expected"]:
            actual = case["text"][span["start"] : span["end"]]
            assert actual == span["value"], (
                f"{case['id']}: label says {span['value']!r} at "
                f"{span['start']}:{span['end']} but found {actual!r}"
            )


def test_corpus_declares_what_it_does_not_measure(corpus: dict) -> None:
    """Partial coverage must be visible, never implied."""
    coverage = corpus["coverage"]
    assert coverage["entities_not_measured"] == 4
    assert "PASSWORD" in corpus["scope_note"]
    assert "FACE_IMAGE" in corpus["scope_note"]


def test_every_required_entity_is_actually_exercised(corpus: dict) -> None:
    present = {
        span["entity"] for case in corpus["cases"] for span in case["expected"]
    }
    missing = REQUIRED_ENTITY_ACCURACY - present
    assert not missing, f"corpus never exercises: {sorted(missing)}"


def test_corpus_contains_decoy_cases(corpus: dict) -> None:
    """Without negatives, precision is unmeasurable."""
    decoys = [case for case in corpus["cases"] if not case["expected"]]
    assert len(decoys) >= 2, "corpus needs decoy cases to measure precision"


# -- per-class reporting (FR-PII-7) -----------------------------------------


def test_per_entity_results_are_published(report) -> None:
    for entity in REQUIRED_ENTITY_ACCURACY:
        assert entity in report.per_entity, f"{entity} has no per-entity result"


def test_per_class_recall_is_reported_not_averaged_away(report) -> None:
    """FR-PII-7: a weak class must be visible rather than hidden by the mean."""
    tallies = [t.recall for t in report.per_entity.values() if t.recall is not None]
    assert tallies, "no per-entity recall figures produced"
    assert min(tallies) >= TARGET_RECALL, (
        f"a class fell below the recall target: min {min(tallies):.4f}"
    )
