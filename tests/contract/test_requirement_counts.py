"""Requirement counts must be derived, never typed.

Every number here describing the size of the requirement set was, until this
test existed, a hand-maintained figure repeated across five documents. They had
drifted: three artifacts claimed **102** functional requirements and **155**
total, while the SRS actually contains **99** and **152**.

A traceability matrix whose totals do not reconcile with its sources is not
traceability. It is decoration with tables.

The counts are now computed by `infra/count_requirements.py`, and these tests
fail if any document disagrees. Adding a requirement now moves the number and
the gate notices, which is the only way a count stays true.

── The coverage test is deliberately strict ───────────────────────────────────
`test_the_rtm_states_its_real_coverage` asserts that whatever coverage figure the
RTM publishes matches reality. Today that is 19 of 99. The RTM previously claimed
completeness. It cannot do that again without this test failing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra"))

from count_requirements import RTM, count, prose  # noqa: E402

README = ROOT / "README.md"
ARCH = ROOT / "docs" / "02-design" / "DES-ARCH-001-solution-architecture.md"

# Documents that publish a headline requirement count.
COUNT_PUBLISHERS = [
    README,
    RTM,
    ROOT / "docs" / "01-requirements" / "REQ-SRS-001-software-requirements-specification.md",
    ROOT / "docs" / "01-requirements" / "REQ-UC-001-use-case-model.md",
    ARCH,
]


@pytest.fixture(scope="module")
def counts() -> dict:
    return count()


# -- the counts themselves -----------------------------------------------------


def test_functional_count_comes_from_the_srs(counts: dict) -> None:
    assert counts["functional"] == 99, counts["functional"]
    assert counts["groups"], "no functional groups found"
    assert not counts["unexpected_groups"], counts["unexpected_groups"]


def test_non_functional_count_comes_from_the_nfr(counts: dict) -> None:
    assert counts["non_functional"] == 53, counts["non_functional"]


def test_the_two_totals_are_both_explicable(counts: dict) -> None:
    """The EI-* ambiguity left open in CR-002, now closed by publishing both.

    Publishing one total while seven interface requirements sat outside it is
    how "102 functional + 53 = 155" came to look authoritative.
    """
    assert counts["external_interfaces"] == 7
    assert counts["total_excluding_interfaces"] == (
        counts["functional"] + counts["non_functional"]
    )
    assert counts["total_including_interfaces"] == (
        counts["total_excluding_interfaces"] + counts["external_interfaces"]
    )


# -- drift detection -----------------------------------------------------------



# -- traceability honesty ------------------------------------------------------


def test_the_rtm_contains_no_phantom_requirements(counts: dict) -> None:
    """An RTM row citing a requirement that does not exist is a fabricated link."""
    phantom = counts["traceability"]["phantom_ids_in_rtm"]
    assert not phantom, (
        f"REQ-RTM-001 cites requirement ids absent from REQ-SRS-001: {phantom}. "
        f"These are invented traceability."
    )


def test_the_rtm_states_its_real_coverage(counts: dict) -> None:
    """Whatever coverage the RTM publishes must be the real number.

    It publishes 19 of 99. It previously implied 100%. This test exists so
    that "complete" can never again be written over a 19% matrix.
    """
    trace = counts["traceability"]
    # Target the summary row specifically. A bare `N / M` search picks up ratios
    # written for other purposes and would report a figure nobody published.
    published = re.search(
        r"Functional requirements traced\**\s*\|\s*\**(\d+)\s*/\s*(\d+)",
        RTM.read_text(encoding="utf-8"),
    )
    if published is None:
        pytest.fail(
            "REQ-RTM-001 publishes no traced-coverage row. A matrix that will "
            "not state its coverage will be believed to be complete."
        )
    traced, total = int(published.group(1)), int(published.group(2))
    assert traced == trace["functional_in_rtm"], (
        f"RTM publishes {traced} traced; the documents contain "
        f"{trace['functional_in_rtm']}"
    )
    assert total == counts["functional"], (
        f"RTM denominator is {total}; the SRS contains {counts['functional']}"
    )


def test_the_known_traceability_gap_is_pinned(counts: dict) -> None:
    """Pins the outstanding gap so it cannot quietly widen.

    80 of 99 functional requirements have no RTM row. That is the largest
    outstanding item in the SDLC, and this assertion makes it visible on every
    run instead of leaving a reviewer to discover it.
    """
    assert counts["traceability"]["functional_untraced"] == 80, (
        f"untraced count moved to {counts['traceability']['functional_untraced']}. "
        f"If rows were added, update REQ-RTM-001 and this number together."
    )


def test_counting_is_reproducible(counts: dict) -> None:
    assert json.loads(json.dumps(counts)) == count()

def test_no_publisher_still_claims_102_functional(counts: dict) -> None:
    stale = [
        p.name
        for p in COUNT_PUBLISHERS
        if p.exists() and re.search(r"\b102\b", prose(p.read_text(encoding="utf-8")))
    ]
    assert not stale, (
        f"these documents still ASSERT 102 functional requirements; the SRS "
        f"contains {counts['functional']}: {stale}"
    )


def test_no_publisher_still_claims_155_total(counts: dict) -> None:
    stale = [
        p.name
        for p in COUNT_PUBLISHERS
        if p.exists() and re.search(r"\b155\b", prose(p.read_text(encoding="utf-8")))
    ]
    assert not stale, (
        f"these documents still ASSERT 155 total; the real totals are "
        f"{counts['total_excluding_interfaces']} excluding EI-* and "
        f"{counts['total_including_interfaces']} including: {stale}"
    )


def test_a_disclosure_may_name_the_wrong_figure(counts: dict) -> None:
    """The gate checks ASSERTIONS, not the whole file.

    Without this, the obvious 'fix' for the failures above would be to delete the
    correction note - which would remove the only record that the error existed.
    """
    rtm = RTM.read_text(encoding="utf-8")
    assert "102" in rtm or "155" in rtm, (
        "the RTM no longer names the figures it corrected. A correction with no "
        "stated original is indistinguishable from never having been wrong."
    )


def test_the_readme_publishes_the_derived_functional_count(counts: dict) -> None:
    assert str(counts["functional"]) in README.read_text(encoding="utf-8")
