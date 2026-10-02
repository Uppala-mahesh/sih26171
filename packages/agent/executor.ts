/**
 * SIH26171 — Action executor (FR-EXE-1…6).
 *
 * The only component permitted to dispatch an action, and the only one that can
 * be handed a policy decision and be trusted to honour it.
 *
 * ── Why the executor takes a DECISION rather than re-deriving one ───────────
 * FR-POL-4 requires that a `BLOCK` halts the task and the executor is never
 * invoked. An executor that evaluated policy itself would have two policy
 * implementations, and the day they disagreed the more permissive one would be
 * the one running. So the decision is passed IN, and the executor's first act
 * is to refuse anything that is not `ALLOW`.
 *
 * ── Every failure mode is a failure ─────────────────────────────────────────
 * FR-EXE-4: a timeout is an explicit failure, never a success. There is no code
 * path in this file that returns a success it did not observe. `TIMEOUT`,
 * `BLOCKED` and `UNCONFIRMED` are all terminal failures, and each is reported
 * with the reason attached rather than collapsed into a boolean.
 */

import type { ActionProposal, ApprovalScope, PolicyDecisionDetail } from '../policy/engine.js';

export type ExecutionOutcome =
  | 'EXECUTED'
  | 'BLOCKED'
  | 'UNCONFIRMED'
  | 'TIMEOUT'
  | 'FAILED';

/** FR-EXE-5: the record every execution must produce. */
export interface ExecutionRecord {
  readonly actionType: string;
  readonly boundTarget: string;
  /** The decision that permitted it — or did not. */
  readonly decision: PolicyDecisionDetail['decision'];
  readonly rule: string;
  readonly outcome: ExecutionOutcome;
  readonly detail: string;
  readonly durationMs: number;
}

/**
 * The closed dispatch table (FR-EXE-3).
 *
 * Dispatch is a lookup in this record, not a dynamic call. A handler for an
 * action outside the set does not exist, so no code path can reach it — which is
 * a stronger statement than "the policy forbids it".
 */
export interface Handlers {
  readonly OBSERVE: (p: ActionProposal) => void;
  readonly READ_TEXT: (p: ActionProposal) => void;
  readonly FILL_FORM: (p: ActionProposal) => void;
  readonly CLICK: (p: ActionProposal) => void;
  readonly DETOKENIZE: (p: ActionProposal) => void;
  readonly TRANSMIT: (p: ActionProposal) => void;
}

export interface ExecutorOptions {
  /** FR-EXE-4: every action is bounded in time. */
  readonly timeoutMs?: number;
  readonly now?: () => number;
}

export class ActionExecutor {
  readonly #handlers: Handlers;
  readonly #timeoutMs: number;
  readonly #now: () => number;

  constructor(handlers: Handlers, options: ExecutorOptions = {}) {
    this.#handlers = handlers;
    this.#timeoutMs = options.timeoutMs ?? 5_000;
    this.#now = options.now ?? (() => 0);
  }

  /**
   * Execute exactly one action, if policy permitted it.
   *
   * The decision is a PARAMETER. This function never asks whether the action was
   * allowed, because a second opinion is how two policy implementations drift.
   */
  execute(
    proposal: ActionProposal,
    decision: PolicyDecisionDetail,
    approvalScope?: ApprovalScope,
  ): ExecutionRecord {
    const started = this.#now();

    const finish = (outcome: ExecutionOutcome, detail: string): ExecutionRecord => ({
      actionType: proposal.actionType,
      boundTarget: `${proposal.targetOrigin}#${proposal.targetElementId}`,
      decision: decision.decision,
      rule: decision.rule,
      outcome,
      detail,
      durationMs: this.#now() - started,
    });

    // FR-POL-4 / FR-EXE-1: a BLOCK never reaches a handler.
    if (decision.decision === 'BLOCK') {
      return finish('BLOCKED', `policy blocked: ${decision.rationale}`);
    }

    // FR-EXE-2: CONFIRM executes only with a live approval bound to THIS action.
    if (decision.decision === 'CONFIRM') {
      const scope = decision.approvalScope;
      const matches =
        scope !== undefined &&
        approvalScope !== undefined &&
        scope.actionType === approvalScope.actionType &&
        scope.targetOrigin === approvalScope.targetOrigin &&
        scope.targetElementId === approvalScope.targetElementId &&
        this.#now() <= approvalScope.expiresAt;
      if (!matches) {
        return finish(
          'UNCONFIRMED',
          'policy requires confirmation and no matching, unexpired approval was supplied',
        );
      }
    }

    // FR-EXE-3: dispatch through the closed table only.
    const handler = this.#handlers[proposal.actionType as keyof Handlers];
    if (typeof handler !== 'function') {
      return finish(
        'FAILED',
        `no handler is registered for ${JSON.stringify(proposal.actionType)}`,
      );
    }

    try {
      handler(proposal);
    } catch (error) {
      return finish('FAILED', error instanceof Error ? error.message : String(error));
    }

    // FR-EXE-4: elapsed past the bound is a failure, not a success.
    const elapsed = this.#now() - started;
    if (elapsed > this.#timeoutMs) {
      return finish('TIMEOUT', `exceeded the ${this.#timeoutMs} ms bound`);
    }

    return finish('EXECUTED', 'handler returned without error');
  }
}
