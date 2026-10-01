/**
 * SIH26171 — Sanitization Contract
 *
 * Implements DES-ARCH-001 rules DP-6 and DP-7.
 *   DP-6  A SanitizationState cannot exist without its evidence.
 *   DP-7  The forbidden state transitions cannot be written.
 *
 * Governed by: SEC-BOUND-001 sections 5.2 / 5.3 / 5.4, conditions S-1..S-4, check V-2.
 * Requirement:  FR-RED-5 (state is never inferred from a boolean flag)
 *
 * ── An honest caveat about TypeScript brands ─────────────────────────────────
 * Brands and `unique symbol` keys are erased at compile time. They give a
 * COMPILE-TIME discipline: the wrong code does not typecheck. They are not a
 * runtime security boundary, because any caller can cast through `any`.
 *
 * The actual security boundary is the ZONE boundary defined in SEC-BOUND-001 -
 * a process boundary. These types make the *intent* checkable and make
 * accidental misuse a build failure. They are defence in depth against
 * developer error, not an enforcement mechanism against a determined attacker.
 *
 * The genuinely runtime-enforced guarantee lives in the Python enclave, where
 * Pydantic validates on every construction. See apps/backend/app/contracts/.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Vocabulary
// ─────────────────────────────────────────────────────────────────────────────

export const SANITIZATION_STATES = [
  'SANITIZED',
  'DEGRADED',
  'UNCERTAIN',
  'NOT_INSTRUMENTED',
] as const;

export type SanitizationState = (typeof SANITIZATION_STATES)[number];

export const VERIFIERS = [
  'text_rescan',
  'pixel_rescan',
  'placeholder_audit',
  'vault_segregation',
] as const;
export type Verifier = (typeof VERIFIERS)[number];

/** SEC-BOUND-001 section 3.2 - the Z1 capability ladder. */
export const CAPABILITY_LADDER = ['webgpu', 'wasm-simd', 'wasm', 'dom-only'] as const;
export type InferenceRung = (typeof CAPABILITY_LADDER)[number];

export type DegradationReason =
  | 'vision_rung_unavailable'
  | 'ocr_failed'
  | 'classifier_unavailable'
  | 'frame_blind'
  | 'opaque_region'
  | 'detector_budget_exhausted';

// ─────────────────────────────────────────────────────────────────────────────
// DP-6 — Evidence is not optional
// ─────────────────────────────────────────────────────────────────────────────

declare const PROOF_BRAND: unique symbol;

/**
 * A verification result. ONLY the Reinspector may produce one
 * (SEC-BOUND-001 S-2: the producer cannot supply the verdict).
 */
export interface VerificationProof {
  readonly [PROOF_BRAND]: 'VERIFICATION_PROOF';
  readonly verifiersRun: readonly Verifier[];
  readonly regionsChecked: number;
  readonly residualFindings: number;
}

/**
 * The four states, each carrying the evidence that justifies it.
 *
 * The discriminated union IS the enforcement mechanism: constructing
 * `{ state: 'SANITIZED' }` without a `proof` is a TYPE ERROR, not a runtime
 * check that might be skipped. That is what DP-6 means in practice.
 */
export type SanitizationEvidence =
  | {
      readonly state: 'SANITIZED';
      /** Mandatory. Absent proof is unrepresentable. */
      readonly proof: VerificationProof;
      readonly rung: InferenceRung;
      readonly declaredAt: number;
    }
  | {
      readonly state: 'DEGRADED';
      /** Why capability was below full. Never silently inferred. */
      readonly reason: DegradationReason;
      readonly rung: InferenceRung;
      readonly declaredAt: number;
    }
  | {
      readonly state: 'UNCERTAIN';
      /** Entity types below threshold, redacted by default. */
      readonly unresolved: readonly string[];
      readonly declaredAt: number;
    }
  | {
      readonly state: 'NOT_INSTRUMENTED';
      /** The specific check that could not run. Never a generic failure. */
      readonly missingCheck: string;
      readonly declaredAt: number;
    };

// ─────────────────────────────────────────────────────────────────────────────
// DP-7 — The forbidden transitions do not exist
// ─────────────────────────────────────────────────────────────────────────────

