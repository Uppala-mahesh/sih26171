/**
 * SIH26171 — Pixel redaction.
 *
 * TypeScript port of apps/backend/app/privacy/pixels.py. Text rendered as an
 * IMAGE defeats every DOM-level control: there is no text node, no attribute,
 * no accessible name for a detector to read. This module is the only defence on
 * that route, so it is a security control, not a rendering nicety.
 *
 * Implements FR-RED-2, FR-RED-3, FR-RED-6 and verifications **V-10** and **V-11**.
 *
 * Design decision: OPAQUE FILL, and nothing else
 * -----------------------------------------------
 * Blur, pixelation, mosaicking, inversion and partial obscuring are all
 * prohibited. They look like redaction while leaving information recoverable:
 *
 *   * blur and mosaic preserve structure and are routinely invertible
 *   * partial masking leaks the uncovered glyph fragments
 *   * inversion leaves high-contrast structure readable
 *
 * A uniform opaque fill overwrites the pixels. The original bytes are destroyed,
 * not merely obscured, which makes V-10 ("reconstruction recovers zero
 * characters") a property of the format rather than a hope about the algorithm.
 *
 * Verification is structural, not statistical
 * ------------------------------------------
 * Three properties are checked and any failure withholds the artefact:
 *
 *   1. OPAQUE       every pixel inside the applied mask equals the fill
 *   2. IRREVERSIBLE  no original pixel survives inside the mask
 *   3. NON-DESTRUCTIVE  every pixel outside every mask is byte-identical
 *
 * No image library: masks are applied to a plain byte buffer, so the logic is
 * directly testable and identical in the Python enclave and the browser.
 */

import {
  asIntTuple,
  boundingBox,
  type BoundingBox,
} from '../contracts/geometry.js';

export const DEFAULT_FILL: readonly [number, number, number] = [0, 0, 0];

/** FR-RED-3 / V-11: mask geometry must match the detection box. */
export const MINIMUM_IOU = 0.9;

/** FR-RED-6: share of pixels outside masks that must be untouched. */
export const MINIMUM_UTILITY = 0.95;

/**
 * The only permitted style.
 *
 * Enumerated so that a future contributor cannot add `BLUR` without the type
 * system objecting, which is the point of naming the prohibition.
 */
export const MaskStyle = { OPAQUE_FILL: 'OPAQUE_FILL' } as const;
export type MaskStyle = (typeof MaskStyle)[keyof typeof MaskStyle];

/** A verification failed. The artefact must be withheld, not shipped. */
export class RedactionFailed extends Error {
  constructor(readonly failures: readonly string[]) {
    super(`pixel redaction verification failed: ${failures.join('; ')}`);
    this.name = 'RedactionFailed';
  }
}

/** An uncompressed image buffer. Deliberately not an image-library type. */
export class PixelFrame {
  readonly width: number;
  readonly height: number;
  readonly channels: number;
  readonly data: Uint8Array;

  constructor(width: number, height: number, channels: number, data: Uint8Array) {
    if (width <= 0 || height <= 0 || channels <= 0) {
      throw new Error('frame dimensions and channels must be positive');
    }
    const expected = width * height * channels;
    if (data.length !== expected) {
      throw new Error(
        `buffer is ${data.length} bytes, expected ${expected} (${width}x${height}x${channels})`,
      );
    }
    this.width = width;
    this.height = height;
    this.channels = channels;
    this.data = data;
  }

  get pixel_count(): number {
    return this.width * this.height;
  }

  pixel_at(x: number, y: number): Uint8Array {
    const start = (y * this.width + x) * this.channels;
    return this.data.subarray(start, start + this.channels);
  }

  /** Raw bytes of the region. */
  region_bytes(box: BoundingBox): Uint8Array {
    const [x0, y0, w, h] = asIntTuple(box);
    const out = new Uint8Array(w * h * this.channels);
    let cursor = 0;
    for (let y = y0; y < y0 + h; y++) {
      for (let x = x0; x < x0 + w; x++) {
        const at = (y * this.width + x) * this.channels;
        out.set(this.data.subarray(at, at + this.channels), cursor);
        cursor += this.channels;
      }
    }
    return out;
  }
}

/** IoU. FR-RED-3 requires >= 0.90 between the requested and applied box. */
export function intersection_over_union(a: BoundingBox, b: BoundingBox): number {
  const left = Math.max(a.x, b.x);
  const top = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);

  if (right <= left || bottom <= top) return 0;

  const intersection = (right - left) * (bottom - top);
  const union = a.width * a.height + b.width * b.height - intersection;
  return union > 0 ? intersection / union : 0;
}

