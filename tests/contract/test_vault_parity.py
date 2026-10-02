"""Cross-runtime parity for the VAULT and SANITIZER — REQ-DATA-001 rule X-4.

The detector parity test proves the two runtimes agree on WHAT is sensitive.
This one proves they agree on the harder, more dangerous question: **can a
redacted value come back, and only to the place it was taken from?**

That question is crossing **B-6** of SEC-BOUND-001, so it is compared rather
than assumed. A divergence here is not cosmetic - it would mean one runtime
refuses an attacker-controlled target and the other honours it.

The corpus pins the nonce so token strings are byte-comparable. Production
nonces are random, and that randomness is exactly what makes a token
unforgeable, so pinning is confined to this harness.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "testdata" / "sanitizer_parity.json"
RUNNER = ROOT / "tests" / "parity" / "run-sanitizer.cjs"
SANITIZER_JS = ROOT / "dist" / "packages" / "privacy" / "sanitizer.js"

sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.privacy.sanitizer import Sanitizer  # noqa: E402
from app.privacy.vault import (  # noqa: E402
    DetokenizationRefused,
    ElementBinding,
    PlaceholderVault,
)


def _refused(fn) -> bool:
    """Whether an operation refused. Mirrors the Node runner's helper."""
    try:
        fn()
        return False
    except DetokenizationRefused:
        return True


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def python_results(corpus: dict) -> list[dict]:
    out = []
    for case in corpus["cases"]:
        vault = PlaceholderVault(corpus["observation_id"], corpus["nonce"])
        outcome = Sanitizer(vault).sanitize(case["text"], case["element_id"])

        binding = ElementBinding(corpus["observation_id"], case["element_id"])
        wrong = ElementBinding(corpus["observation_id"], "node-attacker-controlled")
        first = outcome.records[0] if outcome.records else None

        can_resolve_bound = (
            vault.can_resolve(first.placeholder, binding) if first else None
        )
        can_resolve_wrong = (
            vault.can_resolve(first.placeholder, wrong) if first else None
        )
        cross_refused = (
            _refused(lambda: vault.detokenize_for_target(first.placeholder, wrong))
            if first
            else None
        )

        vault.clear()
        after_clear_refused = (
            _refused(lambda: vault.detokenize_for_target(first.placeholder, binding))
            if first
            else None
        )

        out.append(
            {
                "name": case["name"],
                "text": outcome.text,
                "state": outcome.evidence.state,
                "redactions": outcome.evidence.redactions,
                "unresolved": outcome.evidence.unresolved_count,
                "residual": outcome.evidence.residual_count,
                "pixelCovered": outcome.evidence.pixel_covered,
                "discarded": outcome.discarded,
                "records": [
                    [r.entity_type, r.placeholder, r.start, r.end, r.outcome]
                    for r in outcome.records
                ],
                "summary": {
                    "total": outcome.summary.total_redactions,
                    "byEntity": dict(outcome.summary.by_entity),
                    "unresolved": outcome.summary.unresolved_count,
                },
                "b6": {
                    "canResolveBound": can_resolve_bound,
                    "canResolveWrong": can_resolve_wrong,
                    "crossElementRefused": cross_refused,
                    "afterClearRefused": after_clear_refused,
                    "sizeAfterClear": vault.size,
                },
            }
        )
    return out


@pytest.fixture(scope="module")
def typescript_results(corpus: dict) -> list[dict]:
    if not SANITIZER_JS.exists():
        pytest.fail(f"{SANITIZER_JS} is missing. Run: npm run build:parity")
    completed = subprocess.run(
        ["node", str(RUNNER), str(CORPUS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"Node sanitizer runner failed:\n{completed.stderr}")
    return json.loads(completed.stdout)["results"]



# -- parity --------------------------------------------------------------------


def test_runtimes_agree_on_every_sanitizer_case(
    python_results: list[dict], typescript_results: list[dict]
) -> None:
    assert len(python_results) == len(typescript_results)
    for py, ts in zip(python_results, typescript_results):
        assert py == ts, f"divergence in case {py['name']!r}:\n  py={py}\n  ts={ts}"


def test_runtimes_agree_on_every_b6_decision(
    python_results: list[dict], typescript_results: list[dict]
) -> None:
    """The security assertion, stated separately so a failure names itself."""
    for py, ts in zip(python_results, typescript_results):
        assert py["b6"] == ts["b6"], f"B-6 divergence in {py['name']!r}"


# -- what the comparison is actually asserting ---------------------------------


def test_a_repeated_value_shares_one_token(python_results: list[dict]) -> None:
    """FR-VLT-2, and a parity fixture that would be vacuous without it."""
    case = next(
        r for r in python_results if r["name"] == "repeated-value-shares-one-token"
    )
    assert case["summary"]["total"] == 1
    assert case["records"][0][1] == case["records"][1][1]


def test_bound_target_resolves_but_attacker_target_does_not(
    python_results: list[dict],
) -> None:
    for case in python_results:
        if case["b6"]["canResolveBound"] is None:
            continue
        assert case["b6"]["canResolveBound"] is True
        assert case["b6"]["canResolveWrong"] is False
        assert case["b6"]["crossElementRefused"] is True


def test_clearing_the_vault_refuses_everything(python_results: list[dict]) -> None:
    """FR-VLT-4. Task end must revoke resolution, not merely hide it."""
    for case in python_results:
        assert case["b6"]["afterClearRefused"] in (True, None)
        assert case["b6"]["sizeAfterClear"] == 0


def test_text_pass_never_claims_full_sanitized(python_results: list[dict]) -> None:
    """A text pass has not looked at a single pixel, so it must not say so."""
    for case in python_results:
        assert case["state"] in {"SANITIZED_TEXT", "DEGRADED"}
        assert case["pixelCovered"] is False
