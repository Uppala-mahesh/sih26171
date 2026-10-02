/**
 * SIH26171 — Service worker: the enclave (Z1) and the coordinator.
 *
 * ── Why this file runs the pipeline rather than an offscreen document ────────
 * Z1 was originally an offscreen document, because the design assumed Z1 needed a
 * real `document` to rasterise page pixels. It needs one for nothing else: the
 * content script extracts text, and every privacy operation afterwards is pure
 * computation.
 *
 * The offscreen route was removed from the critical path after it produced two
 * identical "Receiving end does not exist" failures from two different causes -
 * one of them a race between `createDocument()` resolving and the offscreen
 * module registering its listener. That race is inherent to the API, not to this
 * code, and a security boundary should not be built on top of a race.
 *
 * The security property is unchanged. Raw page content still exists on exactly
 * one side of one boundary: a page cannot reach a service worker's memory, its
 * heap, or its module scope. The vault is created per observation.
 *
 * ── What this costs, stated plainly ──────────────────────────────────────────
 * A service worker has NO `document`, so it CANNOT rasterise page pixels. Rather
 * than pretend otherwise, the frame source returns nothing and the pipeline
 * derives `NOT_INSTRUMENTED`, which the guard turns into `WITHHOLD`. The system
 * says "I could not check the pixels, so I am not transmitting" rather than
 * claiming a clean scan of something it never saw. That is the four-state
 * contract doing its job - and it is exactly why the pixel weight is not yet
 * earned, which the README states rather than hides.
 *
 * ── The message-flow rule ────────────────────────────────────────────────────
 * `chrome.tabs.sendMessage` reaches CONTENT SCRIPTS.
 * `chrome.runtime.sendMessage` from the worker reaches EXTENSION PAGES.
 * With the offscreen document gone the worker needs only the first.
 */

import { EgressGuard } from '../../../packages/gateway/guard.js';
import { PlaceholderVault } from '../../../packages/privacy/vault.js';
import { detect } from '../../../packages/privacy/detector.js';
import { CapabilityResolver } from '../../../packages/vision/capability/ladder.js';
import { runPipeline, type PageAdapters, type PipelineResult } from '../../../packages/pipeline/orchestrator.js';
import type { CollectRequest } from './messages.js';

let step = 0;
function trace(message: string): void {
  step += 1;
  console.log(`[sih ${step}] ${message}`);
}

// A bare "Uncaught (in promise)" hides the step that produced it.
self.addEventListener('unhandledrejection', (event) => {
  console.error('[sih] unhandled rejection:', event.reason);
  event.preventDefault();
});

