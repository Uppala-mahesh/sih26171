/**
 * SIH26171 — Egress guard: the single enforcement point at B-2 and B-3.
 *
 * TypeScript port of apps/backend/app/gateway/guard.py.
 *
 * Implements FR-EGR-1..FR-EGR-7, obligation **A-6**, and verification **V-2**.
 *
 * DES-ARCH-001 rule DP-2: this is the ONLY module permitted to perform outbound
 * transmission. Every other module reaches the network by handing an envelope to
 * `transmit()` and letting this module decide whether it is allowed.
 *
 * The whole point: **the receiver does not trust the sender.**
 *
 * v1 accepted an `is_sanitized: true` boolean from the extension, and when the
 * vision pipeline silently failed it produced a 1x1 image carrying that boolean,
 * which the backend accepted as sanitized (v1 defects G-2 and G-6). Here the guard
 * RE-DERIVES the verdict from the payload's actual contents: it strips our own
 * placeholder tokens, re-runs the full detector over everything that would go on
 * the wire, and blocks if anything sensitive survives.
 *
 * Trusting the sender is what made v1's boundary decorative.
 */

import { detect, type DetectionResult } from '../privacy/detector.js';
import { stripTokens } from '../privacy/vault.js';
import {
  transmissionVerdict,
  type SanitizationEvidence,
  type TransmissionVerdict,
} from '../contracts/sanitization.js';
import type { OutboundEnvelope } from '../contracts/payloads.js';

/** An outbound payload was refused. The sender is never invoked. */
export class PrivacyBoundaryBreachError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PrivacyBoundaryBreachError';
  }
}

/** What the independent re-inspection actually found. */
export interface RevalidationReport {
  readonly texts_scanned: number;
  readonly residual_accepted: number;
  readonly residual_uncertain: number;
  readonly clean: boolean;
}

export interface InspectionResult {
  readonly verdict: TransmissionVerdict;
  readonly reason: string;
  readonly revalidation: RevalidationReport;
  readonly state: string;
  readonly permitted: boolean;
}

/** FR-EGR-7: the trail records decisions and counts, never values. */
export interface AuditEvent {
  readonly occurred_at: number;
  readonly destination: string;
  readonly observation_id: string;
  readonly verdict: TransmissionVerdict;
  readonly state: string;
  readonly redaction_count: number;
  readonly unresolved_count: number;
  readonly reason: string;
  readonly payload_bytes: number;
}

/**
 * UTF-8 byte length without depending on `TextEncoder`.
 *
 * The parity build compiles with lib ES2022 only and must produce the same
 * number as the Python side, so the encoding is spelled out rather than
 * delegated to a global that may or may not be typed.
 */
export function utf8Length(text: string): number {
  let bytes = 0;
  for (const ch of text) {
    const cp = ch.codePointAt(0) as number;
    if (cp < 0x80) bytes += 1;
    else if (cp < 0x800) bytes += 2;
    else if (cp < 0x10000) bytes += 3;
    else bytes += 4;
  }
  return bytes;
}

export function payload_size(envelope: OutboundEnvelope): number {
  return utf8Length(JSON.stringify(envelope));
}

const EMPTY_REPORT: RevalidationReport = Object.freeze({
  texts_scanned: 0,
  residual_accepted: 0,
  residual_uncertain: 0,
  clean: true,
});


/**
 * Inspect, then decide, then transmit — in that order, always.
 *
 * Stateless apart from injected collaborators. The audit trail is owned by the
 * caller so its lifecycle follows the task.
 */
export class EgressGuard {
  readonly #audit: AuditEvent[] = [];
  readonly #detect: (text: string) => DetectionResult;

  constructor(detector: (text: string) => DetectionResult = detect) {
    this.#detect = detector;
  }

  /** FR-EGR-6: the trail, in order. Counts and verdicts only. */
  get audit(): readonly AuditEvent[] {
    return this.#audit;
  }

