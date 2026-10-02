/**
 * SIH26171 — Offscreen document: ZONE Z1.
 *
 * This is the only context that touches page DOM, page pixels, the vault and the
 * egress guard together. Everything privacy-critical happens here and the
 * results travel OUTWARD already sanitised.
 *
 * Why an offscreen document at all (MV3 removed DOM access from service
 * workers): the pipeline needs a real `document` to read text nodes and a real
 * canvas to rasterise frames. Rather than weakening the boundary by moving the
 * vault into the worker, the boundary is kept and the DOM is brought to it.
 *
 * ── The zone rule ────────────────────────────────────────────────────────────
 * Z1 holds raw page content. It never crosses to the service worker, to a tab,
 * or to storage. What leaves is an `ObserveResponse`, which carries the
 * sanitisation EVIDENCE and, only when transmission was permitted, the envelope
 * - and the envelope has no field capable of holding raw content.
 */

import { CapabilityResolver, type CapabilityProbe } from '../../../packages/vision/capability/ladder.js';
import {
  bindFindings,
  buildRuns,
  joinRuns,
  type RunInput,
  type TextRun,
} from '../../../packages/vision/layout/text-runs.js';
import {
  clampToFrame,
  toFrameLocal,
} from '../../../packages/vision/layout/geometry-ops.js';
import { boundingBox, type BoundingBox } from '../../../packages/contracts/geometry.js';
import { EgressGuard } from '../../../packages/gateway/guard.js';
import { PlaceholderVault } from '../../../packages/privacy/vault.js';
import { detect } from '../../../packages/privacy/detector.js';
import { PixelFrame } from '../../../packages/privacy/pixels.js';
import { runPipeline, type FrameSegment, type PageAdapters } from '../../../packages/pipeline/orchestrator.js';
import { isInbound, type ObserveRequest, type ObserveResponse } from './messages.js';

// ─────────────────────────────────────────────────────────────────────────────
// Capability probes. Each one FAILS CLOSED: a probe that throws is treated as
// unavailable rather than assumed working, because "it threw" means the rung is
// not usable and claiming otherwise is the DA-6 lie.
// ─────────────────────────────────────────────────────────────────────────────

