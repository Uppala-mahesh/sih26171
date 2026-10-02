"""Cross-runtime parity for the ACTION PLANE (REQ-DATA-001 rules X-1..X-5).

Detection parity lives in test_parity.py. This covers the policy engine, the
completion verifier and the action executor, which were TypeScript-only until
``apps/backend/app/policy/engine.py``, ``agent/verifier.py`` and
``agent/executor.py`` were ported.

Why the action plane needs this as much as detection does
---------------------------------------------------------
The audit's worst defect (G-1) was two PII engines whose vocabularies silently
drifted: JavaScript detected Aadhaar, PAN, UPI, IFSC and OTP, Python detected
none of them. The same shape one layer up is a browser that PERMITS an action the
backend refuses. Nothing raises, no test fails, and the system quietly has two
different policies.

Two registries agreeing on paper proves nothing, so both runtimes execute the same
corpus (testdata/action_plane_corpus.json) and this compares the verdicts
decision-by-decision.

Compared: the decision, the rule that produced it, freshness, per-check pass/fail,
and whether a handler ran. NOT compared: property naming and rationale prose, which
are representation rather than behaviour - except that the rationales are ported
verbatim anyway, because they are the audit trail a human reads.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "testdata" / "action_plane_corpus.json"
RUNNER = ROOT / "tests" / "parity" / "run-action-plane.cjs"
ENGINE_JS = ROOT / "dist" / "packages" / "policy" / "engine.js"

sys.path.insert(0, str(ROOT / "apps" / "backend"))

from app.agent.executor import ActionExecutor  # noqa: E402
from app.agent.verifier import (  # noqa: E402
    Element,
    PerceptionSnapshot,
    TaskGoal,
    VerificationInput,
    verify_completion,
)
from app.policy.engine import (  # noqa: E402
    ACTION_TYPES,
    ActionProposal,
    Approval,
    ApprovalScope,
    PolicyEngine,
    PolicyRule,
)


@pytest.fixture(scope="module")
def corpus() -> dict:
    return json.loads(CORPUS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def node_results() -> dict:
    """The TypeScript runtimes' verdicts.

    Skipped, not failed, when dist/ is absent: a missing build is a setup problem,
    and reporting it as a parity failure would misdescribe it. `npm run build:parity`
    produces dist/.
    """
    if not ENGINE_JS.exists():
        pytest.skip("dist/ not built; run: npm run build:parity")
    proc = subprocess.run(
        ["node", str(RUNNER), str(CORPUS)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"node parity runner failed: {proc.stderr}")
    return json.loads(proc.stdout)
def _proposal(raw: dict) -> ActionProposal:
    return ActionProposal(
        action_type=raw["actionType"],
        target_origin=raw["targetOrigin"],
        target_element_id=raw["targetElementId"],
        irreversible=raw["irreversible"],
        externally_visible=raw["externallyVisible"],
        payload_bytes=raw["payloadBytes"],
        bound_observation_id=raw.get("boundObservationId"),
    )


def _approval(raw: dict | None) -> Approval | None:
    if raw is None:
        return None
    s = raw["scope"]
    return Approval(
        scope=ApprovalScope(
            action_type=s["actionType"],
            target_origin=s["targetOrigin"],
            target_element_id=s["targetElementId"],
            issued_at=s["issuedAt"],
            expires_at=s["expiresAt"],
        ),
        granted_by=raw.get("grantedBy", "operator"),
    )


def _scope(raw: dict | None) -> ApprovalScope | None:
    if raw is None:
        return None
    return ApprovalScope(
        action_type=raw["actionType"],
        target_origin=raw["targetOrigin"],
        target_element_id=raw["targetElementId"],
        issued_at=raw["issuedAt"],
        expires_at=raw["expiresAt"],
    )


def test_the_two_runtimes_agree_on_every_action_type(node_results: dict) -> None:
    assert list(ACTION_TYPES) == node_results["actionTypes"], (
        "the closed action set has drifted between runtimes; a new action that "
        "exists on one side only is an action one runtime can perform and the "
        "other has never heard of"
    )


def test_policy_decisions_match_across_runtimes(corpus: dict, node_results: dict) -> None:
    by_name = {r["name"]: r for r in node_results["policy"]}
    assert len(by_name) == len(corpus["policy"]), "the node runner skipped cases"

    for case in corpus["policy"]:
        rules = [
            PolicyRule(
                action_type=r["actionType"],
                origins=tuple(r["origins"]),
                require_confirmation=r.get("requireConfirmation"),
            )
            for r in case.get("rules", [])
        ]
        engine = PolicyEngine(
            rules,
            max_payload_bytes=case.get("maxPayloadBytes"),
            now=(lambda t=case.get("now", 0): t),
        )
        py = engine.evaluate(_proposal(case["proposal"]), _approval(case.get("approval")))
        js = by_name[case["name"]]
        assert (py.decision, py.rule, py.approval_scope is not None) == (
            js["decision"],
            js["rule"],
            js["scopeBound"],
        ), f"policy diverged on: {case['name']}"


def _snapshot(raw: dict) -> PerceptionSnapshot:
    return PerceptionSnapshot(
        observation_id=raw["observationId"],
        captured_at=raw["capturedAt"],
        title=raw["title"],
        elements=tuple(
            Element(e["role"], e["ariaLabel"], e["sensitive"]) for e in raw["elements"]
        ),
        opaque_regions=tuple(raw["opaqueRegions"]),
        text=raw["text"],
    )


def test_verification_outcomes_match_across_runtimes(corpus: dict, node_results: dict) -> None:
    by_name = {r["name"]: r for r in node_results["verify"]}
    assert len(by_name) == len(corpus["verify"]), "the node runner skipped cases"

    for case in corpus["verify"]:
        goal = TaskGoal(
            id=case["goal"]["id"],
            description=case["goal"]["description"],
            postconditions=tuple(case["goal"]["postconditions"]),
        )
        py = verify_completion(
            VerificationInput(
                goal=goal,
                post_action=_snapshot(case["postAction"]),
                claimed_observation_id=case["claimedObservationId"],
                blocked=case.get("blocked", False),
                bounded_out=case.get("boundedOut", False),
            )
        )
        js = by_name[case["name"]]
        assert (py.outcome, py.fresh, [c.passed for c in py.checks]) == (
            js["outcome"],
            js["fresh"],
            js["passed"],
        ), f"verification diverged on: {case['name']}"


def test_execution_outcomes_match_across_runtimes(corpus: dict, node_results: dict) -> None:
    from app.policy.engine import PolicyDecisionDetail

    by_name = {r["name"]: r for r in node_results["execute"]}
    assert len(by_name) == len(corpus["execute"]), "the node runner skipped cases"

    for case in corpus["execute"]:
        ran: list[str] = []
        handlers = {a: (lambda a=a: ran.append(a)) for a in ACTION_TYPES}
        clock = {"t": case.get("startNow", 0)}
        step = case.get("elapsedPerCall", 0)

        def now() -> int:
            value = clock["t"]
            clock["t"] += step
            return value

        executor = ActionExecutor(handlers, timeout_ms=case.get("timeoutMs"), now=now)
        d = case["decisionDetail"]
        py = executor.execute(
            _proposal(case["proposal"]),
            PolicyDecisionDetail(
                decision=d["decision"],
                rule=d["rule"],
                rationale=d["rationale"],
                approval_scope=_scope(d.get("approvalScope")),
            ),
            _scope(case.get("approvalScope")),
        )
        js = by_name[case["name"]]
        assert (py.outcome, py.decision, len(ran) > 0) == (
            js["outcome"],
            js["decision"],
            js["handlerRan"],
        ), f"execution diverged on: {case['name']}"