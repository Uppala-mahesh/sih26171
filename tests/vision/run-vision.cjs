/**
 * Vision quality runner (Node side).
 *
 * Executes the real role classifier and the real text-run binder over
 * testdata/vision_corpus.json and emits everything the benchmark scores.
 *
 * Both halves run headlessly. The binder normally reads
 * `Range.getClientRects()`; here the corpus supplies the rectangles a
 * deterministic mock layout produces, so the SAME binding code is exercised
 * without a browser. What differs between the harness and the extension is only
 * where the rectangles come from, which is the one thing the binder does not
 * own.
 *
 * Usage:  node tests/vision/run-vision.cjs <corpus.json>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const { classify } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'vision', 'classify', 'role-classifier.js'),
);
const { bindFindings, buildRuns, joinRuns } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'vision', 'layout', 'text-runs.js'),
);
const { boundingBox } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'contracts', 'geometry.js'),
);
const { intersectionOverUnion } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'vision', 'layout', 'geometry-ops.js'),
);
const { detect } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'detector.js'),
);

const corpusPath = process.argv[2];
if (!corpusPath) {
  process.stderr.write('usage: run-vision.cjs <corpus.json>\n');
  process.exit(2);
}
const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));
const r6 = (v) => Math.round(v * 1e6) / 1e6;

// ── role classification ──────────────────────────────────────────────────────

const roles = corpus.elements.map((e) => {
  const result = classify({
    tagName: e.tagName,
    typeAttribute: e.typeAttribute,
    ariaRole: e.ariaRole,
    isInteractive: e.isInteractive,
    isFocusable: e.isFocusable,
    hasChildren: e.hasChildren,
    width: e.width,
    height: e.height,
    aspectRatioCloseness: e.aspectRatioCloseness,
  });
  return {
    name: e.name,
    expected: e.expectedRole,
    actual: result.role,
    correct: result.role === e.expectedRole,
    confidence: result.confidence,
    decidedBy: result.decidedBy,
  };
});

// ── text-run to pixel-box binding ────────────────────────────────────────────

const documents = corpus.documents.map((doc) => {
  // buildRuns/joinRuns, exactly as the extension does it. A hand-rolled join
  // here would let the harness pass while the shipped code failed - which is
  // exactly the defect this corpus was written to catch.
  const runs = buildRuns(
    doc.runs.map((r, i) => ({
      elementId: `run-${i}`,
      text: r.text,
      rects: r.rects.map(([x, y, w, h]) => boundingBox(x, y, w, h)),
    })),
  );

  const text = joinRuns(runs);
  const findings = detect(text).findings;
  const bindings = bindFindings(
    findings.map((f) => ({ entityId: f.entityId, start: f.start, end: f.end })),
    runs,
  );

  const boxes = bindings.flatMap((b) => (b.bound ? b.boxes : []));
  const unbound = bindings.filter((b) => !b.bound);

  // IoU of each produced box against every supplied rect: the best match wins.
  // This measures whether the binder pointed at the glyphs, not merely whether
  // it returned something.
  const supplied = runs.flatMap((r) => r.rects);
  const ious = boxes.map((box) => {
    let best = 0;
    for (const candidate of supplied) {
      best = Math.max(best, intersectionOverUnion(box, candidate));
    }
    return r6(best);
  });

  return {
    name: doc.name,
    expectedBoxes: doc.expectedBoxes,
    actualBoxes: boxes.length,
    expectedUnbound: doc.expectedUnbound ?? 0,
    actualUnbound: unbound.length,
    entities: bindings.filter((b) => b.bound).map((b) => b.entityId),
    worstIou: ious.length === 0 ? null : Math.min(...ious),
    // An unbound span must ALWAYS carry a stated reason.
    unboundReasons: unbound.map((b) => b.reason),
  };
});

process.stdout.write(JSON.stringify({ roles, documents }));
