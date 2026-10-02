/**
 * SIH26171 — Extension message protocol.
 *
 * Zone layout, and why it is drawn this way (SEC-BOUND-001 §3):
 *
 *   page DOM  ──content script──▶  service worker  ──▶  OFFSCREEN DOCUMENT
 *   (untrusted)   collector only      coordinator         Z1: DOM + pixels
 *                                                     + vault + guard
 *
 * The raw sensitive content lives in exactly ONE place: the offscreen document.
 * The service worker coordinates and never holds page text; the content script
 * collects and never sees the vault. That is what makes DP-5 ("no outbound type
 * can hold raw content") structural rather than a promise.
 *
 * `connect-src 'none'` in the manifest is the same idea at the network layer:
 * there is no code path from this extension to a remote origin. Egress means
 * handing an envelope to the local enclave, and nothing else.
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
}

/** Service worker → offscreen. The pipeline request. */
export interface ObserveRequest {
  readonly kind: 'OBSERVE';
  readonly observationId: string;
  readonly taskDescription: string;
  readonly collected: CollectRequest;
}

export type InboundMessage = CollectRequest | ObserveRequest;

/** Offscreen → service worker. Carries the ENVELOPE, never raw content. */
export interface ObserveResponse {
  readonly kind: 'OBSERVE_RESULT';
  readonly observationId: string;
  readonly state: string;
  readonly rung: string;
  readonly redactions: number;
  readonly framesVerified: number;
  readonly transmitted: boolean;
  readonly reason: string | null;
  /** Present only when transmission was permitted. Contains no raw values. */
  readonly envelopeJson: string | null;
  readonly auditTrail: ReadonlyArray<{
    readonly destination: string;
    readonly verdict: string;
    readonly state: string;
    readonly redaction_count: number;
    readonly payload_bytes: number;
    readonly reason: string;
  }>;
}

/** Every message must name its kind; an unknown kind is refused, not ignored. */
export function isInbound(value: unknown): value is InboundMessage {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { kind?: unknown }).kind === 'string' &&
    ((value as { kind: string }).kind === 'COLLECT' ||
      (value as { kind: string }).kind === 'OBSERVE')
  );
}
