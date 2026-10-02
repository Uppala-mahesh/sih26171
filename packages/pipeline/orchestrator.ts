/**
 * SIH26171 — Agent pipeline orchestration.
 *
 * The thing that turns five independently-correct libraries into one system
 * that is actually correct. Every module below this line has been unit-tested
 * and parity-checked against Python; none of them prove they work TOGETHER.
 *
 * Sequence, and why the order is not negotiable:
 *
 *   1. resolve capability        a rung is chosen before anything claims to work
 *   2. capture text segments     DOM content, element-scoped
 *   3. sanitize                  detect -> tokenize -> redact -> re-inspect
 *   4. capture frames            pixels are a SEPARATE route, never implied by 3
 *   5. redact pixels             opaque fill, then verify or withhold
 *   6. earn evidence             re-inspection RECOMPUTES the verdict
 *   7. build the envelope        DP-5: no field can hold raw content
 *   8. transmit via the guard    DP-2: the only egress path in the system
 *
 * Step 4 exists because of the defect this whole project exists to fix: a text
 * pass that succeeds while the vision pipeline quietly returns a 1x1 frame is
 * exactly v1's G-2/G-6. A component must never be able to upgrade its own scope
 * into a system-wide claim, so pixels are verified separately and their absence
 * is declared rather than assumed.
 *
 * ── On testability ───────────────────────────────────────────────────────────
 * The DOM, the pixel source and the clock are INJECTED. That is not a testing
 * convenience; it is what lets the full path run headlessly in CI, so the
 * end-to-end claims in the rubric are backed by executed code rather than by
 * a diagram of how the pieces are supposed to meet.
 */

import type { SanitizationEvidence, InferenceRung, Verifier } from '../contracts/sanitization.js';
import { verificationProof } from '../contracts/sanitization.js';
import type { OutboundEnvelope, SanitizedContext, SafeElementDescriptor } from '../contracts/payloads.js';
import { elementRef } from '../contracts/payloads.js';
import type { BoundingBox } from '../contracts/geometry.js';
import { boundingBox } from '../contracts/geometry.js';
import { Sanitizer, ResidualLeakError } from '../privacy/sanitizer.js';
import { detect, type DetectionResult } from '../privacy/detector.js';
import {
  PixelRedactor,
  assertVerified,
  type PixelFrame,
  type PixelRedactionResult,
} from '../privacy/pixels.js';
import { PlaceholderVault } from '../privacy/vault.js';
import { EgressGuard } from '../gateway/guard.js';

// ─────────────────────────────────────────────────────────────────────────────
// Injected adapters. The pipeline knows nothing about DOM, Chrome, or clocks.
// ─────────────────────────────────────────────────────────────────────────────

export interface TextSegment {
  readonly elementId: string;
  readonly text: string;
  readonly tagName?: string;
  readonly ariaLabel?: string;
}

export interface FrameSegment {
  readonly elementId: string;
  readonly frame: PixelFrame;
  readonly boxes: readonly BoundingBox[];
  readonly entities: readonly string[];
}

export interface Capability {
  readonly rung: InferenceRung;
  /** FR-PER-2: can this environment verify pixels at all? */
  readonly canVerifyPixels: boolean;
  /** The specific check that could not run. Never a generic failure. */
  readonly missingCheck?: string;
}

export interface PageAdapters {
  readonly observationId: string;
  readonly url: string;
  readonly title: string;
  readonly viewport: { readonly width: number; readonly height: number };
  /** FR-PER-4: cross-origin frame blindness is declared, never omitted. */
  readonly frameBlind: boolean;
  readonly capability: Capability;
  captureText(): readonly TextSegment[];
  captureFrames(): readonly FrameSegment[];
  now(): number;
}

export interface PipelineDeps {
  readonly vault: PlaceholderVault;
  readonly guard: EgressGuard;
  readonly redactor?: PixelRedactor;
  readonly detect?: (text: string) => DetectionResult;
}

export interface PipelineResult {
  readonly evidence: SanitizationEvidence;
  readonly envelope: OutboundEnvelope;
  readonly rung: InferenceRung;
  readonly redactionCount: number;
  readonly textSegments: number;
  readonly framesVerified: number;
  /** Non-null when pixel verification failed; the envelope was still built. */
  readonly pixelFailure: string | null;
  readonly transmitted: boolean;
  readonly transmitError: string | null;
}


/**
 * Run the full path and return everything the caller needs to be accountable.
 *
 * Never throws for an expected privacy outcome — a failed verification becomes
 * a declared state, not an exception, because the declared state is what
 * travels with the payload. Throws only when a residual leak survives the
 * sanitizer, which is a bug rather than an outcome.
 */
