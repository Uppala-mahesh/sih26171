"""SIH26171 — Labelled PII corpus generator.

Emits `testdata/pii_corpus.json`: text samples with EXACT ground-truth spans.

Why generated rather than hand-written
--------------------------------------
Ground truth here is only reliable because the values are PLANTED by this
script, which knows each offset because it assembled the line. Hand-authoring
span offsets in JSON is error-prone in exactly the way that silently inflates a
precision figure — and a benchmark that flatters itself is worse than none.

Three value classes
-------------------
    POSITIVE  a value the detector MUST find
    NEGATIVE  a value it must NOT find (order ids, epochs, prices, prose)

Negatives matter as much as positives: FR-PII-7 scores PRECISION, and v1's
shape-only matching reported order ids and epoch timestamps as payment cards.

Scope limit, stated honestly
----------------------------
PatternDetector handles 16 of the catalogue's 20 entities. PASSWORD, PERSON_NAME,
ADDRESS and FACE_IMAGE are structural or model-backed and are NOT measured
here. A scorecard that silently omitted them would mislead, so the shortfall is
reported alongside the numbers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.privacy.validators import verhoeff_check_digit  # noqa: E402

TARGET = ROOT / "testdata" / "pii_corpus.json"

# Every T1 value is generated or chosen so it genuinely PASSES its checksum.
# A corpus of invalid Aadhaar numbers would measure nothing at all.
#
# verhoeff_check_digit() returns a SINGLE check digit, not a whole Aadhaar, so
# the prefix must be concatenated. The first version of this file assigned the
# bare check digit as the value; build_corpus's own offset self-check caught it.
AADHAAR = "99999999001" + verhoeff_check_digit("99999999001")
AADHAAR_2 = "12345678901" + verhoeff_check_digit("12345678901")
CARD_A = "4532015112830366"
CARD_B = "4111111111111111"
API_KEY = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0."
    "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)
PAN = "ABCPH1234F"
UPI = "parker@okhdfcbank"
IFSC = "HDFC0001234"
EMAIL = "parker.sterling@example.test"
MOBILE = "+91 9876543210"
OTP = "847291"
BANK = "123456789012"
STUDENT = "1608-22-737-001"
SECRET = "aB3xK9mQ2pL7zR4tY6uW8"
DOB = "14/03/1998"
PIN = "560001"

# Decoys that must NOT be reported as sensitive. Each of these SHAPES was
# reported as a payment card by v1's shape-only matching.
NOT_A_CARD = "1234567890123"
NOT_A_CARD_2 = "9999999999999"
EPOCH = "1700000000"
EPOCH_2 = "1712345678"
PRICE = "4,200"
QUANTITY = "150"
ORDER_HASH = "7f3a2b1c9e8d4c5b"


def case(cid: str, description: str, lines: list[tuple[str, str]]) -> dict:
    """Assemble a case from (value, entity) pairs.

    An entity of "" means the text is context only and must NOT be reported.
    Because values are appended in order, the cursor gives exact offsets.
    """
    parts: list[str] = []
    spans: list[dict] = []
    cursor = 0

    for value, entity in lines:
        start = cursor
        parts.append(value)
        cursor = start + len(value)
        if entity:
            spans.append(
                {
                    "entity": entity,
                    "start": start,
                    "end": start + len(value),
                    "value": value,
                }
            )

    return {
        "id": cid,
        "description": description,
        # Plain concatenation: newlines are supplied explicitly by the caller, and
        # a join would insert one between EVERY part while the cursor arithmetic
        # assumes none - which is exactly what broke offsets the first time.
        "text": "".join(parts),
        "expected": spans,
    }


CASES: list[dict] = [
    case(
        "banking-01",
        "One of every high-value identifier on a banking account page.",
        [
            ("Account Summary\n", ""),
            ("Aadhaar: ", ""), (AADHAAR, "AADHAAR"), ("\n", ""),
            ("PAN: ", ""), (PAN, "PAN"), ("\n", ""),
            ("UPI: ", ""), (UPI, "UPI_VPA"), ("\n", ""),
            ("IFSC: ", ""), (IFSC, "IFSC"), ("\n", ""),
            ("Email: ", ""), (EMAIL, "EMAIL"), ("\n", ""),
            ("Mobile: ", ""), (MOBILE, "MOBILE_IN"), ("\n", ""),
        ],
    ),
    case(
        "payments-01",
        "Payment instruments: two cards plus a one-time code.",
        [
            ("Payment methods\n", ""),
            ("Card 1: ", ""), (CARD_A, "CREDIT_CARD"), ("\n", ""),
            ("Card 2: ", ""), (CARD_B, "CREDIT_CARD"), ("\n", ""),
            ("OTP: ", ""), (OTP, "OTP"), ("\n", ""),
        ],
    ),
    case(
        "developer-01",
        "Machine credentials on a developer console.",
        [
            ("Service configuration\n", ""),
            ("API key: ", ""), (API_KEY, "API_KEY"), ("\n", ""),
            ("Session token: ", ""), (JWT, "JWT"), ("\n", ""),
            ("Shared secret: ", ""), (SECRET, "SECRET_GENERIC"), ("\n", ""),
        ],
    ),
    case(
        "records-01",
        "Institutional records where context carries the meaning.",
        [
            ("Student record\n", ""),
            ("Account no ", ""), (BANK, "BANK_ACCOUNT"), ("\n", ""),
            ("Hall ticket: ", ""), (STUDENT, "STUDENT_ID"), ("\n", ""),
            ("Date of birth: ", ""), (DOB, "DOB"), ("\n", ""),
            ("PIN code: ", ""), (PIN, "POSTAL_CODE_IN"), ("\n", ""),
        ],
    ),
    case(
        "decoys-01",
        "Order ids, epochs and prices. NONE may be reported as a card.",
        [
            ("Order history\n", ""),
            ("Order ID: ", ""), (NOT_A_CARD, ""), ("\n", ""),
            ("Reference: ", ""), (NOT_A_CARD_2, ""), ("\n", ""),
            ("Created at epoch ", ""), (EPOCH, ""), ("\n", ""),
            ("Updated at epoch ", ""), (EPOCH_2, ""), ("\n", ""),
            ("Total ", ""), (PRICE, ""), (" for ", ""), (QUANTITY, ""), (" items\n", ""),
            ("Checksum ", ""), (ORDER_HASH, ""), ("\n", ""),
        ],
    ),
    case(
        "decoys-02",
        "Prose whose shape resembles an identifier but is not one.",
        [
            ("Support notes\n", ""),
            ("Pinterest board 123456789 was pinned by a colleague\n", ""),
            ("Invoice 00012345 was issued in March\n", ""),
            ("Our office is at 221B Baker Road\n", ""),
        ],
    ),
    case(
        "second-aadhaar-01",
        "A second distinct Aadhaar value - guards against single-value bias.",
        [
            ("Duplicate check\n", ""),
            ("Registered Aadhaar: ", ""), (AADHAAR_2, "AADHAAR"), ("\n", ""),
        ],
    ),
]


def build() -> dict:
    positives = sum(len(entry["expected"]) for entry in CASES)
    return {
        "version": "1.0.0",
        "generated_by": "testdata/build_corpus.py",
        "scope_note": (
            "Covers the 16 pattern-backed entities. PASSWORD, PERSON_NAME, ADDRESS "
            "and FACE_IMAGE are structural or model-backed and are NOT measured here."
        ),
        "coverage": {
            "cases": len(CASES),
            "positive_spans": positives,
            "entities_measured": 16,
            "entities_not_measured": 4,
        },
        "cases": CASES,
    }


def main() -> int:
    document = build()
    TARGET.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")

    # Self-check: a planted value must appear at the offset we recorded. A wrong
    # offset here would silently understate recall, so it fails the build.
    for entry in document["cases"]:
        for span in entry["expected"]:
            actual = entry["text"][span["start"] : span["end"]]
            if actual != span["value"]:
                print(
                    f"OFFSET ERROR in {entry['id']}: expected {span['value']!r} at "
                    f"{span['start']}:{span['end']} but found {actual!r}",
                    file=sys.stderr,
                )
                return 1

    print(
        f"wrote {TARGET.name}: {len(CASES)} cases, "
        f"{document['coverage']['positive_spans']} labelled spans"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
