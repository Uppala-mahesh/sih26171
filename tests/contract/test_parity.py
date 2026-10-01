"""Cross-runtime parity — REQ-DATA-001 rules X-1..X-5.

This module is the enforcement of v1 defect G-1, the worst security defect in
the audit: two PII engines whose vocabularies silently drifted apart, where the
JavaScript side detected Aadhaar, PAN, UPI, IFSC and OTP and the Python side
detected none of them.

Two registries agreeing on paper proves nothing, so this test compares what both
runtimes ACTUALLY DETECT across a shared corpus (testdata/parity_corpus.json)
and fails the build on any divergence (rule X-4).

Findings are reduced to (entity, start, end, outcome) tuples so the comparison
is about detection behaviour rather than incidental representation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "testdata" / "parity_corpus.json"
RUNNER = ROOT / "tests" / "parity" / "run-detector.cjs"
DETECTOR_JS = ROOT / "dist" / "packages" / "privacy" / "detector.js"

sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.privacy.detectors import detect  # noqa: E402
from app.privacy.taxonomy import TAXONOMY  # noqa: E402

_CORPUS_NOTE = (
    "Findings are reduced to (entity, start, end, outcome) tuples so the comparison is "
    "about detection behaviour rather than incidental representation."
)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def python_results(corpus: dict) -> list[dict]:
    out = []
    for case in corpus["cases"]:
        result = detect(case["text"])
        out.append(
            {
                "name": case["name"],
                "discarded": result.discarded,
                "findings": [
                    (
                        f.entity_id,
                        f.start,
                        f.end,
                        f.outcome.value,
                    )
                    for f in result.findings
                ],
            }
        )
    return out


@pytest.fixture(scope="module")
def typescript_results(corpus: dict) -> dict:
    if not DETECTOR_JS.exists():
        pytest.fail(
            f"{DETECTOR_JS} is missing. Run: npm run build:parity"
        )
    completed = subprocess.run(
        ["node", str(RUNNER), str(CORPUS)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        pytest.fail(f"node runner failed: {completed.stderr[:2000]}")
    payload = json.loads(completed.stdout)
    return {
        "supportedEntities": payload["supportedEntities"],
        "results": [
            {
                "name": case["name"],
                "discarded": case["discarded"],
                "findings": [tuple(f) for f in case["findings"]],
            }
            for case in payload["results"]
        ],
    }


# ── X-2: the two runtimes expose an identical entity set ─────────────────────


def test_supported_entity_sets_are_identical(typescript_results: dict) -> None:
    """X-2. A divergence here is exactly the v1 G-1 defect in embryo."""
    python_ids = {s.id for s in TAXONOMY.pattern_backed()}
    typescript_ids = set(typescript_results["supportedEntities"])
    assert python_ids == typescript_ids, (
        f"only in Python: {sorted(python_ids - typescript_ids)}; "
        f"only in TypeScript: {sorted(typescript_ids - python_ids)}"
    )


def test_entity_counts_match(typescript_results: dict) -> None:
    assert len(TAXONOMY.entities) == 20
    assert len(typescript_results["supportedEntities"]) == 16


# ── X-3: the two runtimes DETECT the same things ─────────────────────────────


def test_detections_are_identical_on_every_case(
    python_results: list[dict], typescript_results: dict
) -> None:
    """X-3. Any single differing tuple fails the build."""
    ts_results = typescript_results["results"]
    assert len(python_results) == len(ts_results)

    divergences: list[str] = []
    for py, ts in zip(python_results, ts_results, strict=True):
        assert py["name"] == ts["name"], "corpus case order diverged"
        if py["findings"] != ts["findings"]:
            divergences.append(
                f"  case {py['name']!r}\n"
                f"    Python:     {py['findings']}\n"
                f"    TypeScript: {ts['findings']}"
            )
        if py["discarded"] != ts["discarded"]:
            divergences.append(
                f"  case {py['name']!r} discarded count: "
                f"Python {py['discarded']} vs TypeScript {ts['discarded']}"
            )

    assert not divergences, (
        "cross-runtime divergence (REQ-DATA-001 rule X-4):\n"
        + "\n".join(divergences)
    )


def test_the_corpus_actually_exercises_both_runtimes(
    python_results: list[dict]
) -> None:
    """A corpus where both runtimes find nothing would pass vacuously."""
    total = sum(len(r["findings"]) for r in python_results)
    assert total > 20, f"corpus produced only {total} findings - too weak to be meaningful"
    assert any(r["discarded"] for r in python_results), "no checksum discards exercised"
    assert any(
        f[3] == "UNCERTAIN" for r in python_results for f in r["findings"]
    ), "no UNCERTAIN outcomes exercised"


# ── X-1: the generated registry is not stale ─────────────────────────────────


def test_generated_typescript_registry_is_current() -> None:
    """X-1. Editing entities.yaml without regenerating must fail here."""
    completed = subprocess.run(
        [sys.executable, str(ROOT / "infra" / "generate_taxonomy.py"), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, (
        "generated registry is stale; run: python infra/generate_taxonomy.py\n"
        f"{completed.stderr}"
    )
