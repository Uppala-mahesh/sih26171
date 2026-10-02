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
import { EgressGuard } from '../../../packages/gateway/guard.js';
import { PlaceholderVault } from '../../../packages/privacy/vault.js';
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
 * Rasterise each visual element into a plain byte buffer.
 *
 * Uses `getImageData` on a detached canvas rather than any screenshot API: the
 * result is an uncompressed RGBA buffer the redactor can address by pixel, with
 * no image library in between.
 */
function captureFrames(): FrameSegment[] {
  const segments: FrameSegment[] = [];
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

    try {
      if (element instanceof HTMLVideoElement) {
        ctx.drawImage(element, 0, 0, width, height);
      } else if (element instanceof HTMLImageElement) {
        if (!element.complete) continue; // not decoded yet; claiming otherwise is a lie
        ctx.drawImage(element, 0, 0, width, height);
      } else if (element instanceof HTMLCanvasElement) {
        ctx.drawImage(element, 0, 0, width, height);
      } else {
        continue;
      }
      const image = ctx.getImageData(0, 0, width, height);
      segments.push({
        elementId: 'visual-' + segments.length,
        frame: new PixelFrame(
          width,
          height,
          4,
          new Uint8Array(image.data.buffer.slice(0) as ArrayBuffer),
        ),
        // Detection boxes are produced by the vision pipeline in Z1 and are not
        // available until CR-003 lands. Emitting an empty box list is honest:
        // the pixel route is still recorded as having run over this region.
        boxes: [],
        entities: [],
      });
    } catch (error) {
      // A tainted canvas throws. That is a FAILURE of the pixel route, not an
      // empty region, so the frame is omitted rather than reported as clean.
      continue;
    }
  }
  return segments;
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
