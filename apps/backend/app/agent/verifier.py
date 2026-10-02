"""SIH26171 - Completion verifier (FR-VER-1..5). Python port of
``packages/agent/verifier.ts``.

Cross-runtime parity REQ-DATA-001.

What this exists for
--------------------
v1's central failure was a reasoning model asserting a task was done. When the
vision pipeline quietly returned a 1x1 frame, the model still reported success,
and the success was believed (defects G-2, G-6).

So completion here is never a claim. It is a **deterministic postcondition check
over fresh post-action perception**. The actor's own report is a hypothesis to be
tested, not evidence.

The three properties that make it worth having
---------------------------------------------
1. **FRESH (FR-VER-3).** The verifier refuses perception from before the action.
   An actor reporting "done" against a pre-action snapshot is reporting that
   nothing it did had the claimed effect - which is the whole bug.

2. **DETERMINISTIC (FR-VER-2).** No model, no inference, no sampling. The same
   goal and the same perception always yield the same verdict. A verifier that can
   be talked into agreeing is not a verifier.

3. **POSITIVE-ONLY (FR-VER-5).** ``COMPLETED`` requires every declared
   postcondition to hold. Anything else terminates the task as failed, blocked or
   bounded out - never as a soft success.

Why the checks are declared, not inferred
-----------------------------------------
A goal states its own postconditions. The verifier does not guess what "done" means
for an arbitrary task, because a guessed postcondition is a claim with extra
steps. A goal that declares nothing cannot complete, and saying so is more useful
than inventing a criterion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Sequence, TypedDict

#: Terminal states. ``COMPLETED`` is reachable only through FR-VER-5.
TaskOutcome = Literal["COMPLETED", "FAILED", "BLOCKED", "BOUNDED_OUT"]

#: Whitespace, dashes and dots, which PII is routinely rendered with.
_PUNCTUATION = re.compile(r"[\s\-.]")


@dataclass(frozen=True)
class Element:
    role: str
    aria_label: str
    sensitive: bool


@dataclass(frozen=True)
class PerceptionSnapshot:
    """What the verifier is allowed to see. Note what is absent: no actor report."""

    observation_id: str
    captured_at: int
    title: str
    elements: tuple[Element, ...]
    opaque_regions: tuple[int, ...]
    text: str


class _Postcondition(TypedDict, total=False):
    kind: str
    role: str
    name: str
    values: list[str]
    regions: list[int]
    notBefore: int


@dataclass(frozen=True)
class TaskGoal:
    id: str
    description: str
    postconditions: Sequence[_Postcondition]


@dataclass(frozen=True)
class VerificationInput:
    goal: TaskGoal
    #: Perception captured AFTER the action.
    post_action: PerceptionSnapshot
    #: The observation the ACTOR says it acted on. Freshness check only.
    claimed_observation_id: str
    blocked: bool = False
    bounded_out: bool = False


@dataclass(frozen=True)
class CheckResult:
    kind: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    outcome: TaskOutcome
    checks: tuple[CheckResult, ...]
    #: False when the perception predates the action. See FR-VER-3.
    fresh: bool
    reason: str


def _strip(s: str) -> str:
    """Punctuation-stripped, lowercased form used for every TEXT_ABSENT comparison.

    This normalisation is not cosmetic. A literal substring check was caught by the
    benchmark reporting COMPLETED while the page still displayed
    "4532 0151 1283 0366": the needle was the unspaced "4532015112830366", the
    haystack carried separators, and the value slipped through. A verifier
    defeated by a space is not a verifier.

    Matching MORE aggressively is the correct direction here. Erring toward "value
    still present" costs a false failure; erring the other way costs a disclosure.
    """
    return _PUNCTUATION.sub("", s.lower())


def evaluate_check(condition: _Postcondition, view: PerceptionSnapshot) -> CheckResult:
    """Each variant is a total function over the perception snapshot. None of them
    can consult the actor's own report - that field is not reachable from here."""
    kind = condition["kind"]

    if kind == "ELEMENT_PRESENT":
        role = condition["role"]
        hit = [e for e in view.elements if e.role == role]
        clean = [e for e in hit if not e.sensitive]
        if clean:
            detail = f"found {len(clean)} non-sensitive {role}"
        elif hit:
            detail = f"{role} present but flagged sensitive"
        else:
            detail = f"no {role} present"
        return CheckResult(kind=kind, passed=len(clean) > 0, detail=detail)

    if kind == "NAME_ABSENT":
        name = condition["name"]
        hit = any(e.aria_label == name for e in view.elements)
        return CheckResult(
            kind=kind,
            passed=not hit,
            detail="an element with that name is still present" if hit else "absent",
        )

    if kind == "TEXT_ABSENT":
        haystack = _strip(f"{view.title}\n{view.text}")
        present = [v for v in condition["values"] if _strip(v) in haystack]
        return CheckResult(
            kind=kind,
            passed=len(present) == 0,
            # Counts only. Naming a leaked value in a verification log would copy it
            # into a second place, which is the leak the check exists to prevent.
            detail=(
                "all absent" if not present else f"{len(present)} value(s) still present"
            ),
        )

    if kind == "REGIONS_OPAQUE":
        missing = [r for r in condition["regions"] if r not in view.opaque_regions]
        return CheckResult(
            kind=kind,
            passed=len(missing) == 0,
            detail=(f"{len(missing)} region(s) not opaque" if missing else "all opaque"),
        )

    if kind == "FRESH_AFTER":
        not_before = condition["notBefore"]
        return CheckResult(
            kind=kind,
            passed=view.captured_at >= not_before,
            detail=f"captured {view.captured_at}, required >= {not_before}",
        )

    # An unhandled postcondition kind is a PROGRAMMING error. Defaulting it to
    # "passed" would turn that into a SECURITY error, so it is raised instead.
    raise ValueError(f"Unhandled postcondition: {condition!r}")


