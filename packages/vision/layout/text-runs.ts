/**
 * SIH26171 — Text-run to pixel-box binding (CR-003).
 *
 * Why this needs no model
 * -----------------------
 * The obvious answer to "where are the pixels for this sensitive value" is OCR.
 * It is also the wrong answer for most of the surface area, and the reason is
 * architectural rather than clever:
 *
 * In the offscreen document WE control rendering. Given a text node we can
 * construct a Range over the exact character offsets the detector reported and
 * ask the browser for `getClientRects()`. That returns the precise pixel
 * geometry of those characters. No inference, no confidence, no model drift -
 * an exact answer to an exact question.
 *
 * OCR is required for exactly one case: text painted into a `<canvas>`, an
 * `<img>`, or a CSS background, where no text node exists. That case is real
 * and it is NOT solved here. Rather than return a plausible-looking box from a
 * heuristic and let it read as a guarantee, this module reports those spans as
 * UNBOUND so the pipeline can declare them.
 *
 * ── The asymmetry that matters ───────────────────────────────────────────────
 * Over-masking costs utility. Under-masking costs privacy. So whenever a span
 * cannot be bound precisely, this module widens to the covering run rather than
 * narrowing to the best guess. A slightly larger black box is the correct
 * answer; a slightly smaller one that clips a digit is a breach.
 *
 * Governed by FR-RED-3 (mask geometry), FR-VLT-7 (region-level binding),
 * CR-003. Verification V-11.
 */

import type { BoundingBox } from '../../contracts/geometry.js';
import { area, unionBoxes } from './geometry-ops.js';

/**
 * A contiguous run of characters with known screen geometry.
 *
 * `start`/`end` are offsets into the SAME string the detector scanned, so a
 * finding's offsets can be intersected with a run's without any re-tokenising.
 * `rects` may hold several boxes because text wraps: one rect per line box.
 */
export interface TextRun {
  readonly elementId: string;
  /** The run's own characters. */
  readonly text: string;
  /**
   * Offset of `text` within the CONCATENATION of all runs, which is the string
   * the detector scanned. Callers must build runs before detecting, because the
   * join is what makes the two offset spaces identical.
   */
  readonly start: number;
  readonly end: number;
  readonly rects: readonly BoundingBox[];
}

/**
 * The separator inserted between two text runs when they are concatenated for
 * detection.
 *
 * This constant is the subject of a real defect, found by writing a corpus case
 * with two adjacent runs. Two text nodes were joined with `''`, producing
 *
 *     "Aadhaar 999999990019Email parker.sterling@example.test"
 *
 * which is a string that appears on NO page. The Aadhaar digit run is followed
 * immediately by a letter, so the pattern's trailing `\b` never matches and a
 * perfectly valid Aadhaar was MISSED. Fabricated input to the detector is a
 * privacy failure wearing the costume of a string-formatting bug.
 *
 * A newline fixes it because it restores the word boundary a real layout has
 * between nodes, and because no entity pattern in the taxonomy can match across
 * it. The value is now `RUN_SEPARATOR`, and `buildRuns` is the ONLY supported
 * way to construct runs, so a caller cannot reintroduce the defect by joining
 * by hand.
 */
export const RUN_SEPARATOR = '\n';

export interface RunInput {
  readonly elementId: string;
  readonly text: string;
  readonly rects: readonly BoundingBox[];
}

/**
 * Build runs with offsets in the CONCATENATED space.
 *
 * Callers must use this rather than computing offsets themselves, then pass the
 * runs to `joinRuns` to produce the string the detector scans. Keeping the two
 * together is what guarantees the offset spaces agree.
 */
export function buildRuns(inputs: readonly RunInput[]): TextRun[] {
  const runs: TextRun[] = [];
  let cursor = 0;
  inputs.forEach((input, index) => {
    if (index > 0) cursor += RUN_SEPARATOR.length;
    runs.push({
      elementId: input.elementId,
      text: input.text,
      start: cursor,
      end: cursor + input.text.length,
      rects: input.rects,
    });
    cursor += input.text.length;
  });
  return runs;
}

/** The exact string the detector must scan for a given set of runs. */
export function joinRuns(runs: readonly TextRun[]): string {
  return runs.map((run) => run.text).join(RUN_SEPARATOR);
}

export interface BindingResult {
  readonly elementId: string;
  readonly findingStart: number;
  readonly findingEnd: number;
  readonly entityId: string;
  /** One box per line box covered. Never empty for a bound span. */
  readonly boxes: readonly BoundingBox[];
  readonly bound: boolean;
  /**
   * Why a span could not be bound, in words. Never null when `bound` is false,
   * so an unbound span is always accompanied by a stated reason rather than
   * being silently dropped.
   */
  readonly reason: string | null;
}

/** Does [aStart,aEnd) overlap [bStart,bEnd)? Touching does not count. */
function overlaps(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart < bEnd && bStart < aEnd;
}

/**
 * Bind detector findings to pixel boxes.
 *
 * @param findings spans to mask, in offsets of `runs`' shared string
 * @param runs     the geometry available for that string
 */
export function bindFindings(
  findings: readonly { readonly entityId: string; readonly start: number; readonly end: number }[],
  runs: readonly TextRun[],
): BindingResult[] {
  return findings.map((finding) => {
    const covering = runs.filter((run) =>
      overlaps(finding.start, finding.end, run.start, run.end),
    );

    if (covering.length === 0) {
      return {
        elementId: '',
        findingStart: finding.start,
        findingEnd: finding.end,
        entityId: finding.entityId,
        boxes: [],
        bound: false,
        // The most common cause by far: the value was rendered into pixels
        // rather than into text, so there is no Range to ask about.
        reason:
          'no text run overlaps these offsets; the value is rendered as pixels ' +
          '(canvas/image/CSS background) and requires OCR, which is not ' +
          'available on this rung (CR-003)',
      };
    }

    // One box per LINE box covered, not a single union rectangle: text wraps,
    // and masking the union of a two-line span would black out the whole block,
    // destroying utility for no privacy gain. Per-line keeps the mask tight to
    // the glyphs while still covering every pixel of the value.
    const boxes = covering.flatMap((run) => [...run.rects]);

    return {
      elementId: covering[0]?.elementId ?? '',
      findingStart: finding.start,
      findingEnd: finding.end,
      entityId: finding.entityId,
      boxes,
      bound: boxes.length > 0,
      reason:
        boxes.length === 0
          ? 'the overlapping text run reported no client rectangles, which ' +
            'means the text is not laid out (display:none or detached)'
          : null,
    };
  });
}

/** Total area covered by a binding, for reporting. */
export function coveredArea(result: BindingResult): number {
  return area(unionBoxes(result.boxes));
}
