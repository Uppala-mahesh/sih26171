/**
 * Resource and latency measurement harness (Node side).
 *
 * Measures the 20% "client resources" and 15% "latency" rubric weights.
 *
 * ── Why nothing was instrumented inside the product ─────────────────────────
 * An earlier attempt added `performance.now()` calls to the orchestrator. It
 * was reverted. Instrumentation inside a shipped module is overhead the product
 * pays forever to serve a benchmark, and a harness that measures from OUTSIDE
 * measures what actually ships: in-product timings can be reordered or made
 * cheap by moving work, a wall-clock around a call cannot.
 *
 * ── What these numbers are, precisely ────────────────────────────────────────
 * Node.js numbers for the privacy core on CPU. They are NOT Chrome numbers and
 * NOT inference numbers. A latency figure for a CPU-only path says nothing
 * about a WebGPU model, and the benchmark reports the gap rather than closing
 * it. Claiming otherwise would be the v1 pattern.
 *
 * Usage:  node tests/vision/run-resources.cjs
 */

'use strict';

const os = require('node:os');
const path = require('node:path');

const DIST = path.join(__dirname, '..', '..', 'dist', 'packages');
const {
  runPipeline,
} = require(path.join(DIST, 'pipeline', 'orchestrator.js'));
const { PlaceholderVault } = require(path.join(DIST, 'privacy', 'vault.js'));
const { PixelFrame, PixelRedactor } = require(path.join(DIST, 'privacy', 'pixels.js'));
const { EgressGuard } = require(path.join(DIST, 'gateway', 'guard.js'));
const { detect } = require(path.join(DIST, 'privacy', 'detector.js'));
const { Sanitizer } = require(path.join(DIST, 'privacy', 'sanitizer.js'));
const { bindFindings, buildRuns, joinRuns } = require(
  path.join(DIST, 'vision', 'layout', 'text-runs.js'),
);
const { boundingBox } = require(path.join(DIST, 'contracts', 'geometry.js'));
const { CapabilityResolver } = require(path.join(DIST, 'vision', 'capability', 'ladder.js'));

const NONCE = 'deadbeef';
// Kept modest so the harness runs inside a CI step. Percentiles over 200
// samples are already stable for a CPU path this cheap; the numbers that would
// need thousands of samples are the inference ones, and those are not measured
// here (see the module header).
const WARMUP = 10;
const ITERATIONS = 100;

const SEGMENTS = [
  'Welcome back to your account dashboard',
  'Your Aadhaar is 999999990019 on record',
  'Contact parker.sterling@example.test for support',
  'Or call +91 9876543210 between 9am and 5pm',
  'Card on file 4532 0151 1283 0366 expires soon',
  'UPI identifier parker@okhdfcbank is linked',
  'IFSC HDFC0001234 and account 50100234567890',
  'Verification code 847291 was sent to your device',
  'Date of birth 14/03/1991 and PIN code 560001',
  'Order 7f3a2b1c shipped yesterday and arrived today',
  'Your monthly statement is ready to download now',
  'Thank you for banking with us for five years',
  'Joint holder parker.sterling@example.test on file',
  'Branch code 00123 opened on 02 January 2020',
  'Outstanding balance is zero for this period',
  'Your loan account 445566778899 is in good standing',
];

const RUNS = [
  { text: 'Your Aadhaar is 999999990019 on record', rects: [[20, 40, 260, 16]] },
  { text: 'Contact parker.sterling@example.test', rects: [[20, 60, 280, 16]] },
];

function buildFrame(width, height, channels, boxes) {
  const data = new Uint8Array(width * height * channels).fill(210);
  const ink = new Uint8Array(channels).fill(25);
  boxes.forEach((b, bi) => {
    const [bx, by, bw, bh] = b;
    for (let y = by; y < by + bh; y++) {
      for (let x = bx; x < bx + bw; x++) {
        if (x < 0 || y < 0 || x >= width || y >= height) continue;
        if ((x * 7 + y * 13 + bi * 29) % 5 !== 0) data.set(ink, (y * width + x) * channels);
      }
    }
  });
  return new PixelFrame(width, height, channels, data);
}

const BUILT_RUNS = buildRuns(
  RUNS.map((r, i) => ({
    elementId: `run-${i}`,
    text: r.text,
    rects: r.rects.map(([x, y, w, h]) => boundingBox(x, y, w, h)),
  })),
);
const JOINED = joinRuns(BUILT_RUNS);
const BOXES = bindFindings(
  detect(JOINED).findings.map((f) => ({ entityId: f.entityId, start: f.start, end: f.end })),
  BUILT_RUNS,
)
  .filter((b) => b.bound)
  .flatMap((b) => b.boxes)
  .map((b) => [b.x, b.y, b.width, b.height]);
const FRAME = buildFrame(320, 120, 3, BOXES);

function adapters(rung) {
  return {
    observationId: 'obs-bench',
    url: 'https://bank.test/account',
    title: 'Account dashboard',
    viewport: { width: 1280, height: 720 },
    frameBlind: false,
    capability: { rung, canVerifyPixels: true },
    captureText: () => SEGMENTS.map((text, i) => ({ elementId: `n${i}`, text, tagName: 'P' })),
    captureFrames: () => [
      {
        elementId: 'frame-0',
        frame: FRAME,
        boxes: BOXES.map(([x, y, w, h]) => boundingBox(x, y, w, h)),
        entities: BOXES.map(() => 'AADHAAR'),
      },
    ],
    now: () => 1700000000000,
  };
}

