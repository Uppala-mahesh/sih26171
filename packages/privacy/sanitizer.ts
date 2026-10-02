/**
 * SIH26171 — Text sanitizer.
 *
 * TypeScript port of apps/backend/app/privacy/sanitizer.py. The extension runs
 * in a service worker and an offscreen document, neither of which can execute
 * Python, so the privacy core must exist on both runtimes.
 *
 * Governed by FR-RED-4 (independent re-inspection of the produced artefact),
 * FR-RED-5 (state is never inferred from a boolean flag) and SEC-BOUND-001 V-1.
 *
 * ── On `SANITIZED_TEXT` ──────────────────────────────────────────────────────
 * This label is deliberately NOT the contract's `SANITIZED`. A text pass has
 * verified the DOM's text content and nothing else: it has not looked at a
 * single pixel, so it cannot know whether the same value was also rendered as
 * an image, a canvas, or a CSS background. The Python implementation returns
 * the same narrower label, and both ports are asserted to agree by
 * tests/contract/test_parity.py.
 *
 * Claiming `SANITIZED` here would be exactly the failure SEC-BOUND-001 exists
 * to prevent: a component upgrading its own scope into a system-wide claim.
 */

import { detect, type DetectionResult } from './detector.js';
import {
  elementBinding,
  type ElementBinding,
  type PlaceholderVault,
  type SafePrivacySummary,
} from './vault.js';

/**
 * A raw value survived redaction, so the output is withheld.
 *
 * Thrown rather than returned as a state: a payload that still contains a
 * secret must never become an inspectable artefact.
 */
export class ResidualLeakError extends Error {
  constructor(readonly count: number) {
    super(`${count} raw value(s) survived redaction; output withheld`);
    this.name = 'ResidualLeakError';
  }
}

export interface RedactionRecord {
  readonly placeholder: string;
  readonly entity_type: string;
  readonly sensitivity: string;
  readonly start: number;
  readonly end: number;
  readonly outcome: string;
  readonly confidence: number;
}

/** What actually happened to this text. Honest about its own limits. */
export interface TextRedactionEvidence {
  readonly observation_id: string;
  readonly redactions: number;
  readonly verified: boolean;
  readonly residual_count: number;
  readonly unresolved_count: number;
  readonly pixel_covered: boolean;
  /** `SANITIZED_TEXT` only when the re-scan passed and nothing was uncertain. */
  readonly state: 'SANITIZED_TEXT' | 'DEGRADED';
}

/** The complete result. Safe to serialise: no raw value appears anywhere. */
export interface SanitizationOutcome {
  readonly observation_id: string;
  readonly text: string;
  readonly records: readonly RedactionRecord[];
  readonly summary: SafePrivacySummary;
  readonly evidence: TextRedactionEvidence;
  readonly discarded: number;
}

function buildEvidence(
  observationId: string,
  records: readonly RedactionRecord[],
  pixelCovered: boolean,
): TextRedactionEvidence {
  const unresolved = records.filter((r) => r.outcome === 'UNCERTAIN').length;
  // Never claims a full SANITIZED, because pixels have not been verified here.
  return Object.freeze({
    observation_id: observationId,
    redactions: records.length,
    verified: true,
    residual_count: 0,
    unresolved_count: unresolved,
    pixel_covered: pixelCovered,
    state: unresolved ? 'DEGRADED' : 'SANITIZED_TEXT',
  });
}

/**
 * Detect, tokenise, redact, then PROVE the redaction worked.
 *
 * Stateless apart from the injected detector and vault. The vault is supplied by
 * the caller so its lifecycle is owned by the task, not by this object
 * (FR-VLT-4).
 */
export class Sanitizer {
  readonly #vault: PlaceholderVault;
  readonly #detect: (text: string) => DetectionResult;

  constructor(vault: PlaceholderVault, detector: (text: string) => DetectionResult = detect) {
    this.#vault = vault;
    this.#detect = detector;
  }

  /**
   * Redact every sensitive span in `text`.
   *
   * `elementId` is the node the values are considered to have come from; it is
   * the binding that `detokenize_for_target` will later enforce (B-6).
   */
  sanitize(text: string, elementId = 'page-root'): SanitizationOutcome {
    const detection = this.#detect(text);
    const binding: ElementBinding = elementBinding(
      this.#vault.observation_id,
      elementId,
    );

    const records: RedactionRecord[] = [];
    const replacements: Array<[number, number, string]> = [];

    for (const finding of detection.findings) {
      const raw = text.slice(finding.start, finding.end);
      if (!raw) continue;
      const placeholder = this.#vault.tokenize(
        finding.entityId,
        raw,
        binding,
        finding.sensitivity,
        finding.outcome,
      );
      records.push(
        Object.freeze({
          placeholder,
          entity_type: finding.entityId,
          sensitivity: finding.sensitivity,
          start: finding.start,
          end: finding.end,
          outcome: finding.outcome,
          confidence: finding.confidence,
        }),
      );
      replacements.push([finding.start, finding.end, placeholder]);
    }

    const sanitized = applyReplacements(text, replacements);

    // FR-RED-4: independent re-inspection of the produced artefact.
    const residual = this.#vault.count_residual(sanitized);
    if (residual > 0) throw new ResidualLeakError(residual);

    return Object.freeze({
      observation_id: this.#vault.observation_id,
      text: sanitized,
      records: Object.freeze(records),
      summary: this.#vault.safe_summary(),
      evidence: buildEvidence(this.#vault.observation_id, records, false),
      discarded: detection.discarded,
    });
  }
}

/** Rebuild right-to-left so earlier offsets stay valid as we splice. */
function applyReplacements(text: string, replacements: Array<[number, number, string]>): string {
  let out = text;
  for (const [start, end, placeholder] of [...replacements].sort((a, b) => b[0] - a[0])) {
    out = out.slice(0, start) + placeholder + out.slice(end);
  }
  return out;
}
