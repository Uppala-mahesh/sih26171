"""SIH26171 — Traceability matrix verifier.

Checks every path REQ-RTM-001 claims against the filesystem.

── Why this exists ───────────────────────────────────────────────────────────
`REQ-RTM-001` section 2 listed its "Implementing module" column in the present
tense, and most of those paths do not exist:

    services/vision/sources/dom              - does not exist
    apps/backend/app/privacy/visual_redactor  - the real one is privacy/pixels.py
    apps/backend/app/agent/pipeline           - the real one is packages/pipeline/
    apps/backend/app/policy/*                 - does not exist
    benchmarks/latency                        - the real one is resource_latency.py
    apps/backend/app/agent/verifier           - does not exist
    packages/telemetry                        - does not exist

A traceability matrix that points at modules which were never built is worse than
one that admits it is incomplete, because it converts an unfinished project into
a finished-looking one. That is the v1 pattern this whole repository exists to
eliminate, sitting in the document whose job is to establish what is real.

This module makes the claim checkable. It parses section 2, resolves each
claimed path, and reports which are real. `tests/contract/test_traceability_paths.py`
then FAILS on any claimed module that is absent, so a fabricated path cannot be
committed again.

Usage:
    python infra/verify_traceability.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RTM = ROOT / "docs" / "01-requirements" / "REQ-RTM-001-requirements-traceability-matrix.md"

# Paths are written as `a/b` or `a/*` inside backticks. Directories are matched
# by prefix so a glob like `privacy/*` resolves to the directory.
PATH_IN_BACKTICKS = re.compile(r"`([A-Za-z0-9_./*-]+)`")

# Words that mark a cell as a deliberate non-implementation rather than a claim.
NON_IMPLEMENTED_MARKERS = ("not started", "not implemented", "none", "n/a", "-")


def claimed_paths() -> list[str]:
    """Every path REQ-RTM-001 section 2 claims to implement.

    The scan stops at 2.1 as well as at section 3. The rubric-coverage table in
    2.1 names benchmark paths for weights, not modules, so including it made the
    verifier report `benchmarks/pii_quality` (a stale name in a different
    column) as a missing implementation.
    """
    text = RTM.read_text(encoding="utf-8")
    start = text.find("## 2. Functional requirement mapping")
    if start == -1:
        raise SystemExit("could not locate REQ-RTM-001 section 2")
    candidates = [
        text.find("### 2.1 Rubric coverage check"),
        text.find("## 3. Non-functional requirement mapping"),
    ]
    candidates = [c for c in candidates if c != -1]
    if not candidates:
        raise SystemExit("could not locate the end of REQ-RTM-001 section 2")
    section = text[start : min(candidates)]

    found: list[str] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # Columns: group | design | implementing module | verification | rubric
        if len(cells) < 4:
            continue
        module_cell = cells[2]
        if any(marker in module_cell.lower() for marker in NON_IMPLEMENTED_MARKERS):
            continue
        for candidate in PATH_IN_BACKTICKS.findall(module_cell):
            if "/" not in candidate and not candidate.endswith("*"):
                continue
            if candidate not in found:
                found.append(candidate)
    return found


def resolves(candidate: str) -> bool:
    """Does the claimed path exist, allowing a trailing glob."""
    cleaned = candidate.rstrip("/*")
    target = ROOT / cleaned
    if target.exists():
        return True
    # A glob such as `privacy/*` names a directory that must exist even if the
    # specific file does not.
    if candidate.endswith("*"):
        return (ROOT / cleaned).is_dir()
    return False


def verify() -> dict:
    claims = claimed_paths()
    resolved = [c for c in claims if resolves(c)]
    missing = [c for c in claims if not resolves(c)]
    return {
        "claimed": len(claims),
        "resolved": len(resolved),
        "missing": len(missing),
        "coverage": round(len(resolved) / len(claims), 4) if claims else 0.0,
        "resolved_paths": sorted(resolved),
        "missing_paths": sorted(missing),
    }


def main() -> int:
    report = verify()
    print(json.dumps(report, indent=2))
    return 0 if not report["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
