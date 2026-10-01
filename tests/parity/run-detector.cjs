/**
 * Cross-runtime parity runner (Node side).
 *
 * Reads testdata/parity_corpus.json, runs the COMPILED TypeScript detector over
 * every case, and writes the findings as JSON on stdout.
 *
 * tests/contract/test_parity.py runs the Python detector over the same corpus
 * and compares. Rule X-4 (REQ-DATA-001): divergence fails the build.
 *
 * Findings are reduced to [entityId, start, end, outcome] tuples so the
 * comparison is about DETECTION, not about incidental representation details
 * such as property naming or confidence formatting.
 *
 * Usage:  node tests/parity/run-detector.cjs <corpus.json>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { detect, SUPPORTED_ENTITIES } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'detector.js'),
);

const corpusPath = process.argv[2];
if (!corpusPath) {
  process.stderr.write('usage: run-detector.cjs <corpus.json>\n');
  process.exit(2);
}

const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));

const results = corpus.cases.map((testCase) => {
  const outcome = detect(testCase.text);
  return {
    name: testCase.name,
    discarded: outcome.discarded,
    findings: outcome.findings.map((f) => [f.entityId, f.start, f.end, f.outcome]),
  };
});

process.stdout.write(
  JSON.stringify({ supportedEntities: SUPPORTED_ENTITIES, results }),
);
