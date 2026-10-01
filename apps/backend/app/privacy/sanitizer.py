"""SIH26171 — Text redaction.

Implements FR-RED-1, FR-RED-4 (text half), FR-RED-5, FR-VLT-1..VLT-6 and the
text side of crossing B-6.

Pipeline for one observation:

    raw text
      -> detect (taxonomy-driven, tier-dispatched)
      -> assign a placeholder per finding, recording the target binding
      -> rebuild the text right-to-left so earlier offsets stay valid
      -> RE-SCAN the output and prove every raw value is absent
      -> emit sanitized text + counts

The re-scan is the point. A redactor that reports success because it produced a
token is trusting its own work; this one proves the secret is gone from the
output before declaring anything (FR-RED-4).

Scope, stated honestly
----------------------
This module handles TEXT only. Pixel redaction (FR-RED-2, FR-RED-3, the IoU
check) belongs to the vision engine. So it does NOT emit a full
``SanitizationEvidence``; it emits a ``TextRedactionEvidence``, and the pipeline
composes the four-state contract once pixels have also been verified. Claiming
SANITIZED from a text pass alone would be exactly the unearned claim that
charter gate C-1 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.privacy.detectors import DetectionResult, Outcome, PatternDetector, PiiDetector
from app.privacy.vault import (
    ElementBinding,
    PlaceholderVault,
    SafePrivacySummary,
)


class ResidualLeakError(RuntimeError):
    """A raw value survived redaction.

    Must never happen. Raised rather than logged, and the sanitized output is
    withheld rather than emitted partially redacted (SEC-BOUND-001 section 5.2).
    """


@dataclass(frozen=True, slots=True)
class RedactionRecord:
    """What was redacted and where. Carries no raw value (FR-VLT-1)."""

    placeholder: str
    entity_type: str
    sensitivity: str
    start: int
    end: int
    outcome: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TextRedactionEvidence:
    """What actually happened to this text. Honest about its own limits."""

    observation_id: str
    redactions: int
    verified: bool
    residual_count: int
    unresolved_count: int
    pixel_covered: bool

    @property
    def state(self) -> str:
        """The state this TEXT pass earns on its own.

        ``SANITIZED_TEXT`` only when the re-scan passed and no finding was
        uncertain; ``DEGRADED`` otherwise. It never claims a full
        ``SANITIZED``, because pixels have not been verified here.
        """
        if not self.verified or self.unresolved_count:
            return "DEGRADED"
        return "SANITIZED_TEXT"


@dataclass(frozen=True, slots=True)
class SanitizationOutcome:
    """The complete result. Safe to serialise: no raw value appears anywhere."""

    observation_id: str
    text: str
    records: tuple[RedactionRecord, ...]
    summary: SafePrivacySummary
    evidence: TextRedactionEvidence
    discarded: int

    def safe_dict(self) -> dict[str, object]:
        """Telemetry projection. Never includes the text or any raw value."""
        return {
            "observation_id": self.observation_id,
            "redactions": len(self.records),
            "state": self.evidence.state,
            "verified": self.evidence.verified,
            "unresolved": self.evidence.unresolved_count,
            "summary": self.summary.as_dict(),
        }


class Sanitizer:
    """Detect, tokenise, redact, then PROVE the redaction worked.

    Stateless apart from the injected detector and vault. The vault is supplied
    by the caller so its lifecycle is owned by the task, not by this object
    (FR-VLT-4).
    """

    __slots__ = ("_detector", "_vault")

    def __init__(
        self, vault: PlaceholderVault, detector: PiiDetector | None = None
    ) -> None:
        self._vault = vault
        self._detector = detector or PatternDetector()

    def sanitize(self, text: str, element_id: str = "page-root") -> SanitizationOutcome:
        """Redact every sensitive span in ``text``.

        ``element_id`` is the node the values are considered to have come from;
        it is the binding that ``detokenize_for_target`` will later enforce.
        """
        detection: DetectionResult = self._detector.detect(text)
        binding = ElementBinding(
            observation_id=self._vault.observation_id, element_id=element_id
        )

        records: list[RedactionRecord] = []
        replacements: list[tuple[int, int, str]] = []

        for finding in detection.findings:
            raw = text[finding.start : finding.end]
            if not raw:
                continue
            placeholder = self._vault.tokenize(
                entity_type=finding.entity_id,
                raw=raw,
                bound_to=binding,
                sensitivity=finding.sensitivity,
                outcome=finding.outcome.value,
            )
            records.append(
                RedactionRecord(
                    placeholder=placeholder,
                    entity_type=finding.entity_id,
                    sensitivity=finding.sensitivity,
                    start=finding.start,
                    end=finding.end,
                    outcome=finding.outcome.value,
                    confidence=finding.confidence,
                )
            )
            replacements.append((finding.start, finding.end, placeholder))

        sanitized = self._apply(text, replacements)

        # FR-RED-4: independent re-inspection of the produced artefact.
        residual = self._vault.count_residual(sanitized)
        if residual:
            raise ResidualLeakError(
                f"{residual} raw value(s) survived redaction; output withheld"
            )

        unresolved = sum(1 for r in records if r.outcome == Outcome.UNCERTAIN.value)
        evidence = TextRedactionEvidence(
            observation_id=self._vault.observation_id,
            redactions=len(records),
            verified=True,
            residual_count=0,
            unresolved_count=unresolved,
            pixel_covered=False,
        )

        return SanitizationOutcome(
            observation_id=self._vault.observation_id,
            text=sanitized,
            records=tuple(records),
            summary=self._vault.safe_summary(),
            evidence=evidence,
            discarded=detection.discarded,
        )

    @staticmethod
    def _apply(text: str, replacements: list[tuple[int, int, str]]) -> str:
        """Rebuild right-to-left so earlier offsets stay valid as we splice."""
        out = text
        for start, end, placeholder in sorted(replacements, key=lambda r: r[0], reverse=True):
            out = out[:start] + placeholder + out[end:]
        return out

