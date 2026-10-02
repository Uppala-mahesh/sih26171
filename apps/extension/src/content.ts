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

  /**
   * Count the surfaces that can CONCEAL text from the walker above.
   *
   * A `<canvas>`, an `<img>` carrying a photographed ID, a `<video>` frame, an
   * inline `<svg>` label, or a CSS background can all display a name or a number
   * that appears nowhere in the DOM text. This is the collector's one job beyond
   * walking text, and it is what makes the worker's verdict honest: if this
   * returns 0, there is genuinely nothing painted, and "I checked the pixels"
   * means "there were no pixels to check".
   *
   * Bounded and defensive: `getComputedStyle` throws on detached nodes, and a
   * hostile page can contain thousands of elements.
   */
  function visualSurfaces() {
    var selectors = 'canvas, img, video, svg, picture, object, embed, [style*="background"]';
    var nodes;
    try {
      nodes = document.querySelectorAll(selectors);
    } catch (error) {
      return undefined; // unknown, not zero
    }
    var count = nodes.length;
    try {
      var all = document.querySelectorAll('*');
      var limit = Math.min(all.length, 5000);
      for (var i = 0; i < limit; i += 1) {
        var el = all[i];
        if (!el) continue;
        var bg = window.getComputedStyle(el).backgroundImage;
        if (bg && bg !== 'none') count += 1;
      }
    } catch (error) {
      // A partial count would understate the risk, and understating it is the one
      // direction this number must never err in.
      return undefined;
    }
    return count;
  }

  chrome.runtime.onMessage.addListener(
    function (message, _sender, sendResponse) {
      // Nothing happens on page load. Collection begins only when the operator
      // clicks the toolbar button, and only for that tab. A content script that
      // collected on load would read every page the user merely visits, which is
      // the opposite of a privacy tool (FR-AGT-7).
      if (!message || message.kind !== 'COLLECT') return false;

      sendResponse({
        kind: 'COLLECT',
        url: location.href,
        title: document.title,
        segments: collect(),
        frameBlind: frameBlind(),
        visualSurfaces: visualSurfaces(),
      });
      return false; // responded synchronously
    }
  );
})();
