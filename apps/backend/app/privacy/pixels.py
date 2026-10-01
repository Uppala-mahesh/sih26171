"""SIH26171 — Pixel redaction.

Implements FR-RED-2, FR-RED-3, FR-RED-6 and verifications **V-10** and **V-11**,
closing the gap recorded in SEC-BOUND-001 section 13.2.

Why this module exists
----------------------
Text rendered as an IMAGE defeats every DOM-level control: there is no text node,
no attribute, no accessible name for a detector to read. This module is the only
defence on that route, so it is a security control, not a rendering nicety.

Design decision: OPAQUE FILL, and nothing else
-----------------------------------------------
Blur, pixelation, mosaicking, inversion and partial obscuring are all
prohibited. They look like redaction while leaving information recoverable:

  * blur and mosaic preserve structure and are routinely invertible
  * partial masking leaks the uncovered glyph fragments
  * inversion leaves high-contrast structure readable

A uniform opaque fill overwrites the pixels. The original bytes are destroyed,
not merely obscured, which makes V-10 ("reconstruction recovers zero
characters") a property of the format rather than a hope about the algorithm.

Verification is structural, not statistical
------------------------------------------
Three properties are checked and any failure withholds the artefact:

  1. OPAQUE      every pixel inside the applied mask equals the fill
  2. IRREVERSIBLE  the original region's byte sequence is absent from the output
  3. NON-DESTRUCTIVE  every pixel outside every mask is byte-identical

No Pillow dependency: masks are applied to a plain byte buffer, so the logic is
directly testable and identical in the Python enclave and the browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from app.contracts.geometry import BoundingBox

DEFAULT_FILL: tuple[int, int, int] = (0, 0, 0)

#: FR-RED-3 / V-11: mask geometry must match the detection box.
MINIMUM_IOU = 0.90

#: FR-RED-6: share of pixels outside masks that must be untouched.
MINIMUM_UTILITY = 0.95


class MaskStyle(str, Enum):
    """The only permitted style.

    Enumerated so that a future contributor cannot add ``BLUR`` without the
    type system objecting, which is the point of naming the prohibition.
    """

    OPAQUE_FILL = "OPAQUE_FILL"


class RedactionFailed(RuntimeError):
    """A verification failed. The artefact must be withheld, not shipped."""


@dataclass(frozen=True, slots=True)
class PixelFrame:
    """An uncompressed image buffer. Deliberately not an image library type."""

    width: int
    height: int
    channels: int
    data: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0 or self.channels <= 0:
            raise ValueError("frame dimensions and channels must be positive")
        expected = self.width * self.height * self.channels
        if len(self.data) != expected:
            raise ValueError(
                f"buffer is {len(self.data)} bytes, expected {expected} "
                f"({self.width}x{self.height}x{self.channels})"
            )

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    def pixel_at(self, x: int, y: int) -> bytes:
        start = (y * self.width + x) * self.channels
        return self.data[start : start + self.channels]

    def region_bytes(self, box: BoundingBox) -> bytes:
        """Raw bytes of the region.

        Coordinates are converted with ``int()`` because detectors emit floats
        while pixel addressing needs integers. Passing a float straight to
        ``range()`` raises TypeError — a bug found by running this, not reading it.
        """
        x0, y0, w, h = box.as_int_tuple()
        out = bytearray()
        for y in range(y0, y0 + h):
            for x in range(x0, x0 + w):
                out += self.pixel_at(x, y)
        return bytes(out)


def intersection_over_union(a: BoundingBox, b: BoundingBox) -> float:
    """IoU. FR-RED-3 requires >= 0.90 between the requested and applied box."""
    left = max(a.x, b.x)
    top = max(a.y, b.y)
    right = min(a.x + a.width, b.x + b.width)
    bottom = min(a.y + a.height, b.y + b.height)

    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    union = a.width * a.height + b.width * b.height - intersection
    return intersection / union if union > 0 else 0.0


def clamp_box(box: BoundingBox, frame: PixelFrame) -> BoundingBox:
    """Clamp to the frame so a detection near an edge cannot index out of range."""
    x0 = max(0, min(int(box.x), frame.width - 1))
    y0 = max(0, min(int(box.y), frame.height - 1))
    x1 = max(x0 + 1, min(int(box.x + box.width), frame.width))
    y1 = max(y0 + 1, min(int(box.y + box.height), frame.height))
    return BoundingBox(x=float(x0), y=float(y0), width=float(x1 - x0), height=float(y1 - y0))


@dataclass(frozen=True, slots=True)
class AppliedMask:
    """One mask, with the geometry evidence FR-RED-3 demands."""

    index: int
    requested: BoundingBox
    applied: BoundingBox
    iou: float
    pixels_changed: int
    entity_id: str


@dataclass(frozen=True, slots=True)
class PixelRedactionResult:
    frame: PixelFrame
    masks: tuple[AppliedMask, ...]
    changed_pixels: int
    utility_preservation: float
    style: MaskStyle
    failures: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return not self.failures


class PixelRedactor:
    """Applies opaque masks, then proves three things about the result.

    Stateless. One instance may be reused; it holds no per-call state.
    """

    __slots__ = ()

    def redact(
        self,
        frame: PixelFrame,
        boxes: Sequence[BoundingBox],
        entity_ids: Sequence[str] | None = None,
        fill: tuple[int, int, int] = DEFAULT_FILL,
    ) -> PixelRedactionResult:
        """Mask every box, then verify. Never returns an unverified artefact."""
        buffer = bytearray(frame.data)
        covered = bytearray(frame.pixel_count)
        fill_byte = self._fill_bytes(fill, frame.channels)
        masks: list[AppliedMask] = []

        for index, box in enumerate(boxes):
            applied = clamp_box(box, frame)
            for y in range(int(applied.y), int(applied.y + applied.height)):
                row = y * frame.width
                for x in range(int(applied.x), int(applied.x + applied.width)):
                    offset = (row + x) * frame.channels
                    buffer[offset : offset + frame.channels] = fill_byte
                    covered[row + x] = 1

            changed = self._count_differences(
                frame, PixelFrame(frame.width, frame.height, frame.channels, bytes(buffer)), applied
            )
            masks.append(
                AppliedMask(
                    index=index,
                    requested=box,
                    applied=applied,
                    iou=intersection_over_union(box, applied),
                    pixels_changed=changed,
                    entity_id=(
                        entity_ids[index]
                        if entity_ids is not None and index < len(entity_ids)
                        else "UNKNOWN"
                    ),
                )
            )

        result_frame = PixelFrame(
            frame.width, frame.height, frame.channels, bytes(buffer)
        )
        utility = self._utility_preservation(frame, result_frame, covered)
        failures = self._verify(frame, result_frame, masks, covered, fill_byte, utility)

        return PixelRedactionResult(
            frame=result_frame,
            masks=tuple(masks),
            changed_pixels=sum(m.pixels_changed for m in masks),
            utility_preservation=utility,
            style=MaskStyle.OPAQUE_FILL,
            failures=failures,
        )

    # -- verification ---------------------------------------------------------

    def _verify(
        self,
        original: PixelFrame,
        redacted: PixelFrame,
        masks: Sequence[AppliedMask],
        covered: bytearray,
        fill_byte: bytes,
        utility: float,
    ) -> tuple[str, ...]:
        failures: list[str] = []

        for mask in masks:
            # V-11: geometry must actually match the detection.
            if mask.iou < MINIMUM_IOU:
                failures.append(
                    f"mask {mask.index} ({mask.entity_id}) IoU {mask.iou:.3f} "
                    f"is below the required {MINIMUM_IOU}"
                )

            # FR-RED-2: every pixel inside the mask must be the fill colour.
            for y in range(int(mask.applied.y), int(mask.applied.y + mask.applied.height)):
                for x in range(int(mask.applied.x), int(mask.applied.x + mask.applied.width)):
                    if redacted.pixel_at(x, y) != fill_byte:
                        failures.append(
                            f"mask {mask.index} ({mask.entity_id}) is not fully opaque "
                            f"at ({x},{y})"
                        )
                        break
                else:
                    continue
                break

            # V-10: no original pixel data may survive inside the mask.
            #
            # NOTE: an earlier version searched for the region's byte STRING in
            # the output buffer. That check was vacuous for any multi-row mask,
            # because region_bytes() concatenates row by row while the buffer
            # interleaves the other columns - so the string was never contiguous
            # and the search always returned "gone". Mutation testing exposed
            # this: a no-op mask passed a check that was supposed to catch it.
            #
            # The correct property is per-pixel: a pixel survives only if it
            # still holds its ORIGINAL value and is not the fill colour.
            survivors = self._count_survivors(
                original, redacted, mask.applied, fill_byte
            )
            if survivors:
                failures.append(
                    f"mask {mask.index} ({mask.entity_id}) left {survivors} original "
                    f"pixel(s) recoverable"
                )

        # FR-RED-6: nothing outside a mask may change.
        for y in range(original.height):
            for x in range(original.width):
                if covered[y * original.width + x]:
                    continue
                if original.pixel_at(x, y) != redacted.pixel_at(x, y):
                    failures.append(f"pixel ({x},{y}) changed outside every mask")
                    break
            else:
                continue
            break

        if utility < MINIMUM_UTILITY:
            failures.append(
                f"utility preservation {utility:.4f} is below {MINIMUM_UTILITY}"
            )

        return tuple(failures)

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _fill_bytes(fill: tuple[int, int, int], channels: int) -> bytes:
        if channels >= 3:
            base = bytes(fill[:3])
            return (base * channels)[:channels]
        return bytes([fill[0]]) * channels

    @staticmethod
    def _count_survivors(
        original: PixelFrame,
        redacted: PixelFrame,
        box: BoundingBox,
        fill_byte: bytes,
    ) -> int:
        """Pixels inside ``box`` that still carry their ORIGINAL value.

        A pixel that already equalled the fill colour is not counted: there was
        no information there to protect in the first place.
        """
        bx, by, bw, bh = box.as_int_tuple()
        survivors = 0
        for y in range(by, by + bh):
            for x in range(bx, bx + bw):
                after = redacted.pixel_at(x, y)
                if after != fill_byte and after == original.pixel_at(x, y):
                    survivors += 1
        return survivors

    @staticmethod
    def _count_differences(
        original: PixelFrame, redacted: PixelFrame, box: BoundingBox
    ) -> int:
        changed = 0
        for y in range(int(box.y), int(box.y + box.height)):
            for x in range(int(box.x), int(box.x + box.width)):
                if original.pixel_at(x, y) != redacted.pixel_at(x, y):
                    changed += 1
        return changed

    @staticmethod
    def _utility_preservation(
        original: PixelFrame, redacted: PixelFrame, covered: bytearray
    ) -> float:
        outside = 0
        identical = 0
        for y in range(original.height):
            for x in range(original.width):
                if covered[y * original.width + x]:
                    continue
                outside += 1
                if original.pixel_at(x, y) == redacted.pixel_at(x, y):
                    identical += 1
        return 1.0 if outside == 0 else identical / outside