function observationId(): string {
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return 'obs-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Capability probes, resolved inside the worker.
 *
 * A probe that throws is UNAVAILABLE rather than assumed working: "it threw"
 * means the rung is not usable, and claiming otherwise is the DA-6 lie.
 */
const PROBES = [
  {
    rung: 'webgpu' as const,
    async probe() {
      const gpu = (
        globalThis as {
          navigator?: { gpu?: { requestAdapter(): Promise<unknown> } };
        }
      ).navigator?.gpu;
      if (!gpu) {
        return { available: false as const, reason: 'navigator.gpu is undefined' };
      }
      const adapter = await gpu.requestAdapter();
      return adapter
        ? { available: true as const, detail: 'adapter acquired' }
        : { available: false as const, reason: 'requestAdapter returned null' };
    },
  },
  {
    rung: 'wasm' as const,
    async probe() {
      return typeof WebAssembly === 'object'
        ? { available: true as const, detail: 'WebAssembly present' }
        : { available: false as const, reason: 'WebAssembly undefined' };
    },
  },
];

function buildAdapters(
  collected: CollectRequest,
  observation: string,
  rung: PageAdapters['capability']['rung'],
): PageAdapters {
  return {
    observationId: observation,
    url: collected.url,
    title: collected.title,
    // Zero rather than a guess. The worker has no viewport, and inventing one
    // would put a fabricated number into the outbound payload.
    viewport: { width: 0, height: 0 },
    frameBlind: collected.frameBlind,
    capability: { rung, canVerifyPixels: true },
    captureText: () =>
      collected.segments.map((segment) => ({
        elementId: segment.elementId,
        text: segment.text,
        tagName: segment.tagName,
        ariaLabel: segment.ariaLabel,
      })),
    // A service worker has no `document`, so it cannot rasterise page pixels.
    // Returning nothing makes the pipeline derive NOT_INSTRUMENTED, which the
    // guard turns into WITHHOLD. Claiming an empty scan was clean would be the
    // v1 defect; this is the honest alternative.
    captureFrames: () => [],
    now: () => Date.now(),
  };
}

/**
 * Report a failure to the operator.
 *
 * Every call is individually guarded. A rejected `setBadgeText` inside a catch
 * block produces a NEW unhandled rejection that replaces the real error with
 * "Uncaught (in promise)", which is how a collection failure once presented as a
 * message-routing failure. The surface reporting the problem must not become a
 * second, louder problem.
 */
async function reportFailure(detail: string): Promise<void> {
  trace(`FAILED: ${detail}`);
  console.warn('[sih] ' + detail);
  try {
    await chrome.action.setBadgeText({ text: 'ERR' });
    await chrome.action.setBadgeBackgroundColor({ color: '#b42318' });
    await chrome.action.setTitle({ title: `SIH26171 — ${detail}` });
  } catch (error) {
    console.warn('[sih] could not even set the badge:', error);
  }
}

/**
 * Surface the verdict where the operator can see it without opening devtools.
 *
 * A privacy tool that silently succeeds is indistinguishable from one that is
 * broken, so the declared state goes on the badge. `HOLD` is the important one:
 * it means the system refused to transmit.
 */
async function announce(result: PipelineResult): Promise<void> {
  const state = result.evidence.state;
  const reason = result.pixelFailure ?? result.transmitError;
  const badge = {
    SANITIZED: { text: 'OK', color: '#1a7f37' },
    DEGRADED: { text: 'DEG', color: '#9a6700' },
    UNCERTAIN: { text: 'UNC', color: '#9a6700' },
    NOT_INSTRUMENTED: { text: 'HOLD', color: '#b42318' },
  }[state];

  trace(`verdict ${state}, transmitted=${result.transmitted}`);

  try {
    await chrome.action.setBadgeText({ text: badge?.text ?? '?' });
    await chrome.action.setBadgeBackgroundColor({ color: badge?.color ?? '#57606a' });
    await chrome.action.setTitle({
      title:
        `SIH26171 — ${state}\n` +
        `rung: ${result.rung}\n` +
        `redactions: ${result.redactionCount}\n` +
        `text segments: ${result.textSegments}\n` +
        `frames verified: ${result.framesVerified}\n` +
        `transmitted: ${result.transmitted}` +
        (reason ? `\n${reason}` : '') +
        `\n\nNOTE: this build has no DOM, so page pixels cannot be inspected. ` +
        `The payload is withheld rather than declared clean.`,
    });
  } catch (error) {
    console.warn('[sih] could not set the badge:', error);
  }
}

/**
 * The single user-initiated entry point.
 *
 * The worker asks the CONTENT SCRIPT to collect, and only what the content script
 * returns ever reaches the pipeline. The worker never reads the page itself, so
 * it cannot become a second place raw content lives.
 */
chrome.action.onClicked.addListener((tab) => {
  const tabId = tab.id;
  if (tabId === undefined) return;

  void (async () => {
    try {
      trace('clicked: asking the content script to collect');
      // Typed `void` by @types/chrome, because the response comes from a content
      // script this module cannot see. Cast through `unknown`, never straight to
      // CollectRequest: the shape is checked immediately below.
      const reply = (await chrome.tabs.sendMessage(tabId, {
        kind: 'COLLECT',
      })) as unknown;
      const collected = reply as CollectRequest | undefined;
      trace(`content script answered: ${collected ? collected.kind : 'nothing'}`);

      if (!collected || collected.kind !== 'COLLECT' || !Array.isArray(collected.segments)) {
        await reportFailure('the content script returned no collection');
        return;
      }

      trace(`collected ${collected.segments.length} text segment(s)`);

      const ladder = await new CapabilityResolver(PROBES).resolve();
      trace(`capability resolved: ${ladder.active}`);

      const observation = observationId();
      const vault = new PlaceholderVault(observation);
      const guard = new EgressGuard();

      const result = runPipeline(
        buildAdapters(collected, observation, ladder.active),
        { vault, guard, detect },
        'summarise the active page',
      );
      trace(
        `pipeline finished: ${result.evidence.state}, ` +
          `${result.redactionCount} redaction(s), transmitted=${result.transmitted}`,
      );

      // FR-VLT-4: task end revokes resolution. The vault must not outlive the
      // observation even though nothing else reads it afterwards.
      vault.clear();

      await announce(result);
    } catch (error) {
      // The most likely cause of a send failure is a tab that was already open
      // when the extension was installed or reloaded: content scripts are
      // injected at page load, not retroactively.
      const text = String(error);
      await reportFailure(
        text.includes('Receiving end')
          ? 'no content script in this tab — RELOAD THE PAGE (F5) and try again'
          : `could not observe: ${text}`,
      );
    }
  })();
});

