/**
 * Exhaustive policy-matrix runner.
 *
 * ── The question ─────────────────────────────────────────────────────────────
 * "Can any combination of facts talk the policy engine into performing an action it
 * should refuse?" That is the single most consequential question in the system,
 * and it was previously answered by ~12 hand-written cases.
 *
 * The evidence matrix (run-evidence-matrix.cjs) exists because every BRANCH had a
 * test and no COMBINATION did. The same blind spot applies here with worse
 * consequences, so the whole cross product is enumerated.
 *
 * Dimensions: action validity x rule presence x origin x payload ceiling x
 * B-6 binding x irreversibility x external visibility x approval quality.
 *
 * Approval quality is the interesting one, because it is the only input that can
 * TURN a refusal into a permission. Four qualities are exercised - none, matching,
 * bound-elsewhere, and expired - because a confirmation that leaks on any of the
 * last three is a standing permission, which is what the design forbids.
 *
 * Usage:  node tests/parity/run-policy-matrix.cjs
 */

'use strict';

const path = require('node:path');

const { PolicyEngine, ACTION_TYPES } = require(
  path.join(__dirname, '..', '..', 'dist', 'packages', 'policy', 'engine.js'),
);

// ── dimensions ──────────────────────────────────────────────────────────────
const ACTION_TYPES_USED = ['OBSERVE', 'DETOKENIZE', 'TRANSMIT', 'NOT_AN_ACTION'];
const RULE_PRESENT = [true, false];
const ORIGIN_OK = [true, false];
const PAYLOAD_OVER_CEILING = [false, true];
const BINDING_PRESENT = [true, false];
const IRREVERSIBLE = [false, true];
const EXTERNALLY_VISIBLE = [false, true];
// none | matching | wrong-target | wrong-origin | expired
const APPROVAL = ['none', 'matching', 'wrong-target', 'wrong-origin', 'expired'];

const NOW = 1_000;
const CEILING = 100;
const ORIGIN = 'https://app.test';
const ELEMENT = 'btn-1';

function approvalFor(quality) {
  if (quality === 'none') return undefined;
  const scope = {
    actionType: 'TRANSMIT',
    targetOrigin: ORIGIN,
    targetElementId: quality === 'wrong-target' ? 'btn-OTHER' : ELEMENT,
    issuedAt: 900,
    expiresAt: quality === 'expired' ? 950 : 90_000,
  };
  if (quality === 'wrong-origin') scope.targetOrigin = 'https://evil.test';
  return { scope, grantedBy: 'operator' };
}

const cells = [];

for (const actionType of ACTION_TYPES_USED) {
  for (const rulePresent of RULE_PRESENT) {
    for (const originOk of ORIGIN_OK) {
      for (const payloadOver of PAYLOAD_OVER_CEILING) {
        for (const binding of BINDING_PRESENT) {
          for (const irreversible of IRREVERSIBLE) {
            for (const external of EXTERNALLY_VISIBLE) {
              for (const approval of APPROVAL) {
                // Every VALID action is permitted by origin, so the matrix reaches
                // the later branches. Permitting only OBSERVE would make
                // DETOKENIZE always die at deny-by-default and leave the B-6 binding
                // requirement - a security branch - completely unexercised, which is
                // precisely the blind spot this matrix exists to close.
                const rules = rulePresent
                  ? ACTION_TYPES.map((t) => ({ actionType: t, origins: [ORIGIN] }))
                  : [];
                const engine = new PolicyEngine(rules, {
                  maxPayloadBytes: CEILING,
                  now: () => NOW,
                });

                const proposal = {
                  actionType,
                  targetOrigin: originOk ? ORIGIN : 'https://elsewhere.test',
                  targetElementId: ELEMENT,
                  irreversible,
                  externallyVisible: external,
                  payloadBytes: payloadOver ? CEILING + 1 : 10,
                  boundObservationId: binding ? 'obs-1' : undefined,
                };

                const d = engine.evaluate(proposal, approvalFor(approval));
                cells.push({
                  actionType,
                  rulePresent,
                  originOk,
                  payloadOver,
                  binding,
                  irreversible,
                  external,
                  approval,
                  decision: d.decision,
                  rule: d.rule,
                  scopeBound: d.approvalScope !== undefined,
                });
              }
            }
          }
        }
      }
    }
  }
}

process.stdout.write(
  JSON.stringify({ actionTypes: [...ACTION_TYPES], cellCount: cells.length, cells }),
);