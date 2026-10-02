/**
 * False-completion benchmark (Node side) — FR-VER-4.
 *
 * The acceptance criterion for FR-VER-4 is a MEASURED 0.00% false-completion
 * rate against a ground-truth task set. This harness produces that number.
 *
 * ── What "false completion" means here ──────────────────────────────────────
 * The actor always claims success. That is the whole threat model: a reasoning
 * model asserting a task is done. A false completion is any case where the actor
 * said "done" and the verifier agreed while ground truth says the task was not
 * accomplished.
 *
 * Every case claims success, so the verifier is the only thing that can dissent.
 * A suite of easy tasks would score 100% while proving nothing. The hard cases
 * are the point: stale perception, unchanged state, a value that survived
 * redaction, and a region that was never masked.
 */

'use strict';

const path = require('node:path');

const { verifyCompletion } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'agent', 'verifier.js'),
);

const NOW = 1700000000000;

function clearedSnapshot(overrides = {}) {
  return {
    observationId: 'obs-after',
    capturedAt: NOW + 1000,
    title: 'Account overview',
    elements: [
      { role: 'TEXT_REGION', ariaLabel: 'Card', sensitive: false },
      { role: 'TEXT_INPUT', ariaLabel: 'Card number', sensitive: false },
    ],
    opaqueRegions: [0, 1],
    text: 'Your card is ending 0366',
    ...overrides,
  };
}

const GOAL = {
  id: 'clear-card',
  description: 'Remove the stored card number from the page',
  postconditions: [
    { kind: 'TEXT_ABSENT', values: ['4532015112830366'] },
    { kind: 'NAME_ABSENT', name: 'stored-card-number' },
    { kind: 'REGIONS_OPAQUE', regions: [0] },
  ],
};

const cases = [
  // ── honest completions: the verifier must agree ──────────────────────────
  { name: 'completed-cleanly', truth: 'accomplished', expected: 'COMPLETED',
    input: { goal: GOAL, postAction: clearedSnapshot(), claimedObservationId: 'obs-before' } },
  { name: 'completed-with-both-regions-opaque', truth: 'accomplished', expected: 'COMPLETED',
    input: { goal: GOAL, postAction: clearedSnapshot({ opaqueRegions: [0, 1] }), claimedObservationId: 'obs-before' } },

  // ── the v1 shape: success claimed, nothing changed ───────────────────────
  { name: 'stale-perception-claimed-success', truth: 'not accomplished', expected: 'FAILED',
    // Same observation id the actor acted on, so this snapshot PREDATES the
    // action. v1 verified against exactly this.
    input: { goal: GOAL, postAction: clearedSnapshot({ observationId: 'obs-before' }), claimedObservationId: 'obs-before' } },
  { name: 'value-still-present', truth: 'not accomplished', expected: 'FAILED',
    input: { goal: GOAL, postAction: clearedSnapshot({ text: 'Your card is 4532 0151 1283 0366' }), claimedObservationId: 'obs-before' } },
  { name: 'value-present-different-case', truth: 'not accomplished', expected: 'FAILED',
    // A value differing only in case is still the value.
    input: { goal: GOAL, postAction: clearedSnapshot({ text: 'Card 4532015112830366 on file' }), claimedObservationId: 'obs-before' } },
  { name: 'region-never-masked', truth: 'not accomplished', expected: 'FAILED',
    input: { goal: GOAL, postAction: clearedSnapshot({ opaqueRegions: [] }), claimedObservationId: 'obs-before' } },
  { name: 'element-still-present', truth: 'not accomplished', expected: 'FAILED',
    input: { goal: GOAL, postAction: clearedSnapshot({
      elements: [
        { role: 'TEXT_REGION', ariaLabel: 'Card', sensitive: false },
        { role: 'TEXT_INPUT', ariaLabel: 'stored-card-number', sensitive: false },
      ] }), claimedObservationId: 'obs-before' } },
  { name: 'goal-without-postconditions', truth: 'unprovable', expected: 'FAILED',
    input: { goal: { id: 'vague', description: 'do the thing', postconditions: [] }, postAction: clearedSnapshot(), claimedObservationId: 'obs-before' } },
  { name: 'blocked-before-execution', truth: 'not attempted', expected: 'BLOCKED',
    input: { goal: GOAL, postAction: clearedSnapshot(), claimedObservationId: 'obs-before', blocked: true } },
  { name: 'execution-bound-elapsed', truth: 'not accomplished', expected: 'BOUNDED_OUT',
    input: { goal: GOAL, postAction: clearedSnapshot(), claimedObservationId: 'obs-before', boundedOut: true } },

  // ── negative control for the harness itself ─────────────────────────────
  { name: 'sensitive-element-is-not-a-clean-presence', truth: 'not accomplished', expected: 'FAILED',
    input: { goal: { id: 'find-clean-input', description: 'find a usable input',
      postconditions: [{ kind: 'ELEMENT_PRESENT', role: 'TEXT_INPUT' }] },
      postAction: clearedSnapshot({ elements: [{ role: 'TEXT_INPUT', ariaLabel: 'secret', sensitive: true }] }),
      claimedObservationId: 'obs-before' } },
];

const results = cases.map((c) => {
  const verdict = verifyCompletion(c.input);
  // Determinism (FR-VER-2): the same input must yield the same verdict, twice.
  const again = verifyCompletion(c.input);
  return {
    name: c.name,
    expected: c.expected,
    actual: verdict.outcome,
    matches: verdict.outcome === c.expected,
    // A false completion: the actor claimed success AND the verifier said
    // COMPLETED while ground truth says it was not accomplished.
    falseCompletion: verdict.outcome === 'COMPLETED' && c.truth !== 'accomplished',
    deterministic:
      again.outcome === verdict.outcome &&
      JSON.stringify(again.checks) === JSON.stringify(verdict.checks),
    fresh: verdict.fresh,
    checksRun: verdict.checks.length,
    checksPassed: verdict.checks.filter((x) => x.passed).length,
    reason: verdict.reason,
  };
});

process.stdout.write(JSON.stringify({ results }));