  /**
   * Re-derive the verdict from the payload itself (FR-EGR-4, V-2).
   *
   * Placeholder tokens are stripped first, so this examines only page-authored
   * content and never the system's own substitutions — without that, the nonce
   * digits inside a token would re-detect as an OTP and every scan would carry
   * self-inflicted noise.
   */
  revalidate(envelope: OutboundEnvelope): RevalidationReport {
    const context = envelope.context;
    const segments: string[] = [context.title, ...context.safeTexts];
    for (const element of context.elements) {
      segments.push(element.ariaLabel);
      segments.push(element.textContent);
    }

    let residual_accepted = 0;
    let residual_uncertain = 0;
    let scanned = 0;

    for (const segment of segments) {
      const haystack = stripTokens(segment);
      if (haystack.trim() === '') continue;
      scanned += 1;
      const result = this.#detect(haystack);
      for (const finding of result.findings) {
        if (finding.outcome === 'ACCEPTED') residual_accepted += 1;
        else residual_uncertain += 1;
      }
    }

    return Object.freeze({
      texts_scanned: scanned,
      residual_accepted,
      residual_uncertain,
      clean: residual_accepted === 0,
    });
  }

  /** Decide whether this envelope may cross. Never trusts the sender. */
  inspect(envelope: OutboundEnvelope): InspectionResult {
    const evidence: SanitizationEvidence = envelope.evidence;
    const declared = transmissionVerdict(evidence);

    // 1. A failure is never upgraded. NOT_INSTRUMENTED never leaves the device.
    if (declared === 'WITHHOLD') {
      return refuse(evidence, 'declared state is NOT_INSTRUMENTED', null);
    }

    // 2. INDEPENDENT RE-VERIFICATION. The declared state is a claim; this is the
    //    check. It is the control v1 did not have (V-2).
    const report = this.revalidate(envelope);
    if (!report.clean) {
      return refuse(
        evidence,
        `re-inspection found ${report.residual_accepted} sensitive value(s) ` +
          `in the outbound payload`,
        report,
      );
    }

    // 3. Frame blindness must be visible, not buried (FR-PER-4). A payload that
    //    claims full sanitation while a frame was never inspected is claiming
    //    something the system cannot know.
    if (envelope.context.frameBlind && declared === 'ALLOW') {
      return refuse(
        evidence,
        'payload declares full sanitation while cross-origin frames were ' +
          'never inspected; frame blindness must be declared',
        report,
      );
    }

    // Permitted. Any residual ambiguity travels with the payload.
    if (report.residual_uncertain > 0 || declared === 'ALLOW_DECLARED') {
      return Object.freeze({
        verdict: 'ALLOW_DECLARED' as const,
        reason:
          're-inspection clean; capability loss or ambiguity declared ' +
          'and will travel with the payload',
        revalidation: report,
        state: evidence.state,
        permitted: true,
      });
    }

    return Object.freeze({
      verdict: 'ALLOW' as const,
      reason: 're-inspection clean and no degradation declared',
      revalidation: report,
      state: evidence.state,
      permitted: true,
    });
  }

  /**
   * Inspect, audit, and only then hand the payload to `sender`.
   *
   * `sender` is not reachable from anywhere else, so this is the ENFORCEMENT of
   * rule DP-2 rather than a convention about it.
   */
  transmit<T>(envelope: OutboundEnvelope, sender: (e: OutboundEnvelope) => T): T {
    const result = this.inspect(envelope);
    this.#record(envelope, result);

    if (!result.permitted) {
      throw new PrivacyBoundaryBreachError(
        `egress refused for ${envelope.destination}: ${result.reason}`,
      );
    }
    return sender(envelope);
  }

  #record(envelope: OutboundEnvelope, result: InspectionResult): void {
    this.#audit.push(
      Object.freeze({
        occurred_at: Date.now(),
        destination: envelope.destination,
        observation_id: envelope.context.observationId,
        verdict: result.verdict,
        state: result.state,
        redaction_count: envelope.context.elements.length,
        unresolved_count: 0,
        reason: result.reason,
        payload_bytes: payload_size(envelope),
      }),
    );
  }
}

function refuse(
  evidence: SanitizationEvidence,
  reason: string,
  report: RevalidationReport | null,
): InspectionResult {
  return Object.freeze({
    verdict: 'WITHHOLD' as const,
    reason,
    revalidation: report ?? EMPTY_REPORT,
    state: evidence.state,
    permitted: false,
  });
}
