"""SIH26171 — Entity taxonomy loader.

Reads ``packages/taxonomy/entities.yaml``, the SINGLE SOURCE OF TRUTH
(REQ-DATA-001), and exposes immutable entity specifications.

Why this exists
---------------
v1 had two independent PII engines whose vocabularies had drifted apart
(defect G-1). The JavaScript engine detected Aadhaar, PAN, UPI, IFSC and OTP;
the Python engine detected none of them; and neither could represent the
India-specific identifiers the problem statement names.

This module is the Python half of the fix. There is exactly one list, it
lives in one file, and it is loaded rather than re-declared
(REQ-DATA-001 rule D-1, DES-ARCH-001 driver D-5).

The TypeScript half is generated from the same YAML, and
``tests/contract/test_parity.py`` proves the two runtimes agree. Divergence
fails the build (REQ-DATA-001 rule X-4).

Governed by
    REQ-DATA-001   sections 1.2 (rules D-1..D-4), 3 (registry)
    SEC-BOUND-001  section 6 (handling by sensitivity class)
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import yaml

TAXONOMY_PATH = (
    Path(__file__).resolve().parents[4] / "packages" / "taxonomy" / "entities.yaml"
)


class TaxonomyError(RuntimeError):
    """The taxonomy is malformed. Fails loudly at import, never silently."""


@functools.lru_cache(maxsize=256)
def _compile(expression: str) -> "re.Pattern[str]":
    """Compilation cache.

    A module-level cache rather than ``functools.cached_property``, because
    ``cached_property`` writes to ``__dict__`` and these dataclasses are declared
    ``slots=True``. That combination raises at first access - a bug found by
    running the loader rather than by reading it.
    """
    try:
        return re.compile(expression, re.IGNORECASE)
    except re.error as exc:  # pragma: no cover - guarded by the test suite
        raise TaxonomyError(f"Invalid entity expression: {expression!r} ({exc})") from exc


@dataclass(frozen=True, slots=True)
class EntitySpec:
    """One immutable entity definition, straight from the catalogue."""

    id: str
    display: str
    sensitivity: str
    tier: str
    validator: str | None
    requires_context: bool
    context_cues: tuple[str, ...]
    placeholder: str
    pattern: str | None
    note: str | None = None

    @property
    def compiled(self) -> "re.Pattern[str] | None":
        """Compiled expression, or None for model-backed entities.

        Every pattern in entities.yaml is anchored and free of nested
        quantifiers, so matching is linear-time (constraint DA-5 / RT-10).
        """
        if self.pattern is None:
            return None
        return _compile(self.pattern)


@dataclass(frozen=True, slots=True)
class Taxonomy:
    version: str
    entities: tuple[EntitySpec, ...]
    sensitivity_classes: tuple[str, ...]
    verification_tiers: Mapping[str, str] = field(default_factory=dict)
    index: Mapping[str, EntitySpec] = field(
        default_factory=dict, compare=False, repr=False
    )

    def by_id(self, entity_id: str) -> EntitySpec | None:
        return self.index.get(entity_id)

    def of_sensitivity(self, *classes: str) -> tuple[EntitySpec, ...]:
        return tuple(e for e in self.entities if e.sensitivity in classes)

    def pattern_backed(self) -> tuple[EntitySpec, ...]:
        return tuple(e for e in self.entities if e.pattern is not None)


def _require(mapping: Mapping[str, object], key: str, entity_id: str) -> object:
    if key not in mapping:
        raise TaxonomyError(f"Entity {entity_id} is missing required key {key!r}")
    return mapping[key]


def _load(path: Path) -> Taxonomy:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict) or "entities" not in raw:
        raise TaxonomyError(f"{path} is not a taxonomy document")

    specs: list[EntitySpec] = []
    for entry in raw["entities"]:
        entity_id = str(_require(entry, "id", "<unknown>"))
        specs.append(
            EntitySpec(
                id=entity_id,
                display=str(_require(entry, "display", entity_id)),
                sensitivity=str(_require(entry, "class", entity_id)),
                tier=str(_require(entry, "tier", entity_id)),
                validator=entry.get("validator"),
                requires_context=bool(entry.get("requires_context", False)),
                context_cues=tuple(entry.get("context_cues", ()) or ()),
                placeholder=str(_require(entry, "placeholder", entity_id)),
                pattern=entry.get("pattern"),
                note=entry.get("note"),
            )
        )

    seen: set[str] = set()
    duplicates = {e.id for e in specs if e.id in seen or seen.add(e.id)}  # type: ignore[func-returns-value]
    if duplicates:
        raise TaxonomyError(f"Duplicate entity ids in taxonomy: {sorted(duplicates)}")

    return Taxonomy(
        version=str(raw.get("version", "0.0.0")),
        entities=tuple(specs),
        sensitivity_classes=tuple(raw.get("sensitivity_classes", ())),
        verification_tiers=dict(raw.get("verification_tiers", {}) or {}),
        index={e.id: e for e in specs},
    )


@functools.lru_cache(maxsize=1)
def load_taxonomy(path: Path | None = None) -> Taxonomy:
    """Load and cache the taxonomy. Immutable, so a single instance is safe."""
    return _load(path or TAXONOMY_PATH)


TAXONOMY: Taxonomy = load_taxonomy()
