"""Exhaustive egress-guard matrix (REQ-DATA-001 / SEC-BOUND-001 5).

The guard is the last thing between page content and the wire, and its entire
purpose is that it does NOT trust the sender: it strips its own placeholders, re-runs
the full detector over everything that would leave, and refuses if anything
survives. Trusting the sender is what made v1's boundary decorative.

So the question is not "what does the payload claim" but: **for every combination of
claimed state and actual contents, does a raw value ever go on the wire?** That is
what this enumerates - declared state x payload contents x frame blindness.

The payload-contents dimension is the one that matters. A guard test that only
supplies clean payloads is testing nothing, because a guard that permits clean
payloads is trivially correct.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "parity" / "run-egress-matrix.cjs"
GUARD_JS = ROOT / "dist" / "packages" / "gateway" / "guard.js"

STATES = ["SANITIZED", "DEGRADED", "UNCERTAIN", "NOT_INSTRUMENTED"]
PAYLOADS = [
    "clean",
    "raw-confirmed",
    "raw-confirmed-in-aria",
    "uncertain-only",
    "clean-title-raw-body",
]


@pytest.fixture(scope="module")
def egress_matrix() -> dict:
    if not GUARD_JS.exists():
        pytest.skip("dist/ not built; run: npm run build:parity")
    proc = subprocess.run(
        ["node", str(RUNNER)], capture_output=True, text=True, cwd=ROOT
    )
    if proc.returncode != 0:
        raise AssertionError(f"egress matrix runner failed: {proc.stderr}")
    return json.loads(proc.stdout)


def _label(c: dict) -> str:
    return f"state={c['state']} payload={c['payload']} frameBlind={c['frameBlind']}"


def test_a_raw_value_never_leaves_whatever_the_sender_claims(
    egress_matrix: dict,
) -> None:
    """THE property. Not one of them has an "unless".

    The sender declares a sanitization state. The guard must not believe it. Every
    cell whose payload actually CONTAINS a Verhoeff-valid Aadhaar must be refused -
    including the cells where the sender claims SANITIZED, which is precisely the
    case a trusting guard would wave through.
    """
    raw_cells = [c for c in egress_matrix["cells"] if c["intendedRaw"]]
    assert raw_cells, "the matrix contains no payload carrying a raw value"

    for c in raw_cells:
        assert c["permitted"] is False, (
            f"{_label(c)}: a payload containing a raw Aadhaar was PERMITTED"
        )
        assert c["verdict"] == "WITHHOLD", (
            f"{_label(c)}: verdict was {c['verdict']}, not WITHHOLD"
        )
        # The residual assertion proves the refusal came from RE-INSPECTION rather
        # than from some unrelated check - which is the whole point, since a guard
        # that refused raw payloads for the wrong reason would still refuse them
        # after the re-inspection was removed.
        #
        # NOT_INSTRUMENTED is deliberately excluded: it short-circuits at step 1
        # without re-running the detector, so it never reaches the check under test.
        # That ordering is asserted on its own in the test below.
        if c["state"] != "NOT_INSTRUMENTED":
            assert c["residualAccepted"] >= 1, (
                f"{_label(c)}: refused, but re-inspection found no residual - so it "
                "was refused for some other reason and this test is not testing "
                "what it claims"
            )

    # And the claim must not matter: all four declared states must appear among the
    # refusals, or the guard is only catching the easy ones.
    states_seen = {c["state"] for c in raw_cells}
    assert states_seen == set(STATES), (
        f"raw payloads were only refused under {sorted(states_seen)}"
    )
def test_not_instrumented_never_leaves_and_is_never_even_revalidated(
    egress_matrix: dict,
) -> None:
    """A failure is never upgraded, and the cheap refusal happens FIRST.

    The `residualAccepted == 0` assertion matters as much as the refusal: the guard
    returns at step 1 without re-running the detector. If someone later "optimises"
    that ordering, the residual count starts being reported for these payloads, and a
    future change could read that as "it was checked and passed".
    """
    for c in egress_matrix["cells"]:
        if c["state"] != "NOT_INSTRUMENTED":
            continue
        assert c["permitted"] is False, f"{_label(c)}: NOT_INSTRUMENTED was permitted"
        assert c["verdict"] == "WITHHOLD", _label(c)
        assert c["residualAccepted"] == 0, (
            f"{_label(c)}: NOT_INSTRUMENTED payloads must short-circuit before "
            "re-validation; a non-zero count means the ordering changed"
        )


def test_frame_blindness_must_be_declared_not_buried(egress_matrix: dict) -> None:
    """A payload claiming FULL sanitation while frames were never inspected is
    claiming something the system cannot know (FR-PER-4).

    Only `SANITIZED` claims full sanitation. A DEGRADED or UNCERTAIN payload already
    declares that something was not checked, so frame blindness is not a new lie.
    """
    for c in egress_matrix["cells"]:
        if not c["frameBlind"] or c["state"] != "SANITIZED":
            continue
        assert c["permitted"] is False, (
            f"{_label(c)}: full sanitation claimed while frames were never inspected"
        )


def test_full_sanitation_is_claimed_only_when_everything_is_really_clean(
    egress_matrix: dict,
) -> None:
    """`ALLOW` is the strongest claim the system makes. It must be the hardest.

    Anything ambiguous - an uncertain residual, a declared capability loss, an
    uninspected frame - must downgrade it to ALLOW_DECLARED rather than leave it at
    ALLOW.
    """
    for c in egress_matrix["cells"]:
        if c["verdict"] != "ALLOW":
            continue
        assert c["residualAccepted"] == 0, f"{_label(c)}: ALLOW with an accepted residual"
        assert c["residualUncertain"] == 0, f"{_label(c)}: ALLOW with an uncertain residual"
        assert c["state"] == "SANITIZED", (
            f"{_label(c)}: ALLOW declared for a {c['state']} payload"
        )
        assert c["frameBlind"] is False, f"{_label(c)}: ALLOW while frame blind"


def test_every_cell_of_the_egress_space_was_exercised(egress_matrix: dict) -> None:
    """4 states x 5 payloads x 2 blindness = 40, asserted so a runner that skips a
    combination cannot pass while every invariant above stays green."""
    assert egress_matrix["cellCount"] == 40, egress_matrix["cellCount"]
    keys = {(c["state"], c["payload"], c["frameBlind"]) for c in egress_matrix["cells"]}
    assert len(keys) == 40, f"expected 40 distinct cells, got {len(keys)}"
    assert {k[0] for k in keys} == set(STATES)
    assert {k[1] for k in keys} == set(PAYLOADS)


def test_permitted_never_contradicts_the_verdict(egress_matrix: dict) -> None:
    """`permitted` and `verdict` are two views of one fact.

    If they ever disagree, some caller is reading the boolean while another reads the
    verdict - and one of them is wrong. Asserted because the two are easy to let drift.
    """
    for c in egress_matrix["cells"]:
        assert c["permitted"] == (c["verdict"] != "WITHHOLD"), _label(c)