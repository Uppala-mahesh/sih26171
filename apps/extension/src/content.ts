/**
 * SIH26171 — Content script: COLLECTOR ONLY.
 *
 * Deliberately a CLASSIC script with zero imports.
 *
 * A content script runs in the page's world, alongside page-controlled code. It
 * is the least trustworthy context in the whole system, so it is given the
 * smallest possible job and no capability at all: it reads text and posts it
 * inward. It cannot reach the vault, the detector, or the guard, and it holds no
 * reference to any of them.
 *
 * That restraint is the design. If a compromised content script could ask for a
 * secret, the B-6 binding would stop mattering — the page could simply use this
 * script as a confused deputy. It cannot: it has no channel to the vault at all.
 *
 * ── What it deliberately does NOT do ─────────────────────────────────────────
 * It does not detect, redact, or decide anything. It does not know what counts
 * as sensitive. An attacker who replaced this file entirely would obtain text
 * extraction — which the page already has — and nothing else.
 */

'use strict';

(function () {
  /** Bounded so a pathological page cannot exhaust memory in the collector. */
  var MAX_SEGMENTS = 5000;
  var MAX_SEGMENT_CHARS = 20000;

  function elementId(node: Node, index: number) {
    // Stable within one collection, not a secret: the vault binds to it for the
    // lifetime of a single observation and never after.
    void node;
    return 'n' + index;
  }

  function collect() {
    var segments = [];
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node: Node) {
        var text = node.nodeValue;
        if (!text || text.trim() === '') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    var node: Node | null;
    var index = 0;
    while ((node = walker.nextNode()) !== null && segments.length < MAX_SEGMENTS) {
      var text = (node.nodeValue ?? '').trim();
      if (text.length > MAX_SEGMENT_CHARS) text = text.slice(0, MAX_SEGMENT_CHARS);
      var parent = node.parentElement;
      segments.push({
        elementId: elementId(node, index++),
        text: text,
        tagName: parent ? parent.tagName : 'TEXT',
        ariaLabel: parent ? parent.getAttribute('aria-label') || '' : '',
      });
    }

    return segments;
  }

  /**
   * FR-PER-4: declare frame blindness rather than silently omitting frames.
   *
   * `all_frames` is false in the manifest, so this collector never sees
   * cross-origin frame content. Reporting that is what lets the pipeline declare
   * NOT_INSTRUMENTED instead of quietly claiming full coverage.
   */
  function frameBlind() {
    try {
      return document.querySelectorAll('iframe, frame').length > 0;
    } catch (error) {
      return true;
    }
  }

  chrome.runtime.sendMessage(
    {
      kind: 'COLLECT',
      url: location.href,
      title: document.title,
      segments: collect(),
      frameBlind: frameBlind(),
    },
    function () {
      // Reading lastError suppresses the console noise that appears when the
      // worker is asleep. There is deliberately no retry: a collection that
      // failed simply did not happen, and claiming otherwise would be worse.
      void chrome.runtime.lastError;
    }
  );
})();
