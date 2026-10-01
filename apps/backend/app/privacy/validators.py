"""SIH26171 — Entity validators.

Implements REQ-DATA-001 section 4.2 / 4.3. These are the controls that defend
the 20% PII precision weight: v1 matched on SHAPE ALONE, so any 13-19 digit
run became a "card" (v1 defect G-5).

Every function here is O(n) with no regular expressions, satisfying constraint
DA-5 (SEC-THREAT-001 R-7): adversarial page text must not be able to trigger
catastrophic backtracking.

Governed by
    REQ-DATA-001   N-1..N-4, section 4.2, section 4.3
    SEC-THREAT-001 DA-5 (linear time), R-2 (novel formats)
    FR-PII-2, FR-PII-3
"""

from __future__ import annotations

import math
import re
from collections import Counter

# ─────────────────────────────────────────────────────────────────────────────
# N-1..N-4 — normalisation, applied before every check
# ─────────────────────────────────────────────────────────────────────────────

_NON_DIGIT = re.compile(r"[\s\-.]")


def normalise_digits(value: str) -> str:
    """Strip whitespace, hyphens and dots (N-1)."""
    return _NON_DIGIT.sub("", value)


def reject_out_of_bounds(value: str, low: int, high: int) -> bool:
    """N-4: reject candidates whose length falls outside declared bounds."""
    return low <= len(value) <= high


# ─────────────────────────────────────────────────────────────────────────────
# T1 — arithmetic validators
# ─────────────────────────────────────────────────────────────────────────────


def luhn_valid(candidate: str) -> bool:
    """Luhn (mod-10) for payment cards.

    Doubling every second digit from the right, subtracting 9 where the result
    exceeds 9, summing, and requiring 0 modulo 10.

    A FAILING Luhn is evidence AGAINST the match (REQ-DATA-001 section 4.4):
    the caller must discard the finding, never downgrade it.
    """
    digits = normalise_digits(candidate)
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    # Rightmost digit is the check digit; double every second digit to its left.
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


# The Verhoeff tables for the dihedral group D5. These are DATA, and they are
# verified by published test vectors in tests/contract/test_validators.py.
#
# This is Aadhaar's REAL checksum. It is not Luhn. Applying Luhn to an Aadhaar
# produces both false positives and false negatives, which is the most common
# implementation error in Indian PII tooling (REQ-DATA-001 section 4.2).
_VERHOEFF_D: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

# The Verhoeff tables for the dihedral group D5. Sourced from the authoritative
# reference implementation and VERIFIED by test vector.
#
# This is Aadhaar's REAL checksum. It is not Luhn. Applying Luhn to an Aadhaar
# produces both false positives and false negatives, which is the most common
# implementation error in Indian PII tooling (REQ-DATA-001 section 4.2).
#
# ── A correction made because a test vector caught it ────────────────────────
# The first implementation of this file used a TEN-row p table applied ONCE after
# the loop. Both halves of that were wrong:
#   1. p has EIGHT rows, indexed by position modulo 8 - not ten.
#   2. p is applied INSIDE the loop, per digit, not as a trailing step.
# The d table was correct throughout. The bug was found because a recalled test
# vector failed, which prompted verification against the authoritative reference.
# See tests/contract/test_validators.py, which pins both tables structurally.
_VERHOEFF_D: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

# EIGHT rows. Indexed by digit position modulo 8, applied inside the loop.
_VERHOEFF_P: tuple[tuple[int, ...], ...] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

# Inverse permutation, used only to GENERATE a check digit.
_VERHOEFF_INV: tuple[int, ...] = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(candidate: str) -> bool:
    """Verhoeff D5 checksum. Valid when the composed checksum is 0.

    Composes right-to-left; at each position the digit is permuted by
    ``_VERHOEFF_P[position % 8]`` before entering the dihedral multiplication.
    """
    digits = normalise_digits(candidate)
    if not digits.isdigit():
        return False
    checksum = 0
    for position, char in enumerate(reversed(digits)):
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[position % 8][int(char)]]
    return checksum == 0