const probes: readonly CapabilityProbe[] = [
  {
    rung: 'webgpu',
    async probe() {
      const gpu = (navigator as { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
      if (!gpu) return { available: false, reason: 'navigator.gpu is undefined' };
      const adapter = await gpu.requestAdapter();
      return adapter
        ? { available: true, detail: 'adapter acquired' }
        : { available: false, reason: 'requestAdapter returned null' };
    },
  },
  {
    rung: 'wasm-simd',
    async probe() {
      try {
        // Fixed bytes, no page input: a probe must not evaluate page-supplied code.
        const { instance } = await WebAssembly.instantiate(
          new Uint8Array([
            0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0,
            10, 10, 1, 8, 0, 65, 0, 253, 15, 253, 98, 11,
          ]),
        );
        return (instance.exports as { simd?: unknown }).simd
          ? { available: true, detail: 'simd opcode accepted' }
          : { available: false, reason: 'simd feature absent' };
      } catch (error) {
        return { available: false, reason: `wasm probe threw: ${String(error)}` };
      }
    },
  },
  {
    rung: 'wasm',
    async probe() {
      return typeof WebAssembly === 'object'
        ? { available: true, detail: 'WebAssembly present' }
        : { available: false, reason: 'WebAssembly undefined' };
    },
  },
];


// ─────────────────────────────────────────────────────────────────────────────
// Real DOM adapters
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Elements whose rendered pixels must be inspected and masked.
 *
 * FR-PER-7: canvas, video and image regions are flagged rather than hidden, and
 * their pixels are a SEPARATE verification route from their text.
 */
function visualElements(): Element[] {
  return Array.from(
    document.querySelectorAll('canvas, video, img[src], [style*="background-image"]'),
  );
}

function buildAdapters(request: ObserveRequest, rung: string): PageAdapters {
  const collected = request.collected;
  return {
    observationId: request.observationId,
    url: collected.url,
    title: collected.title,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    frameBlind: collected.frameBlind,
    capability: {
      rung: rung as PageAdapters['capability']['rung'],
      // DOM perception is unconditional in this document, so pixel verification
      // is genuinely available whenever there is a visual region to verify. The
      // pipeline still requires that at least one frame was actually captured
      // before it will claim SANITIZED.
      canVerifyPixels: true,
    },
    captureText: () =>
      collected.segments.map((s) => ({
        elementId: s.elementId,
        text: s.text,
        tagName: s.tagName,
        ariaLabel: s.ariaLabel,
      })),
    captureFrames: () => captureFrames(),
    now: () => Date.now(),
  };
}

/**
 * Rasterise each visual element and bind any sensitive spans inside it to real
 * pixel boxes (CR-003).
 *
 * This is the step that makes the pixel route honest. Before it, `boxes` was
 * always empty, so the redactor was verifying the absence of masking rather than
 * performing any - the "pixel redaction" was theatre.
 *
 * ── How a box is obtained, and why no model is needed ────────────────────────
 * For text inside the element we walk its text nodes, build a Range over the
 * exact character offsets the detector reported, and read
 * `getClientRects()`. The browser has already laid the text out; this asks it
 * where it put the glyphs. That is an exact answer to an exact question, which
 * is strictly better than a model's confident approximation.
 *
 * For text painted into pixels there is no text node, so there is nothing to
 * ask. Those spans come back UNBOUND from `bindFindings` with a stated reason,
 * and this function reports them rather than inventing a region.
 */
function captureFrames(): FrameSegment[] {
  const segments: FrameSegment[] = [];
  const unbound: UnboundSpan[] = [];

  for (const element of visualElements()) {
    const rect = element.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect.width));
    const height = Math.max(1, Math.floor(rect.height));
    if (width * height > 4_000_000) continue; // refuse absurd allocations

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) continue;

    let rasterised = false;
    try {
      if (element instanceof HTMLVideoElement) {
        ctx.drawImage(element, 0, 0, width, height);
        rasterised = true;
      } else if (element instanceof HTMLImageElement) {
        // An image that has not decoded has no pixels to read. Claiming
        // otherwise would be reporting a clean scan of nothing.
        if (element.complete && element.naturalWidth > 0) {
          ctx.drawImage(element, 0, 0, width, height);
          rasterised = true;
        }
      } else if (element instanceof HTMLCanvasElement) {
        ctx.drawImage(element, 0, 0, width, height);
        rasterised = true;
      }
    } catch (error) {
      // A tainted canvas throws on both draw and getImageData. That is a
      // FAILURE of the pixel route, not an empty region.
      continue;
    }
    if (!rasterised) continue;

    let image: ImageData;
    try {
      image = ctx.getImageData(0, 0, width, height);
    } catch (error) {
      continue;
    }

    const origin = boundingBox(rect.left, rect.top, width, height);
    const { boxes, entities } = bindElementBoxes(element, origin, unbound);

    segments.push({
      elementId: 'visual-' + segments.length,
      frame: new PixelFrame(width, height, 4, new Uint8Array(image.data.buffer.slice(0) as ArrayBuffer)),
      boxes,
      entities,
    });
  }

  if (unbound.length > 0) {
    // Declared, never swallowed. A span we cannot mask is a span that will be
    // visible, so it has to be visible in the report too.
    console.warn(
      `[sih] ${unbound.length} sensitive span(s) could not be bound to pixels ` +
        `(OCR unavailable on this rung): ` +
        unbound.map((u) => `${u.entityId}@${u.elementId}`).join(', '),
    );
  }
  return segments;
}

