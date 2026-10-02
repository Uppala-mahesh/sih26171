/**
 * SIH26171 — Box arithmetic shared by the vision pipeline.
 *
 * Kept separate from `contracts/geometry` because the CONTRACT owns the type
 * and the guarantee, while this owns the arithmetic the vision pipeline needs
 * and the backend has no use for. DES-ARCH-001 rule A-2 keeps `contracts` below
 * both; adding conveniences there would make every consumer depend on them.
 *
 * Every function here is TOLERANT of malformed input by returning a degenerate
 * box rather than throwing. A detector that produces one bad box must not be
 * able to abort a redaction run over the remaining nineteen - and the redactor
 * will fail the run anyway if the geometry misses the IoU floor (V-11).
 */

import { boundingBox, type BoundingBox } from '../../contracts/geometry.js';

/** The empty box. Area and IoU against it are both zero. */
export const EMPTY_BOX: BoundingBox = boundingBox(0, 0, 0, 0);

export function area(box: BoundingBox): number {
  return Math.max(0, box.width) * Math.max(0, box.height);
}

/** Smallest box containing both inputs. Degenerate inputs are ignored. */
export function unionBox(a: BoundingBox, b: BoundingBox): BoundingBox {
  if (!isUsable(a)) return b;
  if (!isUsable(b)) return a;
  const left = Math.min(a.x, b.x);
  const top = Math.min(a.y, b.y);
  const right = Math.max(a.x + a.width, b.x + b.width);
  const bottom = Math.max(a.y + a.height, b.y + b.height);
  return boundingBox(left, top, right - left, bottom - top);
}

/** Union of many boxes. An empty list yields EMPTY_BOX. */
export function unionBoxes(boxes: readonly BoundingBox[]): BoundingBox {
  return boxes.reduce<BoundingBox>(unionBox, EMPTY_BOX);
}

/** A box can contribute area and be masked. */
export function isUsable(box: BoundingBox): boolean {
  return (
    Number.isFinite(box.x) &&
    Number.isFinite(box.y) &&
    Number.isFinite(box.width) &&
    Number.isFinite(box.height) &&
    box.width > 0 &&
    box.height > 0
  );
}

export function intersectionArea(a: BoundingBox, b: BoundingBox): number {
  const left = Math.max(a.x, b.x);
  const top = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  if (right <= left || bottom <= top) return 0;
  return (right - left) * (bottom - top);
}

/** FR-RED-3 / V-11: >= 0.90 between the requested and the applied box. */
export function intersectionOverUnion(a: BoundingBox, b: BoundingBox): number {
  const intersection = intersectionArea(a, b);
  if (intersection === 0) return 0;
  const union = area(a) + area(b) - intersection;
  return union > 0 ? intersection / union : 0;
}

/** Clamp to a frame so a box at an edge cannot index out of range. */
export function clampToFrame(
  box: BoundingBox,
  frame: { readonly width: number; readonly height: number },
): BoundingBox {
  const x0 = Math.max(0, Math.min(Math.trunc(box.x), frame.width - 1));
  const y0 = Math.max(0, Math.min(Math.trunc(box.y), frame.height - 1));
  const x1 = Math.max(x0 + 1, Math.min(Math.trunc(box.x + box.width), frame.width));
  const y1 = Math.max(y0 + 1, Math.min(Math.trunc(box.y + box.height), frame.height));
  return boundingBox(x0, y0, x1 - x0, y1 - y0);
}

/** Translate a viewport box into the local coordinates of an element's frame. */
export function toFrameLocal(
  box: BoundingBox,
  origin: BoundingBox,
): BoundingBox {
  return boundingBox(box.x - origin.x, box.y - origin.y, box.width, box.height);
}
