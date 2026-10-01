"""SIH26171 — PII detection: the Strategy pattern.

Implements FR-PII-1..FR-PII-9 and REQ-DATA-001 sections 2.2 / 4.4 / 5.

The detector holds NO entity knowledge of its own. Every entity comes from the
taxonomy (REQ-DATA-001 rule D-1), which is what makes NFR-MAIN-1 ("adding an
entity requires editing one file") true rather than aspirational.

Verification tiers, and what each does with a match
---------------------------------------------------
    T1  checksum / structural arithmetic. A FAILING check DISCARDS the
        finding. It is never downgraded to a lower-confidence positive -
        a failed Luhn is evidence AGAINST the match.
    T2  strict structure. Accepted on shape.
    T3  shape AND a whole-word context cue in a bounded local window.
        No cue -> UNCERTAIN, which still redacts (fail closed, FR-PII-9).
    T4  model-backed. Owned by another strategy; ignored here.

Raw values are deliberately NOT carried on a Finding. A finding records only
span offsets and the caller holds the source text, so nothing here retains a
copy of a secret (FR-VLT-1, SEC-BOUND-001 section 7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from app.privacy.taxonomy import EntitySpec, Taxonomy, load_taxonomy
from app.privacy.validators import (
    entropy_meets,
    ifsc_valid,
    luhn_valid,
    mobile_in_valid,
    pan_valid,
    upi_vpa_valid,
    verhoeff_valid,
)

# REQ-DATA-001 rule G-1: the cue must be LOCAL. Two constraints, both learned
# from a first run that produced four spurious OTP findings inside a card
# number:
#   * the cue must be on the SAME LINE, and
#   * the window is narrow enough not to reach an adjacent field.
CONTEXT_WINDOW = 24

# Shannon-entropy floor for generic secrets, in bits per character.
SECRET_ENTROPY_FLOOR = 3.2

# Sensitivity priority, used to resolve overlapping candidates.
_SENSITIVITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_TIER_RANK = {"T1": 0, "T2": 1, "T3": 2}


class Outcome(str, Enum):
    """REQ-DATA-001 section 4.4. A failing validator yields no finding at all."""

    ACCEPTED = "ACCEPTED"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True, slots=True)
class Finding:
    """A located candidate. Carries offsets, never the raw value."""

    entity_id: str
    start: int
    end: int
    tier: str
    sensitivity: str
    outcome: Outcome
    confidence: float
    placeholder_prefix: str


@dataclass(frozen=True, slots=True)
class DetectionResult:
    findings: tuple[Finding, ...]
    discarded: int

    def accepted(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.outcome is Outcome.ACCEPTED)

    def uncertain(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.outcome is Outcome.UNCERTAIN)

    def ids(self) -> tuple[str, ...]:
        return tuple(f.entity_id for f in self.findings)


# T1/T2 validator dispatch. Adding a validator means adding a name here and a
# function in validators.py - never editing a detector (rule D-1).
_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "verhoeff": verhoeff_valid,
    "luhn": luhn_valid,
    "pan_structure": pan_valid,
    "ifsc_structure": ifsc_valid,
    "psp_allowlist": upi_vpa_valid,
    "mobile_in_structure": mobile_in_valid,
}

_CONFIDENCE = {"T1": 0.99, "T2": 0.90, "T3": 0.85}
_UNCERTAIN_CONFIDENCE = 0.50


class PiiDetector(Protocol):
    """Strategy interface. The sanitizer never needs to know which
    implementation it is holding."""

    @property
    def name(self) -> str: ...

    @property
    def supported_tiers(self) -> frozenset[str]: ...

    def detect(self, text: str) -> DetectionResult: ...


def _line_of(text: str, index: int) -> tuple[int, int]:
    """Bounds of the line containing ``index``, so context cannot cross lines."""
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return start, len(text) if end == -1 else end


def is_isolated_number(text: str, start: int, end: int) -> bool:
    """True when the candidate is a standalone number, not part of a longer run.

    Added after the first run reported the four space-separated groups of
    ``4532 0151 1283 0366`` as four separate OTPs. A genuine OTP stands alone;
    a card fragment is always adjacent to further digit groups.

    Skips at most a few separator characters, so this stays O(1) per candidate
    and linear overall (DA-5).
    """
    index = start - 1
    hops = 0
    while index >= 0 and text[index] in " -" and hops < 3:
        index -= 1
        hops += 1
    before_clear = index < 0 or not text[index].isdigit()

    index = end
    hops = 0
    while index < len(text) and text[index] in " -" and hops < 3:
        index += 1
        hops += 1
    after_clear = index >= len(text) or not text[index].isdigit()

    return before_clear and after_clear


def has_context_cue(spec: EntitySpec, text: str, start: int, end: int) -> bool:
    """REQ-DATA-001 rules G-1..G-5.

    The window deliberately EXCLUDES the candidate span itself, so a cue
    occurring inside the value cannot justify itself (rule G-5). It is also
    confined to the candidate's own line, so a cue in an adjacent field cannot
    lend false credibility to this one.
    """
    line_start, line_end = _line_of(text, start)
    window = (
        f" {text[max(line_start, start - CONTEXT_WINDOW) : start]} "
        f"{text[end : min(line_end, end + CONTEXT_WINDOW)]} "
    ).lower()
    return any(
        re.search(rf"\b{re.escape(cue)}\b", window) for cue in spec.context_cues
    )


def _is_numeric_entity(spec: EntitySpec) -> bool:
    """True when the pattern can only ever match digits.

    The isolation rule applies to numeric entities alone: a card fragment must
    not become a separate OTP, but an email address legitimately sits beside
    other text.
    """
    if not spec.pattern:
        return False
    without_digit_class = spec.pattern.replace(r"\d", "")
    return not re.search(r"[A-Za-z]", without_digit_class)


def resolve_overlaps(findings: list[Finding]) -> list[Finding]:
    """Keep the most significant finding when two candidates share text.

    The first run reported MOBILE_IN and PHONE_INTL at identical offsets, and
    an OTP that was also a valid POSTAL_CODE_IN. Redaction is idempotent, so
    the extra findings were not unsafe - but they inflate the false-positive
    count that FR-PII-7 requires us to publish.

    Priority is sensitivity first, then verification tier: a CRITICAL T1 finding
    always beats a LOW T3 finding covering the same characters.
    """
    ordered = sorted(
        findings,
        key=lambda f: (
            f.start,
            _SENSITIVITY_RANK.get(f.sensitivity, 9),
            _TIER_RANK.get(f.tier, 9),
        ),
    )
    kept: list[Finding] = []
    for candidate in ordered:
        shadowed = any(
            existing.start <= candidate.start and candidate.end <= existing.end
            for existing in kept
        )
        if not shadowed:
            kept.append(candidate)
    return kept


class PatternDetector:
    """The default strategy: taxonomy-driven expression matching with tier
    dispatch. Handles the 16 pattern-backed entities.

    T4 entities (PERSON_NAME, ADDRESS, FACE_IMAGE) and the structural PASSWORD
    case are owned by other strategies and are not reported here.
    """

    def __init__(self, taxonomy: Taxonomy | None = None) -> None:
        self._taxonomy = taxonomy or load_taxonomy()
        self._name = "pattern"

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_tiers(self) -> frozenset[str]:
        return frozenset({"T1", "T2", "T3"})

    @property
    def supported_entities(self) -> tuple[str, ...]:
        return tuple(spec.id for spec in self._taxonomy.pattern_backed())

    def detect(self, text: str) -> DetectionResult:
        """Scan ``text`` once per catalogued entity.

        Complexity is O(E x N) with E entities and N characters; every pattern
        is linear-time (DA-5), so no adversarial page can trigger backtracking.
        """
        if not text:
            return DetectionResult(findings=(), discarded=0)

        findings: list[Finding] = []
        discarded = 0

        for spec in self._taxonomy.pattern_backed():
            expression = spec.compiled
            if expression is None:  # pragma: no cover - pattern_backed guarantees
                continue

            for match in expression.finditer(text):
                candidate = match.group(0)

                # A digit run adjacent to further digit groups is one number,
                # not several. This is what stops a spaced card number being
                # reported as four separate OTPs.
                if _is_numeric_entity(spec) and not is_isolated_number(
                    text, match.start(), match.end()
                ):
                    discarded += 1
                    continue

                # T1 / T2: an arithmetic or structural failure DISCARDS the
                # candidate outright. It is never downgraded to a weaker
                # positive - that is how v1 reported order IDs as cards.
                validator = _VALIDATORS.get(spec.validator or "")
                if validator is not None and not validator(candidate):
                    discarded += 1
                    continue
                if spec.validator == "entropy" and not entropy_meets(
                    candidate, SECRET_ENTROPY_FLOOR
                ):
                    discarded += 1
                    continue

                # T3: context gating. No cue -> UNCERTAIN, which still redacts.
                if spec.requires_context and not has_context_cue(
                    spec, text, match.start(), match.end()
                ):
                    findings.append(
                        Finding(
                            entity_id=spec.id,
                            start=match.start(),
                            end=match.end(),
                            tier=spec.tier,
                            sensitivity=spec.sensitivity,
                            outcome=Outcome.UNCERTAIN,
                            confidence=_UNCERTAIN_CONFIDENCE,
                            placeholder_prefix=spec.placeholder,
                        )
                    )
                    continue

                findings.append(
                    Finding(
                        entity_id=spec.id,
                        start=match.start(),
                        end=match.end(),
                        tier=spec.tier,
                        sensitivity=spec.sensitivity,
                        outcome=Outcome.ACCEPTED,
                        confidence=_CONFIDENCE.get(spec.tier, 0.70),
                        placeholder_prefix=spec.placeholder,
                    )
                )

        resolved = resolve_overlaps(findings)
        resolved.sort(key=lambda f: (f.start, f.entity_id))
        return DetectionResult(findings=tuple(resolved), discarded=discarded)


def detect(text: str) -> DetectionResult:
    """Convenience facade over the default strategy."""
    return PatternDetector().detect(text)