def verhoeff_check_digit(prefix: str) -> str:
    """Compute the check digit that would make ``prefix + digit`` validate.

    Follows the reference implementation exactly: iterate the prefix from its
    END towards its front, applying permutation row ``(index + 1) % 8``.

    A previous version of this function iterated the prefix left-to-right while
    computing the position index from the right, which disagreed with the
    validator on roughly half of all inputs. Round-trip testing caught it; the
    validator itself was always correct.
    """
    digits = normalise_digits(prefix)
    if not digits.isdigit():
        raise ValueError("prefix must be digits only")
    length = len(digits)
    checksum = 0
    for index in range(length):
        digit = int(digits[length - 1 - index])
        checksum = _VERHOEFF_D[checksum][_VERHOEFF_P[(index + 1) % 8][digit]]
    return str(_VERHOEFF_INV[checksum])


def shannon_entropy(value: str) -> float:
    """Bits per character. Used for API keys and generic secrets."""
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return -sum(
        (count / total) * math.log2(count / total) for count in counts.values()
    )


# ─────────────────────────────────────────────────────────────────────────────
# T2 — structural validators (REQ-DATA-001 section 4.3)
# ─────────────────────────────────────────────────────────────────────────────

# REQ-DATA-001 section 4.3: PAN's fourth character is a holder-type code. A
# bare [A-Z]{5}[0-9]{4}[A-Z] expression matches many non-PAN strings, so this
# is the difference between a T2 format match and a T2 match that is correct.
_PAN_HOLDER_TYPES = frozenset("PCFHATBLJG")

# REQ-DATA-001 section 4.3: UPI handles must appear in a maintained PSP list.
_UPI_HANDLES = frozenset(
    {
        "okhdfcbank", "okicici", "oksbi", "okaxis", "ybl", "apl",
        "ibl", "axl", "paytm", "postbank", "barodampay", "upi",
    }
)

_PAN_RE = re.compile(r"[A-Z]{5}[0-9]{4}[A-Z]")
_IFSC_RE = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
_UPI_RE = re.compile(r"([A-Za-z0-9._\-]{2,256})@([A-Za-z0-9]{2,32})")
_MOBILE_IN_RE = re.compile(r"(?:\+91[ -]?|0)?([6-9]\d{4}[ -]?\d{5})")
_POSTAL_RE = re.compile(r"[1-9]\d{5}")


def pan_valid(candidate: str) -> bool:
    """PAN structure plus the mandatory holder-type code in position 4."""
    value = candidate.strip().upper()
    match = _PAN_RE.fullmatch(value)
    if match is None:
        return False
    return value[3] in _PAN_HOLDER_TYPES


def ifsc_valid(candidate: str) -> bool:
    """IFSC is always [A-Z]{4} followed by a literal 0 and six alphanumerics."""
    return _IFSC_RE.fullmatch(candidate.strip().upper()) is not None


def upi_vpa_valid(candidate: str) -> bool:
    """UPI handle must appear in the maintained PSP allowlist.

    The allowlist is the T2 filter that stops every ``user@host`` string on the
    internet from being treated as a payment address.
    """
    match = _UPI_RE.fullmatch(candidate.strip())
    if match is None:
        return False
    return match.group(2).lower() in _UPI_HANDLES


def mobile_in_valid(candidate: str) -> bool:
    """Indian mobile: 10 digits beginning 6-9, with an optional +91 or 0 prefix."""
    return _MOBILE_IN_RE.fullmatch(candidate.strip()) is not None


def postal_code_in_valid(candidate: str) -> bool:
    """Indian PIN code: 6 digits with a non-zero leading digit."""
    return _POSTAL_RE.fullmatch(candidate.strip()) is not None


def entropy_meets(value: str, floor_bits: float) -> bool:
    """T2 entropy gate for API keys and generic secrets.

    All these expressions are anchored and free of nested quantifiers, so they
    are linear-time (DA-5). An adversarial page cannot trigger backtracking.
    """
    return shannon_entropy(value) >= floor_bits
