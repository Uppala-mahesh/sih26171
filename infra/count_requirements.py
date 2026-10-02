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


# A group row is written as a range: `FR-PII-1...9`. The literal ids in the text
# are only the endpoints, so counting identifiers UNDERSTATES coverage.
#
# This was not hypothetical. The matrix covers all 99 functional requirements
# through thirteen ranged rows, and an identifier-only count reported 19/99 - a
# 19.2% "coverage" figure that was published in the matrix itself as a
# disclosure before the measurement behind it was checked. The number was wrong
# in the direction that flattered nobody and misled everyone.
GROUP_RANGE = re.compile(r"\b(FR-[A-Z]+)-(\d+)\s*(?:\.\.\.|…|–)\s*(\d+)\b")


def expand_group_ranges(text: str) -> set[str]:
    """Expand `FR-PII-1...9` into every id it stands for."""
    expanded: set[str] = set()
    for match in GROUP_RANGE.finditer(text):
        group, low, high = match.group(1), int(match.group(2)), int(match.group(3))
        step = 1 if high >= low else -1
        for n in range(low, high + step, step):
            expanded.add(f"{group}-{n}")
    return expanded


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




def _is_disclosure_cell(cell: str) -> bool:
    """Does this cell DECLARE that something is absent, rather than naming it?

    Mirrors verify_traceability._is_disclosure_cell. Duplicated rather than
    imported because the two tools must be independently runnable, and a shared
    helper would let one bug silence both checks at once.
    """
    normalised = cell.strip().strip("`* ").lower()
    if normalised in {"-", "--", "none", "n/a", "tbd"}:
        return True
    return any(
        phrase in cell.lower()
        for phrase in ("not yet written", "not implemented", "not started")
    )

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

    # ── coverage, measured two ways ─────────────────────────────────────────
    # (1) PRESENCE: does the matrix name the requirement at all, either literally
    #     or as part of a ranged group row?
    asserted = prose(rtm_text)
    named = unique(asserted, FR_RE) & functional
    ranged = expand_group_ranges(asserted) & functional
    covered_by_matrix = named | ranged

    # (2) IMPLEMENTATION: does the requirement's group row name a module that
    #     exists? A requirement can be listed and still be unbuilt, and those are
    #     different facts that the matrix used to blur.
    unimplemented_groups = set()
    for line in asserted.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not _is_disclosure_cell(cells[2]):
            continue
        for match in GROUP_RANGE.finditer(cells[0]):
            group, low, high = match.group(1), int(match.group(2)), int(match.group(3))
            step = 1 if high >= low else -1
            for n in range(low, high + step, max(step, 1)):
                identifier = f"{group}-{n}"
                if identifier in functional:
                    unimplemented_groups.add(identifier)

    implemented = covered_by_matrix - unimplemented_groups
    phantom = sorted(unique(asserted, FR_RE) - functional)

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
            "present_in_matrix": len(covered_by_matrix),
            "named_literally": len(named),
            "named_via_group_range": len(ranged - named),
            "unlisted_in_matrix": len(functional - covered_by_matrix),
            "unlisted_ids": sorted(functional - covered_by_matrix),
            "implemented": len(implemented),
            "unimplemented": len(unimplemented_groups),
            "unimplemented_ids": sorted(unimplemented_groups),
            "implementation_coverage": (
                round(len(implemented) / len(functional), 4) if functional else 0.0
            ),
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
