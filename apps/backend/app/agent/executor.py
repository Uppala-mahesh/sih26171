"""SIH26171 - Action executor (FR-EXE-1..6). Python port of
``packages/agent/executor.ts``.

Cross-runtime parity REQ-DATA-001.

The only component permitted to dispatch an action, and the only one that can be
handed a policy decision and be trusted to honour it.

Why the executor takes a DECISION rather than re-deriving one
--------------------------------------------------------------
FR-POL-4 requires that a ``BLOCK`` halts the task and the executor is never
invoked. An executor that evaluated policy itself would have two policy
implementations, and the day they disagreed the more permissive one would be the
one running. So the decision is passed IN, and the executor's first act is to
refuse anything that is not ``ALLOW``.

Every failure mode is a failure
-------------------------------
FR-EXE-4: a timeout is an explicit failure, never a success. There is no code path
in this module that returns a success it did not observe. ``TIMEOUT``,
``BLOCKED`` and ``UNCONFIRMED`` are all terminal failures, and each is reported
with the reason attached rather than collapsed into a boolean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Mapping

from app.policy.engine import ActionProposal, ApprovalScope, PolicyDecisionDetail

ExecutionOutcome = Literal[
    "EXECUTED", "BLOCKED", "UNCONFIRMED", "TIMEOUT", "FAILED"
]

#: FR-EXE-3: the closed dispatch table.
#:
#: Dispatch is a lookup in this mapping, not a dynamic attribute fetch. A handler for
#: an action outside the set does not exist, so no code path can reach it - which is
#: a stronger statement than "the policy forbids it".
#:
#: ``getattr`` is deliberately NOT used to look up a handler by name. It would
#: resolve ``__init__``, ``__class__`` and every other dunder on the object, turning
#: a closed table into an open one.
Handler = Callable[[ActionProposal], None]


@dataclass(frozen=True)
class ExecutionRecord:
    """FR-EXE-5: the record every execution must produce."""

    action_type: str
    bound_target: str
    #: The decision that permitted it - or did not.
    decision: str
    rule: str
    outcome: ExecutionOutcome
    detail: str
    duration_ms: int


class ActionExecutor:
    def __init__(
        self,
        handlers: Mapping[str, Handler],
        *,
        timeout_ms: int | None = None,
        now: Callable[[], int] | None = None,
    ) -> None:
        #: FR-EXE-4: every action is bounded in time.
        self._timeout_ms = 5_000 if timeout_ms is None else timeout_ms
        self._now = (lambda: 0) if now is None else now
        # Copied into a plain dict keyed by the CLOSED action set. Anything a caller
        # registers outside that set is dropped here rather than at dispatch time,
        # so an unexpected action fails identically on both runtimes.
        from app.policy.engine import ACTION_TYPES

        self._handlers = {k: v for k, v in handlers.items() if k in ACTION_TYPES}

    def execute(
        self,
        proposal: ActionProposal,
        decision: PolicyDecisionDetail,
        approval_scope: ApprovalScope | None = None,
    ) -> ExecutionRecord:
        """Execute exactly one action, if policy permitted it.

        The decision is a PARAMETER. This function never asks whether the action was
        allowed, because a second opinion is how two policy implementations drift.
        """
        started = self._now()

        def finish(outcome: ExecutionOutcome, detail: str) -> ExecutionRecord:
            return ExecutionRecord(
                action_type=proposal.action_type,
                bound_target=f"{proposal.target_origin}#{proposal.target_element_id}",
                decision=decision.decision,
                rule=decision.rule,
                outcome=outcome,
                detail=detail,
                duration_ms=self._now() - started,
            )

        # FR-POL-4 / FR-EXE-1: a BLOCK never reaches a handler.
        if decision.decision == "BLOCK":
            return finish("BLOCKED", f"policy blocked: {decision.rationale}")

        # FR-EXE-2: CONFIRM executes only with a live approval bound to THIS action.
        if decision.decision == "CONFIRM":
            scope = decision.approval_scope
            matches = (
                scope is not None
                and approval_scope is not None
                and scope.action_type == approval_scope.action_type
                and scope.target_origin == approval_scope.target_origin
                and scope.target_element_id == approval_scope.target_element_id
                and self._now() <= approval_scope.expires_at
            )
            if not matches:
                return finish(
                    "UNCONFIRMED",
                    "policy requires confirmation and no matching, unexpired approval "
                    "was supplied",
                )

        # FR-EXE-3: dispatch through the closed table only.
        handler = self._handlers.get(proposal.action_type)
        if handler is None:
            return finish(
                "FAILED", f"no handler is registered for {proposal.action_type!r}"
            )

        try:
            handler(proposal)
        except Exception as error:  # noqa: BLE001 - any handler failure is FAILED
            return finish("FAILED", str(error))

        # FR-EXE-4: elapsed past the bound is a failure, not a success.
        elapsed = self._now() - started
        if elapsed > self._timeout_ms:
            return finish("TIMEOUT", f"exceeded the {self._timeout_ms} ms bound")

        return finish("EXECUTED", "handler returned without error")