"""SIH26171 — PII quality benchmark.

Produces the measured figures for the 20% "PII precision and recall" rubric
weight, replacing a target with a number.

Governed by
    REQ-SRS-001   FR-PII-7 (report BOTH precision and recall, per class)
    PROJECT-CHARTER §5 (Recall >= 0.98, Precision >= 0.95)
    REQ-DATA-001  §7.1 (published figures must be regenerable)

Matching policy
---------------
A prediction is a TRUE POSITIVE only when its span AND its entity both match
ground truth exactly. Exact matching is deliberate: a tolerance would quietly
inflate recall whenever a detector returns a slightly wider box, which is the
v1 failure mode (shape-only matching).

Two readings are reported, because they answer different questions
-----------------------------------------------------------------
    STRICT     only ACCEPTED findings count. Measures CONFIRMED detection.
    PROTECTIVE  ACCEPTED + UNCERTAIN count, because UNCERTAIN findings ARE
               redacted (fail-closed, FR-PII-9). Measures whether a secret
               would actually have been hidden.

High PROTECTIVE with low STRICT is not a contradiction: it means the system
redacts aggressively and declares it. Reporting only one would be cherry-picking.

Usage
-----
    python benchmarks/pii_quality.py            # human-readable table
    python benchmarks/pii_quality.py --json     # machine-readable scorecard
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.privacy.detectors import Outcome, PatternDetector  # noqa: E402
from app.privacy.taxonomy import TAXONOMY  # noqa: E402

CORPUS = ROOT / "testdata" / "pii_corpus.json"

TARGET_RECALL = 0.98
TARGET_PRECISION = 0.95


@dataclass(frozen=True, slots=True)
class Truth:
    entity: str
    start: int
    end: int


@dataclass
class Tally:
    """Counts, not rates — rates are derived so rounding can never accumulate."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float | None:
        denominator = self.true_positives + self.false_positives
        return None if denominator == 0 else self.true_positives / denominator

    @property
    def recall(self) -> float | None:
        denominator = self.true_positives + self.false_negatives
        return None if denominator == 0 else self.true_positives / denominator

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or (precision + recall) == 0:
            return None
        return 2 * precision * recall / (precision + recall)


@dataclass
class Report:
    strict: Tally = field(default_factory=Tally)
    protective: Tally = field(default_factory=Tally)
    per_entity: dict[str, Tally] = field(default_factory=dict)
    confusion: dict[str, int] = field(default_factory=dict)
    missed: list[dict] = field(default_factory=list)
    spurious: list[dict] = field(default_factory=list)
    corpus_version: str = ""
    coverage: dict = field(default_factory=dict)


def _bump(tallies: dict[str, Tally], key: str) -> Tally:
    if key not in tallies:
        tallies[key] = Tally()
    return tallies[key]


def evaluate(corpus: dict, detector: PatternDetector | None = None) -> Report:
    """Score the detector against the labelled corpus."""
    detector = detector or PatternDetector()
    report = Report(
        corpus_version=corpus.get("version", "?"),
        coverage=dict(corpus.get("coverage", {})),
    )

    for case in corpus["cases"]:
        text = case["text"]
        truths = [Truth(s["entity"], s["start"], s["end"]) for s in case["expected"]]
        result = detector.detect(text)

        for reading in ("strict", "protective"):
            predictions = (
                [f for f in result.findings if f.outcome is Outcome.ACCEPTED]
                if reading == "strict"
                else list(result.findings)
            )
            tally = report.strict if reading == "strict" else report.protective
            matched: set[int] = set()

            for finding in predictions:
                exact = None
                for index, truth in enumerate(truths):
                    if (
                        index not in matched
                        and truth.entity == finding.entity_id
                        and truth.start == finding.start
                        and truth.end == finding.end
                    ):
                        exact = index
                        break

                if exact is None:
                    tally.false_positives += 1
                    _bump(report.per_entity, finding.entity_id).false_positives += 1
                    overlap = next(
                        (
                            t.entity
                            for t in truths
                            if t.start < finding.end and finding.start < t.end
                        ),
                        "NONE",
                    )
                    label = (
                        f"{overlap}->{finding.entity_id}"
                        if overlap != "NONE"
                        else f"NONE->{finding.entity_id}"
                    )
                    # Confusion is reported for the STRICT reading only. Accumulating
                    # it in both loops double-counted every false positive and
                    # produced a matrix with 9 entries against 1 strict FP.
                    if reading == "strict":
                        report.confusion[label] = report.confusion.get(label, 0) + 1
                        report.spurious.append(
                            {
                                "case": case["id"],
                                "entity": finding.entity_id,
                                "text": text[finding.start : finding.end],
                            }
                        )
                else:
                    matched.add(exact)
                    tally.true_positives += 1
                    _bump(report.per_entity, finding.entity_id).true_positives += 1

            for index, truth in enumerate(truths):
                if index not in matched:
                    tally.false_negatives += 1
                    _bump(report.per_entity, truth.entity).false_negatives += 1
                    if reading == "strict":
                        report.missed.append(
                            {
                                "case": case["id"],
                                "entity": truth.entity,
                                "text": text[truth.start : truth.end],
                            }
                        )

    return report