/** Clamp to the frame so a detection near an edge cannot index out of range. */
export function clamp_box(box: BoundingBox, frame: PixelFrame): BoundingBox {
  const x0 = Math.max(0, Math.min(Math.trunc(box.x), frame.width - 1));
  const y0 = Math.max(0, Math.min(Math.trunc(box.y), frame.height - 1));
  const x1 = Math.max(x0 + 1, Math.min(Math.trunc(box.x + box.width), frame.width));
  const y1 = Math.max(y0 + 1, Math.min(Math.trunc(box.y + box.height), frame.height));
  return boundingBox(x0, y0, x1 - x0, y1 - y0);
}

/** One mask, with the geometry evidence FR-RED-3 demands. */
export interface AppliedMask {
  readonly index: number;
  readonly requested: BoundingBox;
  readonly applied: BoundingBox;
  readonly iou: number;
  readonly pixels_changed: number;
  readonly entity_id: string;
}

export interface PixelRedactionResult {
  readonly frame: PixelFrame;
  readonly masks: readonly AppliedMask[];
  readonly changed_pixels: number;
  readonly utility_preservation: number;
  readonly style: MaskStyle;
  readonly failures: readonly string[];
  readonly verified: boolean;
}


function sameBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

/**
 * Applies opaque masks, then proves three things about the result.
 *
 * Stateless. One instance may be reused; it holds no per-call state.
 */
export class PixelRedactor {
  /** Mask every box, then verify. Never returns an unverified artefact. */
  redact(
    frame: PixelFrame,
    boxes: readonly BoundingBox[],
    entityIds?: readonly string[],
    fill: readonly [number, number, number] = DEFAULT_FILL,
  ): PixelRedactionResult {
    const buffer = new Uint8Array(frame.data);
    const covered = new Uint8Array(frame.pixel_count);
    const fillByte = fillBytes(fill, frame.channels);
    const masks: AppliedMask[] = [];

    boxes.forEach((box, index) => {
      const applied = clamp_box(box, frame);
      for (let y = applied.y; y < applied.y + applied.height; y++) {
        for (let x = applied.x; x < applied.x + applied.width; x++) {
          const offset = (y * frame.width + x) * frame.channels;
          buffer.set(fillByte, offset);
          covered[y * frame.width + x] = 1;
        }
      }

      const partial = new PixelFrame(frame.width, frame.height, frame.channels, buffer);
      const changed = countDifferences(frame, partial, applied);
      masks.push(
        Object.freeze({
          index,
          requested: box,
          applied,
          iou: intersection_over_union(box, applied),
          pixels_changed: changed,
          entity_id:
            entityIds !== undefined && index < entityIds.length
              ? (entityIds[index] as string)
              : 'UNKNOWN',
        }),
      );
    });

    const resultFrame = new PixelFrame(frame.width, frame.height, frame.channels, buffer);
    const utility = utilityPreservation(frame, resultFrame, covered);
    const failures = verify(frame, resultFrame, masks, covered, fillByte, utility);

    return Object.freeze({
      frame: resultFrame,
      masks: Object.freeze(masks),
      changed_pixels: masks.reduce((sum, m) => sum + m.pixels_changed, 0),
      utility_preservation: utility,
      style: MaskStyle.OPAQUE_FILL,
      failures: Object.freeze(failures),
      verified: failures.length === 0,
    });
  }
}

/** Throw rather than let an unverified artefact be shipped. */
export function assertVerified(result: PixelRedactionResult): PixelRedactionResult {
  if (!result.verified) throw new RedactionFailed(result.failures);
  return result;
}


// ── helpers ─────────────────────────────────────────────────────────────────

function fillBytes(fill: readonly [number, number, number], channels: number): Uint8Array {
  const out = new Uint8Array(channels);
  if (channels >= 3) {
    out[0] = fill[0];
    out[1] = fill[1];
    out[2] = fill[2];
  } else {
    out.fill(fill[0] ?? 0);
  }
  return out;
}

