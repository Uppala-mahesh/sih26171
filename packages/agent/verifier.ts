/**
 * SIH26171 — Completion verifier (FR-VER-1…5).
 *
 * ── What this exists for ─────────────────────────────────────────────────────
 * v1's central failure was a reasoning model asserting a task was done. When the
 * vision pipeline quietly returned a 1×1 frame, the model still reported
 * success, and the success was believed (defects G-2, G-6).
 *
 * So completion here is never a claim. It is a **deterministic postcondition
 * check over fresh post-action perception**. The actor's own report is treated
 * as a hypothesis to be tested, not as evidence.
 *
 * ── The three properties that make it worth having ──────────────────────────
 *
 * 1. **FRESH (FR-VER-3).** The verifier refuses perception from before the
 *    action. An actor reporting "done" against a pre-action snapshot is
 *    reporting that nothing it did had the claimed effect — which is the whole
 *    bug. This is checkable, and it is the check v1 could not perform.
 *
 * 2. **DETERMINISTIC (FR-VER-2).** No model, no inference, no sampling. The same
 *    goal and the same perception always yield the same verdict. A verifier that
 *    can be talked into agreeing is not a verifier.
 *
 * 3. **POSITIVE-ONLY (FR-VER-5).** `COMPLETED` requires every declared
 *    postcondition to hold. Anything else terminates the task as failed, blocked
 *    or bounded out — never as a soft success.
 *
 * ── Why the checks are declared, not inferred ───────────────────────────────
 * A goal states its own postconditions. The verifier does not guess what "done"
 * means for an arbitrary task, because a guessed postcondition is a claim with
 * extra steps. A goal that declares nothing cannot complete, and saying so is
 * more useful than inventing a criterion.
 */

/** Terminal states. `COMPLETED` is reachable only through FR-VER-5. */
export type TaskOutcome = 'COMPLETED' | 'FAILED' | 'BLOCKED' | 'BOUNDED_OUT';

/**
 * A deterministic postcondition.
 *
 * Each variant is a total function over the perception snapshot. None of them
 * can consult the actor's own report — that field is not reachable from here.
 */
export type Postcondition =
  | { readonly kind: 'ELEMENT_PRESENT'; readonly role: string }
  | { readonly kind: 'NAME_ABSENT'; readonly name: string }
  | { readonly kind: 'TEXT_ABSENT'; readonly values: readonly string[] }
  | { readonly kind: 'REGIONS_OPAQUE'; readonly regions: readonly number[] }
  | { readonly kind: 'FRESH_AFTER'; readonly notBefore: number };

/** What the verifier is allowed to see. Note what is absent: no actor report. */
export interface PerceptionSnapshot {
  readonly observationId: string;
  readonly capturedAt: number;
  readonly title: string;
  readonly elements: ReadonlyArray<{
    readonly role: string;
    readonly ariaLabel: string;
    readonly sensitive: boolean;
  }>;
  readonly opaqueRegions: readonly number[];
  readonly text: string;
}

export interface TaskGoal {
  readonly id: string;
  readonly description: string;
  readonly postconditions: readonly Postcondition[];
}

export interface VerificationInput {
  readonly goal: TaskGoal;
  /** Perception captured AFTER the action. */
  readonly postAction: PerceptionSnapshot;
  /** The observation the ACTOR says it acted on. Freshness check only. */
  readonly claimedObservationId: string;
  readonly blocked?: boolean;
  readonly boundedOut?: boolean;
}

export interface CheckResult {
  readonly kind: Postcondition['kind'];
  readonly passed: boolean;
  readonly detail: string;
}

export interface VerificationResult {
  readonly outcome: TaskOutcome;
  readonly checks: readonly CheckResult[];
  /** False when the perception predates the action. See FR-VER-3. */
  readonly fresh: boolean;
  readonly reason: string;
}

