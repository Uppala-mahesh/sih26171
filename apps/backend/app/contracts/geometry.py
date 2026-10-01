"""SIH26171 — Shared geometry primitives.

The single home for coordinate types shared across modules.

DES-ARCH-001 rule A-2 sets the layering:
``agent -> {policy, execution} -> {perception, privacy} -> contracts``.

``perception`` and ``privacy`` are SIBLINGS, so neither may import the other.
Both need a bounding box, so it belongs here, in ``contracts``, below both.

This module exists because that mistake was actually made: ``privacy.pixels``
initially imported ``BoundingBox`` from ``perception.base`` — a module that does
not even exist in v2. Running the code caught it; reading it would not have.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Screen or image coordinates.

    Origin is the top-left. ``x`` increases rightward, ``y`` downward.
    Coordinates are stored as floats because detectors produce them as floats;
    consumers that address pixels must convert with ``int()``.
    """

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("bounding box width and height must be non-negative")

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_int_tuple(self) -> tuple[int, int, int, int]:
        """(x, y, width, height) as integers, for pixel addressing."""
        return (int(self.x), int(self.y), int(self.width), int(self.height))
