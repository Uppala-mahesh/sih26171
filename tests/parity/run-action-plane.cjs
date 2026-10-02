/**
 * Cross-runtime parity runner for the ACTION PLANE (Node side).
 *
 * Runs the COMPILED TypeScript policy engine, completion verifier and action
 * executor over the shared corpus, and writes the verdicts as JSON on stdout.
 *
 * tests/contract/test_policy_parity.py runs the Python ports over the SAME corpus
 * and compares decision-by-decision. REQ-DATA-001 rule X-4: divergence fails the
 * build.
 *
 * Why the action plane needs parity as much as detection does: a browser that
 * permits an action the backend refuses - or the reverse - is a confused deputy
 * wearing two uniforms, and neither side raises an error when it happens. The
 * detector drift in audit defect G-1 was the same shape, one layer down.
 *
 * Comparison keys are the DECISION, the RULE that produced it, and whether a
 * handler ran. Property naming and rationale prose are excluded so the test
 * compares behaviour rather than representation.
 *
 * Usage:  node tests/parity/run-action-plane.cjs <corpus.json>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { PolicyEngine, ACTION_TYPES } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'policy', 'engine.js'),
);
const { verifyCompletion } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'agent', 'verifier.js'),
);
const { ActionExecutor } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'agent', 'executor.js'),
);

const corpusPath = process.argv[2];
if (!corpusPath) {
  process.stderr.write('usage: run-action-plane.cjs <corpus.json>\n');
  process.exit(2);
}
const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));

const policyResults = corpus.policy.map((c) => {
  const rules = (c.rules ?? []).map((r) => ({
    actionType: r.actionType,
    origins: r.origins,
    requireConfirmation: r.requireConfirmation,
  }));
  const engine = new PolicyEngine(rules, {
    maxPayloadBytes: c.maxPayloadBytes,
    now: () => c.now ?? 0,
  });
  const d = engine.evaluate(c.proposal, c.approval);
  return {
    name: c.name,
    decision: d.decision,
    rule: d.rule,
    scopeBound: d.approvalScope !== undefined,
  };
});

const verifyResults = corpus.verify.map((c) => {
  const r = verifyCompletion({
    goal: c.goal,
    postAction: c.postAction,
    claimedObservationId: c.claimedObservationId,
    blocked: c.blocked,
    boundedOut: c.boundedOut,
  });
  return {
    name: c.name,
    outcome: r.outcome,
    fresh: r.fresh,
    passed: r.checks.map((x) => x.passed),
  };
});

const executorResults = corpus.execute.map((c) => {
  const ran = [];
  const handlers = {};
  for (const a of ACTION_TYPES) {
    handlers[a] = () => {
      ran.push(a);
    };
  }
  let clock = c.startNow ?? 0;
  const executor = new ActionExecutor(handlers, {
    timeoutMs: c.timeoutMs,
    now: () => {
      const v = clock;
      clock += c.elapsedPerCall ?? 0;
      return v;
    },
  });
  const record = executor.execute(c.proposal, c.decisionDetail, c.approvalScope);
  return {
    name: c.name,
    outcome: record.outcome,
    decision: record.decision,
    handlerRan: ran.length > 0,
  };
});

process.stdout.write(
  JSON.stringify({
    actionTypes: [...ACTION_TYPES],
    policy: policyResults,
    verify: verifyResults,
    execute: executorResults,
  }),
);