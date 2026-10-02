"""SIH26171 - Action policy engine (FR-POL-1..8). Python port of
``packages/policy/engine.ts``.

Cross-runtime parity REQ-DATA-001. Two runtimes that enforce policy separately
drift apart silently, which is the same failure as the detector drift in audit
defect G-1, one layer up: the browser might permit an action the backend refuses,
or the reverse, and neither side would ever notice.

Every decision rule and every rationale string is ported verbatim. The rationales
are part of the audit trail, so paraphrasing them would be a silent change to what
a reviewer reads.

The rule that shapes the entire type surface
--------------------------------------------
**Policy is a function of structured facts only. Page content is not a policy
input, because ``ActionProposal`` has no field that could carry one.**

FR-POL-6, enforced structurally rather than by discipline. An earlier shape of
this design carried a ``page_instruction: str`` field "for logging". It was
removed: a field that exists can be read, and a string that can be read can be
pattern-matched by a rule, and a rule that reads page text is a channel the page
controls. SEC-THREAT-001 S7 (PI-7) is exactly that attack - a page telling the
agent to exfiltrate - so the capability to be misled is not given in the first
place.

If you find yourself wanting to add a free-text field here, the design is telling
you the decision does not belong in policy. In Python that freedom is LARGER, not
smaller: ``readonly`` in TypeScript is what stops you here, and Python has no
equivalent. This docstring is the only guard, which is precisely why it says all
of this at length.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal, Sequence

# Exactly one decision per proposal (FR-POL-1). Never a list.
PolicyDecision = Literal["ALLOW", "CONFIRM", "BLOCK"]

#: The closed set of actions the system may ever perform (FR-POL-3).
#:
#: A closed set rather than free strings, so an action the system cannot perform
#: cannot be named in a policy at all. A string allowlist invites a typo that
#: silently permits something.
ACTION_TYPES: tuple[str, ...] = (
    "OBSERVE",
    "READ_TEXT",
    "FILL_FORM",
    "CLICK",
    "DETOKENIZE",
    "TRANSMIT",
)

APPROVAL_TTL_MS = 60_000


def is_known_action(value: str) -> bool:
    """FR-POL-3: the action must exist in the closed set."""
    return value in ACTION_TYPES


@dataclass(frozen=True)
class ActionProposal:
    """A proposed action, in structured terms.

    Note what is ABSENT: no page text, no element innerText, no page-controlled
    aria value. Everything here is either operator configuration or a fact the
    system derived itself.
    """

    action_type: str
    target_origin: str
    target_element_id: str
    #: Would this change be undoable by the operator?
    irreversible: bool
    #: Would an outside party learn that it happened?
    externally_visible: bool
    payload_bytes: int
    #: For DETOKENIZE: the observation the value came from (B-6 binding).
    bound_observation_id: str | None = None


@dataclass(frozen=True)
class PolicyRule:
    action_type: str
    origins: tuple[str, ...]
    #: Actions here require human confirmation regardless of other rules.
    require_confirmation: bool | None = None


@dataclass(frozen=True)
class ApprovalScope:
    action_type: str
    target_origin: str
    target_element_id: str
    issued_at: int
    #: Approvals expire; an old one is not a current one.
    expires_at: int


class PolicyEngine:
    """Decides exactly one verdict for exactly one proposal (FR-POL-1)."""

    def __init__(
        self,
        rules: Sequence[PolicyRule] = (),
        *,
        max_payload_bytes: int | None = None,
        now: Callable[[], int] | None = None,
    ) -> None:
        """An EMPTY rule set permits nothing, which is the required default
        (FR-POL-2)."""
        self._rules = tuple(rules)
        self._max_payload_bytes = 64 * 1024 if max_payload_bytes is None else max_payload_bytes
        self._now = (lambda: 0) if now is None else now

    def evaluate(
        self, proposal: ActionProposal, approval: Approval | None = None
    ) -> PolicyDecisionDetail:
        """Order is deliberate: the cheapest and most decisive denials run first, so
        a proposal blocked for three independent reasons reports the most
        fundamental one rather than whichever happened to be checked first."""
        # 1. The action must exist in the closed set (FR-POL-3).
        if not is_known_action(proposal.action_type):
            return PolicyDecisionDetail(
                decision="BLOCK",
                rule="closed-action-set",
                rationale=(
                    f"action type {proposal.action_type!r} is not in the declared "
                    "action set; actions outside it are unreachable, not merely "
                    "unpermitted"
                ),
            )
        action_type = proposal.action_type

        # 2. Origin must be operator-permitted (FR-POL-5).
        rule = next((r for r in self._rules if r.action_type == action_type), None)
        if rule is None:
            return PolicyDecisionDetail(
                decision="BLOCK",
                rule="deny-by-default",
                rationale=(
                    f"no rule permits {action_type}; absent an explicit permitting "
                    "rule, no action executes (FR-POL-2)"
                ),
            )
        if proposal.target_origin not in rule.origins:
            return PolicyDecisionDetail(
                decision="BLOCK",
                rule="origin-not-permitted",
                rationale=(
                    f"origin {proposal.target_origin} is not in the permitted set "
                    f"for {action_type}"
                ),
            )

        # 3. Payload ceiling.
        if proposal.payload_bytes > self._max_payload_bytes:
            return PolicyDecisionDetail(
                decision="BLOCK",
                rule="payload-ceiling",
                rationale=(
                    f"payload of {proposal.payload_bytes} bytes exceeds the "
                    f"{self._max_payload_bytes} byte ceiling"
                ),
            )

        # 4. Detokenization must carry a B-6 binding.
        if action_type == "DETOKENIZE" and not proposal.bound_observation_id:
            return PolicyDecisionDetail(
                decision="BLOCK",
                rule="no-binding",
                rationale=(
                    "detokenization without an observation binding would defeat the "
                    "B-6 target restriction"
                ),
            )

        # 5. Irreversible or externally visible actions need a live, scoped human
        #    approval (FR-POL-3).
        needs_confirmation = (
            rule.require_confirmation is True
            or proposal.irreversible
            or proposal.externally_visible
        )

        if needs_confirmation:
            if approval is None or approval.granted_by != "operator":
                return PolicyDecisionDetail(
                    decision="CONFIRM",
                    rule="human-confirmation-required",
                    rationale=(
                        "irreversible or externally-visible actions require explicit "
                        "operator confirmation"
                    ),
                    approval_scope=self._scope_for(proposal),
                )
            if not self._approval_matches(approval, proposal):
                return PolicyDecisionDetail(
                    decision="CONFIRM",
                    rule="approval-out-of-scope",
                    rationale=(
                        "the supplied approval is bound to a different action, target "
                        "or origin, or has expired"
                    ),
                    approval_scope=self._scope_for(proposal),
                )

        return PolicyDecisionDetail(
            decision="ALLOW",
            rule="permitted",
            rationale=f"{action_type} on {proposal.target_origin} is permitted by rule",
        )

    def _scope_for(self, proposal: ActionProposal) -> ApprovalScope:
        issued_at = self._now()
        return ApprovalScope(
            action_type=proposal.action_type,
            target_origin=proposal.target_origin,
            target_element_id=proposal.target_element_id,
            issued_at=issued_at,
            expires_at=issued_at + APPROVAL_TTL_MS,
        )

    def _approval_matches(self, approval: Approval, proposal: ActionProposal) -> bool:
        """An approval is valid only for the exact triple it was granted for, and
        only while unexpired. Anything looser turns a confirmation into a standing
        permission."""
        s = approval.scope
        return (
            s.action_type == proposal.action_type
            and s.target_origin == proposal.target_origin
            and s.target_element_id == proposal.target_element_id
            and self._now() <= s.expires_at
        )
    #: Approvals expire; an old one is not a current one.
    expires_at: int


@dataclass(frozen=True)
class Approval:
    scope: ApprovalScope
    #: Set by the operator's UI, never by the page.
    granted_by: str = "operator"


@dataclass(frozen=True)
class PolicyDecisionDetail:
    decision: PolicyDecision
    rule: str
    rationale: str
    approval_scope: ApprovalScope | None = None