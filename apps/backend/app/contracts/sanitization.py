"""SIH26171 — Sanitization contract (Python / Pydantic).

Mirrors ``packages/contracts/sanitization.ts``.

Why this file exists when TypeScript already defines the contract
---------------------------------------------------------------------
TypeScript brands are erased at compile time. They give a COMPILE-TIME
discipline; they are not a runtime boundary. This module is where the same
rules become RUNTIME-enforced, because Pydantic validates on every
construction — including construction from an untrusted JSON body arriving over
the loopback interface at crossing B-2.

This is the receiver-side re-verification of SEC-BOUND-001 obligation A-6: the
enclave does not trust Z1's assertion, and this module is where that distrust
is expressed in code.

Governed by
    SEC-BOUND-001 sections 5.2, 5.3, 5.4  (states, evidence, transitions)
    DES-ARCH-001 rules DP-5, DP-6, DP-7
    FR-RED-5, FR-EGR-4
"""

from __future__ import annotations

import time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SanitizationState(str, Enum):
    """The four declared states (SEC-BOUND-001 section 5.2)."""

    SANITIZED = "SANITIZED"
    DEGRADED = "DEGRADED"
    UNCERTAIN = "UNCERTAIN"
    NOT_INSTRUMENTED = "NOT_INSTRUMENTED"


class InferenceRung(str, Enum):
    """Z1 capability ladder (SEC-BOUND-001 section 3.2)."""

    WEBGPU = "webgpu"
    WASM_SIMD = "wasm-simd"
    WASM = "wasm"
    DOM_ONLY = "dom-only"


class Verifier(str, Enum):
    TEXT_RESCAN = "text_rescan"
    PIXEL_RESCAN = "pixel_rescan"
    PLACEHOLDER_AUDIT = "placeholder_audit"
    VAULT_SEGREGATION = "vault_segregation"


class TransmissionVerdict(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_DECLARED = "ALLOW_DECLARED"
    WITHHOLD = "WITHHOLD"


class IllegalTransitionError(RuntimeError):
    """A failure may never be upgraded into a success."""


class VerificationProof(BaseModel):
    """Proof that re-inspection actually ran (SEC-BOUND-001 condition S-2).

    The producer cannot supply this. ``Reinspector`` creates it after
    recomputing the verdict from the redacted artefact.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    verifiers_run: frozenset[Verifier] = Field(min_length=1)
    regions_checked: int = Field(ge=0)
    residual_findings: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _proof_must_be_clean(self) -> "VerificationProof":
        # A proof reporting residual findings cannot back a SANITIZED claim.
        if self.residual_findings > 0:
            raise ValueError(
                "VerificationProof with residual_findings > 0 cannot certify "
                "SANITIZED (SEC-BOUND-001 V-10 / V-11)."
            )
        return self


class SanitizedEvidence(BaseModel):
    """Declared state plus the evidence that justifies it (DES-ARCH-001 DP-6)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: SanitizationState
    declared_at: float = Field(default_factory=time.time)

    proof: VerificationProof | None = None
    rung: InferenceRung | None = None
    reason: str | None = None
    unresolved: frozenset[str] | None = None
    missing_check: str | None = None

    @model_validator(mode="after")
    def _evidence_matches_state(self) -> "SanitizedEvidence":
        """DP-6 AT RUNTIME: the declared state must be backed by its evidence.

        This is the check v1 could not express. v1 accepted
        ``is_sanitized=True`` with no proof whatsoever, and a fully-failed
        vision run produced a 1x1 image carrying that exact boolean — which the
        backend then accepted as sanitized (v1 defects G-2 and G-6).
        """
        match self.state:
            case SanitizationState.SANITIZED:
                if self.proof is None:
                    raise ValueError(
                        "SANITIZED requires a VerificationProof. A state presented "
                        "without evidence is NOT_INSTRUMENTED by definition "
                        "(SEC-BOUND-001 section 5.3)."
                    )
                if self.rung is None:
                    raise ValueError("SANITIZED must declare the rung used.")
                if self.reason or self.missing_check:
                    raise ValueError("SANITIZED must not carry degradation reasons.")

            case SanitizationState.DEGRADED:
                if not self.reason:
                    raise ValueError(
                        "DEGRADED must declare why capability was reduced. "
                        "Silent degradation is the v1 failure mode."
                    )
                if self.rung is None:
                    raise ValueError("DEGRADED must declare the rung actually used.")
                if self.proof is not None:
                    raise ValueError("DEGRADED must not claim verification proof.")

            case SanitizationState.UNCERTAIN:
                if self.unresolved is None:
                    raise ValueError(
                        "UNCERTAIN must list the unresolved entity types."
                    )

            case SanitizationState.NOT_INSTRUMENTED:
                if not self.missing_check:
                    raise ValueError(
                        "NOT_INSTRUMENTED must name the check that could not run. "
                        "A generic failure is not a declaration."
                    )

        return self


# SEC-BOUND-001 section 5.4 — illegal edges are ABSENT, not guarded at runtime.
LEGAL_TRANSITIONS: dict[SanitizationState, frozenset[SanitizationState]] = {
    SanitizationState.SANITIZED: frozenset(),
    SanitizationState.DEGRADED: frozenset({SanitizationState.NOT_INSTRUMENTED}),
    SanitizationState.UNCERTAIN: frozenset({SanitizationState.NOT_INSTRUMENTED}),
    SanitizationState.NOT_INSTRUMENTED: frozenset(),
}


def is_legal_transition(
    origin: SanitizationState, target: SanitizationState
) -> bool:
    return target in LEGAL_TRANSITIONS[origin]


def assert_legal_transition(
    origin: SanitizationState, target: SanitizationState
) -> None:
    if not is_legal_transition(origin, target):
        raise IllegalTransitionError(
            f"Illegal sanitization transition {origin.value} -> {target.value}. "
            "A failure may never be upgraded into a success "
            "(SEC-BOUND-001 section 5.4)."
        )


def transmission_verdict(evidence: SanitizedEvidence) -> TransmissionVerdict:
    """Decide whether a payload may cross B-2 or B-3 (SEC-BOUND-001 section 5.2).

    DEGRADED and UNCERTAIN fail in the SAFE direction — the system knows less,
    so it redacts MORE. Over-redaction costs utility, never privacy. They may
    cross, provided the state is declared.

    NOT_INSTRUMENTED fails in the UNSAFE direction: the system does not know
    what it is missing, so the payload is withheld entirely.
    """
    match evidence.state:
        case SanitizationState.SANITIZED:
            return TransmissionVerdict.ALLOW
        case SanitizationState.DEGRADED | SanitizationState.UNCERTAIN:
            return TransmissionVerdict.ALLOW_DECLARED
        case SanitizationState.NOT_INSTRUMENTED:
            return TransmissionVerdict.WITHHOLD

