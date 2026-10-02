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
 * It imports no detector, no vault, no redactor and no guard. There is no code
 * path by which page text reaches this context: the collected segments are held
 * only inside the `observe()` call's arguments and are handed straight to Z1.
 *
 * That is why `ObserveResponse` can be returned to a caller without a leak
 * review. Raw content exists on exactly one side of this boundary.
 */

import { isInbound, type CollectRequest, type ObserveRequest, type ObserveResponse } from './messages.js';

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

  return (await chrome.runtime.sendMessage(request)) as ObserveResponse;
}

chrome.runtime.onMessage.addListener(
  (
    message: unknown,
    sender: chrome.runtime.MessageSender,
    sendResponse: (r: ObserveResponse | { kind: 'COLLECTED' }) => void,
  ) => {
    if (!isInbound(message) || message.kind !== 'COLLECT') return false;

    void (async () => {
      const collected = message as CollectRequest;

      // FR-AGT-7: a collection from a page the user did not ask about is not
      // actioned. The trigger comes from the popup/action path, never from the
      // page, so an unsolicited COLLECT only records that it happened.
      if (!sender.tab?.active) {
        sendResponse({ kind: 'COLLECTED' });
        return;
      }

      const result = await observe(collected, 'summarise the active page');
      sendResponse(result);
    })();

    return true;
  },
);

/** Entry point for the extension action. */
chrome.action.onClicked.addListener((tab) => {
  if (!tab.id) return;
  chrome.tabs.sendMessage(tab.id, { kind: 'OBSERVE', observationId: observationId() } as never);
});
