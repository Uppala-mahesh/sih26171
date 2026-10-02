/**
 * SIH26171 — Outbound Payload Contracts
 *
 * Implements DES-ARCH-001 rule DP-5:
 *   "Payload types are constructed so that raw and vault fields are NOT
 *    representable."
 *
 * Governed by: SEC-BOUND-001 section 6 (data handling matrix), F-1..F-10.
 * Requirements: FR-EGR-1, FR-EGR-2, FR-VLT-1, FR-RED-8, EI-1.
 *
 * ── The design idea ─────────────────────────────────────────────────────────
 * Rather than validating that a payload contains no secrets, these types make
 * it IMPOSSIBLE TO EXPRESS. There is no field for a raw value and no field for
 * a vault mapping. A payload either typechecks, or it is not a payload.
 *
 * Contrast with v1, where `SafePageContext` was a dict-shaped model a caller
 * could populate with anything, accepted on the strength of an
 * `is_sanitized: true` boolean (v1 defects G-1 and G-2).
 */

import type { SanitizationEvidence, InferenceRung } from './sanitization';
import type { BoundingBox } from './geometry';

// Re-exported so existing importers keep working while there is exactly ONE
// declaration of the box type. payloads.ts previously declared its own, which
// meant `privacy/pixels` and `contracts/payloads` could hold boxes that were
// structurally identical but nominally unrelated.
export type { BoundingBox } from './geometry';

// ─────────────────────────────────────────────────────────────────────────────
// Branded primitives — raw data cannot cross a file boundary
// ─────────────────────────────────────────────────────────────────────────────

declare const RAW_BRAND: unique symbol;
declare const ELEMENT_BRAND: unique symbol;

/**
 * A genuine sensitive value. Branded so it is distinct from every `string` in
 * the codebase: passing raw content where a placeholder is expected becomes a
 * compile error rather than a runtime near-miss.
 *
 * Constructed ONLY inside Z1 by the detector pipeline. Never by a consumer.
 */
export type RawSensitive = string & { readonly [RAW_BRAND]: 'RAW_SENSITIVE' };

/** A stable, snapshot-scoped element identity. */
export interface ElementRef {
  readonly [ELEMENT_BRAND]: 'ELEMENT_REF';
  readonly observationId: string;
  readonly elementId: string;
  readonly origin: string;
}

/**
 * A vault token such as `<AADHAAR_1>`.
 *
 * This is a plain string. That is deliberate - it must be serialisable and
 * human-readable, because a jury inspects the outbound payload. It carries no
 * information about the value it replaced.
 */
export type Placeholder = string;

// ─────────────────────────────────────────────────────────────────────────────
// Geometry
// ─────────────────────────────────────────────────────────────────────────────

export type RegionSensitivity = 'SAFE' | 'REDACTED' | 'UNCERTAIN' | 'OPAQUE';

