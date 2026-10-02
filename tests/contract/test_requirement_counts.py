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

from count_requirements import (  # noqa: E402
    RTM,
    count,
    expand_group_ranges,
    prose,
)

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

    Measured two ways, because they are different facts:
      * PRESENCE    - is the requirement listed at all?
      * IMPLEMENTATION - does its group row name a module that exists?

    The matrix lists all 99 through ranged group rows; 80 have an
    implementation. It previously published "19 / 99", which was an
    identifier-only count that saw only the endpoints of each range.
    """
    trace = counts["traceability"]
    text = RTM.read_text(encoding="utf-8")
    published = re.search(
        r"Functional requirements implemented\**\s*\|\s*\**(\d+)\s*/\s*(\d+)",
        text,
    )
    if published is None:
        pytest.fail(
            "REQ-RTM-001 publishes no implemented-coverage row. A matrix that "
            "will not state its coverage will be believed complete."
        )
    traced, total = int(published.group(1)), int(published.group(2))
    assert traced == trace["implemented"], (
        f"RTM publishes {traced} implemented; the documents show "
        f"{trace['implemented']}"
    )
    assert total == counts["functional"], (
        f"RTM denominator is {total}; the SRS contains {counts['functional']}"
    )


def test_every_requirement_is_listed_in_the_matrix(counts: dict) -> None:
    """Presence is total, and that is now measured rather than assumed.

    This is the assertion that would have caught the range bug: a scan for
    literal ids saw 19 endpoints and reported them as the coverage.
    """
    trace = counts["traceability"]
    assert trace["present_in_matrix"] == counts["functional"], (
        f"{trace['unlisted_in_matrix']} requirements are not listed: "
        f"{trace['unlisted_ids']}"
    )
    assert trace["named_via_group_range"] > 0, (
        "no group ranges were expanded; if this is zero the range expander has "
        "stopped working and the coverage figure above is meaningless again"
    )


def test_the_unimplemented_set_is_exactly_the_declared_groups(
    counts: dict,
) -> None:
    """19 unimplemented, and they must be the three declared groups.

    Anything else unimplemented means a row lost its implementation without the
    summary being updated, which is how the matrix started lying in the first
    place.
    """
    unimplemented = set(counts["traceability"]["unimplemented_ids"])
    assert len(unimplemented) == 19, sorted(unimplemented)
    groups = {i.rsplit("-", 1)[0] for i in unimplemented}
    assert groups == {"FR-POL", "FR-EXE", "FR-VER"}, sorted(groups)


def test_group_ranges_expand_correctly() -> None:
    """Unit-check the expander, because the coverage figure depends on it."""
    assert expand_group_ranges("`FR-PII-1...9`") == {f"FR-PII-{n}" for n in range(1, 10)}
    assert expand_group_ranges("`FR-VER-1...5`") == {f"FR-VER-{n}" for n in range(1, 6)}
    # A lone id with no range must not be invented into a range.
    assert expand_group_ranges("`FR-RED-3`") == set()


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
