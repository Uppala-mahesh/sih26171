/**
 * Runtime harness: EXECUTE the built service worker.
 *
 * ── Why this exists ──────────────────────────────────────────────────────────
 * 327 tests passed while the extension did not work in a browser. They tested
 * the privacy core in Node and asserted properties of the built artifact by
 * GREPPING ITS TEXT. Nothing ever imported `background/service-worker.js` and
 * ran it. Every defect in this file's message flow - a missing export, a module
 * that throws on evaluation, a handler that rejects - was invisible to the entire
 * suite.
 *
 * A grep can tell you a call appears. It cannot tell you the call happens.
 *
 * The mock is deliberately strict: every API the worker touches must exist, and
 * anything unexpected throws. A lenient mock lets a broken worker look healthy,
 * which is the same vacuous-pass failure mode as a grep assertion.
 *
 * Usage:  node tests/runtime/worker_harness.mjs
 */

import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { existsSync } from 'node:fs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..', '..');
const WORKER = path.join(ROOT, 'dist-extension', 'background', 'service-worker.js');

if (!existsSync(WORKER)) {
  console.error(`worker not built: ${WORKER}\nrun: node infra/build-extension.cjs`);
  process.exit(1);
}

/** A minimal but STRICT chrome mock; anything unexpected throws. */
function makeChrome(behaviour) {
  const seen = { badge: [], title: [], messages: [] };
  const clicked = [];
  return {
    seen,
    clicked,
    chrome: {
      action: {
        onClicked: { addListener: (fn) => clicked.push(fn) },
        setBadgeText: async (d) => seen.badge.push(d.text),
        setBadgeBackgroundColor: async () => {},
        setTitle: async (d) => seen.title.push(d.title),
      },
      tabs: {
        sendMessage: async (tabId, message) => {
          seen.messages.push({ tabId, message });
          return behaviour.collect();
        },
      },
    },
  };
}

const OK_BADGES = ['OK', 'DEG', 'UNC', 'HOLD'];
const SCENARIOS = [
  {
    name: 'a page full of PII reaches the pipeline and is redacted',
    async collect() {
      return {
        kind: 'COLLECT',
        url: 'https://example.test/form',
        title: 'Application',
        segments: [
          { elementId: 'n0', text: 'Aadhaar 1234 5678 9012', tagName: 'SPAN', ariaLabel: '' },
          { elementId: 'n1', text: 'Call me on +91 98765 43210', tagName: 'P', ariaLabel: '' },
          { elementId: 'n2', text: 'Card 4111 1111 1111 1111', tagName: 'DIV', ariaLabel: '' },
          { elementId: 'n3', text: 'Ordinary prose with nothing sensitive.', tagName: 'P', ariaLabel: '' },
        ],
        frameBlind: false,
      };
    },
    expect(seen) {
      const title = seen.title.at(-1);
      assert.ok(title, 'no title was ever set: the handler never completed');
      assert.match(title, /SIH26171/);
      assert.ok(
        OK_BADGES.includes(seen.badge.at(-1)),
        `badge was ${seen.badge.at(-1)}, not one of the four declared states`,
      );
      // The decisive check: raw values must not reach anything the operator sees.
      for (const secret of ['1234 5678 9012', '98765 43210', '4111 1111 1111 1111']) {
        assert.ok(!title.includes(secret), `raw value leaked into the title: ${secret}`);
      }
      assert.match(title, /redactions: [1-9]/, 'no redactions for a PII-filled page');
    },
  },
  {
    name: 'no content script reports the likely cause, not a generic error',
    async collect() {
      throw new Error('Could not establish connection. Receiving end does not exist.');
    },
    expect(seen) {
      assert.equal(seen.badge.at(-1), 'ERR');
      assert.match(seen.title.at(-1), /RELOAD THE PAGE/);
    },
  },
  {
    name: 'a malformed payload is refused, not trusted',
    async collect() {
      return { kind: 'COLLECT', url: 'x', title: 'y' }; // no `segments`
    },
    expect(seen) {
      assert.equal(seen.badge.at(-1), 'ERR');
      assert.match(seen.title.at(-1), /no collection/);
    },
  },
];

let failures = 0;

for (const scenario of SCENARIOS) {
  const { chrome, seen, clicked } = makeChrome(scenario);
  globalThis.chrome = chrome;
  // The worker registers a rejection handler on `self`. Node has no `self` and no
  // ServiceWorkerGlobalScope, so both are provided here. `addEventListener` must
  // exist as a real function: Node's `globalThis` has none.
  globalThis.self = globalThis;
  globalThis.addEventListener ??= () => {};

  const unhandled = [];
  const onUnhandled = (reason) => unhandled.push(reason);
  process.on('unhandledRejection', onUnhandled);

  try {
    // Re-imported per scenario with a cache-busting query. Node caches ES modules
    // by URL, so without this every scenario would reuse the FIRST mock's
    // listener list and assert against a chrome object that no longer exists -
    // a harness that appears to test three things and tests one.
    await import(pathToFileURL(WORKER).href + `?scenario=${encodeURIComponent(scenario.name)}`);
    assert.equal(clicked.length, 1, 'the worker registered no action.onClicked listener');

    await clicked[0]({ id: 7 });
    await new Promise((r) => setTimeout(r, 50)); // let stray promises settle

    assert.deepEqual(unhandled, [], `unhandled rejection escaped: ${unhandled}`);
    scenario.expect(seen);
    console.log(`  PASS  ${scenario.name}`);
  } catch (error) {
    failures += 1;
    console.error(`  FAIL  ${scenario.name}\n        ${error.message}`);
  } finally {
    process.off('unhandledRejection', onUnhandled);
  }
}

console.log(
  failures === 0
    ? `\nworker harness: ${SCENARIOS.length}/${SCENARIOS.length} passed`
    : `\nworker harness: ${failures} of ${SCENARIOS.length} FAILED`,
);
process.exit(failures === 0 ? 0 : 1);