def verify_completion(verification_input: VerificationInput) -> VerificationResult:
    """Verify a claimed completion. Deterministic and model-independent (FR-VER-2).

    Order matters. A blocked or bounded task reports as such without running
    checks, because there is nothing to verify. Staleness is checked BEFORE the
    postconditions, because verifying against pre-action perception produces a
    verdict about the wrong moment in time.
    """
    if verification_input.blocked:
        return VerificationResult(
            outcome="BLOCKED",
            checks=(),
            fresh=False,
            reason=(
                "policy refused the action; nothing was executed, so nothing can be "
                "verified"
            ),
        )
    if verification_input.bounded_out:
        return VerificationResult(
            outcome="BOUNDED_OUT",
            checks=(),
            fresh=False,
            reason="execution bound elapsed; a timeout is a failure, never a success",
        )

    # FR-VER-3. Comparing observation ids catches "I did the thing" reported against
    # the snapshot taken before the thing.
    fresh = verification_input.post_action.observation_id != (
        verification_input.claimed_observation_id
    )
    if not fresh:
        return VerificationResult(
            outcome="FAILED",
            checks=(),
            fresh=False,
            reason=(
                "post-action perception carries the same observation id the actor "
                "claimed to act on, so it predates the action. This is the v1 shape: "
                "a success claim verified against stale input."
            ),
        )

    if len(verification_input.goal.postconditions) == 0:
        # A goal stating no postcondition cannot be verified. Completing it would
        # mean inventing a criterion at verification time.
        return VerificationResult(
            outcome="FAILED",
            checks=(),
            fresh=True,
            reason="goal declares no postcondition, so completion is unprovable",
        )

    checks = tuple(
        evaluate_check(c, verification_input.post_action)
        for c in verification_input.goal.postconditions
    )
    failed = [c for c in checks if not c.passed]

    # FR-VER-5: positive verification only.
    return VerificationResult(
        outcome="COMPLETED" if not failed else "FAILED",
        checks=checks,
        fresh=True,
        reason=(
            f"all {len(checks)} postcondition(s) hold on fresh perception"
            if not failed
            else f"{len(failed)} of {len(checks)} postcondition(s) failed"
        ),
    )