/**
 * SEC-BOUND-001 section 5.4.
 *
 * Illegal edges are ABSENT rather than guarded at runtime:
 *   NOT_INSTRUMENTED -> SANITIZED   illegal
 *   DEGRADED         -> SANITIZED   illegal
 *   UNCERTAIN        -> SANITIZED   illegal
 *
 * The first is the v1 defect expressed as a type: a fully-failed vision run
 * reported `is_sanitized: true`. A failure can never be upgraded into a
 * success, because the table has no such edge to take.
 */
export const LEGAL_TRANSITIONS = {
  SANITIZED: [],
  DEGRADED: ['NOT_INSTRUMENTED'],
  UNCERTAIN: ['NOT_INSTRUMENTED'],
  NOT_INSTRUMENTED: [],
} as const satisfies Record<SanitizationState, readonly SanitizationState[]>;

export type TargetState = keyof typeof LEGAL_TRANSITIONS;

export function isLegalTransition(from: TargetState, to: TargetState): boolean {
  return (LEGAL_TRANSITIONS[from] as readonly TargetState[]).includes(to);
}

/** Throws rather than silently degrading, so a violation is loud. */
export function assertLegalTransition(from: TargetState, to: TargetState): void {
  if (!isLegalTransition(from, to)) {
    throw new IllegalTransitionError(from, to);
  }
}

export class IllegalTransitionError extends Error {
  constructor(readonly from: TargetState, readonly to: TargetState) {
    super(
      `Illegal sanitization transition ${from} -> ${to}. ` +
        `A failure may never be upgraded into a success (SEC-BOUND-001 section 5.4).`,
    );
    this.name = 'IllegalTransitionError';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Transmission decision — SEC-BOUND-001 section 5.2
// ─────────────────────────────────────────────────────────────────────────────

export type TransmissionVerdict = 'ALLOW' | 'ALLOW_DECLARED' | 'WITHHOLD';

/**
 * DEGRADED and UNCERTAIN both fail in the SAFE direction: the system knows
 * less, so it redacts MORE. Over-redaction costs utility, never privacy — so
 * they may cross, provided the state is declared alongside the payload.
 *
 * NOT_INSTRUMENTED fails in the UNSAFE direction: the system does not know
 * what it is missing. It is withheld entirely, with no degraded substitute.
 */
export function transmissionVerdict(evidence: SanitizationEvidence): TransmissionVerdict {
  switch (evidence.state) {
    case 'SANITIZED':
      return 'ALLOW';
    case 'DEGRADED':
    case 'UNCERTAIN':
      return 'ALLOW_DECLARED';
    case 'NOT_INSTRUMENTED':
      return 'WITHHOLD';
    default: {
      // Exhaustiveness guard: adding a fifth state without handling it is a
      // compile error, not a silently-transmitted payload.
      const never: never = evidence;
      throw new Error(`Unhandled sanitization state: ${JSON.stringify(never)}`);
    }
  }
}

export function mayTransmit(evidence: SanitizationEvidence): boolean {
  return transmissionVerdict(evidence) !== 'WITHHOLD';
}

// ─────────────────────────────────────────────────────────────────────────────
// The single legitimate construction path for a VerificationProof
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Brands are unforgeable outside this module. This factory is therefore the
 * ONLY place the cast below occurs, and it is the audited chokepoint: only
 * `Reinspector` calls it, after recomputing the verdict from the redacted
 * artefact (SEC-BOUND-001 S-2).
 *
 * A caller anywhere else in the codebase cannot construct a proof — not with
 * an object literal, not with a spread, not with `as`. They must come here.
 */
export function verificationProof(input: {
  verifiersRun: readonly Verifier[];
  regionsChecked: number;
  residualFindings: number;
}): VerificationProof {
  if (input.verifiersRun.length === 0) {
    throw new Error('A VerificationProof must record at least one verifier run.');
  }
  if (input.residualFindings > 0) {
    throw new Error(
      'A proof reporting residual findings cannot certify SANITIZED ' +
        '(SEC-BOUND-001 V-10 / V-11).',
    );
  }
  // The single deliberate cast in this module.
  return Object.freeze({
    verifiersRun: Object.freeze([...input.verifiersRun]),
    regionsChecked: input.regionsChecked,
    residualFindings: input.residualFindings,
  }) as unknown as VerificationProof;
}
