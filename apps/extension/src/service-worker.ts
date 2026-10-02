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

/**
 * Chrome permits ONE offscreen document per extension.
 *
 * Reusing it is therefore not an optimisation, it is a correctness requirement -
 * a second `createDocument` call throws. `creating` also collapses concurrent
 * callers onto one promise instead of letting them race.
 */
let creating: Promise<void> | null = null;

async function ensureOffscreen(): Promise<void> {
  if (await chrome.offscreen.hasDocument()) return;
  if (creating) {
    await creating;
    return;
  }
  creating = chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: ['DOM_PARSER' as chrome.offscreen.Reason],
    justification:
      'Read page text and rasterise page pixels on-device so sensitive data can ' +
      'be redacted before anything leaves the browser.',
  });
  try {
    await creating;
  } finally {
    creating = null;
  }
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
        await chrome.action.setBadgeText({ text: 'ERR' });
        await chrome.action.setBadgeBackgroundColor({ color: '#b42318' });
        return;
      }

      const result = await observe(collected, 'summarise the active page');
      await announce(result);
    } catch (error) {
      // A failed collection is reported as a failure. Claiming otherwise is the
      // behaviour this whole project exists to eliminate.
      await chrome.action.setBadgeText({ text: 'ERR' });
      await chrome.action.setBadgeBackgroundColor({ color: '#b42318' });
      await chrome.action.setTitle({
        title: `SIH26171 — could not observe: ${String(error)}`,
      });
    }
  })();
});
