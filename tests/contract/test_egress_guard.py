"""Egress guard tests — FR-EGR-1..7, obligation A-6, verification V-2.

The decisive test is ``test_v2_forged_sanitized_payload_is_refused``: a payload
that DECLARES full sanitation while carrying a raw Aadhaar must be rejected.

That is the direct regression test for the v1 defect where the backend accepted
an ``is_sanitized: true`` boolean from the extension, including the case where a
fully-failed vision run produced a 1x1 image carrying that same boolean.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.contracts.sanitization import (  # noqa: E402
    InferenceRung,
    SanitizedEvidence,
    SanitizationState,
    TransmissionVerdict,
    VerificationProof,
    Verifier,
)
from app.gateway.audit import RingAuditRepository, summarise  # noqa: E402
from app.gateway.guard import (  # noqa: E402
    EgressGuard,
    PrivacyBoundaryBreachError,
)
from app.gateway.payload import (  # noqa: E402
    OutboundEnvelope,
    SanitizedContext,
    Viewport,
)

PROOF = VerificationProof(
    verifiers_run=frozenset({Verifier.TEXT_RESCAN}),
    regions_checked=4,
    residual_findings=0,
)
SANITIZED = SanitizedEvidence(
    state=SanitizationState.SANITIZED, proof=PROOF, rung=InferenceRung.WASM_SIMD
)
DEGRADED = SanitizedEvidence(
    state=SanitizationState.DEGRADED, rung=InferenceRung.WASM, reason="ocr_failed"
)
NOT_INSTRUMENTED = SanitizedEvidence(
    state=SanitizationState.NOT_INSTRUMENTED, missing_check="pixel_rescan"
)

AADHAAR = "9999 9999 0019"


def envelope(
    texts: list[str],
    evidence: SanitizedEvidence = SANITIZED,
    frame_blind: bool = False,
) -> OutboundEnvelope:
    return OutboundEnvelope(
        destination="external_provider",
        context=SanitizedContext(
            observation_id="obs-7",
            context_version=1,
            url="https://bank.test/account",
            safe_texts=tuple(texts),
            viewport=Viewport(width=1280, height=800),
            frame_blind=frame_blind,
        ),
        evidence=evidence,
        rung=InferenceRung.WASM_SIMD,
        task_description="summarise the account",
    )


@pytest.fixture
def guard() -> EgressGuard:
    return EgressGuard(audit=RingAuditRepository(capacity=500))


# -- V-2: the decisive regression test --------------------------------------


def test_v2_forged_sanitized_payload_is_refused(guard: EgressGuard) -> None:
    """Declares SANITIZED, carries a raw Aadhaar. v1 would have sent it."""
    result = guard.inspect(envelope([f"Aadhaar: {AADHAAR}"]))

    assert result.verdict is TransmissionVerdict.WITHHOLD
    assert result.revalidation.residual_accepted == 1
    assert "re-inspection" in result.reason


def test_sender_is_never_invoked_on_a_refused_payload(guard: EgressGuard) -> None:
    """DP-2: the wire is reachable only through transmit(), and only if allowed."""
    sent: list[OutboundEnvelope] = []
    with pytest.raises(PrivacyBoundaryBreachError):
        guard.transmit(envelope([f"Aadhaar: {AADHAAR}"]), sent.append)
    assert sent == []


def test_guard_ignores_the_declared_state_when_content_contradicts_it(guard: EgressGuard) -> None:
    """The declared state is a claim. The content is the check."""
    result = guard.inspect(
        envelope(["PAN: ABCPH1234F", "card 4532 0151 1283 0366"])
    )
    assert result.verdict is TransmissionVerdict.WITHHOLD
    assert result.revalidation.residual_accepted == 2


# -- the four states --------------------------------------------------------


def test_not_instrumented_never_leaves_the_device(guard: EgressGuard) -> None:
    result = guard.inspect(envelope(["anything"], evidence=NOT_INSTRUMENTED))
    assert result.verdict is TransmissionVerdict.WITHHOLD
    assert "NOT_INSTRUMENTED" in result.reason


def test_degraded_is_permitted_only_as_declared(guard: EgressGuard) -> None:
    result = guard.inspect(envelope(["clean text"], evidence=DEGRADED))
    assert result.verdict is TransmissionVerdict.ALLOW_DECLARED


def test_clean_payload_is_allowed(guard: EgressGuard) -> None:
    result = guard.inspect(
        envelope(["Account summary", "Total due 4200", "Status: active"])
    )
    assert result.verdict in (
        TransmissionVerdict.ALLOW,
        TransmissionVerdict.ALLOW_DECLARED,
    )
    assert result.permitted is True


def test_frame_blindness_cannot_hide_behind_a_full_claim(guard: EgressGuard) -> None:
    """FR-PER-4: blindness must be declared, not absorbed into a false claim."""
    result = guard.inspect(envelope(["clean"], frame_blind=True))
    assert result.verdict is TransmissionVerdict.WITHHOLD
    assert "frame" in result.reason


# -- placeholder tokens must not trip the scanner ---------------------------


def test_our_own_tokens_do_not_trigger_self_detection(guard: EgressGuard) -> None:
    """Nonces contain digits; without token stripping every scan would flag them."""
    result = guard.inspect(
        envelope(
            [
                "Aadhaar: <AADHAAR_1#7f3a2b1c>",
                "PAN: <PAN_1#7f3a2b1c>",
                "Email: <EMAIL_1#7f3a2b1c>",
            ]
        )
    )
    assert result.revalidation.residual_accepted == 0
    assert result.permitted is True


# -- FR-EGR-5: audit every attempt, allowed and blocked ---------------------


def test_every_attempt_is_audited_including_blocked_ones(guard: EgressGuard) -> None:
    with pytest.raises(PrivacyBoundaryBreachError):
        guard.transmit(envelope([f"Aadhaar: {AADHAAR}"]), lambda e: "sent")
    guard.transmit(envelope(["clean text"]), lambda e: "sent")

    totals = summarise(guard.audit.all())
    assert totals["total"] == 2
    assert totals["withheld"] == 1
    assert totals["allowed"] + totals["allowed_declared"] == 1


def test_audit_records_contain_no_raw_value(guard: EgressGuard) -> None:
    """NFR-SEC-5 / F-8: the record is metadata only."""
    with pytest.raises(PrivacyBoundaryBreachError):
        guard.transmit(envelope([f"Aadhaar: {AADHAAR}"]), lambda e: "sent")
    rendered = str([e.as_dict() for e in guard.audit.all()])
    assert "999999990019" not in rendered
    assert "9999" not in rendered


def test_blocked_helper_filters_withheld_events(guard: EgressGuard) -> None:
    with pytest.raises(PrivacyBoundaryBreachError):
        guard.transmit(envelope([f"Aadhaar: {AADHAAR}"]), lambda e: "sent")
    guard.transmit(envelope(["clean"]), lambda e: "sent")
    assert len(guard.audit.blocked()) == 1


# -- audit repository is bounded (SEC-BOUND-001 section 7) -----------------


def test_audit_repository_is_bounded() -> None:
    """A long-running task must not accumulate records without limit."""
    repo = RingAuditRepository(capacity=5)
    guard = EgressGuard(audit=repo)
    for index in range(20):
        guard.transmit(envelope([f"line {index}"]), lambda e: "sent")
    assert len(repo) <= 5


def test_ring_repository_rejects_zero_capacity() -> None:
    with pytest.raises(ValueError):
        RingAuditRepository(capacity=0)


# -- DP-5 at runtime: the payload type cannot be abused ---------------------


def test_unknown_field_is_rejected() -> None:
    """extra='forbid' is the v1 asset this module lifts (GOV-LEDG-001)."""
    with pytest.raises(Exception):
        OutboundEnvelope(
            destination="external_provider",
            context=envelope([]).context,
            evidence=SANITIZED,
            rung=InferenceRung.WASM_SIMD,
            raw_vault_map={"<AADHAAR_1>": "9999 9999 0019"},  # type: ignore[call-arg]
        )

