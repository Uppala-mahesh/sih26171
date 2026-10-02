/**
 * Cross-runtime parity runner for the VAULT and SANITIZER (Node side).
 *
 * tests/contract/test_parity.py runs the Python vault/sanitizer over the same
 * corpus and compares. Rule X-4 (REQ-DATA-001): divergence fails the build.
 *
 * Why this corpus exists separately from the detector's: the detector answers
 * "what is sensitive", but the vault answers "can it come back, and only to the
 * right place". A divergence there is a SECURITY divergence, so B-6 refusal
 * behaviour is recorded per case rather than only the happy path.
 *
 * The nonce is injected so tokens are byte-comparable across runtimes. In
 * production it is random per observation - that randomness is precisely what
 * makes a token unforgeable, so it is pinned ONLY for this harness.
 *
 * Usage:  node tests/parity/run-sanitizer.cjs <corpus.json>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { Sanitizer } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'sanitizer.js'),
);
const {
  PlaceholderVault,
  elementBinding,
} = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'vault.js'),
);

const corpusPath = process.argv[2];
if (!corpusPath) {
  process.stderr.write('usage: run-sanitizer.cjs <corpus.json>\n');
  process.exit(2);
}

const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));

/** Record whether an operation refused, rather than letting it throw. */
function refusal(fn) {
  try {
    fn();
    return false;
  } catch {
    return true;
  }
}

const results = corpus.cases.map((testCase) => {
  const vault = new PlaceholderVault(corpus.observation_id, corpus.nonce);
  const outcome = new Sanitizer(vault).sanitize(testCase.text, testCase.element_id);

  const binding = elementBinding(corpus.observation_id, testCase.element_id);
  const wrong = elementBinding(corpus.observation_id, 'node-attacker-controlled');
  const first = outcome.records[0];

  const canResolveBound = first ? vault.can_resolve(first.placeholder, binding) : null;
  const canResolveWrong = first ? vault.can_resolve(first.placeholder, wrong) : null;
  const crossElementRefused = first
    ? refusal(() => vault.detokenize_for_target(first.placeholder, wrong))
    : null;

  // FR-VLT-4: after clear() nothing resolves, including the bound target.
  vault.clear();
  const afterClearRefused = first
    ? refusal(() => vault.detokenize_for_target(first.placeholder, binding))
    : null;
  const sizeAfterClear = vault.size;

  return {
    name: testCase.name,
    text: outcome.text,
    state: outcome.evidence.state,
    redactions: outcome.evidence.redactions,
    unresolved: outcome.evidence.unresolved_count,
    residual: outcome.evidence.residual_count,
    pixelCovered: outcome.evidence.pixel_covered,
    discarded: outcome.discarded,
    records: outcome.records.map((r) => [
      r.entity_type,
      r.placeholder,
      r.start,
      r.end,
      r.outcome,
    ]),
    summary: {
      total: outcome.summary.total_redactions,
      byEntity: outcome.summary.by_entity,
      unresolved: outcome.summary.unresolved_count,
    },
    b6: {
      canResolveBound,
      canResolveWrong,
      crossElementRefused,
      afterClearRefused,
      sizeAfterClear,
    },
  };
});

process.stdout.write(JSON.stringify({ results }));
