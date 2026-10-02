/**
 * End-to-end pipeline runner (Node side).
 *
 * The unit tests prove each library is correct. They cannot prove the libraries
 * are correct TOGETHER, and the whole project exists because a chain of
 * individually-correct components produced a leaky product in v1.
 *
 * So this runs the real orchestration with fake DOM adapters and records what
 * the system actually DID: which state it declared, whether the payload
 * crossed, and whether any raw value survived into the envelope.
 *
 * The scenarios are chosen to include the ones that must fail. A pipeline test
 * that only exercises the happy path proves that nothing.
 *
 * Usage:  node tests/vision/run-pipeline.cjs
 */

'use strict';

const path = require('node:path');

const {
  runPipeline,
} = require(path.join(__dirname, '..', '..', 'dist', 'packages', 'pipeline', 'orchestrator.js'));
const { PlaceholderVault } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'vault.js'),
);
const { PixelFrame } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'pixels.js'),
);
const { EgressGuard } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'gateway', 'guard.js'),
);
const { detect } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'detector.js'),
);
const { bindFindings, buildRuns, joinRuns } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'vision', 'layout', 'text-runs.js'),
);
const { boundingBox } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'contracts', 'geometry.js'),
);

const NONCE = 'deadbeef';
const FIXED_NOW = 1700000000000;

/** Deterministic frame so every scenario builds identical buffers. */
function buildFrame(width, height, channels, boxes) {
  const data = new Uint8Array(width * height * channels).fill(200);
  const ink = new Uint8Array(channels).fill(30);
  boxes.forEach(([bx, by, bw, bh], bi) => {
    for (let y = by; y < by + bh; y++) {
      for (let x = bx; x < bx + bw; x++) {
        if (x < 0 || y < 0 || x >= width || y >= height) continue;
        if ((x * 7 + y * 13 + bi * 29) % 5 !== 0) {
          data.set(ink, (y * width + x) * channels);
        }
      }
    }
  });
  return new PixelFrame(width, height, channels, data);
}

const AADHAAR = '999999990019';

/**
 * Derive mask boxes the way the extension does: from text runs, through the
 * detector, into the binder.
 *
 * The earlier scenarios passed hand-placed rectangles. That made the redaction
 * score depend on the HARNESS choosing good boxes rather than on the system
 * finding them, which is the same substitution this project exists to stop
 * making. These scenarios use the real binder end to end.
 */
function boxesFromRuns(runs) {
  const built = buildRuns(
    runs.map((r, i) => ({
      elementId: `run-${i}`,
      text: r.text,
      rects: r.rects.map(([x, y, w, h]) => boundingBox(x, y, w, h)),
    })),
  );
  const text = joinRuns(built);
  const findings = detect(text).findings;
  const bindings = bindFindings(
    findings.map((f) => ({ entityId: f.entityId, start: f.start, end: f.end })),
    built,
  );
  return bindings.filter((b) => b.bound).flatMap((b) => b.boxes);
}

/**
 * @param {object} opts
 * @param {string[]} opts.texts      raw text segments, as the page would yield
 * @param {object} opts.capability
 * @param {Array}  opts.boxes        pixel boxes, or null for no frames
 * @param {Array}  opts.runs         text runs; boxes are DERIVED from these
 */
function run(name, opts) {
  const derived = opts.runs ? boxesFromRuns(opts.runs) : null;

  // Explicit scenarios state boxes as [x,y,w,h] tuples; derived ones are
  // already BoundingBox objects. Normalise here so both paths hand the
  // redactor the same shape - passing a raw tuple through silently produces
  // NaN geometry and an IoU of 0, which reads as a masking failure.
  let boxes;
  if (derived !== null) boxes = derived;
  else if (opts.boxes === null) boxes = null;
  else boxes = opts.boxes.map(([x, y, w, h]) => boundingBox(x, y, w, h));

  const vault = new PlaceholderVault(`obs-${name}`, NONCE);
  const guard = new EgressGuard();

  const adapters = {
    observationId: `obs-${name}`,
    url: 'https://bank.test/account',
    title: 'Account overview',
    viewport: { width: 1280, height: 720 },
    frameBlind: false,
    capability: opts.capability,
    // Present so the evidence branch has something to reason about. Omitting it
    // is meaningful: `undefined` means the collector could not tell, which is
    // treated as unknown and never as zero.
    ...(opts.visualSurfaces === undefined ? {} : { visualSurfaces: opts.visualSurfaces }),
    captureText: () =>
      opts.texts.map((text, i) => ({
        elementId: `n${i}`,
        text,
        tagName: 'DIV',
        ariaLabel: '',
      })),
    captureFrames: () =>
      boxes === null
        ? []
        : [
            {
              elementId: 'frame-0',
              frame: buildFrame(40, 24, 3, boxes.map((b) => [b.x, b.y, b.width, b.height])),
              boxes,
              entities: boxes.map(() => 'AADHAAR'),
            },
          ],
    now: () => FIXED_NOW,
  };

  // A deterministic stub, so an UNCERTAIN outcome can be produced on demand rather
  // than hunted for in the taxonomy. The real detector has no text fixture that
  // reliably lands below threshold, and a regression test that depends on finding
  // one by accident is a regression test that stops covering the regression.
  const detectFor = opts.detect === undefined ? detect : () => opts.detect;

  const result = runPipeline(adapters, { vault, guard, detect: detectFor }, 'check my account');
  const serialised = JSON.stringify(result.envelope);

  return {
    name,
    state: result.evidence.state,
    rung: result.rung,
    redactions: result.redactionCount,
    textSegments: result.textSegments,
    framesVerified: result.framesVerified,
    pixelFailure: result.pixelFailure !== null,
    transmitted: result.transmitted,
    withheld: result.transmitError !== null,
    // Whether the boxes came from the real binder rather than the harness.
    boxesFromBinder: derived !== null,
    boundBoxes: boxes === null ? 0 : boxes.length,
    // The load-bearing assertion: does any raw value appear in the envelope?
    aadhaarInEnvelope: serialised.includes(AADHAAR),
    envelopeBytes: serialised.length,
    auditVerdicts: guard.audit.map((e) => e.verdict),
  };
}

