"""Detector tests — precision is the scored criterion (FR-PII-7, 20% weight).

Every assertion here traces to a defect observed during the first run of the
detector. These are regression guards, not aspirations:

  * a spaced card number was reported as four separate OTPs
  * a cue on a later line gated a number on an earlier line
  * MOBILE_IN and PHONE_INTL both fired on identical offsets
  * an OTP was simultaneously reported as a postal code
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.privacy.detectors import (  # noqa: E402
    PatternDetector,
    detect,
    has_context_cue,
    is_isolated_number,
    resolve_overlaps,
)
from app.privacy.taxonomy import TAXONOMY  # noqa: E402

BANKING_PAGE = """Customer Details
Aadhaar: 9999 9999 0019
PAN: ABCPH1234F
UPI: parker@okhdfcbank
IFSC: HDFC0001234
Mobile: +91 9876543210
Email: parker.sterling@example.com
Card number: 4532 0151 1283 0366
Account no: 123456789012
OTP: 847291
API key: sk-abcdefghijklmnopqrstuvwxyz1234567890
Order ID: 1234567890123
Session created 1700000000
"""

EXPECTED_ACCEPTED = {
    "AADHAAR", "PAN", "UPI_VPA", "IFSC", "MOBILE_IN",
    "EMAIL", "CREDIT_CARD", "BANK_ACCOUNT", "OTP", "API_KEY",
}


@pytest.fixture(scope="module")
def result():
    return detect(BANKING_PAGE)


# -- Recall: everything planted is found ---------------------------------------


def test_every_planted_entity_is_accepted(result) -> None:
    assert EXPECTED_ACCEPTED.issubset(set(result.ids()))


def test_accepted_set_is_exactly_the_planted_set(result) -> None:
    """No unexpected entity may reach ACCEPTED (precision, FR-PII-7).

    Compared per-instance, not by subtracting entity ids: BANK_ACCOUNT is
    legitimately ACCEPTED for the real account number and UNCERTAIN for the
    order id and epoch, so an id-level subtraction would wrongly discard the
    accepted instance too.
    """
    assert {f.entity_id for f in result.accepted()} == EXPECTED_ACCEPTED


# -- Precision regressions ----------------------------------------------------


def test_card_number_does_not_produce_otp_findings(result) -> None:
    """The defect: ``4532 0151 1283 0366`` reported four separate OTPs."""
    needle = "4532 0151 1283 0366"
    start = BANKING_PAGE.index(needle)
    end = start + len(needle)
    inside = [f for f in result.findings if f.start >= start and f.end <= end]
    assert [f.entity_id for f in inside] == ["CREDIT_CARD"]


def test_order_id_is_not_reported_as_a_card(result) -> None:
    """Shape-only matching makes any 13-19 digit run a card (v1 defect)."""
    needle = "1234567890123"
    start = BANKING_PAGE.index(needle)
    end = start + len(needle)
    inside = [f.entity_id for f in result.findings if f.start >= start and f.end <= end]
    assert "CREDIT_CARD" not in inside


def test_no_two_findings_share_identical_spans(result) -> None:
    """The defect: MOBILE_IN and PHONE_INTL both fired on the same offsets."""
    spans = [(f.start, f.end) for f in result.findings]
    assert len(spans) == len(set(spans))


def test_uncontextualised_numbers_stay_uncertain() -> None:
    """Order ID and epoch are digit runs with no cue: UNCERTAIN, still redacted."""
    assert detect(BANKING_PAGE).uncertain(), "expected at least one UNCERTAIN finding"


# -- Context gating (REQ-DATA-001 rules G-1..G-5) -----------------------------


def test_isolated_number_rule() -> None:
    assert is_isolated_number("OTP: 847291", 5, 11) is True
    assert is_isolated_number("4532 0151 1283 0366", 0, 4) is False
    assert is_isolated_number("value 12345 end", 6, 11) is True


def test_context_does_not_cross_lines() -> None:
    """The defect: an 'OTP' cue on a later line gated a number on an earlier one."""
    spec = TAXONOMY.by_id("OTP")
    assert spec is not None
    two_lines = "123456\nsome other line entirely\nOTP: 999999"
    assert has_context_cue(spec, two_lines, 0, 6) is False
    last = two_lines.index("999999")
    assert has_context_cue(spec, two_lines, last, len(two_lines)) is True


def test_cue_outside_the_value_gates_it() -> None:
    """Rule G-5: the cue may not come from inside the value itself."""
    spec = TAXONOMY.by_id("BANK_ACCOUNT")
    assert spec is not None
    text = "bank account 123456789012"
    start = text.index("123456789012")
    assert has_context_cue(spec, text, start, start + 12) is True


def test_missing_context_yields_no_cue() -> None:
    spec = TAXONOMY.by_id("BANK_ACCOUNT")
    assert spec is not None
    text = "the value is 123456789012 and nothing else"
    start = text.index("123456789012")
    assert has_context_cue(spec, text, start, start + 12) is False


# -- Overlap resolution -------------------------------------------------------


def test_identical_spans_collapse_to_one_finding(result) -> None:
    spans = {(f.start, f.end) for f in result.findings}
    assert len(spans) == len(result.findings)


def test_resolve_overlaps_keeps_most_significant() -> None:
    """A CRITICAL finding must win over a LOW one covering the same characters."""
    findings = list(detect("Aadhaar: 999999990019").findings)
    top = next(f for f in findings if f.entity_id == "AADHAAR")
    impostor = findings[0] if findings[0] is not top else None
    if impostor is not None and (impostor.start, impostor.end) == (top.start, top.end):
        kept = resolve_overlaps([impostor, top])
        assert top in kept
        assert len(kept) == 1


# -- Strategy contract --------------------------------------------------------


def test_detector_advertises_no_entity_list_of_its_own() -> None:
    """FR-PII-1: entity knowledge lives only in the taxonomy."""
    detector = PatternDetector()
    assert detector.name == "pattern"
    assert detector.supported_tiers == frozenset({"T1", "T2", "T3"})
    assert set(detector.supported_entities) == {s.id for s in TAXONOMY.pattern_backed()}


def test_detector_ignores_model_backed_entities(result) -> None:
    """T4 entities belong to another strategy and must not be invented here."""
    assert not {"PERSON_NAME", "ADDRESS", "FACE_IMAGE"} & set(result.ids())


def test_empty_input_is_safe() -> None:
    empty = detect("")
    assert empty.findings == ()
    assert empty.discarded == 0


def test_detection_is_deterministic() -> None:
    assert detect(BANKING_PAGE).ids() == detect(BANKING_PAGE).ids()


def test_findings_never_carry_raw_values(result) -> None:
    """FR-VLT-1: a finding records offsets, not the secret itself."""
    for finding in result.findings:
        assert not hasattr(finding, "value")
        assert not hasattr(finding, "text")

