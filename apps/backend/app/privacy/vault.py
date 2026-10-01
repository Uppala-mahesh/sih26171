"""SIH26171 — Placeholder vault (Z1 only).

Implements FR-VLT-1..FR-VLT-7 and crossing **B-6** of SEC-BOUND-001.

This is the most security-sensitive structure in the system. It is the ONLY
thing that maps a safe token back to a real secret, and the ONLY sanctioned path
by which a raw value legitimately moves after redaction.

Three rules shape the whole design:

1. **It never leaves Z1.** The reverse mapping is in-memory, per task, and is
   never serialised, logged, or included in any outbound payload. The outbound
   contract has no field that could hold it (DES-ARCH-001 rule DP-5).

2. **Detokenization is target-bound (B-6).** A value may be written back ONLY
   into the element it was extracted from. The page cannot ask for a secret to be
   typed into a field it controls, even though it may legitimately display an
   instruction to that effect. This is what stops the PI-7
   exfiltration-by-instruction attack in SEC-THREAT-001 section 7.

3. **Tokens are unforgeable.** Every token carries a per-observation nonce
   generated on-device, so a page that embeds the literal text ``<AADHAAR_1>``
   cannot mint a token that later detokenizes to attacker-chosen content.

   This supersedes the simpler "offset the numbering" rule originally written in
   REQ-DATA-001 section 6 rule P-6. Offsetting is defeated by including every
   plausible offset in the page; a nonce the page cannot predict is not.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Mapping

# Token shape: <TYPE_n#NONCE>. The nonce makes the namespace unforgeable.
TOKEN_RE = re.compile(r"^<(?P<type>[A-Z_]+)_(?P<index>\d+)#(?P<nonce>[0-9a-f]{8})>$")

# Unanchored form, used when stripping our own tokens out of text BEFORE a
# re-inspection scan. Without this, the nonce digits inside a token would be
# re-detected as an OTP and every scan would carry self-inflicted noise.
TOKEN_SCAN_RE = re.compile(r"<[A-Z_]+_\d+#[0-9a-f]{8}>")


def strip_tokens(text: str) -> str:
    """Remove our own placeholder tokens from ``text``.

    Used by the egress re-inspection so that verification examines only
    page-authored content, not the system's own substitutions.
    """
    return TOKEN_SCAN_RE.sub(" ", text)

NONCE_BYTES = 4


class DetokenizationRefused(RuntimeError):
    """A detokenization attempt that crossed the B-6 boundary.

    Raised rather than returning ``None`` so a violation is loud at the call
    site instead of degrading into a silently-typed empty field.
    """


@dataclass(frozen=True, slots=True)
class ElementBinding:
    """The single element a placeholder may legitimately be written back into.

    ``element_id`` is observation-scoped: it identifies a node as it existed when
    the value was captured, which is exactly what FR-AGT-5 rebinding relies on to
    refuse a stale target.
    """

    observation_id: str
    element_id: str

    def __post_init__(self) -> None:
        if not self.observation_id or not self.element_id:
            raise ValueError("ElementBinding requires a non-empty observation and element id")


@dataclass(frozen=True, slots=True)
class SafePrivacySummary:
    """Telemetry-safe view: counts and categories only, never values (FR-VLT-6)."""

    observation_id: str
    total_redactions: int
    by_entity: Mapping[str, int]
    by_sensitivity: Mapping[str, int]
    unresolved_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "total_redactions": self.total_redactions,
            "by_entity": dict(self.by_entity),
            "by_sensitivity": dict(self.by_sensitivity),
            "unresolved_count": self.unresolved_count,
        }


@dataclass(frozen=True, slots=True)
class VaultEntry:
    """One redaction. Holds the raw value, so it must never be serialised."""

    placeholder: str
    entity_type: str
    sensitivity: str
    bound_to: ElementBinding
    raw: str


class PlaceholderVault:
    """In-memory, task-scoped vault.

    One instance per task. ``clear()`` runs on task end, origin navigation and
    user reset (FR-VLT-4); afterwards every token stops resolving and
    detokenization raises.
    """

    __slots__ = (
        "_observation_id",
        "_nonce",
        "_entries",
        "_by_value",
        "_counters",
        "_by_sensitivity",
        "_unresolved",
        "_cleared",
    )

    def __init__(self, observation_id: str, nonce: str | None = None) -> None:
        if not observation_id:
            raise ValueError("vault requires an observation id")
        self._observation_id = observation_id
        # Unpredictable to the page. This is what makes tokens unforgeable.
        self._nonce = nonce if nonce is not None else secrets.token_hex(NONCE_BYTES)
        self._entries: dict[str, VaultEntry] = {}
        self._by_value: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._by_sensitivity: dict[str, int] = {}
        self._unresolved = 0
        self._cleared = False

    # -- introspection (no raw values) ---------------------------------------

    @property
    def observation_id(self) -> str:
        return self._observation_id

    @property
    def nonce(self) -> str:
        return self._nonce

    @property
    def size(self) -> int:
        return len(self._entries)

    def placeholders(self) -> tuple[str, ...]:
        """Token strings only. Safe to place in sanitized output."""
        return tuple(self._entries)

    # -- tokenization ---------------------------------------------------------

    def tokenize(
        self,
        entity_type: str,
        raw: str,
        bound_to: ElementBinding,
        sensitivity: str = "HIGH",
        outcome: str = "ACCEPTED",
    ) -> str:
        """Register a redaction and return its placeholder.

        Identical values share a placeholder within one observation (FR-VLT-2);
        distinct values never do (FR-VLT-3). The binding is recorded here and is
        the only thing detokenization will accept later.
        """
        if self._cleared:
            raise DetokenizationRefused("vault has been cleared; tokenize is not permitted")

        if bound_to.observation_id != self._observation_id:
            raise ValueError(
                "binding observation does not match the vault observation "
                f"({bound_to.observation_id!r} != {self._observation_id!r})"
            )

        # FR-VLT-2: the same value always yields the same token.
        existing = self._by_value.get(raw)
        if existing is not None:
            return existing

        index = self._counters.get(entity_type, 0) + 1
        self._counters[entity_type] = index
        placeholder = f"<{entity_type}_{index}#{self._nonce}>"

        self._entries[placeholder] = VaultEntry(
            placeholder=placeholder,
            entity_type=entity_type,
            sensitivity=sensitivity,
            bound_to=bound_to,
            raw=raw,
        )
        self._by_value[raw] = placeholder
        self._by_sensitivity[sensitivity] = self._by_sensitivity.get(sensitivity, 0) + 1
        if outcome == "UNCERTAIN":
            self._unresolved += 1
        return placeholder

    # -- detokenization: the B-6 gate -----------------------------------------

    def detokenize_for_target(self, placeholder: str, target: ElementBinding) -> str:
        """Resolve a token, but ONLY for the element it was bound to.

        Raises ``DetokenizationRefused`` for an unknown token, a cleared vault,
        or any target other than the bound one. It never returns a value for the
        wrong element, which is the entire point of B-6.
        """
        if self._cleared:
            raise DetokenizationRefused(
                "vault cleared: no placeholder resolves after task end "
                "(FR-VLT-4, REQ-DATA-001 rule VLT-7)"
            )

        entry = self._entries.get(placeholder)
        if entry is None:
            raise DetokenizationRefused(
                f"unknown placeholder {placeholder!r}; a page-supplied token can "
                f"never resolve"
            )

        if entry.bound_to != target:
            raise DetokenizationRefused(
                f"B-6 violation: placeholder bound to "
                f"{entry.bound_to.element_id!r} may not be written to "
                f"{target.element_id!r}"
            )

        return entry.raw

    def can_resolve(self, placeholder: str, target: ElementBinding) -> bool:
        """Non-raising form, for callers that prefer to branch."""
        if self._cleared:
            return False
        entry = self._entries.get(placeholder)
        return entry is not None and entry.bound_to == target

    # -- lifecycle ------------------------------------------------------------

    def clear(self) -> None:
        """Wipe every mapping. Subsequent detokenization raises (FR-VLT-4)."""
        self._entries.clear()
        self._by_value.clear()
        self._counters.clear()
        self._by_sensitivity.clear()
        self._unresolved = 0
        self._cleared = True

    def safe_summary(self) -> SafePrivacySummary:
        """FR-VLT-6: counts and categories only. Never a value, never a token map."""
        by_entity: dict[str, int] = {}
        for entry in self._entries.values():
            by_entity[entry.entity_type] = by_entity.get(entry.entity_type, 0) + 1
        return SafePrivacySummary(
            observation_id=self._observation_id,
            total_redactions=len(self._entries),
            by_entity=by_entity,
            by_sensitivity=dict(self._by_sensitivity),
            unresolved_count=self._unresolved,
        )

    def count_residual(self, haystack: str) -> int:
        """How many stored raw values still appear in ``haystack``.

        The independent re-inspection required by FR-RED-4. It is genuinely
        independent: it searches the produced string for the actual secrets
        rather than trusting that substitution happened correctly.

        Returns a COUNT, never the values. Exposing raw values through a public
        method would be a footgun on the one structure in the system that holds
        them, so the check is performed here and only the tally leaves.
        """
        if self._cleared:
            return 0
        return sum(1 for entry in self._entries.values() if entry.raw in haystack)

    # -- safety net -----------------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover - defensive
        # Never let a raw value reach a log line or a traceback.
        return (
            f"<PlaceholderVault observation={self._observation_id!r} "
            f"entries={len(self._entries)} cleared={self._cleared}>"
        )

    __str__ = __repr__

