/**
 * Exhaustive completion-verifier matrix.
 *
 * ── Why this one matters most ────────────────────────────────────────────────
 * v1's central failure was a reasoning model asserting a task was done. When the
 * vision pipeline quietly returned a 1x1 frame, the model still reported success and
 * the success was believed (defects G-2, G-6).
 *
 * So the verifier exists to make that impossible: completion is a deterministic
 * check over FRESH post-action perception, and the actor's report is unreachable from
 * it. Its most important property is that a false COMPLETED cannot be produced by any
 * combination.
 *
 * A verifier tested one postcondition at a time never learns whether TWO failing
 * postconditions behave differently from one - nor whether an empty set is special-
 * cased correctly. So the whole space of goal declarations is enumerated: every
 * non-empty SUBSET of the five postcondition kinds, run once with all satisfied and
 * once with exactly one violated.
 *
 * Each kind declares what it needs and what BREAKS it, and the perception is built
 * as a UNION over the goal's postconditions.
 *
 * The union matters. An earlier version had each kind REPLACE the whole elements
 * array, so a satisfied NAME_ABSENT silently overwrote a violated ELEMENT_PRESENT
 * with a clean button - and the matrix cheerfully reported COMPLETED for a goal whose
 * element check had failed. The verifier was correct; the harness was lying to it.
 * Anything that models a perception by overwriting shared state has this bug.
 *
 * Usage:  node tests/parity/run-verifier-matrix.cjs
 */

'use strict';

const path = require('node:path');

const { verifyCompletion } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'agent', 'verifier.js'),
);

const KINDS = {
  ELEMENT_PRESENT: {
    satisfied: { kind: 'ELEMENT_PRESENT', role: 'button' },
    // The element is present but flagged sensitive, which must NOT satisfy it.
    violated: { kind: 'ELEMENT_PRESENT', role: 'button' },
    satisfies: (p) => {
      p.elements.push({ role: 'button', ariaLabel: 'Go', sensitive: false });
    },
    violates: (p) => {
      p.elements.push({ role: 'button', ariaLabel: 'Go', sensitive: true });
    },
  },
  NAME_ABSENT: {
    satisfied: { kind: 'NAME_ABSENT', name: 'Delete account' },
    violated: { kind: 'NAME_ABSENT', name: 'Delete account' },
    // A DIFFERENT role and label from ELEMENT_PRESENT, so the two compose instead
    // of fighting over the same element.
    satisfies: (p) => {
      p.elements.push({ role: 'link', ariaLabel: 'Home', sensitive: false });
    },
    violates: (p) => {
      p.elements.push({ role: 'link', ariaLabel: 'Delete account', sensitive: false });
    },
  },
  TEXT_ABSENT: {
    // The unspaced needle against a SPACED haystack. A literal substring check passes
    // this and reports COMPLETED while the page still displays the value - the exact
    // defect the punctuation normalisation exists to prevent.
    satisfied: { kind: 'TEXT_ABSENT', values: ['4532015112830366'] },
    violated: { kind: 'TEXT_ABSENT', values: ['4532015112830366'] },
    satisfies: (p) => {
      p.text = 'card removed';
    },
    violates: (p) => {
      p.text = 'Card 4532 0151 1283 0366';
    },
  },
  REGIONS_OPAQUE: {
    satisfied: { kind: 'REGIONS_OPAQUE', regions: [1, 2] },
    violated: { kind: 'REGIONS_OPAQUE', regions: [1, 2] },
    satisfies: (p) => {
      p.opaqueRegions.push(1, 2);
    },
    violates: (p) => {
      p.opaqueRegions.push(1);
    },
  },
  FRESH_AFTER: {
    // Satisfied when perception is new enough; violated by raising the bound the
    // perception cannot meet. Same condition, different threshold.
    satisfied: { kind: 'FRESH_AFTER', notBefore: 5 },
    violated: { kind: 'FRESH_AFTER', notBefore: 50 },
    satisfies: (p) => {
      p.capturedAt = 7;
    },
    violates: (p) => {
      p.capturedAt = 7;
    },
  },
};

const KIND_NAMES = Object.keys(KINDS);

/** Every non-empty subset, in a stable order. */
function subsets(items) {
  const out = [];
  for (let mask = 1; mask < 1 << items.length; mask += 1) {
    out.push(items.filter((_, i) => mask & (1 << i)));
  }
  return out;
}

function basePerception(observationId) {
  return {
    observationId,
    capturedAt: 7,
    title: 'Account',
    elements: [],
    opaqueRegions: [],
    text: 'nothing',
  };
}

const cells = [];

function record(label, kinds, violatingIndex, extra) {
  const perception = basePerception(extra && extra.observationId ? extra.observationId : 'obs-2');
  const postconditions = kinds.map((name, i) =>
    i === violatingIndex ? KINDS[name].violated : KINDS[name].satisfied,
  );
  for (let i = 0; i < kinds.length; i += 1) {
    if (i === violatingIndex) KINDS[kinds[i]].violates(perception);
    else KINDS[kinds[i]].satisfies(perception);
  }

  const r = verifyCompletion({
    goal: { id: 'g', description: 'd', postconditions },
    postAction: perception,
    claimedObservationId: (extra && extra.claimedObservationId) || 'obs-1',
    blocked: (extra && extra.blocked) || false,
    boundedOut: (extra && extra.boundedOut) || false,
  });

  cells.push({
    label,
    kinds,
    violated: violatingIndex === null ? null : kinds[violatingIndex],
    count: kinds.length,
    outcome: r.outcome,
    fresh: r.fresh,
    failedChecks: r.checks.filter((c) => !c.passed).length,
    totalChecks: r.checks.length,
  });
}
// Every non-empty subset, all satisfied -> must be COMPLETED.
for (const s of subsets(KIND_NAMES)) {
  record(`${s.length} postcondition(s), all satisfied`, s, null);
}

// Every non-empty subset, exactly one violated -> must NOT be COMPLETED.
for (const s of subsets(KIND_NAMES)) {
  for (let i = 0; i < s.length; i += 1) {
    record(`${s.length} postcondition(s), ${s[i]} violated`, s, i);
  }
}

// The terminal states, which must never be COMPLETED regardless of the goal.
const ALL = KIND_NAMES;
record('blocked', ALL, null, { blocked: true });
record('bounded out', ALL, null, { boundedOut: true });
// Same observation id on both sides: perception predates the action.
record('stale perception', ALL, null, { observationId: 'obs-1' });

// A goal that declares nothing cannot be verified at all.
{
  const r = verifyCompletion({
    goal: { id: 'g', description: 'd', postconditions: [] },
    postAction: basePerception('obs-2'),
    claimedObservationId: 'obs-1',
  });
  cells.push({
    label: 'no postconditions declared',
    kinds: [],
    violated: null,
    count: 0,
    outcome: r.outcome,
    fresh: r.fresh,
    failedChecks: 0,
    totalChecks: 0,
  });
}

process.stdout.write(JSON.stringify({ cellCount: cells.length, cells }));