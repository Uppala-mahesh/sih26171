/**
 * SIH26171 — PII detection, TypeScript mirror (the Z1 extension runtime).
 *
 * Implements the same contract as apps/backend/app/privacy/detectors.py:
 *   FR-PII-1..FR-PII-9, REQ-DATA-001 sections 2.2 / 4.4 / 5
 *
 * Consumes the GENERATED registry (packages/taxonomy/generated/entities.ts).
 * This file holds no entity list of its own (REQ-DATA-001 rule D-1), which is
 * what makes NFR-MAIN-1 — adding an entity means editing one file — true.
 *
 * Parity with the Python runtime is proven behaviourally by
 * tests/contract/test_parity.py. Rule X-4 (divergence fails the build) is only
 * meaningful if something actually compares the two.
 */

import { ENTITIES, PATTERN_BACKED, type EntitySpec } from '../taxonomy/generated/entities';
import {
  entropyMeets,
  ifscValid,
  luhnValid,
  mobileInValid,
  panValid,
  upiVpaValid,
  verhoeffValid,
} from './validators';

export type Outcome = 'ACCEPTED' | 'UNCERTAIN';

/**
 * Same window as the Python side, for the same reason: an earlier 48-char
 * window let a cue on one line gate a number on another, producing four
 * spurious OTP findings inside a card number.
 */
export const CONTEXT_WINDOW = 24;
export const SECRET_ENTROPY_FLOOR = 3.2;

const SENSITIVITY_RANK: Record<string, number> = {
  CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3,
};
const TIER_RANK: Record<string, number> = { T1: 0, T2: 1, T3: 2 };

export interface Finding {
  readonly entityId: string;
  readonly start: number;
  readonly end: number;
  readonly tier: string;
  readonly sensitivity: string;
  readonly outcome: Outcome;
  readonly confidence: number;
  readonly placeholderPrefix: string;
}

export interface DetectionResult {
  readonly findings: readonly Finding[];
  readonly discarded: number;
}

/** T1/T2 dispatch. Adding a validator means adding a name here only. */
const VALIDATORS: Record<string, (value: string) => boolean> = {
  verhoeff: verhoeffValid,
  luhn: luhnValid,
  pan_structure: panValid,
  ifsc_structure: ifscValid,
  psp_allowlist: upiVpaValid,
  mobile_in_structure: mobileInValid,
};

const CONFIDENCE: Record<string, number> = { T1: 0.99, T2: 0.9, T3: 0.85 };
const UNCERTAIN_CONFIDENCE = 0.5;

const patternCache = new Map<string, RegExp>();

function compiledFor(spec: EntitySpec): RegExp | null {
  if (spec.pattern === null) return null;
  const cached = patternCache.get(spec.pattern);
  if (cached !== undefined) return cached;
  // The 'i' flag mirrors Python's re.IGNORECASE. Without it the two runtimes
  // would disagree on every mixed-case candidate and parity would be theatre.
  const expression = new RegExp(spec.pattern, 'gi');
  patternCache.set(spec.pattern, expression);
  return expression;
}

function lineBounds(text: string, index: number): [number, number] {
  const start = text.lastIndexOf('\n', index - 1) + 1;
  const end = text.indexOf('\n', index);
  return [start, end === -1 ? text.length : end];
}

function isDigit(char: string): boolean {
  return char >= '0' && char <= '9';
}

export function isIsolatedNumber(text: string, start: number, end: number): boolean {
  let index = start - 1;
  let hops = 0;
  while (index >= 0 && (text[index] === ' ' || text[index] === '-') && hops < 3) {
    index -= 1;
    hops += 1;
  }
  const beforeClear = index < 0 || !isDigit(text[index]!);

  index = end;
  hops = 0;
  while (index < text.length && (text[index] === ' ' || text[index] === '-') && hops < 3) {
    index += 1;
    hops += 1;
  }
  const afterClear = index >= text.length || !isDigit(text[index]!);

  return beforeClear && afterClear;
}

