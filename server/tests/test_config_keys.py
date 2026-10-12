"""A placeholder credential must never read as a configured provider.

`.env.example` ships with documentation placeholders like `gsk_...` and
`AIza... or AQ....`. Those are non-empty strings, so a naive read treats them as
a real key: the provider chain advertises a model it cannot call, and every
step then dies on an authentication error instead of the cockpit showing the
honest "no provider configured".

The opposite failure is worse: a real key must never be filtered out.
"""
import pytest

from server import config


class TestPlaceholderKeysAreNotCredentials:
    @pytest.mark.parametrize("raw", [
        "gsk_...",
        "AIza... or AQ....",
        "sk-or-v1-...,sk-or-v1-...",
        "  gsk_...  ",
        '"gsk_..."',
        "'AIza...'",
    ])
    def test_documentation_placeholders_read_as_unset(self, raw):
        assert config._clean_key(raw) == ""

    def test_a_real_key_survives(self):
        assert config._clean_key("gsk_realKeyAbCdEf123456") == "gsk_realKeyAbCdEf123456"

    def test_whitespace_and_quotes_are_stripped(self):
        assert config._clean_key('  "sk-or-v1-abc123"  ') == "sk-or-v1-abc123"

    def test_empty_stays_empty(self):
        assert config._clean_key("") == ""
        assert config._clean_key(None) == ""


class TestKeyListsDropPlaceholdersButKeepRealKeys:
    def test_mixed_list_keeps_only_real_keys(self):
        assert config._clean_keys("gsk_...,gsk_realOne,gsk_realTwo") == [
            "gsk_realOne", "gsk_realTwo",
        ]

    def test_an_all_placeholder_list_is_empty(self):
        assert config._clean_keys("gsk_...,gsk_...") == []

    def test_blank_entries_are_dropped(self):
        assert config._clean_keys("a,,b,") == ["a", "b"]


class TestGeminiSplitKeysUsesTheSameRule:
    def test_split_keys_is_not_the_naive_split(self):
        """split_keys feeds the Gemini ladder, so it must apply the same filter
        rather than reintroducing placeholders by a different route."""
        assert config.split_keys("AIza... or AQ....,AIzaRealKey123") == ["AIzaRealKey123"]


class TestAPlaceholderIsAnAQKeyNotAnInvalidOne:
    """Regression guard for the original wrong claim in .env.example, which
    asserted an `AQ.`-prefixed Google credential answers 401 on every call.
    It does not -- a real one works. Placeholder detection must therefore key
    on the documentation ellipsis, never on the `AQ.` prefix."""

    def test_aq_prefixed_real_key_is_kept(self):
        assert config._clean_key("AQ.Ab8RN6KlfXyZ0123456789").startswith("AQ.")

    def test_the_ellipsis_is_what_makes_it_a_placeholder(self):
        # Same prefix, one has the documentation ellipsis, one does not.
        assert config._clean_key("AQ.Ab8RN6Klf...") == ""
        assert config._clean_key("AQ.Ab8RN6KlfXyZ0123456789") != ""