/**
 * A single UNCERTAIN finding, injected deterministically.
 *
 * The real detector has no fixture that reliably lands below the confidence
 * threshold, and a regression test that has to go hunting for one stops covering
 * the regression the first time the taxonomy changes. The outcome is therefore
 * stated here rather than induced.
 */
const UNCERTAIN_DETECTION = {
  findings: [
    {
      entityId: 'AADHAAR',
      start: 0,
      end: 16,
      tier: 'T3',
      sensitivity: 'high',
      outcome: 'UNCERTAIN',
      confidence: 0.5,
      placeholderPrefix: 'AADHAAR',
    },
  ],
  discarded: 0,
};

const scenarios = [
  run('clean-webgpu', {
    texts: ['Welcome back', 'Your order shipped yesterday'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: [[4, 4, 12, 8]],
  }),
  run('pii-redacted', {
    texts: [`Your Aadhaar is ${AADHAAR} on record.`, 'Contact us any time'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: [[4, 4, 12, 8]],
  }),
  run('degraded-dom-only', {
    texts: ['Clean text here'],
    capability: { rung: 'dom-only', canVerifyPixels: true },
    boxes: [[4, 4, 12, 8]],
  }),
  run('pixels-unverifiable', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: false, missingCheck: 'pixel_rescan' },
    boxes: [[4, 4, 12, 8]],
  }),
  run('pixel-mask-below-floor', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    // Box mostly outside a 40x24 frame: clamp cannot reach IoU 0.90.
    boxes: [[36, 20, 30, 24]],
  }),
  run('no-frames-captured', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
  }),

  // ── visualSurfaces drives the evidence branch ────────────────────────────────
  // These three were the REGRESSION: the `visualSurfaces` branches were added
  // ahead of the UNCERTAIN branch, and `unresolved` does not contribute to
  // `residualFindings` (an entity below threshold is redacted anyway, so no raw
  // value survives and the residual count stays 0). A SANITIZED branch testing
  // only residuals therefore swallowed UNCERTAIN and declared the page clean.
  //
  // No scenario previously combined an UNCERTAIN detection with zero painted
  // surfaces, which is why 333 tests stayed green through it.
  run('text-only-clean', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
    visualSurfaces: 0,
  }),
  run('text-only-uncertain', {
    texts: ['Your reference is REF-991'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
    visualSurfaces: 0,
    detect: UNCERTAIN_DETECTION,
  }),
  run('painted-surface-uncertain', {
    texts: ['Your reference is REF-991'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
    visualSurfaces: 4,
    detect: UNCERTAIN_DETECTION,
  }),
  run('painted-surface-clean', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
    visualSurfaces: 4,
  }),
  run('unknown-surface-count', {
    texts: ['Clean text here'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    boxes: null,
    // Omitted entirely: the collector could not tell.
  }),

  // ── boxes derived by the REAL binder, not placed by the harness ────────────
  run('binder-derived-boxes', {
    texts: ['Your Aadhaar is 999999990019 on record.'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    runs: [{ text: 'Your Aadhaar is 999999990019 on record.', rects: [[6, 6, 28, 10]] }],
  }),
  run('binder-two-spans', {
    texts: ['Aadhaar 999999990019', 'Email parker.sterling@example.test'],
    capability: { rung: 'webgpu', canVerifyPixels: true },
    runs: [
      { text: 'Aadhaar 999999990019', rects: [[4, 4, 16, 10]] },
      { text: 'Email parker.sterling@example.test', rects: [[4, 14, 22, 8]] },
    ],
  }),
];

process.stdout.write(JSON.stringify({ scenarios }));
