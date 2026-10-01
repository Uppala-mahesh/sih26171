"""SIH26171 — Taxonomy code generator.

Emits the TypeScript entity registry from ``packages/taxonomy/entities.yaml``.

This script IS the enforcement of AD-6 and REQ-DATA-001 rule X-1. The
TypeScript side is never hand-written: it is generated from the same YAML the
Python side loads at runtime. Two runtimes, one source, no possibility of a
hand-edited duplicate drifting — which is precisely how v1's two PII engines
diverged (defect G-1).

Rule X-4 is enforced separately by tests/contract/test_parity.py, which
compares what both runtimes actually DETECT rather than what they declare.

Usage
-----
    python infra/generate_taxonomy.py            # write the file
    python infra/generate_taxonomy.py --check    # fail if stale, write nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages" / "taxonomy" / "entities.yaml"
TARGET = ROOT / "packages" / "taxonomy" / "generated" / "entities.ts"

HEADER = """/**
 * SIH26171 — Entity registry (GENERATED — DO NOT EDIT).
 *
 * Generated from packages/taxonomy/entities.yaml by
 * infra/generate_taxonomy.py. Edit the YAML and re-run; hand edits here are
 * overwritten, and `generate_taxonomy.py --check` fails the build when this
 * file is stale.
 *
 * Regeneration is the enforcement of AD-6 and REQ-DATA-001 rule X-1: both
 * runtimes consume one source, so they cannot drift.
 *
 * Parity is proven BEHAVIOURALLY by tests/contract/test_parity.py, which
 * compares detected findings rather than declared constants — two registries
 * can agree on paper and disagree in practice.
 *
 * @generated
 */
"""


def _ts_string(value: str | None) -> str:
    """Emit a TypeScript string literal. Backslashes must survive intact."""
    if value is None:
        return "null"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _ts_array(values: list[str] | None) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_ts_string(v) for v in values) + "]"


def render(document: dict) -> str:
    """Render the whole TypeScript module from the parsed YAML document."""
    lines: list[str] = [HEADER]

    classes = document.get("sensitivity_classes", [])
    lines.append(f"export const SENSITIVITY_CLASSES = {_ts_array(classes)} as const;")
    lines.append("export type SensitivityClass = (typeof SENSITIVITY_CLASSES)[number];")
    lines.append("")

    tiers = document.get("verification_tiers", {}) or {}
    lines.append("export const VERIFICATION_TIERS = {")
    for key, description in tiers.items():
        lines.append(f"  {_ts_string(key)}: {_ts_string(str(description))},")
    lines.append("} as const;")
    lines.append("export type VerificationTier = keyof typeof VERIFICATION_TIERS;")
    lines.append("")

    lines.append("export interface EntitySpec {")
    lines.append("  readonly id: string;")
    lines.append("  readonly display: string;")
    lines.append("  readonly sensitivity: SensitivityClass;")
    lines.append("  readonly tier: VerificationTier;")
    lines.append("  readonly validator: string | null;")
    lines.append("  readonly requiresContext: boolean;")
    lines.append("  readonly contextCues: readonly string[];")
    lines.append("  readonly placeholder: string;")
    lines.append("  /** Source expression, or null for model-backed entities. */")
    lines.append("  readonly pattern: string | null;")
    lines.append("}")
    lines.append("")

    lines.append("export const ENTITIES: readonly EntitySpec[] = [")
    for entry in document["entities"]:
        lines.append("  {")
        lines.append(f"    id: {_ts_string(entry['id'])},")
        lines.append(f"    display: {_ts_string(entry['display'])},")
        lines.append(f"    sensitivity: {_ts_string(entry['class'])},")
        lines.append(f"    tier: {_ts_string(entry['tier'])},")
        lines.append(f"    validator: {_ts_string(entry.get('validator'))},")
        lines.append(
            f"    requiresContext: "
            f"{'true' if entry.get('requires_context') else 'false'},"
        )
        lines.append(f"    contextCues: {_ts_array(entry.get('context_cues') or [])},")
        lines.append(f"    placeholder: {_ts_string(entry['placeholder'])},")
        lines.append(f"    pattern: {_ts_string(entry.get('pattern'))},")
        lines.append("  },")
    lines.append("];")
    lines.append("")

    ids = [entry["id"] for entry in document["entities"]]
    lines.append(f"export const ENTITY_IDS = {_ts_array(ids)} as const;")
    lines.append("export type EntityId = (typeof ENTITY_IDS)[number];")
    lines.append("")
    lines.append(f"export const TAXONOMY_VERSION = {_ts_string(document.get('version'))};")
    lines.append("")
    lines.append("/** Entities carrying an expression. The rest are model-backed (T4). */")
    lines.append(
        "export const PATTERN_BACKED: readonly EntitySpec[] = ENTITIES.filter("
    )
    lines.append("  (entity) => entity.pattern !== null,")
    lines.append(");")
    lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the TypeScript entity registry.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the generated file is stale; write nothing",
    )
    args = parser.parse_args(argv)

    with SOURCE.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    rendered = render(document)

    if args.check:
        if not TARGET.exists():
            print(f"STALE: {TARGET} does not exist", file=sys.stderr)
            return 1
        if TARGET.read_text(encoding="utf-8") != rendered:
            print(
                f"STALE: {TARGET} differs from entities.yaml. "
                f"Run: python infra/generate_taxonomy.py",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {TARGET.name} up to date ({len(document['entities'])} entities)")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET} ({len(document['entities'])} entities)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

