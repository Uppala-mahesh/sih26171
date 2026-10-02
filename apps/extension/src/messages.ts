/**
 * SIH26171 — Extension message protocol.
 *
 * Zone layout, and why it is drawn this way (SEC-BOUND-001 §3):
 *
 *   page DOM  ──content script──▶  SERVICE WORKER
 *   (untrusted)   collector only       Z1: vault + detector + sanitizer + guard
 *
 * The raw sensitive content lives in exactly ONE place: the worker. The content
 * script collects and never sees the vault, detector or guard — it has no runtime
 * imports at all. That is what makes DP-5 ("no outbound type can hold raw
 * content") structural rather than a promise.
 *
 * Z1 was an offscreen document until its module-evaluation race produced two
 * separate "Receiving end does not exist" failures; see README §8. The message
 * types that race required are gone from this file rather than left behind as
 * dead protocol.
 *
 * Network egress is prevented by the CODE, not by a CSP string: no `fetch`,
 * `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon` or `importScripts`
 * appears anywhere in the shipped artifact, asserted by
 * `test_extension_declares_no_network_egress`. (An earlier manifest used
 * `connect-src 'none'`, which MV3 does not permit for extension pages — Chrome
 * refused to install it.)
 */

/** Content script → service worker. Raw text, which is why it stops here. */
export interface CollectRequest {
  readonly kind: 'COLLECT';
  readonly url: string;
  readonly title: string;
  readonly segments: ReadonlyArray<{
    readonly elementId: string;
    readonly text: string;
    readonly tagName: string;
    readonly ariaLabel: string;
  }>;
  /** FR-PER-4: cross-origin frame blindness, declared by the collector. */
  readonly frameBlind: boolean;
  /**
   * How many painted surfaces the page has: canvas, img, video, svg, and
   * background-images.
   *
   * THIS IS THE COLLECTOR'S MOST IMPORTANT NUMBER. The text walker above cannot
   * see text drawn into a canvas, burned into an image, or supplied by a CSS
   * background - which is exactly where PII hides. The worker has no DOM and
   * cannot rasterise, so this count is what lets it distinguish "this page has
   * nothing to hide" from "this page may be hiding something I cannot see".
   *
   * `undefined` when the collector cannot tell. It is never defaulted to 0,
   * because an unknown count must not read as a clean bill of health.
   */
  readonly visualSurfaces?: number | undefined;
}
/** What the side panel is allowed to display. Counts and verdicts, never values. */
export interface ReportView {
  readonly kind: 'REPORT';
  readonly observationId: string;
  readonly capturedAt: number;
  readonly state: string;
  readonly verdict: string;
  readonly rung: string;
  readonly redactionCount: number;
  readonly textSegments: number;
  readonly framesVerified: number;
  readonly visualSurfaces?: number | undefined;
  readonly transmitted: boolean;
  readonly reason: string | null;
  readonly schemaVersion?: string | undefined;
  readonly destination?: string | undefined;
}

/**
 * Operator asks the side panel to run an observation.
 *
 * A separate channel from the toolbar click so the panel can re-run a task without
 * the operator hunting for the extension icon, and so the panel's lifetime is not
 * tied to `action.onClicked`.
 */
export interface RunRequest {
  readonly kind: 'RUN';
}

export type PanelMessage = ReportView | RunRequest | ReportRequest;

/** The panel asks for the last report so reopening it is not blank. */
export interface ReportRequest {
  readonly kind: 'REPORT_REQUEST';
}

/**
 * The panel builds `innerHTML` from strings, so the values are inserted as TEXT
 * nodes and never as markup. A verdict string is operator-facing, but it is still
 * data, and `textContent` is what makes "it came from our own code" true rather
 * than merely likely.
 */
export function isPanelMessage(value: unknown): value is PanelMessage {
  if (typeof value !== 'object' || value === null) return false;
  const kind = (value as { kind?: unknown }).kind;
  return kind === 'REPORT' || kind === 'RUN' || kind === 'REPORT_REQUEST';
}
