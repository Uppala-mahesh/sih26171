"""Every module REQ-RTM-001 claims must exist on disk.

`REQ-RTM-001` section 2 listed its "Implementing module" column in the present
tense for code that was largely never written. `infra/verify_traceability.py`
found that only **4 of 21** claimed paths resolved - `services/vision/sources/dom`,
`apps/backend/app/agent/pipeline`, `apps/backend/app/policy/*`, `benchmarks/latency`,
`packages/telemetry` and seventeen more.

A traceability matrix pointing at modules that were never built is worse than one
that admits it is unfinished, because it converts an incomplete project into a
finished-looking one. That is the v1 pattern, sitting in the document whose entire
job is to establish what is real.

So the claim is now checkable, and this file fails the build if a path appears
that does not resolve. Adding a row means adding the module or removing the path.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra"))

from verify_traceability import (  # noqa: E402
    _is_disclosure_cell,
    claimed_design_artifacts,
    verify,
    verify_design,
)

# Groups that genuinely have no implementation. Listed here so that REMOVING the
# disclosure is itself a failure: the day one of these ships, this set must shrink
# and the matrix must say so.
DECLARED_UNIMPLEMENTED = {"FR-POL", "FR-EXE", "FR-VER"}


@pytest.fixture(scope="module")
def report() -> dict:
    return verify()


def test_every_claimed_module_path_resolves(report: dict) -> None:
    """The core assertion: no fabricated module paths."""
    assert not report["missing"], (
        "REQ-RTM-001 claims implementing modules that do not exist: "
        f"{report['missing_paths']}. Either build them or remove the path."
    )


def test_the_matrix_claims_a_meaningful_number_of_modules(report: dict) -> None:
    """Guards the opposite failure: a matrix that claims nothing verifies nothing."""
    assert report["claimed"] >= 12, (
        f"only {report['claimed']} paths claimed; a traceability matrix with "
        f"almost no implementation column is not doing its job"
    )


def test_verifier_finds_the_paths_it_should(report: dict) -> None:
    """Sanity: the verifier is not passing because it parses nothing."""
    assert any(p.startswith("packages/") for p in report["resolved_paths"])
    assert any(p.startswith("apps/") for p in report["resolved_paths"])


def test_unimplemented_groups_are_declared_not_mapped(report: dict) -> None:
    """`FR-POL`, `FR-EXE` and `FR-VER` must not acquire module paths silently.

    If one of these is implemented, its row changes and this constant shrinks.
    Keeping the set pinned means "not implemented" stays a fact with an owner
    rather than a status that quietly lapses.
    """
    rtm = (ROOT / "docs" / "01-requirements" / "REQ-RTM-001-requirements-traceability-matrix.md")
    text = rtm.read_text(encoding="utf-8")
    for group in DECLARED_UNIMPLEMENTED:
        assert group in text, f"{group} has disappeared from the matrix entirely"
    # And none of them may appear in a resolved module path.
    for path in report["resolved_paths"]:
        for group in DECLARED_UNIMPLEMENTED:
            assert group.lower().replace("-", "") not in path.lower().replace("-", "").replace("_", ""), (
                f"{group} now appears in resolved path {path!r}; update "
                f"DECLARED_UNIMPLEMENTED if that implementation is real"
            )


def test_the_matrix_states_how_much_it_covers(report: dict) -> None:
    """A matrix that will not state its coverage will be believed complete.

    Asserted as a SHAPE, not a value. This test pinned the literal ``80 / 99``,
    so every honest coverage improvement broke it - which is precisely backwards:
    it made the correct number look like a defect and the stale one look correct.
    The invariant is that a figure of the form ``N / 99`` is published at all.
    """
    text = (
        ROOT / "docs" / "01-requirements" / "REQ-RTM-001-requirements-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert re.search(r"\b(\d+)\s*/\s*99\b", text), (
        "the RTM no longer publishes a coverage figure of the form 'N / 99'"
    )
    # And the figure must be reachable, not only present as struck-through history.
    live = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    assert any(re.search(r"\b(\d+)\s*/\s*99\b", ln) for ln in live), (
        "the only coverage figures are in struck-through history"
    )
    assert "NOT IMPLEMENTED" in text, (
        "the matrix no longer marks unimplemented groups; they must be visible"
    )


# -- the design column, which failed the same way ------------------------------


@pytest.fixture(scope="module")
def design() -> dict:
    return verify_design()


def test_every_cited_design_artifact_exists(design: dict) -> None:
    """The design column was fabricating too: 4 cited, 1 existed.

    A missing DESIGN artifact is the one that lets a project look engineered while
    having no design at all, so it is checked separately from module paths.
    """
    assert design["missing"] == 0, (
        f"cited design artifacts do not exist: {design['missing_artifacts']}"
    )


def test_no_design_artifact_is_merely_acknowledged_as_unwritten(design: dict) -> None:
    """Design debt must be VISIBLE and must not be allowed to persist.

    ``verify_traceability`` deliberately does not treat a "NOT YET WRITTEN" cell as
    a citation - demanding the file would punish the matrix for being honest. But
    excluding it entirely meant the debt vanished: ``missing: 0`` was reported while
    two artifacts were owed, which is a clean bill of health for a known hole.

    So disclosed-but-unwritten artifacts are now counted separately. This test
    asserts that count is zero, which converts "we know we owe design" into a
    failing build. It must be satisfied by writing the document, never by editing
    this test.

    History: DES-CLASS-001 and DES-SEQ-001 were cited across eight rows and had
    never been written. The matrix was corrected to say NOT YET WRITTEN - which is
    honest, and which also made the debt invisible to `verify_traceability`, since
    `missing` counts only real citations. Both are now written; the count is a
    standing guard, not a one-off.
    """
    assert design["acknowledged_unwritten"] == 0, (
        "design artifacts are acknowledged as unwritten and are therefore not "
        f"tracked: {design['acknowledged_unwritten_artifacts']}. Write them, or cite "
        "the design that actually covers the requirement."
    )


def test_the_verifier_can_still_see_design_citations(design: dict) -> None:
    """Guards the opposite failure.

    An earlier revision of `_is_disclosure_cell` tested for the substring `-`,
    which matches every hyphenated identifier in the table. It skipped the entire
    design column and reported `cited 0`, which would have passed forever.
    """
    assert design["cited"] >= 2, (
        f"only {design['cited']} design artifacts detected; the scan is not "
        f"looking at the column it claims to check"
    )
    assert "DES-ARCH-001" in design["present_artifacts"]


def test_a_disclosure_cell_is_not_a_citation() -> None:
    """Naming an absent artifact in order to declare it absent is not claiming it."""
    assert _is_disclosure_cell("**DES-CLASS-001 NOT YET WRITTEN**")
    assert _is_disclosure_cell("none")
    assert _is_disclosure_cell("-")
    assert not _is_disclosure_cell("`DES-ARCH-001` 5")
    assert not _is_disclosure_cell("`REQ-DATA-001`, `DES-STATE-001` 4")


def test_the_previously_absent_design_artifacts_are_now_real(design: dict) -> None:
    """They must not vanish from the matrix entirely.

    This test originally asserted that `DES-CLASS-001` and `DES-SEQ-001` stayed
    marked NOT YET WRITTEN, because both were cited across eight rows and had never
    been written - a `services/`-scale claim over an empty document. Both have now
    been written, so the durable assertion is the opposite: they must appear as
    REAL citations and must exist on disk.

    Checking for the disclosure marker would have made the test fail the moment the
    project did the right thing.
    """
    text = (
        ROOT / "docs" / "01-requirements" / "REQ-RTM-001-requirements-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    for artifact in ("DES-CLASS-001", "DES-SEQ-001"):
        assert artifact in text, f"{artifact} vanished from the matrix entirely"
        assert artifact in design["present_artifacts"], (
            f"{artifact} is cited as though it exists, but it is not on disk"
        )
    # Once written, neither may be cited through a disclosure cell.
    assert "NOT YET WRITTEN" not in text, (
        "an artifact is still marked NOT YET WRITTEN, yet the debt counter reads "
        "zero - the matrix and the verifier disagree"
    )


def test_cited_design_artifacts_are_a_subset_of_what_exists() -> None:
    """Belt and braces: intersect the citation list with the filesystem."""
    for artifact in claimed_design_artifacts():
        assert list((ROOT / "docs").rglob(f"{artifact}*.md")), artifact
