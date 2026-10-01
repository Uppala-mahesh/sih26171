"""Validator tests — the controls that defend the 20% PII precision weight.

v1 matched on SHAPE ALONE (defect G-5): its CREDIT_CARD expression was
``\\b(?:\\d[ -]?){13,19}\\b``, so any 13-19 digit run - an order ID, an epoch
timestamp - was reported as a card number. These tests are the evidence that
v2 does not repeat that.

Two bugs were found by these tests and are recorded in the modules where they
were fixed:
  1. A ten-row Verhoeff p table applied once after the loop. The correct table
     has EIGHT rows and is applied INSIDE the loop.
  2. A check-digit generator that iterated the prefix left-to-right while
     indexing from the right, disagreeing with the validator on ~half of
     inputs.
Neither would have been found by testing the validator alone.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.privacy.validators import (  # noqa: E402
    _VERHOEFF_D,
    _VERHOEFF_P,
    entropy_meets,
    ifsc_valid,
    luhn_valid,
    mobile_in_valid,
    normalise_digits,
    pan_valid,
    postal_code_in_valid,
    shannon_entropy,
    upi_vpa_valid,
    verhoeff_check_digit,
    verhoeff_valid,
)

PREFIXES = [
    "99999999001", "12345678901", "23456789012", "98765432109", "00000000000",
    "11111111111", "55555555555", "99999999999", "12121212121", "13131313131",
    "10000000000", "10000000001", "98765432100", "87654321098", "76543210987",
    "65432109876", "54321098765", "43210987654", "32109876543", "21098765432",
    "10987654321", "19876543210", "98761234509", "87612345098", "76123450987",
    "61234509876", "12345098765", "23450987654", "34509876543", "45098765432",
]


# -- Table structure: a wrong table must fail here -----------------------------


def test_verhoeff_d_has_ten_permutation_rows() -> None:
    assert len(_VERHOEFF_D) == 10
    for row in _VERHOEFF_D:
        assert sorted(row) == list(range(10)), f"d row is not a permutation: {row}"


def test_verhoeff_p_has_eight_permutation_rows() -> None:
    """Eight, not ten. A ten-row p table is the bug that was fixed."""
    assert len(_VERHOEFF_P) == 8
    for row in _VERHOEFF_P:
        assert sorted(row) == list(range(10)), f"p row is not a permutation: {row}"


# -- Ground truth --------------------------------------------------------------


def test_known_valid_aadhaar_is_accepted() -> None:
    assert verhoeff_valid("999999990019") is True


def test_known_invalid_aadhaar_is_rejected() -> None:
    assert verhoeff_valid("123456789012") is False


def test_normalisation_strips_separators() -> None:
    assert normalise_digits("9999 9999 0019") == "999999990019"
    assert verhoeff_valid("9999-9999-0019") is True


def test_non_digit_input_fails_closed() -> None:
    assert verhoeff_valid("abcdefghijkl") is False
    assert luhn_valid("not-a-number") is False


# -- Luhn (payment cards) -----------------------------------------------------


@pytest.mark.parametrize("card", ["4111111111111111", "4532015112830366", "6011111111111117"])
def test_luhn_accepts_valid_cards(card: str) -> None:
    assert luhn_valid(card) is True


@pytest.mark.parametrize("card", ["4111111111111112", "1234567890123456", "99999999999999999999"])
def test_luhn_rejects_invalid_cards(card: str) -> None:
    """This is the v1 defect: shape alone must NOT admit a card."""
    assert luhn_valid(card) is False


def test_luhn_rejects_order_ids_and_timestamps() -> None:
    """Thirteen to nineteen digits that are NOT cards must be rejected."""
    for order_id in ["1234567890123", "9999999999999", "1700000000000"]:
        assert luhn_valid(order_id) is False, f"{order_id} should not be a card"


# -- Verhoeff properties: the two guarantees the algorithm is designed for -----


@pytest.mark.parametrize("prefix", PREFIXES)
def test_check_digit_round_trip(prefix: str) -> None:
    assert verhoeff_valid(prefix + verhoeff_check_digit(prefix)) is True


def test_all_single_digit_mutations_are_detected() -> None:
    """Verhoeff guarantee 1: every single-digit error is detected."""
    base = "99999999001" + verhoeff_check_digit("99999999001")
    undetected = [
        base[:i] + d + base[i + 1 :]
        for i in range(len(base))
        for d in "0123456789"
        if d != base[i] and verhoeff_valid(base[:i] + d + base[i + 1 :])
    ]
    assert undetected == [], f"undetected single-digit mutations: {undetected}"


def test_all_adjacent_transpositions_are_detected() -> None:
    """Verhoeff guarantee 2: all adjacent transpositions are detected."""
    base = "12345678901" + verhoeff_check_digit("12345678901")
    undetected = [
        base[:i] + base[i + 1] + base[i] + base[i + 2 :]
        for i in range(len(base) - 1)
        if base[i] != base[i + 1]
        and verhoeff_valid(base[:i] + base[i + 1] + base[i] + base[i + 2 :])
    ]
    assert undetected == [], f"undetected transpositions: {undetected}"


# -- Structural validators ----------------------------------------------------


@pytest.mark.parametrize("pan", ["ABCPH1234F", "AAAAA0000A", "ZZZGZ9999Z"])
def test_pan_requires_holder_type_character(pan: str) -> None:
    """P, A and G are declared holder types (REQ-DATA-001 section 4.3).

    A PAN is five letters, four digits, one letter - so the holder type sits at
    index 3 of a ten-character string.
    """
    assert pan_valid(pan) is True


@pytest.mark.parametrize(
    "pan",
    [
        "ABCDX1234F",  # index 3 is D - not a declared holder type
        "ABCZE1234F",  # index 3 is Z - not a holder type either
        "ZZZZG9999Z",  # four Z's before the G, so index 3 is still Z
        "ABCDE1234",   # one character short
        "AB-DE1234F",  # separator
        "TOOSHORT1X",
    ],
)
def test_pan_rejects_wrong_holder_type_or_shape(pan: str) -> None:
    """A bare [A-Z]{5}[0-9]{4}[A-Z] shape match is deliberately insufficient."""
    assert pan_valid(pan) is False


@pytest.mark.parametrize("code", ["HDFC0001234", "SBIN0000123", "ICIC0000001"])
def test_ifsc_accepts_valid_codes(code: str) -> None:
    assert ifsc_valid(code) is True


@pytest.mark.parametrize("code", ["HDFC1001234", "HDFC000123", "HDFC00012345"])
def test_ifsc_requires_literal_zero_in_fifth_position(code: str) -> None:
    assert ifsc_valid(code) is False


@pytest.mark.parametrize(
    "vpa", ["user@okhdfcbank", "parker@okaxis", "a.b@paytm", "ab@ybl"]
)
def test_upi_accepts_known_psp_handles(vpa: str) -> None:
    assert upi_vpa_valid(vpa) is True


@pytest.mark.parametrize(
    "vpa",
    [
        "user@example.com",  # handle not in the PSP allowlist
        "user@gmail.com",    # nor is this one
        "not-an-email",      # no @ at all
        "x@ybl",             # localpart below the 2-character minimum
    ],
)
def test_upi_rejects_unknown_handles(vpa: str) -> None:
    """The allowlist stops every email address on the web being a payment address."""
    assert upi_vpa_valid(vpa) is False


@pytest.mark.parametrize("number", ["9876543210", "+919876543210", "09876543210", "98765 43210"])
def test_mobile_in_accepts_valid_numbers(number: str) -> None:
    assert mobile_in_valid(number) is True


@pytest.mark.parametrize("number", ["1234567890", "987654321", "abcdefghij", "98765432101"])
def test_mobile_in_rejects_invalid_numbers(number: str) -> None:
    assert mobile_in_valid(number) is False


@pytest.mark.parametrize("pin", ["110001", "560001", "999999"])
def test_postal_code_accepts_valid_pins(pin: str) -> None:
    assert postal_code_in_valid(pin) is True


@pytest.mark.parametrize("pin", ["012345", "12345", "1234567", "abcdef"])
def test_postal_code_rejects_leading_zero_and_bad_shapes(pin: str) -> None:
    assert postal_code_in_valid(pin) is False


# -- Entropy ------------------------------------------------------------------


def test_entropy_separates_secret_from_prose() -> None:
    assert shannon_entropy("aaaaaaaaaaaaaaaa") < 1.0
    assert shannon_entropy("aB3xK9mQ2pL7zR4tY6uW1") > 3.5


def test_entropy_gate_blocks_low_entropy_candidates() -> None:
    assert entropy_meets("aaaaaaaaaaaaaaaa", 3.0) is False
    assert entropy_meets("aB3xK9mQ2pL7zR4tY6uW1", 3.0) is True


# -- DA-5: adversarial input must not trigger backtracking (RT-10) ------------


def test_validators_are_linear_time_on_adversarial_input() -> None:
    """SEC-THREAT-001 R-7 / DA-5 / RT-10.

    Fifty thousand digits with separators - the shape that defeats a naive
    nested-quantifier expression - must complete well inside the main-thread
    budget of NFR-PERF-5.
    """
    adversarial = ("9 " * 25_000).strip()
    start = time.perf_counter()
    for _ in range(20):
        normalise_digits(adversarial)
        verhoeff_valid(adversarial)
        luhn_valid(adversarial)
        mobile_in_valid(adversarial)
        postal_code_in_valid(adversarial)
        upi_vpa_valid(adversarial)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 500, f"adversarial input took {elapsed_ms:.0f} ms"

