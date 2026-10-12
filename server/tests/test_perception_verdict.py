"""The perception verdict must describe what a step PROVED, not what it tried.

Every case here is a way a real observation can be less than a clean one. The
risk being guarded against is not a crash -- it is a step that reports success
while a capability quietly failed, which is how a demo ends up claiming a
privacy guarantee nobody measured.
"""
import pytest

from server.schemas import (
    VERDICT_ALLOW_DECLARED,
    VERDICT_DEGRADED,
    VERDICT_SANITIZED,
    VERDICT_WITHHOLD,
    Observation,
    worse,
)


class TestSanitizedOnlyWhenEverythingWorked:
    def test_dom_only_step_is_sanitized(self):
        """No screenshot was asked for, so nothing about pixels is unproven."""
        obs = Observation(page_text="hello")
        assert obs.perception_verdict == VERDICT_SANITIZED
        assert obs.perception_notes

    def test_dom_and_pixels_both_contributed_is_sanitized(self):
        obs = Observation(
            screenshot="b64",
            ocr_regions=[{"text": "Total"}],
            visual_scores={"e1": 0.91},
        )
        assert obs.perception_verdict == VERDICT_SANITIZED

    def test_a_verdict_always_explains_itself(self):
        """No state may be reported without a reason a human can read."""
        samples = [
            Observation(),
            Observation(screenshot="x"),
            Observation(screenshot="x", ocr_error="boom"),
            Observation(screenshot="x", ocr_leak_detected=True),
            Observation(read_by_sight=True),
        ]
        for obs in samples:
            assert obs.perception_notes, obs.perception_verdict
            assert all(isinstance(n, str) and n.strip() for n in obs.perception_notes)


class TestAllowDeclared:
    def test_screenshot_nothing_read_is_not_reported_as_clean(self):
        """A capture that no on-device pass produced anything from proves
        nothing about pixels. Saying SANITIZED here would imply it did."""
        obs = Observation(screenshot="x")
        assert obs.perception_verdict == VERDICT_ALLOW_DECLARED

    def test_page_closed_to_extensions_is_declared_not_clean(self):
        obs = Observation(read_by_sight=True)
        assert obs.perception_verdict == VERDICT_ALLOW_DECLARED


class TestDegraded:
    @pytest.mark.parametrize("field", ["ocr_error", "visual_error", "screenshot_error"])
    def test_a_failed_on_device_capability_degrades_the_step(self, field):
        obs = Observation(**{field: "engine unavailable"})
        assert obs.perception_verdict == VERDICT_DEGRADED

    def test_the_failing_capability_is_named(self):
        obs = Observation(ocr_error="tesseract timed out")
        joined = " ".join(obs.perception_notes).lower()
        assert "ocr" in joined
        assert "tesseract timed out" in joined


class TestWithholdIsFailClosed:
    def test_a_caught_redaction_leak_withholds_everything(self):
        obs = Observation(
            screenshot="x",
            ocr_regions=[{"text": "Total"}],
            visual_scores={"e1": 0.9},
            ocr_leak_detected=True,
            ocr_leak_kinds=["CARD"],
        )
        # Everything else succeeded. WITHHOLD must still win.
        assert obs.perception_verdict == VERDICT_WITHHOLD

    def test_the_leak_note_names_the_kind_never_the_value(self):
        obs = Observation(ocr_leak_detected=True, ocr_leak_kinds=["CARD"])
        joined = " ".join(obs.perception_notes)
        assert "CARD" in joined

    def test_an_unmaskable_page_cannot_claim_a_redaction(self):
        obs = Observation(read_by_sight=True, mask_note="content script blocked here")
        assert obs.perception_verdict == VERDICT_WITHHOLD
        assert "content script blocked here" in " ".join(obs.perception_notes)


class TestAggregation:
    def test_withhold_dominates_every_other_state(self):
        for other in (VERDICT_SANITIZED, VERDICT_ALLOW_DECLARED, VERDICT_DEGRADED):
            assert worse(other, VERDICT_WITHHOLD) == VERDICT_WITHHOLD
            assert worse(VERDICT_WITHHOLD, other) == VERDICT_WITHHOLD

    def test_degraded_dominates_allow_declared_and_sanitized(self):
        assert worse(VERDICT_SANITIZED, VERDICT_DEGRADED) == VERDICT_DEGRADED
        assert worse(VERDICT_ALLOW_DECLARED, VERDICT_DEGRADED) == VERDICT_DEGRADED

    def test_sanitized_is_the_floor(self):
        assert worse(VERDICT_SANITIZED) == VERDICT_SANITIZED
        assert worse(VERDICT_SANITIZED, VERDICT_ALLOW_DECLARED) == VERDICT_ALLOW_DECLARED


class TestVerdictCannotBeForged:
    def test_it_is_derived_not_stored(self):
        """A caller must not be able to assert a verdict; it is computed from
        the measured fields every time it is read."""
        obs = Observation()
        # Setting an attribute of the same name cannot change the property.
        with pytest.raises((AttributeError, ValueError)):
            obs.perception_verdict = VERDICT_SANITIZED
        assert obs.perception_verdict == VERDICT_SANITIZED

    def test_changing_a_measured_field_changes_the_verdict(self):
        obs = Observation(screenshot="x")
        assert obs.perception_verdict == VERDICT_ALLOW_DECLARED
        obs.ocr_regions = [{"text": "found"}]
        assert obs.perception_verdict == VERDICT_SANITIZED
        obs.ocr_leak_detected = True
        assert obs.perception_verdict == VERDICT_WITHHOLD