export function runPipeline(
  adapters: PageAdapters,
  deps: PipelineDeps,
  taskDescription = 'observe the page',
): PipelineResult {
  const detectFn = deps.detect ?? detect;
  const redactor = deps.redactor ?? new PixelRedactor();
  const now = adapters.now();

  // ── 1. capability is resolved BEFORE anything claims to have worked ──────
  const rung = adapters.capability.rung;

  // ── 2/3. text: detect -> tokenize -> redact -> re-inspect ────────────────
  const sanitizer = new Sanitizer(deps.vault, detectFn);
  const segments = adapters.captureText();
  const elements: SafeElementDescriptor[] = [];
  const safeTexts: string[] = [];
  const unresolved: string[] = [];
  let sanitizedBlob = '';

  for (const segment of segments) {
    // FR-RED-4 already re-inspected inside sanitize(); doing it AGAIN here is
    // deliberate. The second pass is the one that feeds the proof, so the proof
    // is earned from the artefact rather than inherited from a callee's claim.
    const outcome = sanitizer.sanitize(segment.text, segment.elementId);
    sanitizedBlob += `${outcome.text}\n`;
    for (const record of outcome.records) {
      if (record.outcome === 'UNCERTAIN') unresolved.push(record.entity_type);
    }
    elements.push({
      ref: elementRef({
        observationId: adapters.observationId,
        elementId: segment.elementId,
        origin: adapters.url,
      }),
      tagName: segment.tagName ?? 'DIV',
      role: 'TEXT_REGION',
      ariaLabel: segment.ariaLabel ?? '',
      textContent: outcome.text,
      placeholder: null,
      bounds: boundingBox(0, 0, 0, 0),
      isInteractive: false,
      isSensitive: outcome.records.length > 0,
      opaque: false,
      confidence: 1,
    });
  }

  // ── 4/5. pixels: a SEPARATE route, verified separately or declared absent ─
  const frames = adapters.captureFrames();
  let framesVerified = 0;
  let pixelFailure: string | null = null;

  for (const frameSegment of frames) {
    try {
      const result = redactor.redact(
        frameSegment.frame,
        frameSegment.boxes,
        frameSegment.entities,
      );
      assertVerified(result);
      framesVerified += 1;
    } catch (error) {
      // Recorded and declared. Never swallowed: the state below is derived
      // from this, so a failure here becomes NOT_INSTRUMENTED rather than a
      // silently unverified SANITIZED.
      pixelFailure = error instanceof Error ? error.message : String(error);
    }
  }

  // ── 6. earn the evidence by recomputing it ───────────────────────────────
  const residualText = detectFn(sanitizedBlob).findings.filter(
    (f) => f.outcome === 'ACCEPTED',
  ).length;
  const residualPlaceholder = deps.vault.count_residual(sanitizedBlob);

  const verifiersRun: Verifier[] = ['text_rescan', 'placeholder_audit'];
  if (adapters.capability.canVerifyPixels) verifiersRun.push('pixel_rescan');
  // F-2: vault segregation is structural. No outbound type has a field capable
  // of holding the reverse mapping, so it is recorded as enforced by type
  // rather than asserted by a runtime scan that could not fail.
  verifiersRun.push('vault_segregation');

  const residualFindings =
    residualText + residualPlaceholder + (pixelFailure !== null ? 1 : 0);

  let evidence: SanitizationEvidence;
  if (!adapters.capability.canVerifyPixels) {
    evidence = {
      state: 'NOT_INSTRUMENTED',
      missingCheck: adapters.capability.missingCheck ?? 'pixel_rescan',
      declaredAt: now,
    };
  } else if (pixelFailure !== null || residualFindings > 0) {
    // DP-6: a state cannot exist without its evidence, so when no valid proof
    // can be produced the honest answer is NOT_INSTRUMENTED - the payload has
    // no certificate behind it. This is also the v1 shape: a failed check that
    // reported success.
    evidence = {
      state: 'NOT_INSTRUMENTED',
      missingCheck: pixelFailure !== null ? 'pixel_rescan' : 'text_rescan',
      declaredAt: now,
    };
  } else if (frames.length === 0) {
    // A capability claim with nothing examined is the defect this project exists
    // to fix. v1's vision pipeline could fail silently and return a 1x1 frame -
    // or no frame at all - and the payload was still reported sanitized
    // (defects G-2/G-6).
    //
    // Declaring `pixel_rescan` as a verifier that ran over zero regions is
    // exactly that lie, one level down: the proof would be honest about its own
    // contents and still mean nothing. `regionsChecked` would read 1 (the text
    // segment) and the reader would reasonably conclude pixels were covered.
    //
    // The system cannot distinguish "this page has no pixels" from "the capture
    // failed", so it fails closed. An adapter that genuinely has nothing to
    // verify must say so via `canVerifyPixels: false`, which is a claim the
    // pipeline can reason about rather than a silent absence.
    evidence = {
      state: 'NOT_INSTRUMENTED',
      missingCheck: 'pixel_rescan',
      declaredAt: now,
    };
  } else if (unresolved.length > 0) {
    evidence = {
      state: 'UNCERTAIN',
      unresolved: [...new Set(unresolved)],
      declaredAt: now,
    };
  } else if (rung !== 'webgpu') {
    evidence = {
      state: 'DEGRADED',
      reason: 'vision_rung_unavailable',
      rung,
      declaredAt: now,
    };
  } else {
    evidence = {
      state: 'SANITIZED',
      proof: verificationProof({
        verifiersRun,
        regionsChecked: segments.length + frames.length,
        residualFindings: 0,
      }),
      rung,
      declaredAt: now,
    };
  }

  // ── 7. build the envelope. No field here can hold raw content. ────────────
  const context: SanitizedContext = {
    observationId: adapters.observationId,
    contextVersion: 1,
    capturedAt: now,
    url: adapters.url,
    title: adapters.title,
    elements,
    safeTexts,
    visualRegions: [],
    viewport: adapters.viewport,
    frameBlind: adapters.frameBlind,
    opaqueRegions: [],
  };

  const envelope: OutboundEnvelope = {
    schemaVersion: '1.0.0',
    destination: 'external_provider',
    context,
    evidence,
    rung,
    taskDescription,
  };

  // ── 8. DP-2: the only egress path in the system ───────────────────────────
  let transmitted = false;
  let transmitError: string | null = null;
  try {
    deps.guard.transmit(envelope, () => {
      transmitted = true;
    });
  } catch (error) {
    transmitError = error instanceof Error ? error.message : String(error);
  }

  return Object.freeze({
    evidence,
    envelope,
    rung,
    redactionCount: deps.vault.size,
    textSegments: segments.length,
    framesVerified,
    pixelFailure,
    transmitted,
    transmitError,
  });
}

export { ResidualLeakError };
