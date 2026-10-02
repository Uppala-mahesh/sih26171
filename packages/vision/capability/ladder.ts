/**
 * SIH26171 — Vision capability ladder.
 *
 * Implements FR-CAP-1..FR-CAP-4 and FR-CAP-7, and verification V-5.
 * Governed by SEC-BOUND-001 section 13.4, which records this as the last
 * unbuilt piece of the honesty story.
 *
 * WHY THIS EXISTS
 * ---------------
 * Degradation only ever happens on the vision path, so until the system can
 * report WHICH rung it is running on, it cannot declare degradation truthfully
 * for the part that actually degrades. Charter gate C-5 requires a degraded
 * subsystem to DECLARE itself. This module is that declaration's source.
 *
 * WHY PROBES ARE INJECTED
 * -----------------------
 * Probing `navigator.gpu` requires a browser, so a ladder that probes
 * internally could only be tested in a browser - and would therefore be
 * untested in CI. Inverting the dependency (the caller supplies probes) makes
 * every branch, including total unavailability, reachable from a unit test.
 *
 * THE RULE THAT MATTERS (FR-CAP-4)
 * --------------------------------
 * No failure path may ever produce an artefact asserting SANITIZED. The ladder
 * therefore cannot return "unavailable" without also returning a reason, and
 * `declaration()` is the only way a caller learns its rung — so the rung and
 * the declaration cannot drift apart.
 */

export const CAPABILITY_LADDER = ['webgpu', 'wasm-simd', 'wasm', 'dom-only'] as const;

export type InferenceRung = (typeof CAPABILITY_LADDER)[number];

/** Rungs that require an actual probe. `dom-only` is the unconditional floor. */
export type ProbeableRung = Exclude<InferenceRung, 'dom-only'>;

export type DegradationReason =
  | 'vision_rung_unavailable'
  | 'ocr_failed'
  | 'classifier_unavailable'
  | 'frame_blind'
  | 'opaque_region'
  | 'detector_budget_exhausted';

export type ProbeOutcome =
  | { readonly available: true; readonly detail: string }
  | { readonly available: false; readonly reason: string };

export interface CapabilityProbe {
  readonly rung: ProbeableRung;
  probe(): Promise<ProbeOutcome>;
}

export interface LadderResult {
  /** The rung actually in use. Never null: `dom-only` is always available. */
  readonly active: InferenceRung;
  /** The best rung the host could offer. */
  readonly preferred: InferenceRung;
  readonly degraded: boolean;
  /** Non-null whenever degraded. FR-CAP-4: absence is never silent. */
  readonly degradationReason: DegradationReason | null;
  /** The specific probe failure behind the degradation, verbatim. */
  readonly degradationDetail: string | null;
  readonly outcomes: readonly (readonly [ProbeableRung, ProbeOutcome])[];
}

export class CapabilityResolver {
  readonly #probes: readonly CapabilityProbe[];
  readonly #preferred: InferenceRung;

  constructor(probes: readonly CapabilityProbe[], preferred: InferenceRung = 'webgpu') {
    this.#probes = probes;
    this.#preferred = preferred;
  }

  /**
   * Probe every rung in order and select the first available one.
   *
   * FR-CAP-7: callers are expected to cache the result rather than re-probe
   * per perception. This method is pure and side-effect free, so caching is the
   * caller's choice, not a hidden behaviour here.
   */
  async resolve(): Promise<LadderResult> {
    const outcomes: (readonly [ProbeableRung, ProbeOutcome])[] = [];
    let active: InferenceRung = 'dom-only';

    for (const rung of CAPABILITY_LADDER) {
      if (rung === 'dom-only') {
        // The unconditional floor: DOM perception always works.
        active = 'dom-only';
        break;
      }

      const probe = this.#probes.find((candidate) => candidate.rung === rung);
      // FR-CAP-2 / DA-6: a rung with no probe is UNAVAILABLE. Defaulting to
      // "available" would be a lie told on the host's behalf.
      //
      // A probe that THROWS is also unavailable. `requestAdapter()` rejects on
      // hosts without WebGPU, and several probes reject on policy grounds, so
      // an unhandled rejection here would take down the vision path instead of
      // stepping it down the ladder - the opposite of what FR-CAP-1 requires.
      let outcome: ProbeOutcome;
      if (probe === undefined) {
        outcome = { available: false, reason: 'no probe registered for this rung' };
      } else {
        try {
          outcome = await probe.probe();
        } catch (error) {
          outcome = {
            available: false,
            reason: `probe threw: ${error instanceof Error ? error.message : String(error)}`,
          };
        }
      }

      outcomes.push([rung, outcome]);
      if (outcome.available) {
        active = rung;
        break;
      }
    }

    const degraded = active !== this.#preferred;

    // FR-CAP-4: absence is never silent. A single reason covers every ladder
    // fallback - the cause is always "a rung was unavailable" - so the SPECIFIC
    // probe failure is carried separately in `degradationDetail` rather than
    // being squeezed into a generic enum member that would lose it.
    const firstFailure = outcomes.find(([, outcome]) => !outcome.available);
    const detail =
      firstFailure && !firstFailure[1].available ? firstFailure[1].reason : null;

    return {
      active,
      preferred: this.#preferred,
      degraded,
      degradationReason: degraded ? 'vision_rung_unavailable' : null,
      degradationDetail: degraded ? detail : null,
      outcomes,
    };
  }

  /**
   * The single supported way to learn the rung.
   *
   * Returning the declaration alongside the result is deliberate: a caller
   * cannot know the rung without also being handed the obligation to declare
   * degradation, which is what stops the two drifting apart.
   */
  async declaration(): Promise<{
    rung: InferenceRung;
    state: string;
    reason: DegradationReason | null;
    detail: string | null;
  }> {
    const result = await this.resolve();
    return {
      rung: result.active,
      // A ladder below preferred is always DEGRADED (FR-CAP-3, FR-CAP-4).
      state: result.degraded ? 'DEGRADED' : 'FULL_CAPABILITY',
      reason: result.degradationReason,
      detail: result.degradationDetail,
    };
  }
}
