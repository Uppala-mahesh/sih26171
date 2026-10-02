/**
 * SIH26171 — Service worker: COORDINATOR ONLY.
 *
 * The worker is the least trusted context that still needs to exist, because it
 * is the only one that survives tab close and the only one Chrome lets us open an
 * offscreen document from. It therefore does the smallest useful job:
 *
 *   1. receive a COLLECT message from the content script
 *   2. open (or reuse) the offscreen document
 *   3. forward an OBSERVE request
 *   4. return the ObserveResponse to whoever asked
 *
 * ── What this file deliberately cannot do ────────────────────────────────────
 * It imports no detector, no vault, no redactor, no guard and no policy engine.
 * There is no code path by which page text reaches this context: the collected
 * segments are held only inside the `onClicked` handler's arguments and are
 * handed straight to Z1.
 *
 * That is why `ObserveResponse` can be returned to a caller without a leak
 * review. Raw content exists on exactly one side of the Z1 boundary.
 *
 * ── The message-flow rule ────────────────────────────────────────────────────
 * `chrome.tabs.sendMessage` reaches CONTENT SCRIPTS.
 * `chrome.runtime.sendMessage` from the worker reaches EXTENSION PAGES.
 * Sending a message to the wrong one produces "Could not establish connection.
 * Receiving end does not exist", and the extension then does nothing at all.
 * Every `sendMessage` below is annotated with which world it targets.
 */

import type {
  CollectRequest,
  ObserveRequest,
  ObserveResponse,
} from './messages.js';

const OFFSCREEN_PATH = 'offscreen/offscreen.html';
const OFFSCREEN_READY_TIMEOUT_MS = 5_000;

/**
 * Chrome permits ONE offscreen document per extension, so reuse is a
 * correctness requirement rather than an optimisation - a second
 * `createDocument` call throws.
 */
let creating: Promise<void> | null = null;

/**
 * Resolved when Z1 announces that its message listener is registered.
 *
 * `chrome.offscreen.createDocument()` resolves when the DOCUMENT is created, not
 * when its module has EVALUATED. The offscreen document registers its
 * `onMessage` listener as a side effect of that evaluation, so sending the instant
 * creation resolves races it and fails with "Receiving end does not exist".
 *
 * This promise is the handshake that closes that window.
 */
let offscreenReady: Promise<void> | null = null;
let markOffscreenReady: (() => void) | null = null;

function awaitOffscreenReady(): Promise<void> {
  if (!offscreenReady) {
    offscreenReady = new Promise<void>((resolve) => {
      markOffscreenReady = resolve;
      // Bounded: a readiness ping that never arrives must surface as a failure
      // rather than hanging the click forever.
      setTimeout(resolve, OFFSCREEN_READY_TIMEOUT_MS);
    });
  }
  return offscreenReady;
}

/**
 * The one listener the worker keeps: Z1 announcing readiness.
 *
 * The message shapes are type-only imports and the comparison below is a string
 * test, so the built worker still has ZERO runtime imports.
 */
chrome.runtime.onMessage.addListener(
  (
    message: unknown,
    _sender: chrome.runtime.MessageSender,
    sendResponse: (r: unknown) => void,
  ) => {
    const kind = (message as { kind?: unknown } | null)?.kind;
    if (kind !== 'OFFSCREEN_READY') return false;
    markOffscreenReady?.();
    markOffscreenReady = null;
    sendResponse({ kind: 'READY_ACK' });
    return false;
  },
);

async function ensureOffscreen(): Promise<void> {
  const alreadyOpen = await chrome.offscreen.hasDocument();
  if (!alreadyOpen) {
    if (!creating) {
      creating = chrome.offscreen
        .createDocument({
          url: OFFSCREEN_PATH,
          reasons: ['DOM_PARSER' as chrome.offscreen.Reason],
          justification:
            'Read page text and rasterise page pixels on-device so sensitive ' +
            'data can be redacted before anything leaves the browser.',
        })
        .then(() => undefined);
    }
    try {
      await creating;
    } finally {
      creating = null;
    }
  }
  // The document exists; now wait for its module to have run.
  await awaitOffscreenReady();
}

