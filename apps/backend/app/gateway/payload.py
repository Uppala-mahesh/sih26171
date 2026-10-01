"""SIH26171 — Outbound payload contracts (Python).

Implements DES-ARCH-001 rule DP-5 at RUNTIME.

The TypeScript side enforces DP-5 at compile time with branded types. Those are
erased at runtime, so they are a developer discipline rather than a boundary.
Here, `extra="forbid"` plus the absence of any field capable of holding raw
data means a payload either validates or does not exist.

This is also where v1's single best asset is reused: `extra="forbid"` was
lifted from v1's `gateway/schema.py` (see GOV-LEDG-001, LIFT).

Two things this module deliberately CANNOT express, because no field exists:

  * a raw sensitive value              (DP-5, F-1, F-4)
  * the vault reverse mapping          (DP-5, F-2)

And one property it cannot be trusted about: whether its contents are actually
sanitized. That is re-verified by the EgressGuard, not asserted here
(FR-EGR-4, SEC-BOUND-001 I-7).
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.geometry import BoundingBox
from app.contracts.sanitization import InferenceRung, SanitizedEvidence

Destination = Literal["local_enclave", "external_provider"]
RegionSensitivity = Literal["SAFE", "REDACTED", "UNCERTAIN", "OPAQUE"]
UiRole = Literal[
    "BUTTON", "TEXT_INPUT", "PASSWORD_INPUT", "CHECKBOX", "RADIO", "SELECT",
    "LINK", "MENU_ITEM", "TAB", "DIALOG", "TABLE", "FORM", "NAVIGATION",
    "IMAGE", "TEXT_REGION", "UNKNOWN",
]

SCHEMA_VERSION = "1.0.0"


class StrictModel(BaseModel):
    """Base for every outbound model. Unknown fields are a hard error.

    This single class is what makes an unexpected field - including one named
    ``raw_value`` or ``vault_map`` - impossible to smuggle across B-2.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class ElementRef(StrictModel):
    observation_id: str
    element_id: str
    origin: str


class VisualRegion(StrictModel):
    box: BoundingBox
    role: str
    sensitivity: RegionSensitivity
    placeholder: str | None = None


class SafeElementDescriptor(StrictModel):
    """FR-PER-1 / FR-PII-5.

    Note what is absent: no ``value`` field capable of holding raw content, and
    no ``attributes`` mapping. Every text-bearing field is a string that the
    sanitizer has already replaced sensitive spans within.
    """

    ref: ElementRef
    tag_name: str
    role: UiRole
    aria_label: str = ""
    text_content: str = ""
    placeholder: str | None = None
    bounds: BoundingBox
    is_interactive: bool = False
    is_sensitive: bool = False
    opaque: bool = False
    confidence: float = Field(ge=0.0, le=1.0)


class Viewport(StrictModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SanitizedContext(StrictModel):
    """The only shape that may cross B-2 or B-3."""

    observation_id: str
    context_version: int = Field(ge=0)
    captured_at: float = Field(default_factory=time.time)
    url: str
    title: str = ""
    elements: tuple[SafeElementDescriptor, ...] = ()
    safe_texts: tuple[str, ...] = ()
    visual_regions: tuple[VisualRegion, ...] = ()
    viewport: Viewport
    """FR-PER-4: cross-origin frame blindness is DECLARED, never silently omitted."""
    frame_blind: bool = False
    opaque_regions: tuple[BoundingBox, ...] = ()


class OutboundEnvelope(StrictModel):
    """The single outbound envelope (SEC-BOUND-001 condition S-4).

    ``evidence`` is mandatory and carries its own proof, so a payload cannot be
    constructed without declaring what was actually done to it. DP-6 again, now
    enforced at runtime.
    """

    schema_version: str = SCHEMA_VERSION
    destination: Destination
    context: SanitizedContext
    evidence: SanitizedEvidence
    rung: InferenceRung
    task_description: str = ""


def payload_size(envelope: OutboundEnvelope) -> int:
    """Serialised size, for the audit record. Never the content itself."""
    return len(envelope.model_dump_json())
