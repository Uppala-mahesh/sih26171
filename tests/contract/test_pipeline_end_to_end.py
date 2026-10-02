"""End-to-end pipeline verification — the claim no unit test can make.

Every other suite in this repository proves that one component is correct. This
one proves the components are correct **together**, which is the only claim the
rubric's privacy weights actually depend on.

That distinction is not academic. v1 was a chain of individually reasonable
components that together leaked: the vision pipeline returned a 1x1 frame, the
payload carried ``is_sanitized: true``, and the backend believed it. Each part
passed its own test.

The scenarios deliberately include the ones that MUST fail. A pipeline suite that
only exercises the happy path proves that nothing is wrong, which is not the same
as proving that nothing can be.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "vision" / "run-pipeline.cjs"
ORCHESTRATOR_JS = ROOT / "dist" / "packages" / "pipeline" / "orchestrator.js"


@pytest.fixture(scope="module")
def scenarios() -> dict[str, dict]:
    if not ORCHESTRATOR_JS.exists():
        pytest.fail(f"{ORCHESTRATOR_JS} is missing. Run: npm run build:parity")
    completed = subprocess.run(
        ["node", str(RUNNER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"Node pipeline runner failed:\n{completed.stderr}")
    raw = json.loads(completed.stdout)["scenarios"]
    return {case["name"]: case for case in raw}


# -- the load-bearing assertions ----------------------------------------------


def test_an_uncertain_detection_is_never_declared_sanitized(
    scenarios: dict[str, dict],
) -> None:
    """The regression that 333 green tests did not catch.

    `unresolved` does NOT contribute to `residualFindings`: an entity below the
    confidence threshold is redacted anyway, so no raw value survives and the
    residual count stays at zero. A SANITIZED branch testing only residuals
    therefore swallowed UNCERTAIN and declared the page clean, discarding the list
    of entity types that were merely guessed at.

    It was introduced when the `visualSurfaces` branches were added ahead of the
    UNCERTAIN branch, and it stayed hidden because no scenario combined an
    UNCERTAIN detection with zero painted surfaces.
    """
    case = scenarios["text-only-uncertain"]
    assert case["state"] == "UNCERTAIN", (
        "a page with an uncertain detection was declared "
        f"{case['state']}: the unresolved list is being dropped"
    )
    # And the same must hold when painted content is ALSO present.
    painted = scenarios["painted-surface-uncertain"]
    assert painted["state"] == "UNCERTAIN", (
        f"uncertain + painted reported {painted['state']}"
    )
    # Both still transmit: UNCERTAIN is a declared verdict, not a refusal.
    assert case["transmitted"] is True and painted["transmitted"] is True


def test_the_visual_surface_decision_table(scenarios: dict[str, dict]) -> None:
    """The full evidence table, asserted rather than described.

    Ordering is part of the contract: an unknown surface count is evaluated
    BEFORE a positive one, because reading unknown as zero is precisely the
    optimistic failure the four-state model exists to prevent.
    """
    expected = {
        # nothing painted, nothing uncertain -> full coverage
        "text-only-clean": ("SANITIZED", True),
        # painted content -> coverage is partial, and that is declared
        "painted-surface-clean": ("DEGRADED", True),
        # unknown count -> fail closed, never read as zero
        "unknown-surface-count": ("NOT_INSTRUMENTED", False),
    }
    for name, (state, transmitted) in expected.items():
        case = scenarios[name]
        assert case["state"] == state, f"{name}: expected {state}, got {case['state']}"
        assert case["transmitted"] is transmitted, (
            f"{name}: transmitted={case['transmitted']}, expected {transmitted}"
        )


def test_no_raw_value_reaches_the_envelope(scenarios: dict[str, dict]) -> None:
    """The one assertion the entire project exists to support."""
    planted = "999999990019"
    for name, case in scenarios.items():
        assert case["aadhaarInEnvelope"] is False, (
            f"{name}: a raw Aadhaar survived into the outbound envelope"
        )
    # Guard against the check being vacuous.
    assert any(case["redactions"] > 0 for case in scenarios.values()), (
        "no scenario actually planted a redaction, so the leak check proves nothing"
    )


def test_a_clean_page_on_full_capability_is_sanitized(scenarios: dict[str, dict]) -> None:
    case = scenarios["clean-webgpu"]
    assert case["state"] == "SANITIZED"
    assert case["transmitted"] is True
    assert case["framesVerified"] == 1
    assert case["auditVerdicts"] == ["ALLOW"]


def test_detected_pii_is_redacted_and_the_payload_still_crosses(
    scenarios: dict[str, dict],
) -> None:
    """Redaction is not withholding. The system still does its job."""
    case = scenarios["pii-redacted"]
    assert case["redactions"] == 1
    assert case["state"] == "SANITIZED"
    assert case["transmitted"] is True
    assert case["aadhaarInEnvelope"] is False


# -- degradation fails safe, not closed ----------------------------------------


def test_capability_loss_is_declared_and_still_travels(scenarios: dict[str, dict]) -> None:
    """DEGRADED redacts more, so it may cross provided the state travels."""
    case = scenarios["degraded-dom-only"]
    assert case["state"] == "DEGRADED"
    assert case["transmitted"] is True
    assert case["auditVerdicts"] == ["ALLOW_DECLARED"]


# -- the failures that must NOT cross -----------------------------------------


def test_unverifiable_pixels_are_withheld(scenarios: dict[str, dict]) -> None:
    case = scenarios["pixels-unverifiable"]
    assert case["state"] == "NOT_INSTRUMENTED"
    assert case["transmitted"] is False
    assert case["auditVerdicts"] == ["WITHHOLD"]


def test_a_mask_below_the_geometry_floor_is_withheld(scenarios: dict[str, dict]) -> None:
    """An unverifiable mask must not be laundered into a success."""
    case = scenarios["pixel-mask-below-floor"]
    assert case["pixelFailure"] is True
    assert case["framesVerified"] == 0
    assert case["state"] == "NOT_INSTRUMENTED"
    assert case["transmitted"] is False


def test_claiming_pixel_verification_with_no_frames_is_withheld(
    scenarios: dict[str, dict],
) -> None:
    """v1 defect G-2/G-6, caught by this suite's first run.

    Declaring ``pixel_rescan`` as a verifier that ran over zero regions is the
    same lie one level down: the proof would be internally honest and still
    mean nothing. ``regionsChecked`` would read 1 from the text segments, and a
    reader would reasonably conclude pixels were covered.

    Found by writing this scenario, not by reading the code.
    """
    case = scenarios["no-frames-captured"]
    assert case["framesVerified"] == 0
    assert case["state"] == "NOT_INSTRUMENTED"
    assert case["transmitted"] is False
    assert case["auditVerdicts"] == ["WITHHOLD"]


# -- harness integrity ---------------------------------------------------------


def test_every_scenario_is_recorded_in_the_audit_trail(
    scenarios: dict[str, dict],
) -> None:
    """DP-2: nothing reaches the network without leaving a record."""
    for name, case in scenarios.items():
        assert len(case["auditVerdicts"]) == 1, f"{name} left no audit record"


def test_transmission_and_audit_verdict_always_agree(
    scenarios: dict[str, dict],
) -> None:
    """A payload that crossed was allowed; one that did not, was withheld."""
    for name, case in scenarios.items():
        verdict = case["auditVerdicts"][0]
        if case["transmitted"]:
            assert verdict in {"ALLOW", "ALLOW_DECLARED"}, name
        else:
            assert verdict == "WITHHOLD", name


def test_the_suite_cannot_pass_vacuously(scenarios: dict[str, dict]) -> None:
    """Both outcomes must appear, or the assertions above prove nothing."""
    assert any(c["transmitted"] for c in scenarios.values()), "nothing ever crossed"
    assert any(not c["transmitted"] for c in scenarios.values()), "nothing was ever blocked"


def test_scenarios_exist_that_use_boxes_from_the_real_binder(
    scenarios: dict[str, dict],
) -> None:
    """The redaction score must not depend on the harness placing good boxes.

    Until CR-003, every scenario passed hand-placed rectangles, so the pixel
    result measured the harness's box-picking rather than the system's. These
    scenarios derive their masks through text runs -> detector -> binder, which
    is the path the extension actually takes.
    """
    binder = {k: v for k, v in scenarios.items() if v["boxesFromBinder"]}
    assert len(binder) >= 2, "no scenario exercises the real binder"
    for name, case in binder.items():
        assert case["boundBoxes"] > 0, f"{name} bound no boxes at all"
        assert case["framesVerified"] == 1, f"{name}: derived boxes were not masked"
        assert case["transmitted"] is True, name
        assert case["aadhaarInEnvelope"] is False, name


def test_both_box_sources_are_represented(scenarios: dict[str, dict]) -> None:
    """Placed and derived boxes must both be exercised, so a regression in
    either normalisation path is caught."""
    assert any(c["boxesFromBinder"] for c in scenarios.values())
    assert any(not c["boxesFromBinder"] for c in scenarios.values())
