/**
 * Exhaustive evidence-matrix runner.
 *
 * ── Why this exists ──────────────────────────────────────────────────────────
 * A real regression shipped through 337 GREEN tests: a page with an uncertain
 * detection was declared SANITIZED, because `unresolved` does not contribute to
 * `residualFindings` and the SANITIZED branch tested residuals alone.
 *
 * It was not caught because the suite tested individual BRANCHES, never their
 * COMBINATIONS. Every branch had a test; the cell that mattered had none.
 *
 * So this enumerates the CROSS PRODUCT of every input the evidence decision reads
 * and records what the pipeline actually declared for each cell. A combination
 * nobody thought of cannot be left untested when the whole space is enumerated.
 *
 * Usage:  node tests/vision/run-evidence-matrix.cjs
 */

'use strict';

const path = require('node:path');

const { runPipeline } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'pipeline', 'orchestrator.js'),
);
const { PlaceholderVault } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'privacy', 'vault.js'),
);
const { EgressGuard } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'gateway', 'guard.js'),
);

const NONCE = new Uint8Array(32).fill(7);
const FIXED_NOW = 1_700_000_000_000;

/**
 * Build a detector for one matrix cell.
 *
 * The finding is returned ONCE and then never again.
 *
 * This models a correct detector: the value is replaced by a placeholder on the
 * sanitize pass, so a re-scan of the sanitised text finds nothing. A stub that
 * re-emits its finding on every call instead models a BROKEN detector - and it
 * produces exactly the wrong lesson, because every cell then reports
 * NOT_INSTRUMENTED and the matrix looks like it is finding a product bug when it
 * is faithfully reporting a bad stub.
 *
 * That distinction matters: "the re-scan found a residual" is the correct verdict
 * for a residual, and the only way to test the matrix is with a stub whose
 * re-scan is realistic.
 */
function detectorFor(result) {
  let calls = 0;
  return () => {
    calls += 1;
    return calls === 1 ? result : { findings: [], discarded: 0 };
  };
}


/** A finding below the confidence threshold: redacted by default, and UNRESOLVED. */
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

/** A finding that is accepted outright. */
const ACCEPTED_DETECTION = {
  findings: [
    {
      entityId: 'AADHAAR',
      start: 0,
      end: 16,
      tier: 'T1',
      sensitivity: 'high',
      outcome: 'ACCEPTED',
      confidence: 0.99,
      placeholderPrefix: 'AADHAAR',
    },
  ],
  discarded: 0,
};

// Every value the evidence decision can read.
const CAN_VERIFY = [true, false];
const SURFACES = [0, 4, undefined];
const DETECTIONS = [
  ['none', { findings: [], discarded: 0 }],
  ['accepted', ACCEPTED_DETECTION],
  ['uncertain', UNCERTAIN_DETECTION],
];
const RUNGS = ['webgpu', 'dom-only'];

const cells = [];

for (const canVerifyPixels of CAN_VERIFY) {
  for (const visualSurfaces of SURFACES) {
    for (const [detectionName, detectResult] of DETECTIONS) {
      for (const rung of RUNGS) {
        const vault = new PlaceholderVault('obs-matrix', NONCE);
        const guard = new EgressGuard();

        const adapters = {
          observationId: 'obs-matrix',
          url: 'https://bank.test/account',
          title: 'Account',
          viewport: { width: 1280, height: 720 },
          frameBlind: false,
          capability: { rung, canVerifyPixels, missingCheck: 'pixel_rescan' },
          ...(visualSurfaces === undefined ? {} : { visualSurfaces }),
          captureText: () => [
            { elementId: 'n0', text: 'Your reference is REF-991', tagName: 'DIV', ariaLabel: '' },
          ],
          // No frames, ever: this matrix is about the DECISION, not pixels.
          captureFrames: () => [],
          now: () => FIXED_NOW,
        };

        const result = runPipeline(
          adapters,
          { vault, guard, detect: detectorFor(detectResult) },
          'matrix cell',
        );

        cells.push({
          canVerifyPixels,
          visualSurfaces: visualSurfaces === undefined ? null : visualSurfaces,
          detection: detectionName,
          rung,
          state: result.evidence.state,
          transmitted: result.transmitted,
          redactionCount: result.redactionCount,
        });
      }
    }
  }
}

process.stdout.write(JSON.stringify({ cells }));
