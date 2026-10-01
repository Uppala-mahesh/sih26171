"""Vault and sanitizer tests — the B-6 crossing and FR-RED-4 re-verification.

Every assertion corresponds to a specific rule:

  FR-VLT-1  the reverse mapping never appears in any output
  FR-VLT-2  an identical value yields an identical placeholder
  FR-VLT-3  distinct values never share a placeholder
  FR-VLT-4  clearing the vault stops every resolution
  FR-VLT-5  detokenization happens only for the bound target  (B-6)
  FR-VLT-6  telemetry carries counts only, never values
  FR-RED-1  no raw value survives in the sanitized text
  FR-RED-4  the produced artefact is independently re-inspected
  FR-RED-5  the declared state never overstates what happened
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from app.privacy.detectors import Finding, Outcome  # noqa: E402
from app.privacy.sanitizer import ResidualLeakError, Sanitizer  # noqa: E402
from app.privacy.vault import (  # noqa: E402
    DetokenizationRefused,
    ElementBinding,
    PlaceholderVault,
)

PAGE = """Customer Details
Aadhaar: 9999 9999 0019
PAN: ABCPH1234F
Email: parker.sterling@example.com
Card number: 4532 0151 1283 0366
"""

SECRETS = ("9999 9999 0019", "ABCPH1234F", "parker.sterling@example.com", "4532 0151 1283 0366")

BOUND = ElementBinding("obs-42", "page-root")


@pytest.fixture
def vault() -> PlaceholderVault:
    return PlaceholderVault("obs-42")


@pytest.fixture
def outcome(vault: PlaceholderVault):
    return Sanitizer(vault).sanitize(PAGE)


# -- FR-RED-1 / FR-RED-4: the raw text is gone, and proven gone ------------


def test_no_raw_value_survives(outcome) -> None:
    for secret in SECRETS:
        assert secret not in outcome.text, f"{secret!r} survived redaction"


def test_every_planted_entity_was_redacted(outcome) -> None:
    kinds = {r.entity_type for r in outcome.records}
    assert {"AADHAAR", "PAN", "EMAIL", "CREDIT_CARD"}.issubset(kinds)


def test_placeholder_is_nonce_bearing_and_unforgeable(outcome) -> None:
    """P-6: a page cannot mint a token that later resolves."""
    for record in outcome.records:
        assert record.placeholder.startswith("<")
        assert "#" in record.placeholder, "token must carry the per-observation nonce"
        assert record.placeholder.endswith(">")


def test_residual_scan_has_teeth(vault: PlaceholderVault) -> None:
    """FR-RED-4: a detector redacting only ONE of two copies must be caught.

    This is the test proving the re-inspection is real rather than a formality.
    The stub reports the first occurrence only, so the second copy survives in
    the output and the redactor must refuse to emit it.
    """

    class OnlyFirstOccurrence:
        def detect(self, text: str):
            first = text.index("4111111111111111")
            finding = Finding(
                "CREDIT_CARD", first, first + 16, "T1", "CRITICAL",
                Outcome.ACCEPTED, 0.99, "CARD",
            )
            return type("R", (), {"findings": (finding,), "discarded": 0})()

    duplicated = "card 4111111111111111 and again 4111111111111111"
    with pytest.raises(ResidualLeakError, match="survived redaction"):
        Sanitizer(vault, detector=OnlyFirstOccurrence()).sanitize(duplicated)


# -- FR-VLT-1 / FR-VLT-6: the mapping never leaks -------------------------


def test_safe_summary_contains_no_raw_value(outcome, vault: PlaceholderVault) -> None:
    rendered = str(vault.safe_summary().as_dict())
    for secret in SECRETS:
        assert secret not in rendered


def test_safe_dict_carries_no_raw_value(outcome) -> None:
    rendered = str(outcome.safe_dict())
    for secret in SECRETS:
        assert secret not in rendered


def test_records_carry_no_raw_value(outcome) -> None:
    for record in outcome.records:
        assert not hasattr(record, "raw")
        assert not hasattr(record, "value")


def test_repr_does_not_leak(vault: PlaceholderVault) -> None:
    vault.tokenize("AADHAAR", "9999 9999 0019", BOUND)
    for rendering in (repr(vault), str(vault)):
        assert "9999" not in rendering
        assert "PlaceholderVault" in rendering


# -- FR-VLT-2 / FR-VLT-3 -------------------------------------------------


def test_identical_values_share_one_placeholder(vault: PlaceholderVault) -> None:
    first = vault.tokenize("EMAIL", "a@b.com", BOUND)
    second = vault.tokenize("EMAIL", "a@b.com", BOUND)
    assert first == second
    assert vault.size == 1


def test_distinct_values_never_share_a_placeholder(vault: PlaceholderVault) -> None:
    first = vault.tokenize("EMAIL", "a@b.com", BOUND)
    second = vault.tokenize("EMAIL", "c@d.com", BOUND)
    assert first != second
    assert vault.size == 2


def test_counters_are_per_entity_type(vault: PlaceholderVault) -> None:
    a1 = vault.tokenize("AADHAAR", "1111", BOUND)
    c1 = vault.tokenize("CREDIT_CARD", "2222", BOUND)
    a2 = vault.tokenize("AADHAAR", "3333", BOUND)
    assert "_1#" in a1 and "_1#" in c1 and "_2#" in a2


# -- FR-VLT-5 / B-6: the target-binding gate ------------------------------


def test_detokenize_succeeds_for_the_bound_element(vault: PlaceholderVault) -> None:
    token = vault.tokenize("AADHAAR", "9999 9999 0019", BOUND)
    assert vault.detokenize_for_target(token, BOUND) == "9999 9999 0019"


def test_pi7_exfiltration_into_another_element_is_refused(vault: PlaceholderVault) -> None:
    """SEC-THREAT-001 section 7: the attack redaction alone cannot stop."""
    token = vault.tokenize("OTP", "847291", BOUND)
    attacker_field = ElementBinding("obs-42", "attacker-controlled-input")
    with pytest.raises(DetokenizationRefused, match="B-6 violation"):
        vault.detokenize_for_target(token, attacker_field)


def test_page_supplied_placeholder_never_resolves(vault: PlaceholderVault) -> None:
    """P-6: page-authored token text cannot resolve."""
    vault.tokenize("AADHAAR", "9999 9999 0019", BOUND)
    with pytest.raises(DetokenizationRefused, match="unknown placeholder"):
        vault.detokenize_for_target("<AADHAAR_1>", BOUND)


def test_cross_observation_binding_is_refused(vault: PlaceholderVault) -> None:
    token = vault.tokenize("AADHAAR", "9999", BOUND)
    other = ElementBinding("obs-99", "page-root")
    with pytest.raises(DetokenizationRefused, match="B-6 violation"):
        vault.detokenize_for_target(token, other)


def test_binding_from_another_observation_cannot_be_registered(vault: PlaceholderVault) -> None:
    with pytest.raises(ValueError, match="does not match"):
        vault.tokenize("AADHAAR", "1", ElementBinding("obs-99", "x"))


# -- FR-VLT-4: lifecycle -------------------------------------------------


def test_clearing_the_vault_stops_every_resolution(vault: PlaceholderVault) -> None:
    token = vault.tokenize("AADHAAR", "9999 9999 0019", BOUND)
    vault.clear()
    with pytest.raises(DetokenizationRefused, match="cleared"):
        vault.detokenize_for_target(token, BOUND)


def test_cleared_vault_refuses_new_tokenization(vault: PlaceholderVault) -> None:
    vault.clear()
    with pytest.raises(DetokenizationRefused, match="cleared"):
        vault.tokenize("AADHAAR", "1", BOUND)


def test_can_resolve_is_the_non_raising_form(vault: PlaceholderVault) -> None:
    token = vault.tokenize("AADHAAR", "1", BOUND)
    assert vault.can_resolve(token, BOUND) is True
    assert vault.can_resolve(token, ElementBinding("obs-42", "other")) is False
    vault.clear()
    assert vault.can_resolve(token, BOUND) is False


# -- FR-RED-5: the state never overstates -------------------------------


def test_state_is_honest_about_pixels(outcome) -> None:
    """A text pass may not claim a full SANITIZED; pixels are unverified here."""
    assert outcome.evidence.state == "SANITIZED_TEXT"
    assert outcome.evidence.pixel_covered is False
    assert outcome.safe_dict()["state"] == "SANITIZED_TEXT"


def test_uncertain_findings_downgrade_the_state(vault: PlaceholderVault) -> None:
    text = "the number 123456789012 appears with no cue at all"
    result = Sanitizer(vault).sanitize(text)
    assert result.evidence.unresolved_count > 0
    assert result.evidence.state == "DEGRADED"


def test_clean_page_is_sanitized_text(vault: PlaceholderVault) -> None:
    result = Sanitizer(vault).sanitize("Welcome to our website.")
    assert result.evidence.state == "SANITIZED_TEXT"
    assert result.evidence.redactions == 0