/** Median / p95 of a sample. Input is MILLISECONDS; output is microseconds. */
function stats(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const at = (q) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
  return {
    n: sorted.length,
    min_us: Math.round(sorted[0] * 1000),
    median_us: Math.round(at(0.5) * 1000),
    p95_us: Math.round(at(0.95) * 1000),
    max_us: Math.round(sorted[sorted.length - 1] * 1000),
  };
}

function time(iterations, body) {
  const samples = [];
  for (let i = 0; i < WARMUP + iterations; i++) {
    const t0 = performance.now();
    body(i);
    const dt = performance.now() - t0; // milliseconds
    if (i >= WARMUP) samples.push(dt);
  }
  return stats(samples);
}

const heapUsedKb = () => Math.round(process.memoryUsage().heapUsed / 1024);


// ── measurements ─────────────────────────────────────────────────────────────

const endToEnd = {};
for (const rung of ['webgpu', 'dom-only']) {
  endToEnd[rung] = time(ITERATIONS, () => {
    const vault = new PlaceholderVault('obs-bench', NONCE);
    runPipeline(adapters(rung), { vault, guard: new EgressGuard(), detect }, 'bench');
  });
}

/**
 * Components in isolation.
 *
 * Isolating them is what makes a regression attributable: a p95 that doubles
 * tells you nothing until you know which stage moved.
 */
const components = {
  detect_text: time(ITERATIONS * 5, () => detect(JOINED)),
  sanitize_text: time(ITERATIONS * 5, () => {
    new Sanitizer(new PlaceholderVault('obs-bench', NONCE), detect).sanitize(JOINED, 'n0');
  }),
  redact_pixels: time(ITERATIONS, () =>
    new PixelRedactor().redact(
      FRAME,
      BOXES.map(([x, y, w, h]) => boundingBox(x, y, w, h)),
    ),
  ),
  guard_revalidate: time(ITERATIONS * 5, () => {
    new EgressGuard().revalidate({
      schemaVersion: '1.0.0',
      destination: 'external_provider',
      context: {
        observationId: 'obs-bench',
        contextVersion: 1,
        capturedAt: 0,
        url: 'https://bank.test/account',
        title: 'Account dashboard',
        elements: [
          {
            ref: { observationId: 'obs-bench', elementId: 'n0', origin: 'https://bank.test' },
            tagName: 'P',
            role: 'TEXT_REGION',
            ariaLabel: '',
            textContent: 'Contact parker.sterling@example.test',
            placeholder: null,
            bounds: boundingBox(0, 0, 0, 0),
            isInteractive: false,
            isSensitive: false,
            opaque: false,
            confidence: 1,
          },
        ],
        safeTexts: SEGMENTS.slice(0, 3),
        visualRegions: [],
        viewport: { width: 1280, height: 720 },
        frameBlind: false,
        opaqueRegions: [],
      },
      evidence: { state: 'DEGRADED', reason: 'ocr_failed', rung: 'dom-only', declaredAt: 0 },
      rung: 'dom-only',
      taskDescription: 'bench',
    });
  }),
};

async function ladderProbe() {
  // Probes report UNAVAILABLE for WebGPU because Node has no navigator.gpu.
  // That is the honest answer on this host, and it exercises the fall-through.
  const resolver = new CapabilityResolver([
    {
      rung: 'webgpu',
      probe: async () => ({ available: false, reason: 'no navigator.gpu in Node' }),
    },
    { rung: 'wasm-simd', probe: async () => ({ available: true, detail: 'stub' }) },
    { rung: 'wasm', probe: async () => ({ available: true, detail: 'stub' }) },
  ]);
  for (let i = 0; i < WARMUP; i++) await resolver.resolve();
  const samples = [];
  for (let i = 0; i < ITERATIONS; i++) {
    const t0 = performance.now();
    await resolver.resolve();
    samples.push(performance.now() - t0); // milliseconds
  }
  return { ...stats(samples), resolved_rung: (await resolver.resolve()).active };
}

function footprint() {
  if (global.gc) global.gc();
  const before = heapUsedKb();
  const vaults = [];
  for (let i = 0; i < 50; i++) {
    const vault = new PlaceholderVault(`obs-${i}`, NONCE);
    new Sanitizer(vault, detect).sanitize(JOINED, 'n0');
    vaults.push(vault);
  }
  if (global.gc) global.gc();
  const after = heapUsedKb();

  const result = runPipeline(adapters('dom-only'), {
    vault: new PlaceholderVault('obs-bench', NONCE),
    guard: new EgressGuard(),
    detect,
  });
  const envelopeBytes = JSON.stringify(result.envelope).length;

  return {
    vault_entries_per_observation: vaults[0].size,
    heap_kb_after_50_observations: after,
    heap_delta_kb: after - before,
    frame_buffer_bytes: FRAME.data.length,
    frame_buffer_kb: Math.round(FRAME.data.length / 1024),
    envelope_bytes: envelopeBytes,
    bound_boxes: BOXES.length,
    // Zero is a real number here, not a placeholder: CR-003 ships no model
    // weights, so the extension carries none. It stays zero until weights are
    // acquired, and the budget must be revisited when they are.
    model_weights_bytes: 0,
  };
}

(async () => {
  process.stdout.write(
    JSON.stringify({
      environment: {
        node: process.version,
        platform: process.platform,
        arch: process.arch,
        cpu_count: os.cpus().length,
        iterations: ITERATIONS,
        warmup: WARMUP,
        heap_baseline_kb: heapUsedKb(),
      },
      end_to_end: endToEnd,
      components,
      ladder_probe: await ladderProbe(),
      footprint: footprint(),
    }),
  );
})();
