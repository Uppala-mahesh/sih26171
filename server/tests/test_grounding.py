"""A currency-prefixed amount must still count as a checkable answer.

The finish guard asks whether the answer is supported by the observed page.
`_distinctive_terms` used to keep only words of six or more characters, so
"The order total is ₹1,799." produced exactly one term (the number) and the
guard treated a real answer as "no answer given". Five-letter content words
such as "order" and "total" are distinctive enough to support the answer.
"""
from server.loop import _distinctive_terms, _grounding_ratio
from server.schemas import Observation


def test_currency_prefixed_amount_with_short_content_words_is_grounded():
    summary = "The order total is ₹1,799."
    terms = _distinctive_terms(summary)

    assert "order" in terms
    assert "total" in terms
    assert any("1,799" in term for term in terms)

    obs = Observation(
        url="http://127.0.0.1:8787/fixtures/pii",
        title="Customer record - PII redaction fixture",
        page_text="Order total: ₹1,799. Customer record and account details.",
    )
    ratio = _grounding_ratio(summary, obs)

    assert ratio is not None
    assert ratio >= 0.5
