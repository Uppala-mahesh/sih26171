"""SIH26171 — Authoritative requirement counting.

Counts requirement identifiers by reading the DOCUMENTS, never by trusting a
number typed into a summary.

── Why this exists ───────────────────────────────────────────────────────────
Three separate artifacts claimed "102 functional requirements" and "155 total".
The documents contain 99 and 152. The counts had drifted, and nothing detected
it because every one of them was a hand-maintained figure.

That is precisely the failure mode this project exists to eliminate. A
traceability matrix whose own totals do not reconcile with its sources is not
traceability; it is decoration with tables.

This module is the single source for those numbers, and
tests/contract/test_requirement_counts.py FAILS if any artifact disagrees with
it. Adding a requirement now means the count moves and the gate notices.

Usage:
    python infra/count_requirements.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQS = ROOT / "docs" / "01-requirements"

SRS = REQS / "REQ-SRS-001-software-requirements-specification.md"
NFR = REQS / "REQ-NFR-001-non-functional-requirements.md"
RTM = REQS / "REQ-RTM-001-requirements-traceability-matrix.md"
UC = REQS / "REQ-UC-001-use-case-model.md"

# `\b` before FR is load-bearing. Without it, `FR-[A-Z]+-\d+` matches INSIDE
# `NFR-PERF-1`, and the counter then reports eight perfectly legitimate
# non-functional rows as "phantom functional requirements". That mistake was
# made, written into REQ-RTM-001 as a disclosure of "fabricated traceability",
# and was wrong. The phantom check has to distinguish FR- from NFR-.
FR_RE = re.compile(r"\bFR-[A-Z]+-\d+")
NFR_RE = re.compile(r"\bNFR-[A-Z]+-\d+")
EI_RE = re.compile(r"\bEI-\d+")

# The thirteen functional groups declared by REQ-SRS-001 section 3.
FUNCTIONAL_GROUPS = (
    "FR-AGT",
    "FR-CAP",
    "FR-EGR",
    "FR-EXE",
    "FR-PER",
    "FR-PII",
    "FR-POL",
    "FR-RED",
    "FR-TEL",
    "FR-UI",
    "FR-VER",
    "FR-VIS",
    "FR-VLT",
)


def unique(text: str, pattern: re.Pattern[str]) -> set[str]:
    return set(pattern.findall(text))


def prose(text: str) -> str:
    """The document's ASSERTIONS, with blockquoted material removed.

    A disclosure must be able to name the wrong figure in order to correct it
    ("three artifacts claimed 102 while the SRS contains 99"). A gate that
    forbade the string `102` everywhere would therefore ban the disclosure that
    documents the fix.

    Blockquote lines (`>`) carry narrative: correction notes, quoted v1 defects,
    historical references. The assertion is what is left.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def group_of(identifier: str) -> str:
    parts = identifier.rsplit("-", 1)
    return parts[0] if len(parts) == 2 else identifier


def count() -> dict:
    srs_text = SRS.read_text(encoding="utf-8")
    nfr_text = NFR.read_text(encoding="utf-8")
    rtm_text = RTM.read_text(encoding="utf-8")
    uc_text = UC.read_text(encoding="utf-8")

    functional = unique(srs_text, FR_RE)
    non_functional = unique(nfr_text, NFR_RE)
    interfaces = unique(srs_text, EI_RE)

    by_group = Counter(group_of(f) for f in functional)
    unexpected = sorted(g for g in by_group if g not in FUNCTIONAL_GROUPS)

    # Traceability: which functional requirements the RTM actually names.
    # Only assertive rows count. A disclosure that lists the phantom ids in
    # order to say they were removed is not itself a phantom reference.
    traced = unique(prose(rtm_text), FR_RE) & functional
    untraced = sorted(functional - traced)
    phantom = sorted(unique(prose(rtm_text), FR_RE) - functional)

    return {
        "source": "counted from the documents themselves",
        "functional": len(functional),
        "non_functional": len(non_functional),
        "external_interfaces": len(interfaces),
        "total_including_interfaces": len(functional) + len(non_functional) + len(interfaces),
        "total_excluding_interfaces": len(functional) + len(non_functional),
        "groups": {g: by_group[g] for g in FUNCTIONAL_GROUPS if g in by_group},
        "unexpected_groups": unexpected,
        "traceability": {
            "functional_in_rtm": len(traced),
            "functional_untraced": len(untraced),
            "coverage": round(len(traced) / len(functional), 4) if functional else 0.0,
            "untraced_ids": untraced,
            "phantom_ids_in_rtm": phantom,
        },
        "use_cases": len(unique(uc_text, re.compile(r"UC-\d+"))),
    }


def main() -> int:
    result = count()
    print(json.dumps(result, indent=2))
    # Non-zero when the set is internally inconsistent, so it can gate CI.
    inconsistent = bool(result["unexpected_groups"])
    return 1 if inconsistent else 0


if __name__ == "__main__":
    sys.exit(main())
