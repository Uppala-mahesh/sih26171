"""Cross-runtime parity for PIXEL REDACTION and the EGRESS GUARD.

REQ-DATA-001 rule X-4. The other parity suites each answer one question. This
one answers the two that decide whether the product is honest:

  1. Is the sensitive thing actually ERASED from the pixels?
  2. Does the guard still refuse a payload that merely CLAIMS to be sanitized?

The second is v1 defect G-2/G-6, so ``forged-sanitized-carrying-raw-pii`` is a
fixture rather than a hypothetical. A TypeScript guard that trusted the sender
would look perfectly correct right up until it shipped.

Frame bytes are generated from integer arithmetic on both sides rather than read
from a stored blob, so the buffers are identical by construction and the IoU and
survivor figures are reproducible instead of trusted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "testdata" / "pixel_guard_parity.json"
RUNNER = ROOT / "tests" / "parity" / "run-pixel-guard.cjs"
PIXELS_JS = ROOT / "dist" / "packages" / "privacy" / "pixels.js"

sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.contracts.geometry import BoundingBox  # noqa: E402
from app.contracts.sanitization import (  # noqa: E402
    InferenceRung,
    SanitizationState,
    SanitizedEvidence,
    VerificationProof,
    Verifier,
)
from app.gateway.guard import EgressGuard  # noqa: E402
from app.gateway.payload import (  # noqa: E402
    ElementRef,
    OutboundEnvelope,
    SafeElementDescriptor,
    SanitizedContext,
    Viewport,
)
from app.privacy.pixels import PixelFrame, PixelRedactor  # noqa: E402


def r6(value: float) -> float:
    return round(value, 6)


def _colour(rgb: list[int], channels: int) -> bytes:
    if channels >= 3:
        return bytes(rgb[:3])
    return bytes([rgb[0]]) * channels


def _build_frame(spec: dict, background: list[int], ink: list[int]) -> PixelFrame:
    """Mirrors run-pixel-guard.cjs exactly. Integer arithmetic, no rounding."""
    width, height, channels = spec["width"], spec["height"], spec["channels"]
    bg = _colour(background, channels)
    ink_byte = _colour(ink, channels)

    buffer = bytearray(bg * (width * height))
    for box_index, (bx, by, bw, bh) in enumerate(spec["boxes"]):
        for y in range(by, by + bh):
            for x in range(bx, bx + bw):
                if x < 0 or y < 0 or x >= width or y >= height:
                    continue
                if (x * 7 + y * 13 + box_index * 29) % 5 != 0:
                    offset = (y * width + x) * channels
                    buffer[offset : offset + channels] = ink_byte

    return PixelFrame(width, height, channels, bytes(buffer))


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def typescript_all() -> dict:
    if not PIXELS_JS.exists():
        pytest.fail(f"{PIXELS_JS} is missing. Run: npm run build:parity")
    completed = subprocess.run(
        ["node", str(RUNNER), str(CORPUS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"Node pixel/guard runner failed:\n{completed.stderr}")
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def python_pixels(corpus: dict) -> list[dict]:
    redactor = PixelRedactor()
    out = []
    for spec in corpus["frames"]:
        frame = _build_frame(spec, corpus["background"], corpus["ink"])
        boxes = [BoundingBox(*box) for box in spec["boxes"]]
        result = redactor.redact(frame, boxes, spec["entities"])
        out.append(
            {
                "name": spec["name"],
                "masks": [
                    [m.index, r6(m.iou), m.pixels_changed, m.entity_id]
                    for m in result.masks
                ],
                "changed_pixels": result.changed_pixels,
                "utility_preservation": r6(result.utility_preservation),
                "style": result.style.value,
                "verified": result.verified,
                "failures": list(result.failures),
            }
        )
    return out


def _build_evidence(state: str) -> SanitizedEvidence:
    declared_at = 1700000000.0
    if state == "SANITIZED":
        return SanitizedEvidence(
            state=SanitizationState.SANITIZED,
            proof=VerificationProof(
                verifiers_run=frozenset(
                    {Verifier.TEXT_RESCAN, Verifier.PIXEL_RESCAN}
                ),
                regions_checked=1,
                residual_findings=0,
            ),
            rung=InferenceRung.DOM_ONLY,
            declared_at=declared_at,
        )
    if state == "DEGRADED":
        return SanitizedEvidence(
            state=SanitizationState.DEGRADED,
            reason="ocr_failed",
            rung=InferenceRung.DOM_ONLY,
            declared_at=declared_at,
        )
    return SanitizedEvidence(
        state=SanitizationState.NOT_INSTRUMENTED,
        missing_check="pixel_rescan",
        declared_at=declared_at,
    )


@pytest.fixture(scope="module")
def python_guard(corpus: dict) -> list[dict]:
    guard = EgressGuard()
    out = []
    for case in corpus["guard_cases"]:
        elements = tuple(
            SafeElementDescriptor(
                ref=ElementRef(
                    observation_id="obs-guard-parity",
                    element_id=f"n{i}",
                    origin="https://example.test",
                ),
                tag_name="DIV",
                role="TEXT_REGION",
                aria_label=element["ariaLabel"],
                text_content=element["textContent"],
                bounds=BoundingBox(0.0, 0.0, 10.0, 10.0),
                confidence=0.99,
            )
            for i, element in enumerate(case["elements"])
        )
        envelope = OutboundEnvelope(
            destination="external_provider",
            context=SanitizedContext(
                observation_id="obs-guard-parity",
                context_version=1,
                captured_at=1700000000.0,
                url="https://example.test/account",
                title=case["title"],
                elements=elements,
                safe_texts=tuple(case["safeTexts"]),
                viewport=Viewport(width=1280, height=720),
                frame_blind=case["frameBlind"],
            ),
            evidence=_build_evidence(case["state"]),
            rung=InferenceRung.DOM_ONLY,
            task_description="read the account page",
        )
        result = guard.inspect(envelope)
        out.append(
            {
                "name": case["name"],
                "verdict": result.verdict.value,
                "permitted": result.permitted,
                "reason": result.reason,
                "revalidation": {
                    "texts_scanned": result.revalidation.texts_scanned,
                    "residual_accepted": result.revalidation.residual_accepted,
                    "residual_uncertain": result.revalidation.residual_uncertain,
                    "clean": result.revalidation.clean,
                },
            }
        )
    return out


# -- parity --------------------------------------------------------------------


def test_runtimes_agree_on_every_pixel_case(
    python_pixels: list[dict], typescript_all: dict
) -> None:
    ts = typescript_all["pixels"]
    assert len(python_pixels) == len(ts)
    for py, node in zip(python_pixels, ts):
        assert py == node, f"pixel divergence in {py['name']!r}:\n  py={py}\n  ts={node}"


def test_runtimes_agree_on_every_guard_decision(
    python_guard: list[dict], typescript_all: dict
) -> None:
    """The security assertion, stated separately so a failure names itself."""
    ts = typescript_all["guard"]
    assert len(python_guard) == len(ts)
    for py, node in zip(python_guard, ts):
        assert py == node, f"guard divergence in {py['name']!r}:\n  py={py}\n  ts={node}"


# -- what the comparison is actually asserting ---------------------------------


def test_forged_sanitized_claim_is_withheld_on_both_runtimes(
    python_guard: list[dict], typescript_all: dict
) -> None:
    """v1 defect G-2/G-6, asserted on BOTH runtimes.

    A payload that declares SANITIZED while carrying a raw email is the exact
    shape that v1's backend accepted. The guard must re-derive the verdict from
    the contents and refuse, regardless of what the sender claimed.
    """
    for results in (python_guard, typescript_all["guard"]):
        case = next(r for r in results if r["name"] == "forged-sanitized-carrying-raw-pii")
        assert case["verdict"] == "WITHHOLD"
        assert case["permitted"] is False
        assert case["revalidation"]["residual_accepted"] == 1


def test_frame_blindness_cannot_ride_along_with_a_full_claim(
    python_guard: list[dict], typescript_all: dict
) -> None:
    """FR-PER-4: blindness must be declared, not buried (SEC-BOUND-001 I-6)."""
    for results in (python_guard, typescript_all["guard"]):
        case = next(r for r in results if r["name"] == "frame-blind-but-claims-sanitized")
        assert case["verdict"] == "WITHHOLD"
        assert case["revalidation"]["residual_accepted"] == 0


def test_not_instrumented_never_leaves_the_device(
    python_guard: list[dict], typescript_all: dict
) -> None:
    for results in (python_guard, typescript_all["guard"]):
        case = next(r for r in results if r["name"] == "not-instrumented")
        assert case["verdict"] == "WITHHOLD"
        assert case["permitted"] is False


def test_degradation_travels_with_the_payload_instead_of_blocking_it(
    python_guard: list[dict],
) -> None:
    """DEGRADED fails safe, not closed: it redacts more, so it may cross."""
    case = next(r for r in python_guard if r["name"] == "degraded-but-clean")
    assert case["verdict"] == "ALLOW_DECLARED"
    assert case["permitted"] is True


def test_a_genuinely_clean_payload_is_allowed(python_guard: list[dict]) -> None:
    """Without this, WITHHOLD-everything would pass every other test here."""
    case = next(r for r in python_guard if r["name"] == "clean-sanitized")
    assert case["verdict"] == "ALLOW"
    assert case["revalidation"]["clean"] is True


def test_out_of_bounds_box_is_reported_as_unverified(
    python_pixels: list[dict], typescript_all: dict
) -> None:
    """A mask that cannot reach the geometry floor must not claim success."""
    for results in (python_pixels, typescript_all["pixels"]):
        case = next(r for r in results if r["name"] == "out-of-bounds")
        assert case["verified"] is False
        assert any("IoU" in f for f in case["failures"])


def test_in_bounds_masks_are_fully_opaque_and_lossless_outside(
    python_pixels: list[dict], typescript_all: dict
) -> None:
    for results in (python_pixels, typescript_all["pixels"]):
        case = next(r for r in results if r["name"] == "two-in-bounds")
        assert case["verified"] is True
        assert case["failures"] == []
        assert case["style"] == "OPAQUE_FILL"
        assert case["utility_preservation"] >= 0.95
