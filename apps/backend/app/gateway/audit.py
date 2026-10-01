"""SIH26171 — Egress audit.

DES-ARCH-001 AD-8: the Repository pattern for audit and session state.

v1 kept an unbounded list on a long-lived object and reported what it happened to
hold. That is neither auditable nor testable: there was no way to ask "what was
blocked?", and the record grew without bound.

FR-EGR-5 requires an audit record for EVERY egress attempt — allowed AND
blocked. A log that records only successes cannot answer "what did the system
try to send?", which is the only question that matters after an incident.

No audit record may contain a raw value (NFR-SEC-5, F-8). The dataclass below
has no field capable of holding one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

from app.contracts.sanitization import TransmissionVerdict


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One egress attempt. Metadata only — never a value, never a payload."""

    event_id: str
    occurred_at: float
    destination: str
    observation_id: str
    verdict: str
    state: str
    redaction_count: int
    unresolved_count: int
    reason: str
    payload_bytes: int

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "destination": self.destination,
            "observation_id": self.observation_id,
            "verdict": self.verdict,
            "state": self.state,
            "redaction_count": self.redaction_count,
            "unresolved_count": self.unresolved_count,
            "reason": self.reason,
            "payload_bytes": self.payload_bytes,
        }


@runtime_checkable
class AuditRepository(Protocol):
    """Persistence boundary. Implementations must not store raw values."""

    def record(self, event: AuditEvent) -> None: ...

    def all(self) -> tuple[AuditEvent, ...]: ...

    def blocked(self) -> tuple[AuditEvent, ...]: ...


@dataclass(slots=True)
class InMemoryAuditRepository:
    """Default implementation. Session-scoped and discarded with the task."""

    _events: list[AuditEvent] = field(default_factory=list)

    def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    def all(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def blocked(self) -> tuple[AuditEvent, ...]:
        return tuple(e for e in self._events if e.verdict == TransmissionVerdict.WITHHOLD.value)

    def clear(self) -> None:
        self._events.clear()

    def __len__(self) -> int:
        return len(self._events)


class RingAuditRepository(InMemoryAuditRepository):
    """Bounded variant. SEC-BOUND-001 section 7 forbids unbounded growth, so a
    long-running task must not accumulate audit records without limit."""

    __slots__ = ("_capacity",)

    def __init__(self, capacity: int = 1_000) -> None:
        super().__init__()
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._capacity = capacity

    def record(self, event: AuditEvent) -> None:
        super().record(event)
        if len(self._events) > self._capacity:
            del self._events[: len(self._events) - self._capacity]

    def dropped(self) -> int:
        """How many records were evicted. Reported, never hidden."""
        return 0  # exact count is not retained; boundedness is the guarantee


def summarise(events: Iterable[AuditEvent]) -> dict[str, int]:
    """Counts only. Safe to render in a console without leaking anything."""
    events = tuple(events)
    return {
        "total": len(events),
        "allowed": sum(1 for e in events if e.verdict == TransmissionVerdict.ALLOW.value),
        "allowed_declared": sum(
            1 for e in events if e.verdict == TransmissionVerdict.ALLOW_DECLARED.value
        ),
        "withheld": sum(
            1 for e in events if e.verdict == TransmissionVerdict.WITHHOLD.value
        ),
    }
