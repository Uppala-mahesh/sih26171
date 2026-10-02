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

DESIGN_ARTIFACT = re.compile(r"DES-[A-Z]+-\d+")

#: Design artifacts the RTM names in a disclosure cell ("NOT YET WRITTEN").
#:
#: Populated by :func:`claimed_design_artifacts`. A disclosure must not become a
#: demand for a file, but it must not become invisible either: an artifact nobody
#: is writing is a gap in the SDLC, and reporting `missing: 0` while two are owed
#: is a clean bill of health for a known hole.
_DISCLOSED_DESIGN_ARTIFACTS: set[str] = set()

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
        if _is_disclosure_cell(module_cell):
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


def _is_disclosure_cell(cell: str) -> bool:
    """Does this cell DECLARE that something is absent, rather than naming it?

    Matches only whole-value markers. A substring test for "-" is a substring
    test against every hyphenated identifier in the table.
    """
    normalised = cell.strip().strip("`* ").lower()
    if normalised in {"-", "--", "none", "n/a", "tbd"}:
        return True
    return any(
        phrase in cell.lower()
        for phrase in ("not yet written", "not implemented", "not started")
    )


def claimed_design_artifacts() -> list[str]:
    """Every DES-* artifact REQ-RTM-001 section 2 cites, whether or not it exists.

    Checked separately from module paths because the two columns fail
    differently. A missing module is a gap in the build; a missing DESIGN
    artifact is a gap in the SDLC, and it is the one that lets a project look
    engineered while having no design at all.
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
    disclosed: list[str] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # Columns: group | design | implementing module | verification | rubric
        design_cell = cells[1] if len(cells) > 1 else ""
        # A cell that says the artifact is not written is a DISCLOSURE, not a
        # citation. Naming `DES-CLASS-001 NOT YET WRITTEN` must not make the
        # verifier demand the file - that is the same trap as naming a missing
        # module in prose, and it is why the marker is checked explicitly.
        #
        # But excluding it must not make the debt INVISIBLE. The previous version
        # skipped the row entirely, so `missing: 0` was reported while two design
        # artifacts were owed - a clean bill of health for a known gap. Disclosed
        # artifacts are now collected separately and reported as their own line.
        if _is_disclosure_cell(design_cell):
            for match in DESIGN_ARTIFACT.finditer(line):
                if match.group(0) not in disclosed:
                    disclosed.append(match.group(0))
            continue
        for match in DESIGN_ARTIFACT.finditer(line):
            if match.group(0) not in found:
                found.append(match.group(0))
    _DISCLOSED_DESIGN_ARTIFACTS.clear()
    _DISCLOSED_DESIGN_ARTIFACTS.update(disclosed)
    return found


def verify_design() -> dict:
    cited = claimed_design_artifacts()
    present = []
    missing = []
    for artifact in cited:
        matches = list((ROOT / "docs").rglob(f"{artifact}*.md"))
        (present if matches else missing).append(artifact)

    # Disclosed-but-unwritten artifacts are reported SEPARATELY from `missing`.
    #
    # They are not `missing`, because the matrix never claimed them - demanding the
    # file would punish the RTM for being honest. But folding them into `cited`
    # would also be wrong: that field means "artifacts this design rests on", and an
    # artifact nobody has written cannot bear weight. So they get their own line and
    # are never silently zero.
    owed = sorted(
        a
        for a in _DISCLOSED_DESIGN_ARTIFACTS
        if not list((ROOT / "docs").rglob(f"{a}*.md"))
    )
    return {
        "cited": len(cited),
        "present": len(present),
        "missing": len(missing),
        "missing_artifacts": sorted(missing),
        "present_artifacts": sorted(present),
        "acknowledged_unwritten": len(owed),
        "acknowledged_unwritten_artifacts": owed,
    }


def main() -> int:
    report = verify()
    design = verify_design()
    report["design"] = design
    print(json.dumps(report, indent=2))
    return 0 if not report["missing"] and not design["missing"] else 1


if __name__ == "__main__":
    sys.exit(main())
