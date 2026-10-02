"""Capability ladder tests — FR-CAP-1..FR-CAP-7 and verification V-5.

The resolver is exercised through tests/vision/run-ladder.cjs with INJECTED
probes, so every branch including total unavailability is reachable from CI.
That is the entire reason probes are injected rather than probed internally:
`navigator.gpu` needs a browser, so a self-probing ladder could only ever be
tested in a browser - and would therefore go untested.

The invariants asserted here are the ones that matter:

  FR-CAP-1  rungs are tried in order and the first available one is selected
  FR-CAP-2  a rung with no probe is UNAVAILABLE, never assumed available
  FR-CAP-3  any fallback from preferred is DEGRADED and declared
  FR-CAP-4  a degraded ladder NEVER yields a non-declared state
  FR-CAP-6  no rung requires a discrete GPU
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests" / "vision" / "run-ladder.cjs"
LADDER_JS = ROOT / "dist" / "packages" / "vision" / "capability" / "ladder.js"


@pytest.fixture(scope="module")
def payload() -> dict:
    if not LADDER_JS.exists():
        pytest.fail(f"{LADDER_JS} is missing. Run: npm run build:parity")
    completed = subprocess.run(
        ["node", str(RUNNER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"ladder exerciser failed: {completed.stderr[:2000]}")
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def scenarios(payload: dict) -> dict[str, dict]:
    return {case["name"]: case for case in payload["scenarios"]}


# -- FR-CAP-1: order and selection ------------------------------------------


def test_ladder_order_is_gpu_then_simd_then_wasm_then_dom(payload: dict) -> None:
    assert payload["ladder"] == ["webgpu", "wasm-simd", "wasm", "dom-only"]


def test_full_capability_selects_the_top_rung(scenarios: dict) -> None:
    case = scenarios["full capability"]
    assert case["active"] == "webgpu"
    assert case["degraded"] is False
    assert case["declarationState"] == "FULL_CAPABILITY"


def test_falls_back_in_order_when_gpu_is_absent(scenarios: dict) -> None:
    assert scenarios["no webgpu"]["active"] == "wasm-simd"
    assert scenarios["no gpu and no simd"]["active"] == "wasm"
    assert scenarios["dom only"]["active"] == "dom-only"


def test_probing_stops_at_the_first_available_rung(scenarios: dict) -> None:
    """Full capability must not probe rungs it does not need (FR-CAP-7)."""
    assert scenarios["full capability"]["probedRungs"] == ["webgpu"]


# -- FR-CAP-2: absence is never assumed away ---------------------------------


def test_no_registered_probe_means_unavailable(scenarios: dict) -> None:
    """A rung with no probe must never be reported as available."""
    case = scenarios["no probes registered at all"]
    assert case["active"] == "dom-only"
    assert case["degraded"] is True
    assert "no probe registered" in case["detail"]


def test_a_throwing_probe_is_treated_as_unavailable(scenarios: dict) -> None:
    """requestAdapter() rejects on hosts without WebGPU; that must not crash."""
    case = scenarios["probes that throw"]
    assert case["active"] == "wasm"
    assert "probe threw" in case["detail"]


def test_total_probe_failure_still_yields_a_usable_rung(scenarios: dict) -> None:
    """Every rung failing is the worst realistic case, and must degrade cleanly."""
    case = scenarios["every probe throws"]
    assert case["active"] == "dom-only"
    assert case["degraded"] is True
    assert case["declarationState"] == "DEGRADED"


# -- FR-CAP-3 / FR-CAP-4: degradation is always declared ---------------------


def test_every_fallback_is_declared_degraded(scenarios: dict) -> None:
    for name, case in scenarios.items():
        if case["degraded"]:
            assert case["declarationState"] == "DEGRADED", name
            assert case["reason"] == "vision_rung_unavailable", name


def test_no_scenario_yields_an_undeclared_state(scenarios: dict) -> None:
    """FR-CAP-4: the ladder can never quietly imply full capability."""
    for name, case in scenarios.items():
        assert case["declarationState"] in {"FULL_CAPABILITY", "DEGRADED"}, name
        if not case["degraded"]:
            assert case["declarationState"] == "FULL_CAPABILITY", name
        else:
            assert case["declarationState"] == "DEGRADED", name


def test_missing_the_preferred_rung_counts_as_degraded(scenarios: dict) -> None:
    """webgpu works, but the caller asked for wasm-simd: still degraded."""
    case = scenarios["preferred is not the best available"]
    assert case["active"] == "webgpu"
    assert case["preferred"] == "wasm-simd"
    assert case["degraded"] is True
    assert case["declarationState"] == "DEGRADED"


# -- FR-CAP-6: no GPU is ever required ---------------------------------------


def test_dom_only_is_always_reachable(payload: dict, scenarios: dict) -> None:
    """A CPU-only host must still perceive the page."""
    assert "dom-only" in payload["ladder"]
    assert scenarios["every probe throws"]["active"] == "dom-only"


def test_a_rung_available_at_the_top_is_not_degraded(scenarios: dict) -> None:
    """Guards against over-degradation, which would waste the 25% visual weight."""
    assert scenarios["only webgpu available"]["degraded"] is False
    assert scenarios["only webgpu available"]["declarationState"] == "FULL_CAPABILITY"
