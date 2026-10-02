/**
 * SIH26171 — Action policy engine (FR-POL-1…8).
 *
 * ── The rule that shapes the entire type surface ────────────────────────────
 * **Policy is a function of structured facts only. Page content is not a policy
 * input, because `ActionProposal` has no field that could carry one.**
 *
 * This is FR-POL-6, enforced structurally rather than by discipline. An earlier
 * shape of this design carried a `pageInstruction: string` field on the
 * proposal "for logging". It was removed: a field that exists can be read, and a
 * string that can be read can be pattern-matched by a rule, and a rule that
 * reads page text is a channel the page controls. SEC-THREAT-001 §7 (PI-7) is
 * exactly that attack — a page telling the agent to exfiltrate — so the
 * capability to be misled is not given to it in the first place.
 *
 * If you find yourself wanting to add a free-text field here, the design is
 * telling you the decision does not belong in policy.
 *
 * Implements FR-POL-1..FR-POL-8 and obligation A-4.
 */

/** Exactly one decision per proposal (FR-POL-1). Never a list. */
export type PolicyDecision = 'ALLOW' | 'CONFIRM' | 'BLOCK';

/**
 * The closed set of actions the system may ever perform (FR-POL-3).
 *
 * An enum rather than a string, so an action the system cannot perform cannot be
 * named in a policy at all. A string allowlist invites a typo that silently
 * permits something; a typo here is a compile error.
 */
export const ACTION_TYPES = [
  'OBSERVE',
  'READ_TEXT',
  'FILL_FORM',
  'CLICK',
  'DETOKENIZE',
  'TRANSMIT',
] as const;
export type ActionType = (typeof ACTION_TYPES)[number];

function isKnownAction(value: string): value is ActionType {
  return (ACTION_TYPES as readonly string[]).includes(value);
}

/**
 * A proposed action, in structured terms.
 *
 * Note what is ABSENT: no page text, no element innerText, no page-controlled
 * aria value. Everything here is either operator configuration or a fact the
 * system derived itself.
 */
export interface ActionProposal {
  readonly actionType: string;
  readonly targetOrigin: string;
  readonly targetElementId: string;
  /** Would this change be undoable by the operator? */
  readonly irreversible: boolean;
  /** Would an outside party learn that it happened? */
  readonly externallyVisible: boolean;
  readonly payloadBytes: number;
  /** For DETOKENIZE: the observation the value came from (B-6 binding). */
  readonly boundObservationId?: string;
}

export interface PolicyRule {
  readonly actionType: ActionType;
  readonly origins: readonly string[];
  /** Actions here require human confirmation regardless of other rules. */
  readonly requireConfirmation?: boolean;
}

export interface ApprovalScope {
  readonly actionType: string;
  readonly targetOrigin: string;
  readonly targetElementId: string;
  readonly issuedAt: number;
  /** Approvals expire; an old one is not a current one. */
  readonly expiresAt: number;
}

export interface Approval {
  readonly scope: ApprovalScope;
  /** Set by the operator's UI, never by the page. */
  readonly grantedBy: 'operator';
}

export interface PolicyDecisionDetail {
  readonly decision: PolicyDecision;
  readonly rule: string;
  readonly rationale: string;
  /**
   * Scope a human approval to exactly one action. An approval not bound to a
   * single (action, target, origin) triple is a standing permission, and a
   * standing permission is what an attacker wants (FR-POL-3).
   */
  readonly approvalScope?: ApprovalScope;
}

export class PolicyEngine {
  readonly #rules: readonly PolicyRule[];
  readonly #maxPayloadBytes: number;
  readonly #now: () => number;

  /**
   * @param rules permitted combinations. An EMPTY rule set permits nothing, which
   *   is the required default (FR-POL-2).
   */
  constructor(
    rules: readonly PolicyRule[] = [],
    options: { maxPayloadBytes?: number; now?: () => number } = {},
  ) {
    this.#rules = rules;
    this.#maxPayloadBytes = options.maxPayloadBytes ?? 64 * 1024;
    this.#now = options.now ?? (() => 0);
  }

