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
    // The content script is the only context with a DOM, so it is the only one
    // that can say whether painted content exists at all. This number decides
    // between SANITIZED and WITHHOLD, and it is passed through UNVERIFIED: the
    // worker never inspects or adjusts it.
    visualSurfaces: collected.visualSurfaces,
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
        (state === 'SANITIZED'
          ? '\n\nThis page has no images, canvas, video or CSS backgrounds, so' +
            '\nthere are no painted pixels that could conceal text. The text was' +
            '\ninspected and the sensitive values replaced with placeholders.'
          : '\n\nThis page has painted content that cannot be inspected from here,' +
            '\nso the payload is withheld rather than declared clean.'),
    });
  } catch (error) {
    console.warn('[sih] could not set the badge:', error);
  }
}

/**
 * Get page text out of a tab, injecting the collector if it is not there yet.
 *
 * Declarative content scripts are injected at PAGE LOAD. A tab that was open
 * before the extension was installed or reloaded therefore has no receiver, and
 * `tabs.sendMessage` fails with "Receiving end does not exist" - the same string
 * it uses for every other routing problem, which is why this cost several rounds
 * of misdiagnosis.
 *
 * Rather than ask the operator to reload the page, inject on demand. The
 * `scripting` permission is already declared, so this needs no new capability and
 * no new prompt: the extension already has `<all_urls>`.
 */
async function collectFrom(tabId: number): Promise<CollectRequest | undefined> {
  const ask = async () =>
    (await chrome.tabs.sendMessage(tabId, { kind: 'COLLECT' })) as unknown;

  try {
    return (await ask()) as CollectRequest | undefined;
  } catch (error) {
    if (!String(error).includes('Receiving end')) throw error;
    trace('no receiver; injecting the collector into the tab');
  }

  // Throws for pages an extension may never touch: chrome://*, the Web Store,
  // other extensions' pages, and file:// without "Allow access to file URLs".
  // That is a genuine limit of the platform, not a bug, and it is reported as
  // such rather than as a generic failure.
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ['content/content.js'],
  });
  trace('collector injected; asking again');

  return (await ask()) as CollectRequest | undefined;
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
      trace('clicked: collecting from the tab');
      // Cast through `unknown`, never straight to CollectRequest: the shape comes
      // from a content script this module cannot see, and is checked below.
      const collected = await collectFrom(tabId);
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
      // Chrome reports every unreachable context with the same sentence, so the
      // only way to be useful is to name the CAUSES rather than repeat it. In
      // order of likelihood: a page type no extension may script at all, and a
      // genuinely broken build.
      const text = String(error);
      await reportFailure(
        /Cannot access|Missing host permission|chrome:\/\//i.test(text)
          ? 'this page type cannot be scripted (chrome:// pages, the Web Store, ' +
            'and other extensions\' pages) - open a normal website and try again'
          : /Receiving end/i.test(text)
            ? 'no collector in this tab and injection was refused - reload the page (F5)'
            : `could not observe: ${text}`,
      );
    }
  })();
});