function observationId(): string {
  // Random per observation. Not a secret, but it must not be guessable enough
  // to let a page correlate two observations of itself across a task.
  const bytes = new Uint8Array(8);
  crypto.getRandomValues(bytes);
  return 'obs-' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function observe(
  collected: CollectRequest,
  taskDescription: string,
): Promise<ObserveResponse> {
  await ensureOffscreen();

  const request: ObserveRequest = {
    kind: 'OBSERVE',
    observationId: observationId(),
    taskDescription,
    collected,
  };

  // `chrome.runtime.sendMessage` from the worker targets EXTENSION PAGES, which
  // is the offscreen document. `chrome.tabs.sendMessage` targets CONTENT
  // SCRIPTS. Mixing the two is how you get "Receiving end does not exist".
  return (await chrome.runtime.sendMessage(request)) as ObserveResponse;
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
async function announce(result: ObserveResponse): Promise<void> {
  const badge = {
    SANITIZED: { text: 'OK', color: '#1a7f37' },
    DEGRADED: { text: 'DEG', color: '#9a6700' },
    UNCERTAIN: { text: 'UNC', color: '#9a6700' },
    NOT_INSTRUMENTED: { text: 'HOLD', color: '#b42318' },
  }[result.state as 'SANITIZED' | 'DEGRADED' | 'UNCERTAIN' | 'NOT_INSTRUMENTED'];

  try {
    await chrome.action.setBadgeText({ text: badge?.text ?? '?' });
    await chrome.action.setBadgeBackgroundColor({ color: badge?.color ?? '#57606a' });
    await chrome.action.setTitle({
      title:
        `SIH26171 — ${result.state}\n` +
        `rung: ${result.rung}\n` +
        `redactions: ${result.redactions}\n` +
        `frames verified: ${result.framesVerified}\n` +
        `transmitted: ${result.transmitted}` +
        (result.reason ? `\n${result.reason}` : ''),
    });
  } catch (error) {
    console.warn('[sih] could not set the badge:', error);
  }
}

/**
 * The single user-initiated entry point.
 *
 * Order matters and is the whole point: the worker asks the CONTENT SCRIPT to
 * collect, and only what the content script returns ever reaches Z1. The worker
 * never reads the page itself, so it cannot become a second place raw content
 * lives.
 */
chrome.action.onClicked.addListener((tab) => {
  // Captured as a const: TypeScript does not narrow `tab.id` inside the async
  // closure, and passing `tab.id` directly produced a `number | undefined` error
  // at the sendMessage call.
  const tabId = tab.id;
  if (tabId === undefined) return;

  void (async () => {
    try {
      // Typed `void` by @types/chrome, because the response comes from a content
      // script this module cannot see. Cast through `unknown`, never straight to
      // CollectRequest: the shape is checked immediately below.
      const reply = (await chrome.tabs.sendMessage(tabId, {
        kind: 'COLLECT',
      })) as unknown;
      const collected = reply as CollectRequest | undefined;

      if (!collected || collected.kind !== 'COLLECT') {
        await reportFailure('the content script returned no collection');
        return;
      }

      const result = await observe(collected, 'summarise the active page');
      await announce(result);
    } catch (error) {
      // The single most likely cause of a send failure here is a tab that was
      // already open when the extension was installed or reloaded: content
      // scripts are injected at page load, not retroactively. Saying so is more
      // useful than printing "Receiving end does not exist".
      const text = String(error);
      await reportFailure(
        text.includes('Receiving end')
          ? 'no content script in this tab — RELOAD THE PAGE (F5) and try again'
          : `could not observe: ${text}`,
      );
    }
  })();
});
