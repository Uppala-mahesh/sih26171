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


# ── the exhaustive policy matrix ─────────────────────────────────────────────
# "Can any combination of facts talk the engine into a forbidden action?" is the
# most consequential question in the system, and ~12 hand-written cases answered
# it. The evidence matrix exists because every BRANCH had a test and no
# COMBINATION did; the same blind spot applies here with worse consequences.

POLICY_MATRIX_RUNNER = ROOT / "tests" / "parity" / "run-policy-matrix.cjs"
NOW_M = 1_000
CEILING = 100
ORIGIN = "https://app.test"
ELEMENT = "btn-1"
VALID_ACTIONS = ["OBSERVE", "DETOKENIZE", "TRANSMIT", "NOT_AN_ACTION"]
APPROVAL_QUALITIES = ["none", "matching", "wrong-target", "wrong-origin", "expired"]


def _matrix_approval(quality: str) -> Approval | None:
    if quality == "none":
        return None
    return Approval(
        scope=ApprovalScope(
            action_type="TRANSMIT",
            target_origin="https://evil.test" if quality == "wrong-origin" else ORIGIN,
            target_element_id="btn-OTHER" if quality == "wrong-target" else ELEMENT,
            issued_at=900,
            expires_at=950 if quality == "expired" else 90_000,
        )
    )


def _python_matrix() -> list[tuple[str, str, bool]]:
    """The same cells through the Python port, for a cross-runtime comparison."""
    out: list[tuple[str, str, bool]] = []
    for action_type in VALID_ACTIONS:
        for rule_present in (True, False):
            for origin_ok in (True, False):
                for payload_over in (False, True):
                    for binding in (True, False):
                        for irreversible in (False, True):
                            for external in (False, True):
                                for approval in APPROVAL_QUALITIES:
                                    rules = (
                                        [
                                            PolicyRule(action_type=t, origins=(ORIGIN,))
                                            for t in ACTION_TYPES
                                        ]
                                        if rule_present
                                        else []
                                    )
                                    engine = PolicyEngine(
                                        rules,
                                        max_payload_bytes=CEILING,
                                        now=lambda: NOW_M,
                                    )
                                    d = engine.evaluate(
                                        ActionProposal(
                                            action_type=action_type,
                                            target_origin=(
                                                ORIGIN if origin_ok else "https://elsewhere.test"
                                            ),
                                            target_element_id=ELEMENT,
                                            irreversible=irreversible,
                                            externally_visible=external,
                                            payload_bytes=CEILING + 1 if payload_over else 10,
                                            bound_observation_id="obs-1" if binding else None,
                                        ),
                                        _matrix_approval(approval),
                                    )
                                    out.append(
                                        (d.decision, d.rule, d.approval_scope is not None)
                                    )
    return out


