"""SIH26171 — Redaction precision benchmark.

Scores the 20% "redaction precision" rubric weight. Where pii_quality asks
"was the sensitive thing found?", this asks the harder question: **"given that
it was found, is it actually gone, and was anything else harmed?"**

Governed by
    REQ-SRS-001  FR-RED-1..FR-RED-8, FR-VLT-1..FR-VLT-6
    SEC-BOUND-001 V-1 (zero residual), V-10 (irreversible), V-11 (IoU),
                   V-12 (utility preservation)
    PROJECT-CHARTER §5  residual leakage 0.00%, utility >= 0.95

Four independent measurements
-----------------------------
    RESIDUAL LEAKAGE   the sanitized text is re-scanned; anything the detector
                       still recognises is a leak (V-1)
    MASK GEOMETRY      IoU between each applied mask and its detection box
                       must be >= 0.90 (V-11)
    IRREVERSIBILITY    per-pixel survivor count must be zero (V-10)
    UTILITY            non-sensitive characters and pixels must survive
                       unchanged (V-12 / FR-RED-6)

The pixel half needs ground-truth boxes, so this module also renders a synthetic
page. Rendering rather than shipping screenshots means the geometry is known by
CONSTRUCTION - a hand-labelled bounding box is exactly the kind of thing that is
quietly wrong and inflates a result.

Usage
-----
    python benchmarks/redaction_precision.py
    python benchmarks/redaction_precision.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.contracts.geometry import BoundingBox  # noqa: E402
from app.privacy.detectors import PatternDetector  # noqa: E402
from app.privacy.pixels import (  # noqa: E402
    MINIMUM_IOU,
    MINIMUM_UTILITY,
    PixelFrame,
    PixelRedactor,
)
from app.privacy.sanitizer import Sanitizer  # noqa: E402
from app.privacy.taxonomy import load_taxonomy  # noqa: E402
from app.privacy.validators import verhoeff_check_digit  # noqa: E402
from app.privacy.vault import ElementBinding, PlaceholderVault  # noqa: E402

CORPUS = ROOT / "testdata" / "redaction_corpus.json"

# Rendering geometry. Chosen so a 12-digit value and a 3-letter value both fit.
PAGE_WIDTH, PAGE_HEIGHT = 320, 200
CHANNELS = 3
MARGIN_X, MARGIN_Y = 12, 12
ROW_HEIGHT = 18
BACKGROUND = (235, 235, 235)


# ── the corpus ────────────────────────────────────────────────────────────────

AADHAAR = "99999999001" + verhoeff_check_digit("99999999001")
CASES: list[dict] = [
    {
        "id": "redact-01",
        "description": "One high-value identifier surrounded by ordinary prose.",
        "fields": [
            ("Your Aadhaar number", ""),
            (AADHAAR, "AADHAAR"),
            ("is registered to this account", ""),
            ("Contact parker.sterling@example.test", "EMAIL"),
            ("or call +91 9876543210", "MOBILE_IN"),
        ],
    },
    {
        "id": "redact-02",
        "description": "Payment details including a tokenised card.",
        "fields": [
            ("Card on file", ""),
            ("4532 0151 1283 0366", "CREDIT_CARD"),
            ("Verification code", ""),
            ("847291", "OTP"),
            ("Billing PIN code", ""),
            ("560001", "POSTAL_CODE_IN"),
        ],
    },
    {
        "id": "redact-03",
        "description": "Prose only. Nothing here should be redacted at all.",
        "fields": [
            ("Welcome back", ""),
            ("Your order shipped yesterday", ""),
            ("Total 4,200 rupees", ""),
            ("Reference 7f3a2b1c", ""),
            ("Thanks for banking with us", ""),
        ],
    },
    {
        "id": "redact-04",
        "description": (
            "Box deliberately driven past the frame edge. Exercises clamp_box, "
            "so the IoU metric is not measuring a trivial 1.0."
        ),
        "fields": [
            ("Edge case", ""),
            (AADHAAR, "AADHAAR:oob"),
        ],
    },
]


def build_corpus() -> dict:
    return {
        "version": "1.0.0",
        "generated_by": "benchmarks/redaction_precision.py",
        "cases": CASES,
        "coverage": {
            "cases": len(CASES),
            "labelled_values": sum(1 for c in CASES for _, e in c["fields"] if e),
            "prose_only_cases": sum(1 for c in CASES if not any(e for _, e in c["fields"])),
        },
    }


# __APPEND__



# ── synthetic page rendering ─────────────────────────────────────────────────
#
# Ground truth by CONSTRUCTION. Each labelled value occupies a box whose
# geometry the renderer decides, so the IoU denominator is never a number
# someone typed into a JSON file and got wrong.


def _fill(frame: PixelFrame, rgb: tuple[int, int, int]) -> None:
    row = bytes(rgb) * frame.width
    for y in range(frame.height):
        start = y * frame.width * frame.channels
        frame.data[start : start + len(row)] = row


def _ink(seed: int, width: int, height: int) -> list[tuple[int, int]]:
    """Deterministic pseudo-glyph pixels. Seeded so reruns are identical."""
    out: list[tuple[int, int]] = []
    state = seed * 2654435761 + 1
    for y in range(height):
        for x in range(width):
            state = (state * 1103515245 + 12345) & 0x7FFFFFFF
            if state % 5 == 0:
                out.append((x, y))
    return out


def render_case(case: dict) -> tuple[PixelFrame, list[tuple[str, BoundingBox]]]:
    """Lay each field out as a row. Labelled values also get drawn ink."""
    frame = PixelFrame(
        width=PAGE_WIDTH,
        height=PAGE_HEIGHT,
        channels=CHANNELS,
        data=bytearray(PAGE_WIDTH * PAGE_HEIGHT * CHANNELS),
    )
    _fill(frame, BACKGROUND)
    boxes: list[tuple[str, BoundingBox]] = []
    y = MARGIN_Y
    for index, (text, entity) in enumerate(case["fields"]):
        width = min(PAGE_WIDTH - 2 * MARGIN_X, max(8, len(text) * 7))
        height = ROW_HEIGHT - 4
        if entity:
            base = entity.split(":")[0]
            if entity.endswith(":oob"):
                # Overflow the RIGHT edge by 5% only. A box mostly outside the
                # frame cannot reach IoU 0.90 no matter how correct the
                # redactor is - it is geometrically impossible, so it would be
                # an unfair test. 5% overflow yields IoU ~0.917: above the
                # threshold, but far enough from a trivial 1.0 to mean
                # something.
                width = int(PAGE_WIDTH * 1.05)
                y = 40
                height = ROW_HEIGHT - 4
            box = BoundingBox(x=MARGIN_X, y=y, width=width, height=height)
            for dx, dy in _ink(index + 1, min(width, PAGE_WIDTH - MARGIN_X), height):
                if box.x + dx >= PAGE_WIDTH or box.y + dy >= PAGE_HEIGHT:
                    continue
                offset = ((box.y + dy) * frame.width + box.x + dx) * frame.channels
                frame.data[offset : offset + 3] = bytes((32, 32, 32))
            boxes.append((base, box))
        y += ROW_HEIGHT
    return frame, boxes


# ── measurement ───────────────────────────────────────────────────────────────


@dataclass
class Report:
    cases: int = 0
    planted_values: int = 0
    prose_cases: int = 0

    residual_detections: list[dict] = field(default_factory=list)
    token_residuals: list[dict] = field(default_factory=list)
    raw_value_survivors: list[dict] = field(default_factory=list)
    over_redactions: list[dict] = field(default_factory=list)

    boxes: int = 0
    masks_applied: int = 0
    worst_iou: float = 1.0
    worst_iou_case: str = ""
    pixel_survivors: int = 0
    utility_cases: list[tuple[str, float]] = field(default_factory=list)
    failed_cases: list[dict] = field(default_factory=list)

    @property
    def residual_rate(self) -> float:
        """Share of planted values still recognisable after redaction."""
        return len(self.residual_detections) / max(1, self.planted_values)

    @property
    def mask_recall(self) -> float:
        return self.masks_applied / max(1, self.boxes)

    @property
    def worst_utility(self) -> float:
        return min((u for _, u in self.utility_cases), default=1.0)


def evaluate(corpus: dict) -> Report:
    report = Report()
    taxonomy = load_taxonomy()
    # PiiDetector is the Protocol; PatternDetector is the implementation.
    detector = PatternDetector(taxonomy)
    redactor = PixelRedactor()

    for case in corpus["cases"]:
        report.cases += 1
        lines = [text for text, _ in case["fields"]]
        page_text = "\n".join(lines)
        raw_values = [t for t, e in case["fields"] if e]
        report.planted_values += len(raw_values)
        if not raw_values:
            report.prose_cases += 1

        # 1. residual leakage - is the value actually gone?
        vault = PlaceholderVault(observation_id=f"obs-{case['id']}")
        # Sanitizer's signature is (vault, detector) - vault first, because the
        # vault's lifecycle is owned by the task, not by the sanitizer.
        outcome = Sanitizer(vault, detector).sanitize(page_text, element_id=case["id"])

        for finding in detector.detect(outcome.text).accepted():
            report.residual_detections.append(
                {
                    "case": case["id"],
                    "entity": finding.entity_id,
                    "text": outcome.text[finding.start : finding.end],
                }
            )
        residual_tokens = vault.count_residual(outcome.text)
        if residual_tokens:
            report.token_residuals.append(
                {"case": case["id"], "count": residual_tokens}
            )
        for value in raw_values:
            if value in outcome.text:
                report.raw_value_survivors.append(
                    {"case": case["id"], "value": value}
                )

        # 2. mask geometry, 3. irreversibility, 4. utility
        frame, boxes = render_case(case)
        result = redactor.redact(
            frame,
            [box for _, box in boxes],
            [entity for entity, _ in boxes],
        )
        report.boxes += len(boxes)
        report.masks_applied += len(result.masks)
        for mask in result.masks:
            if mask.iou < report.worst_iou:
                report.worst_iou = mask.iou
                report.worst_iou_case = case["id"]
        for failure in result.failures:
            if "surviv" in failure:
                report.pixel_survivors += 1
            report.failed_cases.append({"case": case["id"], "failure": failure})
        report.utility_cases.append((case["id"], result.utility_preservation))

        # redaction precision - prose must not be masked
        if not raw_values and result.masks:
            report.over_redactions.append(
                {"case": case["id"], "masks": len(result.masks)}
            )

    return report


def to_dict(report: Report) -> dict:
    return {
        "benchmark": "redaction_precision",
        "cases": report.cases,
        "planted_values": report.planted_values,
        "prose_only_cases": report.prose_cases,
        "residual_leakage": {
            "rate": round(report.residual_rate, 6),
            "target": 0.0,
            "detections": report.residual_detections,
            "token_residuals": report.token_residuals,
            "raw_value_survivors": report.raw_value_survivors,
        },
        "mask_geometry": {
            "boxes": report.boxes,
            "masks_applied": report.masks_applied,
            "mask_recall": round(report.mask_recall, 6),
            "worst_iou": round(report.worst_iou, 6),
            "worst_iou_case": report.worst_iou_case,
            "target_iou": MINIMUM_IOU,
        },
        "irreversibility": {
            "pixel_survivors": report.pixel_survivors,
            "target": 0,
            "verification_failures": report.failed_cases,
        },
        "utility": {
            "worst_case": round(report.worst_utility, 6),
            "target": MINIMUM_UTILITY,
            "per_case": [
                {"case": c, "preserved": round(u, 6)}
                for c, u in report.utility_cases
            ],
        },
        "redaction_precision": {
            "prose_masked": report.over_redactions,
            "verdict": "clean" if not report.over_redactions else "OVER-REDACTED",
        },
    }


def render(report: Report) -> str:
    d = to_dict(report)
    out: list[str] = []
    add = out.append
    add("=" * 78)
    add("SIH26171 - REDACTION PRECISION BENCHMARK")
    add("=" * 78)
    add(f"Cases / planted values : {report.cases} / {report.planted_values}")
    add(f"Prose-only cases      : {report.prose_cases}")
    add("")

    leak = d["residual_leakage"]
    add("--- RESIDUAL LEAKAGE (re-scan after redaction) ---")
    add(f"  leaks {len(report.residual_detections)}  rate "
        f"{leak['rate']:.4%}  target <= {leak['target']:.2%}")
    if report.residual_detections:
        for item in report.residual_detections:
            add(f"    LEAK {item['case']} {item['entity']} {item['text']!r}")
    else:
        add("    none")
    if report.raw_value_survivors:
        for item in report.raw_value_survivors:
            add(f"    RAW SURVIVED {item['case']} {item['value']!r}")
    if report.token_residuals:
        add(f"    TOKEN RESIDUALS {report.token_residuals}")
    add("")

    geom = d["mask_geometry"]
    add("--- MASK GEOMETRY ---")
    add(f"  boxes {report.boxes}  masks {report.masks_applied}  "
        f"recall {geom['mask_recall']:.2%}")
    add(f"  worst IoU {geom['worst_iou']:.4f} in {report.worst_iou_case!r}  "
        f"target >= {MINIMUM_IOU}")
    add("")

    irr = d["irreversibility"]
    add("--- IRREVERSIBILITY (V-10, per pixel) ---")
    add(f"  survivors {report.pixel_survivors}  target = {irr['target']}")
    add(f"  verification failures {len(report.failed_cases)}")
    add("")

    util = d["utility"]
    add("--- UTILITY PRESERVATION (V-12, outside masks) ---")
    add(f"  worst case {util['worst_case']:.4f}  target >= {MINIMUM_UTILITY}")
    for item in util["per_case"]:
        add(f"    {item['case']}  {item['preserved']:.4f}")
    add("")

    prec = d["redaction_precision"]
    add("--- REDACTION PRECISION (prose must survive) ---")
    add(f"  prose cases masked : {len(report.over_redactions)}")
    add(f"  verdict            : {prec['verdict']}")
    add("=" * 78)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIH26171 redaction benchmark")
    parser.add_argument("--json", action="store_true", help="emit a scorecard")
    parser.add_argument(
        "--write-corpus", action="store_true", help="regenerate the corpus"
    )
    args = parser.parse_args(argv)

    if args.write_corpus:
        CORPUS.write_text(
            json.dumps(build_corpus(), indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {CORPUS.name}")
        return 0

    corpus = build_corpus()
    report = evaluate(corpus)
    if args.json:
        print(json.dumps(to_dict(report), indent=2))
    else:
        print(render(report))

    clean = (
        not report.residual_detections
        and not report.raw_value_survivors
        and not report.token_residuals
        and not report.over_redactions
        and report.worst_iou >= MINIMUM_IOU
        and report.worst_utility >= MINIMUM_UTILITY
        and not report.failed_cases
    )
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
