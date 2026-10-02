/**
 * SIH26171 — Shared geometry primitives.
 *
 * The single home for coordinate types shared across modules.
 *
 * DES-ARCH-001 rule A-2 sets the layering:
 *   agent -> {policy, execution} -> {perception, privacy} -> contracts
 *
 * `perception` and `privacy` are SIBLINGS, so neither may import the other.
 * Both need a bounding box, so it belongs here, in `contracts`, below both.
 *
 * This module exists because that mistake was actually made on the Python side:
 * `privacy.pixels` initially imported `BoundingBox` from `perception.base` — a
 * module that did not exist. Running the code caught it; reading it would not.
 */

/** Origin top-left. `x` increases rightward, `y` downward. */
export interface BoundingBox {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

/**
 * Construct a box, rejecting negative extents.
 *
 * Returns a frozen object so a box cannot be mutated after a detector has been
 * compared against it — a box that changes under its own IoU calculation would
 * make the verification meaningless.
 */
export function boundingBox(
  x: number,
  y: number,
  width: number,
  height: number,
): BoundingBox {
  if (width < 0 || height < 0) {
    throw new Error('bounding box width and height must be non-negative');
  }
  return Object.freeze({ x, y, width, height });
}

export function area(box: BoundingBox): number {
  return box.width * box.height;
}

/** (x, y, width, height) as integers, for pixel addressing. */
export function asIntTuple(box: BoundingBox): [number, number, number, number] {
  return [
    Math.trunc(box.x),
    Math.trunc(box.y),
    Math.trunc(box.width),
    Math.trunc(box.height),
  ];
}

/** Structural equality, used by the parity harness. */
export function boxEquals(a: BoundingBox, b: BoundingBox): boolean {
  return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
}
