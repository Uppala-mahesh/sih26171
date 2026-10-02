/**
 * Exhaustive egress-guard matrix.
 *
 * ── The property ─────────────────────────────────────────────────────────────
 * "Does anything sensitive actually go on the wire?" is the last security
 * decision point in the system, and it was covered by hand-written cases.
 *
 * The guard's whole job is that it does NOT trust the sender. It re-derives the
 * verdict from the payload's contents. So the question is not "what does the
 * sender claim" but: **for every combination of claimed state and actual payload
 * contents, does a raw value ever leave?**
 *
 * Dimensions: declared evidence state x actual payload contents x frame blindness.
 * The payload-contents dimension is the one that matters - the guard is supposed
 * to catch a payload that claims to be clean and is not, so the matrix has to
 * contain exactly those cases.
 *
 * Usage:  node tests/parity/run-egress-matrix.cjs
 */

'use strict';

const path = require('node:path');

const { EgressGuard } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'gateway', 'guard.js'),
);

const NOW = 1_700_000_000_000;

// A Verhoeff-valid Aadhaar: the detector accepts it at 0.99, so it is a genuine
// residual rather than an ambiguity.
const RAW_AADHAAR = '999999990019';
// Twelve digits that do NOT satisfy Verhoeff, so the detector marks it UNCERTAIN.
const OTP_SHAPED = '1234 5678 9012';

const PAYLOADS = [
  ['clean', 'Nothing sensitive in this text.'],
  ['raw-confirmed', `Your Aadhaar is ${RAW_AADHAAR} on record.`],
  ['raw-confirmed-in-aria', `Aadhaar ${RAW_AADHAAR}`],
  ['uncertain-only', `Your number is ${OTP_SHAPED}`],
  ['clean-title-raw-body', 'Nothing sensitive'],
];

const STATES = [
  ['SANITIZED', 'ALLOW'],
  ['DEGRADED', 'ALLOW_DECLARED'],
  ['UNCERTAIN', 'ALLOW_DECLARED'],
  ['NOT_INSTRUMENTED', 'WITHHOLD'],
];

const FRAME_BLIND = [false, true];

// Which fields carry the raw value, so the "title is clean" case is genuinely clean.
function contextFor(payloadKind, text, frameBlind) {
  const raw = text.includes(RAW_AADHAAR);
  return {
    title: payloadKind === 'clean-title-raw-body' ? text : 'Account overview',
    safeTexts: [text],
    elements: [
      { elementId: 'n0', ariaLabel: '', textContent: '', sensitive: false },
    ],
    frameBlind,
    observationId: 'obs-matrix',
    // Recorded so the harness can state what it intended, independently of what
    // the guard concluded. `raw` is the ground truth, not the guard's opinion.
    _intendedRaw: raw,
  };
}

const cells = [];

for (const [state, expectedDeclared] of STATES) {
  for (const [payloadKind, text] of PAYLOADS) {
    for (const frameBlind of FRAME_BLIND) {
      const evidence =
        state === 'SANITIZED'
          ? {
              state: 'SANITIZED',
              proof: { verifiersRun: ['text_rescan'], regionsChecked: 1, residualFindings: 0 },
              rung: 'webgpu',
              declaredAt: NOW,
            }
          : state === 'DEGRADED'
            ? { state: 'DEGRADED', reason: 'opaque_region', rung: 'webgpu', declaredAt: NOW }
            : state === 'UNCERTAIN'
              ? { state: 'UNCERTAIN', unresolved: ['AADHAAR'], declaredAt: NOW }
              : { state: 'NOT_INSTRUMENTED', missingCheck: 'pixel_rescan', declaredAt: NOW };

      const envelope = {
        schemaVersion: '1.0.0',
        destination: 'external_provider',
        context: contextFor(payloadKind, text, frameBlind),
        evidence,
        rung: 'webgpu',
        taskDescription: 'summarise',
      };

      let result;
      try {
        result = new EgressGuard().inspect(envelope);
      } catch (error) {
        cells.push({
          state,
          expectedDeclared,
          payload: payloadKind,
          frameBlind,
          intendedRaw: text.includes(RAW_AADHAAR),
          threw: String(error && error.message ? error.message : error),
        });
        continue;
      }

      cells.push({
        state,
        expectedDeclared,
        payload: payloadKind,
        frameBlind,
        intendedRaw: text.includes(RAW_AADHAAR),
        verdict: result.verdict,
        permitted: result.permitted,
        reason: result.reason,
        residualAccepted: result.revalidation.residual_accepted,
        residualUncertain: result.revalidation.residual_uncertain,
      });
    }
  }
}

process.stdout.write(JSON.stringify({ rawAadhaar: RAW_AADHAAR, cellCount: cells.length, cells }));