function evaluateCheck(
  condition: Postcondition,
  view: PerceptionSnapshot,
): CheckResult {
  switch (condition.kind) {
    case 'ELEMENT_PRESENT': {
      const hit = view.elements.filter((e) => e.role === condition.role);
      const clean = hit.filter((e) => !e.sensitive);
      return {
        kind: condition.kind,
        passed: clean.length > 0,
        detail: clean.length
          ? `found ${clean.length} non-sensitive ${condition.role}`
          : hit.length
            ? `${condition.role} present but flagged sensitive`
            : `no ${condition.role} present`,
      };
    }
    case 'NAME_ABSENT': {
      const hit = view.elements.some((e) => e.ariaLabel === condition.name);
      return {
        kind: condition.kind,
        passed: !hit,
        detail: hit ? `an element with that name is still present` : 'absent',
      };
    }
    case 'TEXT_ABSENT': {
      // Compare on a PUNCTUATION-STRIPPED form of both sides.
      //
      // This normalisation is not cosmetic. A literal substring check was caught
      // by the benchmark reporting COMPLETED while the page still displayed
      // "4532 0151 1283 0366": the needle was the unspaced
      // "4532015112830366", the haystack carried separators, and the value
      // slipped through. A verifier defeated by a space is not a verifier.
      //
      // Matching MORE aggressively is the correct direction here. Erring toward
      // "value still present" costs a false failure; erring the other way costs
      // a disclosure. Whitespace, dashes and dots are stripped because PII is
      // routinely rendered with them.
      const strip = (s: string) => s.toLowerCase().replace(/[\s\-.]/g, '');
      const haystack = strip(`${view.title}\n${view.text}`);
      const present = condition.values.filter((v) => haystack.includes(strip(v)));
      return {
        kind: condition.kind,
        passed: present.length === 0,
        // Counts only. Naming a leaked value in a verification log would copy it
        // into a second place, which is the leak the check exists to prevent.
        detail:
          present.length === 0 ? 'all absent' : `${present.length} value(s) still present`,
      };
    }
    case 'REGIONS_OPAQUE': {
      const missing = condition.regions.filter((r) => !view.opaqueRegions.includes(r));
      return {
        kind: condition.kind,
        passed: missing.length === 0,
        detail: missing.length
          ? `${missing.length} region(s) not opaque`
          : 'all opaque',
      };
    }
    case 'FRESH_AFTER': {
      return {
        kind: condition.kind,
        passed: view.capturedAt >= condition.notBefore,
        detail: `captured ${view.capturedAt}, required >= ${condition.notBefore}`,
      };
    }
    default: {
      // Exhaustiveness guard. An unhandled postcondition kind is a programming
      // error; defaulting it to "passed" would turn that into a security error.
      const never: never = condition;
      throw new Error(`Unhandled postcondition: ${JSON.stringify(never)}`);
    }
  }
}

/**
 * Verify a claimed completion. Deterministic and model-independent (FR-VER-2).
 *
 * Order matters. A blocked or bounded task reports as such without running
 * checks, because there is nothing to verify. Staleness is checked BEFORE the
 * postconditions, because verifying against pre-action perception produces a
 * verdict about the wrong moment in time.
 */
export function verifyCompletion(input: VerificationInput): VerificationResult {
  if (input.blocked) {
    return {
      outcome: 'BLOCKED',
      checks: [],
      fresh: false,
      reason:
        'policy refused the action; nothing was executed, so nothing can be verified',
    };
  }
  if (input.boundedOut) {
    return {
      outcome: 'BOUNDED_OUT',
      checks: [],
      fresh: false,
      reason: 'execution bound elapsed; a timeout is a failure, never a success',
    };
  }

  // FR-VER-3. Comparing observation ids catches "I did the thing" reported
  // against the snapshot taken before the thing.
  const fresh = input.postAction.observationId !== input.claimedObservationId;
  if (!fresh) {
    return {
      outcome: 'FAILED',
      checks: [],
      fresh: false,
      reason:
        'post-action perception carries the same observation id the actor ' +
        'claimed to act on, so it predates the action. This is the v1 shape: a ' +
        'success claim verified against stale input.',
    };
  }

  if (input.goal.postconditions.length === 0) {
    // A goal stating no postcondition cannot be verified. Completing it would
    // mean inventing a criterion at verification time.
    return {
      outcome: 'FAILED',
      checks: [],
      fresh: true,
      reason: 'goal declares no postcondition, so completion is unprovable',
    };
  }

  const checks = input.goal.postconditions.map((c) => evaluateCheck(c, input.postAction));
  const failed = checks.filter((c) => !c.passed);

  // FR-VER-5: positive verification only.
  return {
    outcome: failed.length === 0 ? 'COMPLETED' : 'FAILED',
    checks,
    fresh: true,
    reason:
      failed.length === 0
        ? `all ${checks.length} postcondition(s) hold on fresh perception`
        : `${failed.length} of ${checks.length} postcondition(s) failed`,
  };
}