@pytest.fixture(scope="module")
def policy_matrix() -> dict:
    if not ENGINE_JS.exists():
        pytest.skip("dist/ not built; run: npm run build:parity")
    proc = subprocess.run(
        ["node", str(POLICY_MATRIX_RUNNER)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if proc.returncode != 0:
        raise AssertionError(f"policy matrix runner failed: {proc.stderr}")
    return json.loads(proc.stdout)


def _label(c: dict) -> str:
    return (
        f"action={c['actionType']} rule={c['rulePresent']} originOk={c['originOk']} "
        f"over={c['payloadOver']} binding={c['binding']} "
        f"irrev={c['irreversible']} external={c['external']} approval={c['approval']}"
    )


def test_no_combination_of_facts_can_turn_a_refusal_into_a_permission(
    policy_matrix: dict,
) -> None:
    """The security invariants, stated as properties rather than per-cell values.

    A per-cell table can be edited to match whatever the code does. These cannot:
    each is a property that must hold for EVERY cell, so a future change has to
    break a rule in plain English rather than a row.
    """
    cells = policy_matrix["cells"]
    assert cells, "the matrix runner produced no cells"

    for c in cells:
        label = _label(c)
        d, rule = c["decision"], c["rule"]

        # 1. Only three outcomes exist, and one is never anything else.
        assert d in {"ALLOW", "CONFIRM", "BLOCK"}, f"{label}: unknown decision {d}"

        # 2. Every hard refusal is unconditional. None of these has an "unless".
        if c["actionType"] not in ACTION_TYPES:
            assert d == "BLOCK" and rule == "closed-action-set", (
                f"{label}: an action outside the closed set was not blocked"
            )
        if not c["rulePresent"]:
            assert d == "BLOCK", f"{label}: no rule, yet the decision was {d}"
        if not c["originOk"]:
            assert d == "BLOCK", f"{label}: unpermitted origin, yet the decision was {d}"
        if c["payloadOver"]:
            assert d == "BLOCK", f"{label}: over the ceiling, yet the decision was {d}"
        if c["actionType"] == "DETOKENIZE" and not c["binding"] and c["rulePresent"] and c["originOk"] and not c["payloadOver"]:
            assert d == "BLOCK" and rule == "no-binding", (
                f"{label}: detokenize without a B-6 binding was not blocked"
            )

        # 3. An irreversible or externally-visible action is NEVER allowed on an
        #    approval that is absent, bound elsewhere, or expired. This is the
        #    property that stops a confirmation becoming a standing permission.
        if c["irreversible"] or c["external"]:
            if c["approval"] in {"none", "wrong-target", "wrong-origin", "expired"}:
                if d == "ALLOW":
                    raise AssertionError(
                        f"{label}: irreversible/external action ALLOWED on a "
                        f"{c['approval']} approval"
                    )

        # 4. A confirmation always carries a scope; anything else never does.
        if d == "CONFIRM":
            assert c["scopeBound"], f"{label}: CONFIRM without an approval scope"
        else:
            assert not c["scopeBound"], f"{label}: {d} carried an approval scope"


def test_every_policy_branch_is_reachable(policy_matrix: dict) -> None:
    """A branch no cell reaches is a branch nobody has verified.

    An earlier version of this matrix permitted only OBSERVE, so DETOKENIZE always
    died at deny-by-default and the B-6 binding requirement - a security branch -
    was never executed. The matrix looked comprehensive and was not.
    """
    produced = {(c["decision"], c["rule"]) for c in policy_matrix["cells"]}
    expected = {
        ("BLOCK", "closed-action-set"),
        ("BLOCK", "deny-by-default"),
        ("BLOCK", "origin-not-permitted"),
        ("BLOCK", "payload-ceiling"),
        ("BLOCK", "no-binding"),
        ("CONFIRM", "human-confirmation-required"),
        ("CONFIRM", "approval-out-of-scope"),
        ("ALLOW", "permitted"),
    }
    assert produced == expected, (
        "the matrix does not exercise every branch; "
        f"missing {sorted(expected - produced)}, unexpected {sorted(produced - expected)}"
    )


def test_the_matrix_reached_every_cell(policy_matrix: dict) -> None:
    """4 actions x 2 rule x 2 origin x 2 payload x 2 binding x 2 irrev x 2 external
    x 5 approval = 1280. Asserted so a runner that skips a combination cannot pass
    while every invariant above stays green."""
    assert policy_matrix["cellCount"] == 1280, policy_matrix["cellCount"]
    assert len(policy_matrix["cells"]) == 1280


def test_both_runtimes_agree_on_every_matrix_cell(policy_matrix: dict) -> None:
    """Parity at matrix scale, not just on hand-picked cases.

    1280 cells is where a divergence stops being a curiosity. A policy engine that
    permits in Node and refuses in Python is a confused deputy wearing two
    uniforms - the same shape as the audit's detector drift, one layer up.
    """
    js = [(c["decision"], c["rule"], c["scopeBound"]) for c in policy_matrix["cells"]]
    py = _python_matrix()
    assert len(js) == len(py), f"cell counts differ: {len(js)} vs {len(py)}"

    divergences = [
        (_label(c), js[i], py[i])
        for i, c in enumerate(policy_matrix["cells"])
        if js[i] != py[i]
    ]
    assert not divergences, (
        f"{len(divergences)} cells diverge between runtimes; first: {divergences[0]}"
    )


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