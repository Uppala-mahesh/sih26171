'use strict';

/**
 * Capability ladder exerciser.
 *
 * Runs every branch of the resolver with INJECTED probes and reports each
 * outcome as JSON, so tests/contract/test_capability_ladder.py can assert on
 * them. No browser is involved: that is the whole point of injecting probes, and
 * it is why the degradation path is reachable from CI at all.
 *
 * Usage:  node tests/vision/run-ladder.cjs
 */

const path = require('node:path');

const {
  CapabilityResolver,
  CAPABILITY_LADDER,
} = require(path.join(__dirname, '..', '..', 'dist', 'packages', 'vision', 'capability', 'ladder.js'));

/** Build a probe that reports a fixed outcome. */
function probe(rung, available, detail = 'stubbed') {
  return {
    rung,
    probe: async () => (available ? { available: true, detail } : { available: false, reason: detail }),
  };
}

function throwingProbe(rung, message) {
  return {
    rung,
    probe: async () => {
      throw new Error(message);
    },
  };
}

const ALL = [
  probe('webgpu', true, 'adapter acquired'),
  probe('wasm-simd', true, 'simd module validated'),
  probe('wasm', true, 'wasm present'),
];

async function scenario(name, probes, preferred) {
  const resolver = new CapabilityResolver(probes, preferred);
  const result = await resolver.resolve();
  const declaration = await resolver.declaration();
  return {
    name,
    active: result.active,
    preferred: result.preferred,
    degraded: result.degraded,
    reason: result.degradationReason,
    detail: result.degradationDetail,
    declarationState: declaration.state,
    probedRungs: result.outcomes.map(([rung]) => rung),
  };
}

async function main() {
  const results = [];

  results.push(await scenario('full capability', ALL));
  results.push(await scenario('no webgpu', [probe('webgpu', false, 'no adapter'), ...ALL.slice(1)]));
  results.push(await scenario('no gpu and no simd', [
    probe('webgpu', false, 'no adapter'),
    probe('wasm-simd', false, 'simd unsupported'),
    probe('wasm', true, 'wasm present'),
  ]));
  results.push(await scenario('dom only', [
    probe('webgpu', false, 'no adapter'),
    probe('wasm-simd', false, 'simd unsupported'),
    probe('wasm', false, 'no wasm'),
  ]));
  results.push(await scenario('no probes registered at all', []));
  results.push(await scenario('probes that throw', [
    throwingProbe('webgpu', 'requestAdapter rejected'),
    throwingProbe('wasm-simd', 'compile failed'),
    probe('wasm', true, 'wasm present'),
  ]));
  results.push(await scenario('every probe throws', [
    throwingProbe('webgpu', 'boom'),
    throwingProbe('wasm-simd', 'boom'),
    throwingProbe('wasm', 'boom'),
  ]));
  results.push(await scenario('preferred is not the best available', ALL, 'wasm-simd'));
  results.push(await scenario('only webgpu available', [probe('webgpu', true, 'adapter'), probe('wasm-simd', false, 'nope'), probe('wasm', false, 'nope')]));

  process.stdout.write(
    JSON.stringify({ ladder: CAPABILITY_LADDER, scenarios: results }),
  );
}

main().catch((error) => {
  process.stderr.write(`ladder exerciser failed: ${error.message}\n`);
  process.exit(1);
});