  /**
   * Decide exactly one verdict for exactly one proposal (FR-POL-1).
   *
   * Order is deliberate: the cheapest and most decisive denials run first, so a
   * proposal blocked for three independent reasons reports the most fundamental
   * one rather than whichever happened to be checked first.
   */
  evaluate(proposal: ActionProposal, approval?: Approval): PolicyDecisionDetail {
    // 1. The action must exist in the closed set (FR-POL-3).
    if (!isKnownAction(proposal.actionType)) {
      return {
        decision: 'BLOCK',
        rule: 'closed-action-set',
        rationale:
          `action type ${JSON.stringify(proposal.actionType)} is not in the ` +
          `declared action set; actions outside it are unreachable, not merely ` +
          `unpermitted`,
      };
    }
    const actionType: ActionType = proposal.actionType;

    // 2. Origin must be operator-permitted (FR-POL-5).
    const rule = this.#rules.find((r) => r.actionType === actionType);
    if (!rule) {
      return {
        decision: 'BLOCK',
        rule: 'deny-by-default',
        rationale:
          `no rule permits ${actionType}; absent an explicit permitting rule, ` +
          `no action executes (FR-POL-2)`,
      };
    }
    if (!rule.origins.includes(proposal.targetOrigin)) {
      return {
        decision: 'BLOCK',
        rule: 'origin-not-permitted',
        rationale:
          `origin ${proposal.targetOrigin} is not in the permitted set for ` +
          `${actionType}`,
      };
    }

    // 3. Payload ceiling.
    if (proposal.payloadBytes > this.#maxPayloadBytes) {
      return {
        decision: 'BLOCK',
        rule: 'payload-ceiling',
        rationale:
          `payload of ${proposal.payloadBytes} bytes exceeds the ` +
          `${this.#maxPayloadBytes} byte ceiling`,
      };
    }

    // 4. Detokenization must carry a B-6 binding.
    if (actionType === 'DETOKENIZE' && !proposal.boundObservationId) {
      return {
        decision: 'BLOCK',
        rule: 'no-binding',
        rationale:
          'detokenization without an observation binding would defeat the B-6 ' +
          'target restriction',
      };
    }

    // 5. Irreversible or externally visible actions need a live, scoped human
    //    approval (FR-POL-3).
    const needsConfirmation =
      rule.requireConfirmation === true ||
      proposal.irreversible ||
      proposal.externallyVisible;

    if (needsConfirmation) {
      if (!approval || approval.grantedBy !== 'operator') {
        return {
          decision: 'CONFIRM',
          rule: 'human-confirmation-required',
          rationale:
            'irreversible or externally-visible actions require explicit ' +
            'operator confirmation',
          approvalScope: this.#scopeFor(proposal),
        };
      }
      if (!this.#approvalMatches(approval, proposal)) {
        return {
          decision: 'CONFIRM',
          rule: 'approval-out-of-scope',
          rationale:
            'the supplied approval is bound to a different action, target or ' +
            'origin, or has expired',
          approvalScope: this.#scopeFor(proposal),
        };
      }
    }

    return {
      decision: 'ALLOW',
      rule: 'permitted',
      rationale: `${actionType} on ${proposal.targetOrigin} is permitted by rule`,
    };
  }

  #scopeFor(proposal: ActionProposal): ApprovalScope {
    const issuedAt = this.#now();
    return Object.freeze({
      actionType: proposal.actionType,
      targetOrigin: proposal.targetOrigin,
      targetElementId: proposal.targetElementId,
      issuedAt,
      expiresAt: issuedAt + 60_000,
    });
  }

  /**
   * An approval is valid only for the exact triple it was granted for, and only
   * while unexpired. Anything looser turns a confirmation into a standing
   * permission.
   */
  #approvalMatches(approval: Approval, proposal: ActionProposal): boolean {
    const s = approval.scope;
    return (
      s.actionType === proposal.actionType &&
      s.targetOrigin === proposal.targetOrigin &&
      s.targetElementId === proposal.targetElementId &&
      this.#now() <= s.expiresAt
    );
  }
}
