"""SIH26171 — Egress guard: the single enforcement point at B-2 and B-3.

Implements FR-EGR-1..FR-EGR-7, obligation **A-6**, and verification **V-2**.

DES-ARCH-001 rule DP-2: this is the ONLY module permitted to perform outbound
transmission. Every other module reaches the network by handing an envelope to
``transmit()`` and letting this module decide whether it is allowed.

The whole point: **the receiver does not trust the sender.**

v1 accepted an ``is_sanitized: true`` boolean from the extension, and when the
vision pipeline silently failed it produced a 1x1 image carrying that boolean,
which the backend accepted as sanitized (v1 defects G-2 and G-6). Here the guard
RE-DERIVES the verdict from the payload's actual contents: it strips our own
placeholder tokens, re-runs the full detector over everything that would go on
the wire, and blocks if anything sensitive survives.

Trusting the sender is what made v1's boundary decorative.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from app.contracts.sanitization import (
    SanitizedEvidence,
    TransmissionVerdict,
    transmission_verdict,
)
from app.gateway.audit import AuditEvent, AuditRepository, InMemoryAuditRepository
from app.gateway.payload import OutboundEnvelope, payload_size
from app.privacy.detectors import PiiDetector, PatternDetector
from app.privacy.vault import strip_tokens


class PrivacyBoundaryBreachError(RuntimeError):
    """An outbound payload was refused. The sender is never invoked."""


@dataclass(frozen=True, slots=True)
class RevalidationReport:
    """What the independent re-inspection actually found."""

    texts_scanned: int
    residual_accepted: int
    residual_uncertain: int

    @property
    def clean(self) -> bool:
        return self.residual_accepted == 0


@dataclass(frozen=True, slots=True)
class InspectionResult:
    verdict: TransmissionVerdict
    reason: str
    revalidation: RevalidationReport
    state: str

    @property
    def permitted(self) -> bool:
        return self.verdict is not TransmissionVerdict.WITHHOLD


class EgressGuard:
    """Inspect, then decide, then transmit — in that order, always.

    Stateless apart from injected collaborators. The audit repository is owned by
    the caller so its lifecycle follows the task.
    """

    __slots__ = ("_audit", "_detector")

    def __init__(
        self,
        audit: AuditRepository | None = None,
        detector: PiiDetector | None = None,
    ) -> None:
        self._audit = audit if audit is not None else InMemoryAuditRepository()
        self._detector = detector or PatternDetector()

    @property
    def audit(self) -> AuditRepository:
        return self._audit

    def revalidate(self, envelope: OutboundEnvelope) -> RevalidationReport:
        """Re-derive the verdict from the payload itself (FR-EGR-4, V-2).

        Placeholder tokens are stripped first, so this examines only
        page-authored content and never the system's own substitutions — without
        that, the nonce digits inside a token would re-detect as an OTP and
        every scan would carry self-inflicted noise.
        """
        context = envelope.context
        segments: list[str] = [context.title, *context.safe_texts]
        for element in context.elements:
            segments.append(element.aria_label)
            segments.append(element.text_content)

        residual_accepted = 0
        residual_uncertain = 0
        scanned = 0

        for segment in segments:
            haystack = strip_tokens(segment)
            if not haystack.strip():
                continue
            scanned += 1
            result = self._detector.detect(haystack)
            residual_accepted += len(result.accepted())
            residual_uncertain += len(result.uncertain())

        return RevalidationReport(
            texts_scanned=scanned,
            residual_accepted=residual_accepted,
            residual_uncertain=residual_uncertain,
        )


    def inspect(self, envelope: OutboundEnvelope) -> InspectionResult:
            """Decide whether this envelope may cross. Never trusts the sender."""
            evidence: SanitizedEvidence = envelope.evidence
            declared = transmission_verdict(evidence)

            # 1. A failure is never upgraded. NOT_INSTRUMENTED never leaves the device.
            if declared is TransmissionVerdict.WITHHOLD:
                return self._refuse(
                    envelope, evidence, "declared state is NOT_INSTRUMENTED", None
                )

            # 2. INDEPENDENT RE-VERIFICATION. The declared state is a claim; this is
            #    the check. It is the control v1 did not have (V-2).
            report = self.revalidate(envelope)
            if not report.clean:
                return self._refuse(
                    envelope,
                    evidence,
                    f"re-inspection found {report.residual_accepted} sensitive value(s) "
                    f"in the outbound payload",
                    report,
                )

            # 3. Frame blindness must be visible, not buried (FR-PER-4). A payload
            #    that claims full sanitation while a frame was never inspected is
            #    claiming something the system cannot know.
            if envelope.context.frame_blind and declared is TransmissionVerdict.ALLOW:
                return self._refuse(
                    envelope,
                    evidence,
                    "payload declares full sanitation while cross-origin frames were "
                    "never inspected; frame blindness must be declared",
                    report,
                )

            # Permitted. Any residual ambiguity travels with the payload.
            if report.residual_uncertain or declared is TransmissionVerdict.ALLOW_DECLARED:
                return InspectionResult(
                    verdict=TransmissionVerdict.ALLOW_DECLARED,
                    reason=(
                        "re-inspection clean; capability loss or ambiguity declared "
                        "and will travel with the payload"
                    ),
                    revalidation=report,
                    state=evidence.state.value,
                )

            return InspectionResult(
                verdict=TransmissionVerdict.ALLOW,
                reason="re-inspection clean and no degradation declared",
                revalidation=report,
                state=evidence.state.value,
            )

    def transmit(
        self,
        envelope: OutboundEnvelope,
        sender: Callable[[OutboundEnvelope], Any],
    ) -> Any:
        """Inspect, audit, and only then hand the payload to ``sender``.

        ``sender`` is not reachable from anywhere else, so this is the
        ENFORCEMENT of rule DP-2 rather than a convention about it.
        """
        result = self.inspect(envelope)
        self._record(envelope, result)

        if not result.permitted:
            raise PrivacyBoundaryBreachError(
                f"egress refused for {envelope.destination}: {result.reason}"
            )

        return sender(envelope)

    # -- internals ------------------------------------------------------------

    def _refuse(
        self,
        envelope: OutboundEnvelope,
        evidence: SanitizedEvidence,
        reason: str,
        report: RevalidationReport | None,
    ) -> InspectionResult:
        return InspectionResult(
            verdict=TransmissionVerdict.WITHHOLD,
            reason=reason,
            revalidation=report
            or RevalidationReport(
                texts_scanned=0, residual_accepted=0, residual_uncertain=0
            ),
            state=evidence.state.value,
        )

    def _record(self, envelope: OutboundEnvelope, result: InspectionResult) -> None:
        unresolved = envelope.evidence.unresolved
        self._audit.record(
            AuditEvent(
                event_id=str(uuid.uuid4()),
                occurred_at=time.time(),
                destination=envelope.destination,
                observation_id=envelope.context.observation_id,
                verdict=result.verdict.value,
                state=result.state,
                redaction_count=len(envelope.context.elements),
                unresolved_count=len(unresolved) if unresolved else 0,
                reason=result.reason,
                payload_bytes=payload_size(envelope),
            )
        )