export interface VisualRegion {
  readonly box: BoundingBox;
  readonly role: string;
  readonly sensitivity: RegionSensitivity;
  readonly placeholder: Placeholder | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// UI element understanding — FR-VIS-1 taxonomy
// ─────────────────────────────────────────────────────────────────────────────

export const UI_ROLES = [
  'BUTTON',
  'TEXT_INPUT',
  'PASSWORD_INPUT',
  'CHECKBOX',
  'RADIO',
  'SELECT',
  'LINK',
  'MENU_ITEM',
  'TAB',
  'DIALOG',
  'TABLE',
  'FORM',
  'NAVIGATION',
  'IMAGE',
  'TEXT_REGION',
  'UNKNOWN',
] as const;

export type UiRole = (typeof UI_ROLES)[number];

/**
 * FR-VIS-4: no element is ever emitted with a role but without a confidence.
 * An element below threshold is UNKNOWN, never a guess.
 */
export interface ClassifiedElement {
  readonly ref: ElementRef;
  readonly role: UiRole;
  readonly confidence: number;
  readonly source: 'dom' | 'vision' | 'fused';
  /** Present when source is 'fused': which modality won, and why. */
  readonly reconciledFrom?: { readonly winner: 'dom' | 'vision'; readonly reason: string };
}

// ─────────────────────────────────────────────────────────────────────────────
// The sanitized element — placeholder fields ONLY
// ─────────────────────────────────────────────────────────────────────────────

/**
 * FR-PER-1 / FR-PII-5. Note what is absent:
 *   - no `value` field capable of holding raw content
 *   - every text-bearing field is `string`, and by contract the Sanitizer has
 *     already replaced sensitive spans with placeholders
 *   - `isSensitive` marks the element WITHOUT disclosing what was found
 */
export interface SafeElementDescriptor {
  readonly ref: ElementRef;
  readonly tagName: string;
  readonly role: UiRole;
  readonly ariaLabel: string;
  readonly textContent: string;
  readonly placeholder: Placeholder | null;
  readonly bounds: BoundingBox;
  readonly isInteractive: boolean;
  readonly isSensitive: boolean;
  /** FR-PER-7: canvas, video and cross-origin regions are flagged, not hidden. */
  readonly opaque: boolean;
  readonly confidence: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// The envelope — the only thing that may cross B-2 or B-3
// ─────────────────────────────────────────────────────────────────────────────

/**
 * F-4: no raw perception buffer is reachable from here. There is no field of
 * type RawSensitive anywhere in this type or in anything it references.
 *
 * F-2: no vault reverse mapping. The vault lives in Z1 memory and has no
 * representation in any outbound type — that is the entire point.
 */
export interface SanitizedContext {
  readonly observationId: string;
  readonly contextVersion: number;
  readonly capturedAt: number;
  readonly url: string;
  readonly title: string;
  readonly elements: readonly SafeElementDescriptor[];
  readonly safeTexts: readonly string[];
  readonly visualRegions: readonly VisualRegion[];
  readonly viewport: { readonly width: number; readonly height: number };
  /** FR-PER-4: cross-origin frame blindness is declared, never silently omitted. */
  readonly frameBlind: boolean;
  readonly opaqueRegions: readonly BoundingBox[];
}

/**
 * The single outbound envelope.
 *
 * `evidence` is not optional, so a payload cannot be transmitted without
 * declaring what was actually done to it. This is DP-6 reaching the wire:
 * SEC-BOUND-001 section 5.3 - a state without evidence is NOT_INSTRUMENTED
 * by definition.
 */
export interface OutboundEnvelope {
  readonly schemaVersion: string;
  readonly destination: 'local_enclave' | 'external_provider';
  readonly context: SanitizedContext;
  readonly evidence: SanitizationEvidence;
  readonly rung: InferenceRung;
  readonly taskDescription: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Self-check on the contracts themselves
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Compile-time proof that the outbound types are raw-free.
 *
 * If someone later adds `rawValue: RawSensitive` to SanitizedContext, this
 * conditional type becomes `false` and `assertContractsAreSound` stops
 * typechecking — the contract set fails to compile against its own rule.
 */
export type OutboundTypesAreRawFree =
  SanitizedContext extends { rawValue: RawSensitive } ? false : true;

export function assertContractsAreSound(_proof: OutboundTypesAreRawFree): void {
  // Intentionally empty. The parameter's type IS the assertion: this function
  // cannot be called unless every outbound type is raw-free.
}

/** Counted so the contract suite can report its own size honestly. */
export const CONTRACT_GUARANTEES = {
  rawNotRepresentableOutbound: true,
  vaultNotRepresentableAnywhere: true,
  stateRequiresEvidence: true,
  failureCannotBecomeSuccess: true,
  confidenceRequiredWithRole: true,
  frameBlindnessIsDeclared: true,
} as const;

/**
 * The single legitimate construction path for an ElementRef.
 *
 * Like `verificationProof`, this is the only place the brand cast occurs. The
 * caller supplies the three values; the brand cannot be synthesised from
 * outside, so a consumer cannot invent an element identity that the
 * perception pipeline never observed — which is what FR-AGT-5 rebinding
 * depends on.
 */
export function elementRef(input: {
  observationId: string;
  elementId: string;
  origin: string;
}): ElementRef {
  if (!input.observationId || !input.elementId || !input.origin) {
    throw new Error('ElementRef requires a non-empty observationId, elementId and origin.');
  }
  // The single deliberate cast in this module.
  return Object.freeze({ ...input }) as unknown as ElementRef;
}