def _pct(value: float | None) -> str:
    return "  n/a " if value is None else f"{value * 100:6.2f}%"


def render(report: Report) -> str:
    lines: list[str] = []
    coverage = report.coverage
    measured = coverage.get("entities_measured", 0)
    unmeasured = coverage.get("entities_not_measured", 0)

    lines.append("=" * 78)
    lines.append("SIH26171 - PII QUALITY BENCHMARK")
    lines.append("=" * 78)
    lines.append(f"Corpus version : {report.corpus_version}")
    lines.append(
        f"Cases / spans  : {coverage.get('cases', '?')} / "
        f"{coverage.get('positive_spans', '?')}"
    )
    lines.append(f"Entities       : {measured} of {measured + unmeasured} MEASURED")
    lines.append(
        f"                 {unmeasured} NOT measured (PASSWORD, PERSON_NAME, "
        f"ADDRESS, FACE_IMAGE - structural or model-backed)"
    )
    lines.append("")

    for label, tally in (
        ("STRICT - confirmed detections only", report.strict),
        ("PROTECTIVE - accepted + uncertain (what actually gets redacted)", report.protective),
    ):
        lines.append(f"--- {label} ---")
        lines.append(
            f"  TP {tally.true_positives:3}    FP {tally.false_positives:3}    "
            f"FN {tally.false_negatives:3}"
        )
        lines.append(f"  precision  {_pct(tally.precision)}   target >= {TARGET_PRECISION * 100:.0f}%")
        lines.append(f"  recall     {_pct(tally.recall)}   target >= {TARGET_RECALL * 100:.0f}%")
        lines.append(f"  F1         {_pct(tally.f1)}")
        lines.append("")

    lines.append("--- PER ENTITY (strict) ---")
    lines.append(f"  {'entity':<18}{'TP':>4}{'FP':>4}{'FN':>4}{'precision':>12}{'recall':>10}")
    for entity in sorted(report.per_entity):
        tally = report.per_entity[entity]
        lines.append(
            f"  {entity:<18}{tally.true_positives:>4}{tally.false_positives:>4}"
            f"{tally.false_negatives:>4}{_pct(tally.precision):>12}{_pct(tally.recall):>10}"
        )
    lines.append("")

    lines.append("--- CONFUSION (strict false positives) ---")
    if report.confusion:
        for label, count in sorted(report.confusion.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {label:<42} {count}")
    else:
        lines.append("  none")
    lines.append("")

    for heading, entries in (("MISSED", report.missed), ("SPURIOUS", report.spurious)):
        lines.append(f"--- {heading} (strict) ---")
        if entries:
            for entry in entries:
                lines.append(
                    f"  {entry['case']:<20} {entry['entity']:<16} {entry['text']!r}"
                )
        else:
            lines.append("  none")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIH26171 PII quality benchmark")
    parser.add_argument("--json", action="store_true", help="emit a machine-readable scorecard")
    args = parser.parse_args(argv)

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    report = evaluate(corpus)

    if args.json:
        print(json.dumps({
            "benchmark": "pii_quality",
            "corpus_version": report.corpus_version,
            "coverage": report.coverage,
            "targets": {"recall": TARGET_RECALL, "precision": TARGET_PRECISION},
            "strict": {
                "true_positives": report.strict.true_positives,
                "false_positives": report.strict.false_positives,
                "false_negatives": report.strict.false_negatives,
                "precision": report.strict.precision,
                "recall": report.strict.recall,
                "f1": report.strict.f1,
            },
            "protective": {
                "true_positives": report.protective.true_positives,
                "false_positives": report.protective.false_positives,
                "false_negatives": report.protective.false_negatives,
                "precision": report.protective.precision,
                "recall": report.protective.recall,
            },
            "confusion": report.confusion,
            "missed": report.missed,
            "spurious": report.spurious,
        }, indent=2))
    else:
        print(render(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

