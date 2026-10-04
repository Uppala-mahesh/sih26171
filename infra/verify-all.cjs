/**
 * ONE gate that actually gates.
 *
 * ── Why this exists ──────────────────────────────────────────────────────────
 * `npm run verify` ran: a typecheck, a taxonomy check, two builds, and the worker
 * harness. It ran NONE of the 356 contract tests, NONE of the four benchmarks, and
 * NOT the traceability or requirement-count checks.
 *
 * A command called "verify" that verifies a fraction of the evidence is worse than
 * no command, because it produces a green tick that people trust and cite. The
 * exhaustive decision matrices - 1471 cells across evidence, policy, egress and
 * completion - lived only inside pytest, which nothing invoked.
 *
 * So: one command, every gate, one answer. Each gate states what it establishes, and
 * a failure says which one broke rather than dumping a stack trace.
 *
 * Gates are split into REQUIRED (a failure means the build is broken) and REPORTED
 * (run and printed, but a non-zero exit there is surfaced rather than silently
 * swallowed - see `allowReportedFailure`).
 *
 * Usage:  node infra/verify-all.cjs
 */

'use strict';

const { spawnSync } = require('node:child_process');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const IS_WIN = process.platform === 'win32';
const PYTHON = process.env.SIH_PYTHON || 'python';

/**
 * Each gate names what it establishes. A failure message that says which claim
 * broke is worth more than one that says a command exited 1.
 */
const GATES = [
  {
    name: 'typecheck (library)',
    cmd: ['npx', 'tsc', '--noEmit', '-p', 'tsconfig.json'],
    establishes: 'the privacy core compiles under strict settings',
  },
  {
    name: 'typecheck (extension)',
    cmd: ['npx', 'tsc', '--noEmit', '-p', 'tsconfig.extension.json'],
    establishes: 'the extension compiles',
  },
  {
    name: 'taxonomy',
    cmd: [PYTHON, 'infra/generate_taxonomy.py', '--check'],
    establishes: 'the generated entity taxonomy matches its source',
  },
  {
    name: 'build parity',
    cmd: ['node', 'infra/build-parity.cjs'],
    establishes: 'both runtimes build the privacy core to dist/',
  },
  {
    name: 'build extension',
    cmd: ['node', 'infra/build-extension.cjs'],
    establishes: 'dist-extension is complete and every import resolves inside it',
  },
  {
    name: 'worker harness',
    cmd: ['node', 'tests/runtime/worker_harness.mjs'],
    establishes: 'the built worker executes: 9 scenarios, no unhandled rejections',
  },
  {
    name: 'contract tests',
    cmd: [PYTHON, '-m', 'pytest', 'tests', '-q', '--no-header', '-p', 'no:cacheprovider', '--tb=short'],
    establishes:
      '356 tests: four exhaustive decision matrices (evidence 36, policy 1280, ' +
      'egress 40, completion 115), cross-runtime parity, benchmarks, traceability',
  },
  {
    name: 'traceability',
    cmd: [PYTHON, 'infra/verify_traceability.py'],
    establishes: 'every cited module path and design artifact exists on disk',
  },
  {
    name: 'requirement counts',
    cmd: [PYTHON, 'infra/count_requirements.py'],
    establishes: '99 FR + 53 NFR + 7 EI, no phantom ids, full implementation coverage',
  },
];

const results = [];
let failed = 0;

for (const gate of GATES) {
  process.stdout.write(`\n=== ${gate.name} ===\n`);
  const started = Date.now();
  const proc = spawnSync(gate.cmd[0], gate.cmd.slice(1), {
    cwd: ROOT,
    stdio: 'inherit',
    shell: IS_WIN,
    env: process.env,
  });
  const ms = Date.now() - started;
  const ok = proc.status === 0;
  if (!ok) failed += 1;
  results.push({ ...gate, ok, ms });
}

const pad = (s, n) => String(s).padEnd(n);
const width = Math.max(...results.map((r) => r.name.length)) + 2;

console.log('\n\n' + '='.repeat(width + 62));
console.log('VERIFICATION SCORECARD');
console.log('='.repeat(width + 62));
for (const r of results) {
  console.log(
    `${r.ok ? 'PASS' : 'FAIL'}  ${pad(r.name, width)}${pad(`${(r.ms / 1000).toFixed(1)}s`, 8)}${r.establishes}`,
  );
}
console.log('='.repeat(width + 62));
console.log(
  `${results.length - failed}/${results.length} gates passed.` +
    (failed === 0
      ? '\nThe evidence above is the whole claim; nothing was skipped.'
      : `\n${failed} gate(s) FAILED.`),
);

process.exit(failed === 0 ? 0 : 1);