function isNumericEntity(spec: EntitySpec): boolean {
  if (spec.pattern === null) return false;
  return !/[A-Za-z]/.test(spec.pattern.replace(/\\d/g, ''));
}

export function hasContextCue(
  spec: EntitySpec,
  text: string,
  start: number,
  end: number,
): boolean {
  const [lineStart, lineEnd] = lineBounds(text, start);
  const window = [
    ' ',
    text.slice(Math.max(lineStart, start - CONTEXT_WINDOW), start),
    ' ',
    text.slice(end, Math.min(lineEnd, end + CONTEXT_WINDOW)),
    ' ',
  ]
    .join('')
    .toLowerCase();

  return spec.contextCues.some((cue) => {
    const escaped = cue.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`\\b${escaped}\\b`).test(window);
  });
}

export function resolveOverlaps(findings: readonly Finding[]): Finding[] {
  const ordered = [...findings].sort(
    (a, b) =>
      a.start - b.start ||
      (SENSITIVITY_RANK[a.sensitivity] ?? 9) - (SENSITIVITY_RANK[b.sensitivity] ?? 9) ||
      (TIER_RANK[a.tier] ?? 9) - (TIER_RANK[b.tier] ?? 9),
  );

  const kept: Finding[] = [];
  for (const candidate of ordered) {
    const shadowed = kept.some(
      (existing) => existing.start <= candidate.start && candidate.end <= existing.end,
    );
    if (!shadowed) kept.push(candidate);
  }
  return kept;
}

export function detect(text: string): DetectionResult {
  if (text.length === 0) return { findings: [], discarded: 0 };

  const findings: Finding[] = [];
  let discarded = 0;

  for (const spec of PATTERN_BACKED) {
    const expression = compiledFor(spec);
    if (expression === null) continue;

    expression.lastIndex = 0;
    let match = expression.exec(text);

    while (match !== null) {
      const candidate = match[0]!;
      const start = match.index;
      const end = start + candidate.length;

      // A digit run adjacent to further digit groups is ONE number, not
      // several. This is what stops a spaced card number becoming four OTPs.
      if (isNumericEntity(spec) && !isIsolatedNumber(text, start, end)) {
        discarded += 1;
      } else {
        const validator =
          spec.validator === null ? undefined : VALIDATORS[spec.validator];
        const failsValidator = validator !== undefined && !validator(candidate);
        const failsEntropy =
          spec.validator === 'entropy' && !entropyMeets(candidate, SECRET_ENTROPY_FLOOR);

        if (failsValidator || failsEntropy) {
          // A failed checksum is evidence AGAINST the match. Discard outright;
          // never downgrade to a weaker positive (REQ-DATA-001 section 4.4).
          discarded += 1;
        } else {
          const uncertain =
            spec.requiresContext && !hasContextCue(spec, text, start, end);

          findings.push({
            entityId: spec.id,
            start,
            end,
            tier: spec.tier,
            sensitivity: spec.sensitivity,
            outcome: uncertain ? 'UNCERTAIN' : 'ACCEPTED',
            confidence: uncertain ? UNCERTAIN_CONFIDENCE : (CONFIDENCE[spec.tier] ?? 0.7),
            placeholderPrefix: spec.placeholder,
          });
        }
      }

      // Zero-length safety: a global expression able to match empty would
      // otherwise spin forever.
      if (start === expression.lastIndex) expression.lastIndex += 1;
      match = expression.exec(text);
    }
  }

  const resolved = resolveOverlaps(findings);
  resolved.sort((a, b) => a.start - b.start || a.entityId.localeCompare(b.entityId));
  return { findings: resolved, discarded };
}

/** Entity ids, for parity comparison against the Python runtime. */
export const SUPPORTED_ENTITIES: readonly string[] = ENTITIES.filter(
  (e) => e.pattern !== null,
).map((e) => e.id);

