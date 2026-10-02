/**
 * SIH26171 — Placeholder vault (Z1 only).
 *
 * TypeScript port of apps/backend/app/privacy/vault.py. A Chrome extension
 * cannot execute Python, so every privacy-core module must exist on BOTH
 * runtimes or the extension is not a product. Parity between the two ports is
 * enforced by tests/contract/test_parity.py.
 *
 * Implements FR-VLT-1..FR-VLT-7 and crossing **B-6** of SEC-BOUND-001.
 *
 * Three rules shape the whole design:
 *
 * 1. **It never leaves Z1.** The reverse mapping is in-memory, per task, and is
 *    never serialised, logged, or included in any outbound payload (DP-5).
 * 2. **Detokenization is target-bound (B-6).** A value may be written back ONLY
 *    into the element it was extracted from. This is what stops the PI-7
 *    exfiltration-by-instruction attack in SEC-THREAT-001 section 7.
 * 3. **Tokens are unforgeable.** Every token carries a per-observation nonce
 *    generated on-device, so a page that embeds the literal text `<AADHAAR_1>`
 *    cannot mint a token that later detokenizes to attacker-chosen content.
 */

/** Token shape: <TYPE_n#NONCE>. The nonce makes the namespace unforgeable. */
export const TOKEN_RE = /^<([A-Z_]+)_(\d+)#([0-9a-f]{8})>$/;

/**
 * Unanchored form, used when stripping our own tokens out of text BEFORE a
 * re-inspection scan. Without this, the nonce digits inside a token would be
 * re-detected as an OTP and every scan would carry self-inflicted noise.
 */
export const TOKEN_SCAN_RE = /<[A-Z_]+_\d+#[0-9a-f]{8}>/g;

/**
 * Remove our own placeholder tokens from `text`.
 *
 * Used by the egress re-inspection so that verification examines only
 * page-authored content, not the system's own substitutions.
 */
export function stripTokens(text: string): string {
  return text.replace(TOKEN_SCAN_RE, ' ');
}

const NONCE_BYTES = 4;

/**
 * Random hex, sourced from the platform CSPRNG.
 *
 * If no CSPRNG is reachable this THROWS rather than falling back. A predictable
 * nonce would let a page pre-mint tokens, which defeats rule 3 of this module
 * entirely, so failing closed is the only safe behaviour.
 *
 * Typed structurally rather than via `crypto` from lib.dom, because the parity
 * build compiles with lib ES2022 only and must produce the same behaviour.
 */
function randomNonce(): string {
  const webcrypto = (globalThis as { crypto?: { getRandomValues<T>(a: T): T } }).crypto;
  if (!webcrypto) {
    throw new Error('no CSPRNG available; refusing to mint a predictable nonce');
  }
  const bytes = new Uint8Array(NONCE_BYTES);
  webcrypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * A detokenization attempt that crossed the B-6 boundary.
 *
 * Thrown rather than returning null so a violation is loud at the call site
 * instead of degrading into a silently-typed empty field.
 */
export class DetokenizationRefused extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DetokenizationRefused';
  }
}

/**
 * The single element a placeholder may legitimately be written back into.
 *
 * `element_id` is observation-scoped: it identifies a node as it existed when
 * the value was captured, which is what FR-AGT-5 rebinding relies on to refuse a
 * stale target.
 */
export interface ElementBinding {
  readonly observation_id: string;
  readonly element_id: string;
}

export function elementBinding(observationId: string, elementId: string): ElementBinding {
  if (!observationId || !elementId) {
    throw new Error('ElementBinding requires a non-empty observation and element id');
  }
  return Object.freeze({ observation_id: observationId, element_id: elementId });
}

function sameBinding(a: ElementBinding, b: ElementBinding): boolean {
  return a.observation_id === b.observation_id && a.element_id === b.element_id;
}

/** Telemetry-safe view: counts and categories only, never values (FR-VLT-6). */
export interface SafePrivacySummary {
  readonly observation_id: string;
  readonly total_redactions: number;
  readonly by_entity: Readonly<Record<string, number>>;
  readonly by_sensitivity: Readonly<Record<string, number>>;
  readonly unresolved_count: number;
}

/** One redaction. Holds the raw value, so it must never be serialised. */
interface VaultEntry {
  readonly placeholder: string;
  readonly entity_type: string;
  readonly sensitivity: string;
  readonly bound_to: ElementBinding;
  readonly raw: string;
}


/**
 * In-memory, task-scoped vault.
 *
 * One instance per task. `clear()` runs on task end, origin navigation and
 * user reset (FR-VLT-4); afterwards every token stops resolving and
 * detokenization throws.
 */
export class PlaceholderVault {
  readonly #observationId: string;
  readonly #nonce: string;
  readonly #entries = new Map<string, VaultEntry>();
  readonly #byValue = new Map<string, string>();
  readonly #counters = new Map<string, number>();
  readonly #bySensitivity = new Map<string, number>();
  #unresolved = 0;
  #cleared = false;

  constructor(observationId: string, nonce?: string) {
    if (!observationId) throw new Error('vault requires an observation id');
    this.#observationId = observationId;
    // Unpredictable to the page. This is what makes tokens unforgeable.
    this.#nonce = nonce ?? randomNonce();
  }

