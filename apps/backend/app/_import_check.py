"""Smoke check: the three newly-ported modules import and behave.

Run directly (``python apps/backend/app/_import_check.py``) so a broken port is
caught by import rather than discovered by whichever test happens to touch it
first.
"""

from __future__ import annotations

import os
import sys

# ``.../apps/backend/app/_import_check.py`` -> ``.../apps/backend``, which is the
# directory that must be on sys.path for ``app`` to be importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.executor import ActionExecutor  # noqa: E402
from app.agent.verifier import Element, PerceptionSnapshot, TaskGoal, VerificationInput, verify_completion  # noqa: E402
from app.policy.engine import ActionProposal, PolicyEngine, PolicyRule  # noqa: E402


def main() -> int:
    # Policy: empty rule set permits nothing (FR-POL-2).
    engine = PolicyEngine()
    detail = engine.evaluate(
        ActionProposal(
            action_type="OBSERVE",
            target_origin="https://example.test",
            target_element_id="n0",
            irreversible=False,
            externally_visible=False,
            payload_bytes=10,
        )
    )
    assert detail.decision == "BLOCK", detail
    assert detail.rule == "deny-by-default", detail

    # A permitted, non-destructive action is ALLOW.
    permitted = PolicyEngine([PolicyRule("OBSERVE", ("https://example.test",))])
    assert (
        permitted.evaluate(
            ActionProposal(
                action_type="OBSERVE",
                target_origin="https://example.test",
                target_element_id="n0",
                irreversible=False,
                externally_visible=False,
                payload_bytes=10,
            )
        ).decision
        == "ALLOW"
    )

    # Verifier: stale perception must not report COMPLETED (FR-VER-3).
    stale = verify_completion(
        VerificationInput(
            goal=TaskGoal(
                id="g",
                description="d",
                postconditions=({"kind": "TEXT_ABSENT", "values": ["4532 0151 1283 0366"]},),
            ),
            post_action=PerceptionSnapshot(
                observation_id="obs-1",
                captured_at=1,
                title="t",
                elements=(Element("button", "Submit", False),),
                opaque_regions=(),
                text="Card 4532-0151-1283-0366",
            ),
            claimed_observation_id="obs-1",
        )
    )
    assert stale.outcome == "FAILED" and not stale.fresh, stale

    # Same input, fresh perception, punctuation stripped: still present, so FAILED.
    fresh = verify_completion(
        VerificationInput(
            goal=TaskGoal(
                id="g",
                description="d",
                postconditions=({"kind": "TEXT_ABSENT", "values": ["4532015112830366"]},),
            ),
            post_action=PerceptionSnapshot(
                observation_id="obs-2",
                captured_at=2,
                title="t",
                elements=(Element("button", "Submit", False),),
                opaque_regions=(),
                text="Card 4532 0151 1283 0366",
            ),
            claimed_observation_id="obs-1",
        )
    )
    assert fresh.outcome == "FAILED", fresh

    # Executor: a BLOCK never reaches a handler.
    called = []
    record = ActionExecutor({"OBSERVE": lambda p: called.append(p)}).execute(
        ActionProposal(
            action_type="OBSERVE",
            target_origin="https://example.test",
            target_element_id="n0",
            irreversible=False,
            externally_visible=False,
            payload_bytes=10,
        ),
        detail,
    )
    assert record.outcome == "BLOCKED", record
    assert called == [], "a blocked action reached its handler"

    print("policy/verifier/executor ports import and behave correctly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())