function countDifferences(
  original: PixelFrame,
  redacted: PixelFrame,
  box: BoundingBox,
): number {
  const [x0, y0, w, h] = asIntTuple(box);
  let changed = 0;
  for (let y = y0; y < y0 + h; y++) {
    for (let x = x0; x < x0 + w; x++) {
      if (!sameBytes(original.pixel_at(x, y), redacted.pixel_at(x, y))) changed++;
    }
  }
  return changed;
}

/**
 * Pixels inside `box` that still carry their ORIGINAL value.
 *
 * A pixel that already equalled the fill colour is not counted: there was no
 * information there to protect in the first place.
 */
function countSurvivors(
  original: PixelFrame,
  redacted: PixelFrame,
  box: BoundingBox,
  fillByte: Uint8Array,
): number {
  const [bx, by, bw, bh] = asIntTuple(box);
  let survivors = 0;
  for (let y = by; y < by + bh; y++) {
    for (let x = bx; x < bx + bw; x++) {
      const after = redacted.pixel_at(x, y);
      if (
        !sameBytes(after, fillByte) &&
        sameBytes(after, original.pixel_at(x, y))
      ) {
        survivors++;
      }
    }
  }
  return survivors;
}

/** FR-RED-6: share of pixels outside every mask that are byte-identical. */
function utilityPreservation(
  original: PixelFrame,
  redacted: PixelFrame,
  covered: Uint8Array,
): number {
  let outside = 0;
  let identical = 0;
  for (let y = 0; y < original.height; y++) {
    for (let x = 0; x < original.width; x++) {
      if (covered[y * original.width + x]) continue;
      outside++;
      if (sameBytes(original.pixel_at(x, y), redacted.pixel_at(x, y))) identical++;
    }
  }
  return outside === 0 ? 1.0 : identical / outside;
}

/**
 * Three structural properties, checked on the produced bytes.
 *
 * Mirrors the Python control flow exactly, including the fact that each check
 * reports AT MOST ONE failure per mask: a mask that is not opaque everywhere
 * produces one diagnostic, not one per pixel, so the failure list stays
 * readable rather than becoming a per-pixel dump.
 *
 * NOTE on V-10: an earlier Python version searched for the region's byte STRING
 * in the output buffer. That check was vacuous for any multi-row mask, because
 * region_bytes() concatenates row by row while the buffer interleaves the other
 * columns, so the string was never contiguous and the search always returned
 * "gone". Mutation testing exposed it: a no-op mask passed a check that was
 * supposed to catch it. The correct property is per-pixel, which is what this
 * implements.
 */
function verify(
  original: PixelFrame,
  redacted: PixelFrame,
  masks: readonly AppliedMask[],
  covered: Uint8Array,
  fillByte: Uint8Array,
  utility: number,
): string[] {
  const failures: string[] = [];

  for (const mask of masks) {
    // V-11: geometry must actually match the detection.
    if (mask.iou < MINIMUM_IOU) {
      failures.push(
        `mask ${mask.index} (${mask.entity_id}) IoU ${mask.iou.toFixed(3)} ` +
          `is below the required ${MINIMUM_IOU}`,
      );
    }

    // FR-RED-2: every pixel inside the mask must be the fill colour.
    outer: for (let y = mask.applied.y; y < mask.applied.y + mask.applied.height; y++) {
      for (let x = mask.applied.x; x < mask.applied.x + mask.applied.width; x++) {
        if (!sameBytes(redacted.pixel_at(x, y), fillByte)) {
          failures.push(
            `mask ${mask.index} (${mask.entity_id}) is not fully opaque at (${x},${y})`,
          );
          break outer;
        }
      }
    }

    // V-10: no original pixel data may survive inside the mask.
    const survivors = countSurvivors(original, redacted, mask.applied, fillByte);
    if (survivors > 0) {
      failures.push(
        `mask ${mask.index} (${mask.entity_id}) left ${survivors} original ` +
          `pixel(s) recoverable`,
      );
    }
  }

  // FR-RED-6: nothing outside a mask may change.
  outerOutside: for (let y = 0; y < original.height; y++) {
    for (let x = 0; x < original.width; x++) {
      if (covered[y * original.width + x]) continue;
      if (!sameBytes(original.pixel_at(x, y), redacted.pixel_at(x, y))) {
        failures.push(`pixel (${x},${y}) changed outside every mask`);
        break outerOutside;
      }
    }
  }

  if (utility < MINIMUM_UTILITY) {
    failures.push(
      `utility preservation ${utility.toFixed(4)} is below ${MINIMUM_UTILITY}`,
    );
  }

  return failures;
}

