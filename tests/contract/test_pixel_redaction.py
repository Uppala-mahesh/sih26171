"""Pixel redaction tests — FR-RED-2, FR-RED-3, FR-RED-6, V-10, V-11, V-12.

Text rendered as an image defeats every DOM-level control, so this module is
the only defence on that route (SEC-THREAT-001 AS-3). The tests therefore check
three STRUCTURAL properties rather than a visual impression:

  1. OPAQUE         every pixel inside a mask is the fill colour
  2. IRREVERSIBLE   the original region's bytes are absent from the output
  3. NON-DESTRUCTIVE nothing outside a mask changes at all
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.contracts.geometry import BoundingBox  # noqa: E402
from app.privacy.pixels import (  # noqa: E402
    DEFAULT_FILL,
    MINIMUM_IOU,
    MINIMUM_UTILITY,
    MaskStyle,
    PixelFrame,
    PixelRedactor,
    clamp_box,
    intersection_over_union,
)

WIDTH, HEIGHT, CHANNELS = 40, 20, 3
FILL_BYTES = bytes(DEFAULT_FILL)

# The "secret" region: varied pixels, so there is genuine information to protect.
SECRET = BoundingBox(x=10, y=5, width=12, height=6)


def build_frame() -> PixelFrame:
    data = bytearray()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            if 10 <= x < 22 and 5 <= y < 11:
                data += bytes([(x * 17) % 256, (y * 31) % 256, (x * y * 7) % 256])
            else:
                data += bytes([200, 200, 200])
    return PixelFrame(WIDTH, HEIGHT, CHANNELS, bytes(data))


@pytest.fixture
def frame() -> PixelFrame:
    return build_frame()


@pytest.fixture
def redactor() -> PixelRedactor:
    return PixelRedactor()


# -- the three structural properties ----------------------------------------


def test_mask_is_fully_opaque(frame: PixelFrame, redactor: PixelRedactor) -> None:
    """FR-RED-2: no blur, no mosaic, no partial obscuring."""
    result = redactor.redact(frame, [SECRET], entity_ids=["AADHAAR"])
    # as_int_tuple(): detectors emit floats, pixel addressing needs integers.
    # Passing box.y straight to range() raises TypeError — which this very test
    # did before it was corrected.
    bx, by, bw, bh = result.masks[0].applied.as_int_tuple()
    values = {
        result.frame.pixel_at(x, y)
        for y in range(by, by + bh)
        for x in range(bx, bx + bw)
    }
    assert len(values) == 1, f"mask is not uniform: {values}"
    assert values == {FILL_BYTES}


def test_original_pixel_data_is_destroyed(frame: PixelFrame, redactor: PixelRedactor) -> None:
    """V-10: reconstruction must recover zero characters.

    Asserted PER PIXEL, not by searching the output buffer for the region's
    byte string. That earlier approach was vacuous for any multi-row mask:
    the region is concatenated row by row while the buffer interleaves the other
    columns, so the string was never contiguous and the search always reported
    "gone". A no-op mask passed a check that existed to catch exactly that.
    """
    original_region = frame.region_bytes(SECRET)
    assert len(set(original_region)) > 1, "fixture must contain real information"

    result = redactor.redact(frame, [SECRET], entity_ids=["AADHAAR"])
    bx, by, bw, bh = result.masks[0].applied.as_int_tuple()

    survivors = sum(
        1
        for y in range(by, by + bh)
        for x in range(bx, bx + bw)
        if result.frame.pixel_at(x, y) != FILL_BYTES
        and result.frame.pixel_at(x, y) == frame.pixel_at(x, y)
    )
    assert survivors == 0, f"{survivors} original pixel(s) still recoverable"
    assert not any("recoverable" in failure for failure in result.failures)


def test_nothing_outside_the_mask_changes(frame: PixelFrame, redactor: PixelRedactor) -> None:
    """FR-RED-6: non-sensitive pixels are untouched, not merely similar."""
    result = redactor.redact(frame, [SECRET], entity_ids=["AADHAAR"])
    bx, by, bw, bh = result.masks[0].applied.as_int_tuple()

    for y in range(HEIGHT):
        for x in range(WIDTH):
            if bx <= x < bx + bw and by <= y < by + bh:
                continue
            assert frame.pixel_at(x, y) == result.frame.pixel_at(x, y), (
                f"pixel ({x},{y}) changed outside the mask"
            )


def test_utility_preservation_meets_the_budget(
    frame: PixelFrame, redactor: PixelRedactor
) -> None:
    """V-12."""
    result = redactor.redact(frame, [SECRET], entity_ids=["AADHAAR"])
    assert result.utility_preservation >= MINIMUM_UTILITY
    assert result.verified is True
    assert result.failures == ()


# -- V-11: geometry must actually match -------------------------------------


def test_mask_geometry_matches_the_detection(
    frame: PixelFrame, redactor: PixelRedactor
) -> None:
    result = redactor.redact(frame, [SECRET], entity_ids=["AADHAAR"])
    assert result.masks[0].iou == pytest.approx(1.0)
    assert result.masks[0].iou >= MINIMUM_IOU


def test_a_clamped_box_is_reported_as_a_failure(
    frame: PixelFrame, redactor: PixelRedactor
) -> None:
    """A detection running past the edge cannot be fully masked — so say so."""
    overhanging = BoundingBox(x=35, y=5, width=12, height=6)
    result = redactor.redact(frame, [overhanging], entity_ids=["CREDIT_CARD"])

    assert result.masks[0].iou < MINIMUM_IOU
    assert result.verified is False
    assert any("IoU" in failure for failure in result.failures)


def test_iou_maths() -> None:
    a = BoundingBox(x=0, y=0, width=10, height=10)
    assert intersection_over_union(a, a) == pytest.approx(1.0)
    assert intersection_over_union(a, BoundingBox(x=20, y=20, width=5, height=5)) == 0.0
    assert intersection_over_union(
        a, BoundingBox(x=0, y=0, width=5, height=10)
    ) == pytest.approx(0.5)


def test_clamp_never_exceeds_the_frame() -> None:
    frame = build_frame()
    clamped = clamp_box(BoundingBox(x=-5, y=-5, width=100, height=100), frame)
    assert clamped.x >= 0 and clamped.y >= 0
    assert clamped.x + clamped.width <= frame.width
    assert clamped.y + clamped.height <= frame.height


# -- the style enum is closed ------------------------------------------------


def test_only_opaque_fill_exists() -> None:
    """FR-RED-2: blur and mosaic are prohibited, so the enum has one member."""
    assert [style.value for style in MaskStyle] == ["OPAQUE_FILL"]


# -- degenerate cases --------------------------------------------------------


def test_no_boxes_changes_nothing(frame: PixelFrame, redactor: PixelRedactor) -> None:
    result = redactor.redact(frame, [])
    assert result.frame.data == frame.data
    assert result.changed_pixels == 0
    assert result.utility_preservation == 1.0
    assert result.verified is True


def test_frame_rejects_a_mismatched_buffer() -> None:
    with pytest.raises(ValueError, match="expected"):
        PixelFrame(4, 4, 3, b"\x00" * 10)


def test_frame_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError):
        PixelFrame(0, 4, 3, b"")


def test_bounding_box_rejects_negative_extent() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        BoundingBox(x=0, y=0, width=-1, height=5)


def test_overlapping_masks_are_both_verified(
    frame: PixelFrame, redactor: PixelRedactor
) -> None:
    boxes = [
        BoundingBox(x=10, y=5, width=12, height=6),
        BoundingBox(x=18, y=7, width=6, height=4),
    ]
    result = redactor.redact(frame, boxes, entity_ids=["AADHAAR", "EMAIL"])
    assert len(result.masks) == 2
    assert all(m.iou >= MINIMUM_IOU for m in result.masks)
    assert result.verified is True


def test_grayscale_and_rgba_buffers_are_supported() -> None:
    """The browser uses canvas; the enclave may use other channel counts."""
    for channels in (1, 4):
        data = bytes((x * y) % 256 for y in range(4) for x in range(4) for _ in range(channels))
        frame = PixelFrame(4, 4, channels, data)
        result = PixelRedactor().redact(frame, [BoundingBox(x=1, y=1, width=2, height=2)])
        assert result.verified is True