  // -- introspection (no raw values) ------------------------------------------

  get observation_id(): string {
    return this.#observationId;
  }

  get nonce(): string {
    return this.#nonce;
  }

  get size(): number {
    return this.#entries.size;
  }

  /** Token strings only. Safe to place in sanitized output. */
  placeholders(): readonly string[] {
    return [...this.#entries.keys()];
  }

  // -- tokenization -----------------------------------------------------------

  /**
   * Register a redaction and return its placeholder.
   *
   * Identical values share a placeholder within one observation (FR-VLT-2);
   * distinct values never do (FR-VLT-3). The binding is recorded here and is
   * the only thing detokenization will accept later.
   */
  tokenize(
    entityType: string,
    raw: string,
    boundTo: ElementBinding,
    sensitivity = 'HIGH',
    outcome = 'ACCEPTED',
  ): string {
    if (this.#cleared) {
      throw new DetokenizationRefused('vault has been cleared; tokenize is not permitted');
    }
    if (boundTo.observation_id !== this.#observationId) {
      throw new Error(
        'binding observation does not match the vault observation ' +
          `(${boundTo.observation_id} != ${this.#observationId})`,
      );
    }

    // FR-VLT-2: the same value always yields the same token.
    const existing = this.#byValue.get(raw);
    if (existing !== undefined) return existing;

    const index = (this.#counters.get(entityType) ?? 0) + 1;
    this.#counters.set(entityType, index);
    const placeholder = `<${entityType}_${index}#${this.#nonce}>`;

    this.#entries.set(placeholder, {
      placeholder,
      entity_type: entityType,
      sensitivity,
      bound_to: boundTo,
      raw,
    });
    this.#byValue.set(raw, placeholder);
    this.#bySensitivity.set(sensitivity, (this.#bySensitivity.get(sensitivity) ?? 0) + 1);
    if (outcome === 'UNCERTAIN') this.#unresolved += 1;
    return placeholder;
  }

  // -- lifecycle --------------------------------------------------------------

  /** Wipe every mapping. Subsequent detokenization throws (FR-VLT-4). */
  clear(): void {
    this.#entries.clear();
    this.#byValue.clear();
    this.#counters.clear();
    this.#bySensitivity.clear();
    this.#unresolved = 0;
    this.#cleared = true;
  }

  /** FR-VLT-6: counts and categories only. Never a value, never a token map. */
  safe_summary(): SafePrivacySummary {
    const byEntity: Record<string, number> = {};
    for (const entry of this.#entries.values()) {
      byEntity[entry.entity_type] = (byEntity[entry.entity_type] ?? 0) + 1;
    }
    return Object.freeze({
      observation_id: this.#observationId,
      total_redactions: this.#entries.size,
      by_entity: Object.freeze(byEntity),
      by_sensitivity: Object.freeze(Object.fromEntries(this.#bySensitivity)),
      unresolved_count: this.#unresolved,
    });
  }

  /**
   * How many stored raw values still appear in `haystack`.
   *
   * The independent re-inspection required by FR-RED-4. It is genuinely
   * independent: it searches the produced string for the actual secrets rather
   * than trusting that substitution happened correctly.
   *
   * Returns a COUNT, never the values. Exposing raw values through a public
   * method would be a footgun on the one structure in the system that holds
   * them, so the check is performed here and only the tally leaves.
   */
  count_residual(haystack: string): number {
    if (this.#cleared) return 0;
    let count = 0;
    for (const entry of this.#entries.values()) {
      if (haystack.includes(entry.raw)) count += 1;
    }
    return count;
  }

  /** Never let a raw value reach a log line or a traceback. */
  toString(): string {
    return (
      `<PlaceholderVault observation=${JSON.stringify(this.#observationId)} ` +
      `entries=${this.#entries.size} cleared=${this.#cleared}>`
    );
  }

  // -- detokenization: the B-6 gate -------------------------------------------

  /**
   * Resolve a token, but ONLY for the element it was bound to.
   *
   * Throws `DetokenizationRefused` for an unknown token, a cleared vault, or any
   * target other than the bound one. It never returns a value for the wrong
   * element, which is the entire point of B-6.
   */
  detokenize_for_target(placeholder: string, target: ElementBinding): string {
    if (this.#cleared) {
      throw new DetokenizationRefused(
        'vault cleared: no placeholder resolves after task end (FR-VLT-4, rule VLT-7)',
      );
    }
    const entry = this.#entries.get(placeholder);
    if (entry === undefined) {
      throw new DetokenizationRefused(
        `unknown placeholder ${placeholder}; a page-supplied token can never resolve`,
      );
    }
    if (!sameBinding(entry.bound_to, target)) {
      throw new DetokenizationRefused(
        `B-6 violation: placeholder bound to ${entry.bound_to.element_id} ` +
          `may not be written to ${target.element_id}`,
      );
    }
    return entry.raw;
  }

  /** Non-raising form, for callers that prefer to branch. */
  can_resolve(placeholder: string, target: ElementBinding): boolean {
    if (this.#cleared) return false;
    const entry = this.#entries.get(placeholder);
    return entry !== undefined && sameBinding(entry.bound_to, target);
  }
}
