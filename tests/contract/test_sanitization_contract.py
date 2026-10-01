"""Contract tests — the sanitization contract must REJECT, not merely describe.

These are not documentation tests. Each one asserts that a specific malformed
input is refused. A contract that has never rejected anything has not been
tested.

Covers DES-ARCH-001 DP-6 and DP-7, and SEC-BOUND-001 section 5.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.contracts.sanitization import (  # noqa: E402
    IllegalTransitionError,
    InferenceRung,
    SanitizationState,
    SanitizedEvidence,
    TransmissionVerdict,
    VerificationProof,
    Verifier,
    assert_legal_transition,
    is_legal_transition,
    transmission_verdict,
)

CLEAN_PROOF = VerificationProof(
    verifiers_run=frozenset({Verifier.TEXT_RESCAN, Verifier.PIXEL_RESCAN}),
    regions_checked=12,
    residual_findings=0,
)


# ── DP-6: a state cannot exist without its evidence ──────────────────────────


def test_sanitized_without_proof_is_rejected() -> None:
    """The v1 defect, as an executable test."""
    with pytest.raises(ValidationError, match="requires a VerificationProof"):
        SanitizedEvidence(state=SanitizationState.SANITIZED, rung=InferenceRung.WASM_SIMD)


def test_sanitized_without_rung_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must declare the rung"):
        SanitizedEvidence(state=SanitizationState.SANITIZED, proof=CLEAN_PROOF)


def test_degraded_without_reason_is_rejected() -> None:
    """Silent degradation is exactly the v1 failure mode."""
    with pytest.raises(ValidationError, match="must declare why capability was reduced"):
        SanitizedEvidence(state=SanitizationState.DEGRADED, rung=InferenceRung.WASM)


def test_degraded_cannot_claim_proof() -> None:
    """A degraded run must not present itself as verified."""
    with pytest.raises(ValidationError, match="must not claim verification proof"):
        SanitizedEvidence(
            state=SanitizationState.DEGRADED,
            rung=InferenceRung.WASM,
            reason="ocr_failed",
            proof=CLEAN_PROOF,
        )


def test_uncertain_requires_unresolved_types() -> None:
    with pytest.raises(ValidationError, match="must list the unresolved entity types"):
        SanitizedEvidence(state=SanitizationState.UNCERTAIN)


def test_not_instrumented_must_name_the_check() -> None:
    """A generic failure is not a declaration."""
    with pytest.raises(ValidationError, match="must name the check that could not run"):
        SanitizedEvidence(state=SanitizationState.NOT_INSTRUMENTED)


def test_proof_with_residual_findings_is_rejected() -> None:
    """A proof reporting residuals cannot certify SANITIZED (V-10 / V-11)."""
    with pytest.raises(ValidationError, match="cannot certify SANITIZED"):
        VerificationProof(
            verifiers_run=frozenset({Verifier.PIXEL_RESCAN}),
            regions_checked=4,
            residual_findings=1,
        )


def test_unknown_field_is_rejected() -> None:
    """extra='forbid' is the v1 asset this module LIFTS (REQ-DATA-001 rule D-2)."""
    with pytest.raises(ValidationError):
        SanitizedEvidence(
            state=SanitizationState.NOT_INSTRUMENTED,
            missing_check="ocr",
            is_sanitized=True,  # type: ignore[call-arg]
        )


# ── DP-7: the forbidden transitions do not exist ─────────────────────────────


def test_failure_cannot_be_upgraded_to_success() -> None:
    """The core invariant: NOT_INSTRUMENTED -> SANITIZED is illegal."""
    assert not is_legal_transition(
        SanitizationState.NOT_INSTRUMENTED, SanitizationState.SANITIZED
    )
    with pytest.raises(IllegalTransitionError):
        assert_legal_transition(
            SanitizationState.NOT_INSTRUMENTED, SanitizationState.SANITIZED
        )


def test_degraded_cannot_be_upgraded_to_success() -> None:
    assert not is_legal_transition(
        SanitizationState.DEGRADED, SanitizationState.SANITIZED
    )


@pytest.mark.parametrize(
    "origin,target",
    [
        (SanitizationState.DEGRADED, SanitizationState.NOT_INSTRUMENTED),
        (SanitizationState.UNCERTAIN, SanitizationState.NOT_INSTRUMENTED),
    ],
)
def test_worsening_transitions_are_legal(
    origin: SanitizationState, target: SanitizationState
) -> None:
    """Any state may report that something failed. Only improvement is blocked."""
    assert is_legal_transition(origin, target)
    assert_legal_transition(origin, target)


# ── Transmission decision ────────────────────────────────────────────────────


def test_sanitized_payload_may_transmit() -> None:
    evidence = SanitizedEvidence(
        state=SanitizationState.SANITIZED,
        proof=CLEAN_PROOF,
        rung=InferenceRung.WASM_SIMD,
    )
    assert transmission_verdict(evidence) is TransmissionVerdict.ALLOW


def test_degraded_payload_transmits_but_must_declare() -> None:
    evidence = SanitizedEvidence(
        state=SanitizationState.DEGRADED,
        rung=InferenceRung.WASM,
        reason="ocr_failed",
    )
    assert transmission_verdict(evidence) is TransmissionVerdict.ALLOW_DECLARED


def test_not_instrumented_payload_is_withheld() -> None:
    """Failure direction: we do not know what is missing, so nothing is sent."""
    evidence = SanitizedEvidence(
        state=SanitizationState.NOT_INSTRUMENTED, missing_check="pixel_rescan"
    )
    assert transmission_verdict(evidence) is TransmissionVerdict.WITHHOLD