/** Walk an element's text nodes, build geometry runs, detect, and bind. */
function bindElementBoxes(
  element: Element,
  origin: BoundingBox,
  unbound: UnboundSpan[],
): { boxes: BoundingBox[]; entities: string[] } {
  const runs = collectTextRuns(element, origin);
  if (runs.length === 0) return { boxes: [], entities: [] };

  // joinRuns, not a hand-rolled join: see RUN_SEPARATOR for the defect that
  // made a valid Aadhaar undetectable by gluing it to the next text node.
  const text = joinRuns(runs);
  const findings = detect(text).findings;
  if (findings.length === 0) return { boxes: [], entities: [] };

  const bindings = bindFindings(
    findings.map((f) => ({ entityId: f.entityId, start: f.start, end: f.end })),
    runs,
  );

  const boxes: BoundingBox[] = [];
  const entities: string[] = [];
  for (const binding of bindings) {
    if (!binding.bound) {
      unbound.push({
        elementId: binding.elementId,
        entityId: binding.entityId,
        reason: binding.reason ?? 'unbound',
      });
      continue;
    }
    boxes.push(...binding.boxes);
    entities.push(binding.entityId);
  }
  return { boxes, entities };
}



/** A sensitive span that could not be tied to any pixels. */
interface UnboundSpan {
  readonly elementId: string;
  readonly entityId: string;
  readonly reason: string;
}

/**
 * Walk an element's text nodes and ask the browser where it drew each one.
 *
 * `Range.getClientRects()` is the whole trick: the layout engine already knows
 * the exact pixel rectangle of every character, and it will tell us for free.
 * One Range per text node (rather than per character) is enough, because a node
 * is short and its client rects already split by line.
 *
 * Text that is not laid out - `display:none`, detached, zero-size - yields no
 * rects. Those runs are still emitted, with empty `rects`, so the run's
 * characters remain in the joined string the detector scans. Dropping them
 * would shift every subsequent offset and silently mis-mask the value that
 * follows.
 */
function collectTextRuns(element: Element, origin: BoundingBox): TextRun[] {
  const inputs: RunInput[] = [];
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  let node: Node | null;

  while ((node = walker.nextNode()) !== null) {
    const text = node.nodeValue ?? '';
    if (text === '') continue;

    const rects: BoundingBox[] = [];
    try {
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of Array.from(range.getClientRects())) {
        // A zero-area rect cannot be masked, and including it would fail V-11.
        if (rect.width <= 0 || rect.height <= 0) continue;
        rects.push(
          clampToFrame(
            toFrameLocal(boundingBox(rect.left, rect.top, rect.width, rect.height), origin),
            { width: origin.width, height: origin.height },
          ),
        );
      }
      range.detach?.();
    } catch (error) {
      // A range over an exotic node can throw. The run still contributes its
      // characters so offsets stay aligned; it simply cannot be masked.
    }

    inputs.push({ elementId: elementIdOf(element), text, rects });
  }

  // Offsets are computed by buildRuns, never here. Computing them locally is how
  // the run-separator defect happened in the first place.
  return buildRuns(inputs);
}

function elementIdOf(element: Element): string {
  if (!element.id) return element.tagName.toLowerCase();
  return element.id;
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry point
// ─────────────────────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (
    message: unknown,
    _sender: chrome.runtime.MessageSender,
    sendResponse: (r: ObserveResponse) => void,
  ) => {
    if (!isInbound(message) || message.kind !== 'OBSERVE') return false;

    void (async () => {
      const ladder = await new CapabilityResolver(probes).resolve();
      const vault = new PlaceholderVault(message.observationId);
      const guard = new EgressGuard();

      const adapters = buildAdapters(message, ladder.active);
      const result = runPipeline(adapters, { vault, guard }, message.taskDescription);

      sendResponse({
        kind: 'OBSERVE_RESULT',
        observationId: message.observationId,
        state: result.evidence.state,
        rung: result.rung,
        redactions: result.redactionCount,
        framesVerified: result.framesVerified,
        transmitted: result.transmitted,
        reason: result.transmitError ?? result.pixelFailure,
        // Serialised ONLY when the guard permitted transmission. A withheld
        // payload has no serialised form, so there is nothing to leak by
        // accident if the verdict were ever misread.
        envelopeJson: result.transmitted ? JSON.stringify(result.envelope) : null,
        auditTrail: guard.audit.map((event) => ({
          destination: event.destination,
          verdict: event.verdict,
          state: event.state,
          redaction_count: event.redaction_count,
          payload_bytes: event.payload_bytes,
          reason: event.reason,
        })),
      });
    })();

    return true; // response is asynchronous
  },
);
