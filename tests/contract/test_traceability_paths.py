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

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra"))

from verify_traceability import claimed_paths, verify  # noqa: E402

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
    """A matrix that will not state its coverage will be believed complete."""
    text = (
        ROOT / "docs" / "01-requirements" / "REQ-RTM-001-requirements-traceability-matrix.md"
    ).read_text(encoding="utf-8")
    assert "19 / 99" in text, "the RTM no longer publishes its real coverage"
    assert "NOT IMPLEMENTED" in text, (
        "the matrix no longer marks unimplemented groups; they must be visible"
    )
