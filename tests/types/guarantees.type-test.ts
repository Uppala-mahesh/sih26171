/**
 * COMPILE-TIME NEGATIVE TESTS — the type guarantees, verified.
 *
 * A type definition that merely compiles proves nothing. What matters is
 * whether it REJECTS the code it claims to reject. These tests close that gap.
 *
 * `@ts-expect-error` succeeds only if the following line genuinely fails to
 * typecheck. If someone later weakens a guarantee the directive becomes UNUSED
 * and tsc reports an error — so the guarantee verifies itself and cannot be
 * removed without breaking the build.
 *
 * Run with:  npm run typecheck
 *
 * ── A correction made because these tests failed the first time ─────────────
 * An earlier draft claimed DP-7 was "enforced by the type system". It is not.
 * `assertLegalTransition('NOT_INSTRUMENTED','SANITIZED')` typechecks fine,
 * because both arguments are valid state names; the rejection happens at
 * RUNTIME. What the type system does guarantee is that the illegal edges are
 * ABSENT from the transition table — the positions do not exist to index.
 * The runtime rejection is tested separately in the Python contract tests.
 */

import {
  assertContractsAreSound,
  elementRef,
  type ElementRef,
  type SafeElementDescriptor,
} from '../../packages/contracts/payloads';
import {
  LEGAL_TRANSITIONS,
  verificationProof,
  type SanitizationEvidence,
  type VerificationProof,
} from '../../packages/contracts/sanitization';

// ─────────────────────────────────────────────────────────────────────────────
// POSITIVE CONTROL — the legitimate path must work
// ─────────────────────────────────────────────────────────────────────────────

const legitProof: VerificationProof = verificationProof({
  verifiersRun: ['pixel_rescan', 'placeholder_audit'],
  regionsChecked: 3,
  residualFindings: 0,
});

const legitRef: ElementRef = elementRef({
  observationId: 'obs-1',
  elementId: 'el-1',
  origin: 'https://example.test',
});

const legitimate: SanitizationEvidence = {
  state: 'SANITIZED',
  proof: legitProof,
  rung: 'wasm-simd',
  declaredAt: 0,
};

// ─────────────────────────────────────────────────────────────────────────────
// DP-6 — a state cannot exist without its evidence
// ─────────────────────────────────────────────────────────────────────────────

// @ts-expect-error SANITIZED requires a proof. This is the v1 defect: an is_sanitized flag with nothing behind it.
const noProof: SanitizationEvidence = { state: 'SANITIZED', rung: 'wasm', declaredAt: 0 };

// @ts-expect-error DEGRADED requires a declared reason. Silent degradation is the v1 failure mode.
const silentDegradation: SanitizationEvidence = { state: 'DEGRADED', rung: 'wasm', declaredAt: 0 };

// @ts-expect-error NOT_INSTRUMENTED must name the missing check. A generic failure is not a declaration.
const vagueFailure: SanitizationEvidence = { state: 'NOT_INSTRUMENTED', declaredAt: 0 };

// @ts-expect-error UNCERTAIN must list the unresolved entity types.
const vagueUncertainty: SanitizationEvidence = { state: 'UNCERTAIN', declaredAt: 0 };

// @ts-expect-error The proof is branded. Producers cannot forge one; only Reinspector may (S-2).
const forgedProof: SanitizationEvidence = { state: 'SANITIZED', rung: 'wasm', declaredAt: 0, proof: { verifiersRun: ['pixel_rescan'], regionsChecked: 1, residualFindings: 0 } };

// ─────────────────────────────────────────────────────────────────────────────
// DP-7 — the illegal upgrade edges do not exist in the table
// ─────────────────────────────────────────────────────────────────────────────

// @ts-expect-error NOT_INSTRUMENTED has no successor, so the upgrade edge cannot even be indexed.
const illegalEdge = LEGAL_TRANSITIONS.NOT_INSTRUMENTED[0];

// @ts-expect-error The only legal successor of DEGRADED is NOT_INSTRUMENTED.
const wrongSuccessor: 'SANITIZED' = LEGAL_TRANSITIONS.DEGRADED[0];

// ─────────────────────────────────────────────────────────────────────────────
// DP-5 — outbound types cannot carry raw or vault data
// ─────────────────────────────────────────────────────────────────────────────

/**
 * `OutboundTypesAreRawFree` resolves to `true` only while no outbound type
 * carries a RawSensitive field. If someone adds one, this directive becomes
 * unused and the build fails.
 */
// @ts-expect-error Outbound contracts are raw-free; this assertion must fail.
assertContractsAreSound(false);

// @ts-expect-error The element brand cannot be synthesised from outside the module.
const fakeRef: ElementRef = { observationId: 'o', elementId: 'e', origin: 'x' };

// @ts-expect-error The UI role taxonomy is closed. STEPPER is not a declared role.
const inventedRole: SafeElementDescriptor['role'] = 'STEPPER';

export const CASES = {
  legitProof,
  legitRef,
  legitimate,
  noProof,
  silentDegradation,
  vagueFailure,
  vagueUncertainty,
  forgedProof,
  illegalEdge,
  wrongSuccessor,
  fakeRef,
  inventedRole,
} as const;
