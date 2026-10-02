/**
 * Cross-runtime parity runner for PIXEL REDACTION and the EGRESS GUARD.
 *
 * tests/contract/test_pixel_guard_parity.py runs the Python modules over the
 * same corpus and compares. Rule X-4: divergence fails the build.
 *
 * Why this corpus exists separately: the detector, vault and sanitizer parity
 * suites each answer one question. This one answers the two that decide whether
 * the product is honest - "is the sensitive thing actually erased from the
 * pixels" and "does the guard still refuse a payload that merely CLAIMS to be
 * sanitized". The second is v1 defect G-2/G-6, so it is a fixture, not a
 * hypothetical.
 *
 * Frame bytes are generated here from integer arithmetic rather than read from
 * a stored blob, so both runtimes construct identical buffers and the IoU and
 * survivor numbers are reproducible rather than trusted.
 *
 * Floats are rounded to 6 decimal places before comparison: IEEE-754 is
 * deterministic for the same operations in both languages, but guarding against
 * a formatting difference keeps the failure message about the real divergence.
 *
 * Usage:  node tests/parity/run-pixel-guard.cjs <corpus.json>
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');

const {
  PixelFrame,
  PixelRedactor,
} = require(path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'pixels.js'));
const { boundingBox } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'contracts', 'geometry.js'),
);
const { EgressGuard } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'gateway', 'guard.js'),
);
const { verificationProof } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'contracts', 'sanitization.js'),
);

const corpusPath = process.argv[2];
if (!corpusPath) {
  process.stderr.write('usage: run-pixel-guard.cjs <corpus.json>\n');
  process.exit(2);
}

const corpus = JSON.parse(fs.readFileSync(corpusPath, 'utf8'));

const r6 = (v) => Math.round(v * 1e6) / 1e6;

/** Byte colour for a given channel count. */
function colour(rgb, channels) {
  const out = new Uint8Array(channels);
  if (channels >= 3) {
    out[0] = rgb[0];
    out[1] = rgb[1];
    out[2] = rgb[2];
  } else {
    out.fill(rgb[0]);
  }
  return out;
}

function buildFrame(spec) {
  const { width: w, height: h, channels: c } = spec;
  const data = new Uint8Array(w * h * c);
  const bg = colour(corpus.background, c);
  for (let i = 0; i < w * h; i++) data.set(bg, i * c);

  const ink = colour(corpus.ink, c);
  spec.boxes.forEach((box, bi) => {
    const [bx, by, bw, bh] = box;
    for (let y = by; y < by + bh; y++) {
      for (let x = bx; x < bx + bw; x++) {
        if (x < 0 || y < 0 || x >= w || y >= h) continue;
        if ((x * 7 + y * 13 + bi * 29) % 5 !== 0) data.set(ink, (y * w + x) * c);
      }
    }
  });
  return new PixelFrame(w, h, c, data);
}

const redactor = new PixelRedactor();
const pixelResults = corpus.frames.map((spec) => {
  const frame = buildFrame(spec);
  const boxes = spec.boxes.map(([x, y, w, h]) => boundingBox(x, y, w, h));
  const result = redactor.redact(frame, boxes, spec.entities);
  return {
    name: spec.name,
    masks: result.masks.map((m) => [m.index, r6(m.iou), m.pixels_changed, m.entity_id]),
    changed_pixels: result.changed_pixels,
    utility_preservation: r6(result.utility_preservation),
    style: result.style,
    verified: result.verified,
    failures: [...result.failures],
  };
});

/** Build the declared evidence for a state, exactly as the pipeline would. */
function buildEvidence(state) {
  const declaredAt = 1700000000000;
  switch (state) {
    case 'SANITIZED':
      return {
        state: 'SANITIZED',
        proof: verificationProof({
          verifiersRun: ['text_rescan', 'pixel_rescan'],
          regionsChecked: 1,
          residualFindings: 0,
        }),
        rung: 'dom-only',
        declaredAt,
      };
    case 'DEGRADED':
      return {
        state: 'DEGRADED',
        reason: 'ocr_failed',
        rung: 'dom-only',
        declaredAt,
      };
    case 'NOT_INSTRUMENTED':
      return { state: 'NOT_INSTRUMENTED', missingCheck: 'pixel_rescan', declaredAt };
    default:
      throw new Error(`unknown state ${state}`);
  }
}

const guard = new EgressGuard();
const guardResults = corpus.guard_cases.map((testCase) => {
  const envelope = {
    schemaVersion: '1.0.0',
    destination: 'external_provider',
    context: {
      observationId: 'obs-guard-parity',
      contextVersion: 1,
      capturedAt: 1700000000000,
      url: 'https://example.test/account',
      title: testCase.title,
      elements: testCase.elements.map((e, i) => ({
        ref: { observationId: 'obs-guard-parity', elementId: `n${i}`, origin: 'https://example.test' },
        tagName: 'DIV',
        role: 'TEXT_REGION',
        ariaLabel: e.ariaLabel,
        textContent: e.textContent,
        placeholder: null,
        bounds: boundingBox(0, 0, 10, 10),
        isInteractive: false,
        isSensitive: false,
        opaque: false,
        confidence: 0.99,
      })),
      safeTexts: testCase.safeTexts,
      visualRegions: [],
      viewport: { width: 1280, height: 720 },
      frameBlind: testCase.frameBlind,
      opaqueRegions: [],
    },
    evidence: buildEvidence(testCase.state),
    rung: 'dom-only',
    taskDescription: 'read the account page',
  };

  const result = guard.inspect(envelope);
  return {
    name: testCase.name,
    verdict: result.verdict,
    permitted: result.permitted,
    reason: result.reason,
    revalidation: result.revalidation,
  };
});

process.stdout.write(
  JSON.stringify({ pixels: pixelResults, guard: guardResults }),
);
