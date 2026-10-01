/**
 * SIH26171 — Entity validators (TypeScript mirror of the Python implementation).
 *
 * Governed by
 *     REQ-DATA-001   sections 4.2 / 4.3
 *     SEC-THREAT-001 DA-5 (linear time), R-7
 *     FR-PII-2, FR-PII-3
 *
 * ── Why this file is a mirror, and how the mirror is kept honest ─────────────
 * v1 had two PII engines whose vocabularies silently drifted apart (defect
 * G-1): the JavaScript engine knew Aadhaar, PAN, UPI, IFSC and OTP, and the
 * Python engine knew none of them.
 *
 * REQ-DATA-001 rules X-1 to X-5 exist to prevent a recurrence. Two registries
 * agreeing on paper is not sufficient, so tests/contract/test_parity.py
 * compares what BOTH RUNTIMES ACTUALLY DETECT across a shared corpus and fails
 * the build on divergence.
 *
 * Every algorithm below is O(n) with no nested quantifiers, satisfying DA-5.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Normalisation — REQ-DATA-001 rules N-1..N-4
// ─────────────────────────────────────────────────────────────────────────────

const SEPARATORS = /[\s\-.]/g;

export function normaliseDigits(value: string): string {
  return value.replace(SEPARATORS, '');
}

// ─────────────────────────────────────────────────────────────────────────────
// T1 — arithmetic validators
// ─────────────────────────────────────────────────────────────────────────────

export function luhnValid(candidate: string): boolean {
  const digits = normaliseDigits(candidate);
  if (!/^\d+$/.test(digits)) return false;
  if (digits.length < 13 || digits.length > 19) return false;

  let total = 0;
  for (let index = 0; index < digits.length; index += 1) {
    // Rightmost digit is the check digit; double every second digit to its left.
    let value = Number(digits[digits.length - 1 - index]);
    if (index % 2 === 1) {
      value *= 2;
      if (value > 9) value -= 9;
    }
    total += value;
  }
  return total % 10 === 0;
}

// Verhoeff D5 — Aadhaar's real checksum. NOT Luhn.
//
// These tables correspond to apps/backend/app/privacy/validators.py and are
// pinned by the parity test. The first implementation in this project used a
// TEN-row p table applied once after the loop; the correct table has EIGHT rows
// applied INSIDE the loop. That bug was caught because a ground-truth vector
// failed, and is recorded here so it is not repeated.
const VERHOEFF_D: readonly (readonly number[])[] = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
  [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
  [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
  [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
  [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
  [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
  [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
  [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
  [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
];

const VERHOEFF_P: readonly (readonly number[])[] = [
  [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
  [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
  [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
  [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
  [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
  [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
  [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
  [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
];

const VERHOEFF_INV: readonly number[] = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9];

export function verhoeffValid(candidate: string): boolean {
  const digits = normaliseDigits(candidate);
  if (!/^\d+$/.test(digits)) return false;

  let checksum = 0;
  for (let position = 0; position < digits.length; position += 1) {
    const digit = Number(digits[digits.length - 1 - position]!);
    // Intermediate variables rather than a chained `a![b![c]]!`: the chained
    // form is ambiguous to parse under noUncheckedIndexedAccess and this is
    // clearer to review against the reference implementation.
    const permutationRow = VERHOEFF_P[position % 8]!;
    const permuted = permutationRow[digit]!;
    const multiplicationRow = VERHOEFF_D[checksum]!;
    checksum = multiplicationRow[permuted]!;
  }
  return checksum === 0;
}

export function verhoeffCheckDigit(prefix: string): string {
  const digits = normaliseDigits(prefix);
  if (!/^\d+$/.test(digits)) throw new Error('prefix must be digits only');

  let checksum = 0;
  for (let index = 0; index < digits.length; index += 1) {
    const digit = Number(digits[digits.length - 1 - index]!);
    const permutationRow = VERHOEFF_P[(index + 1) % 8]!;
    const permuted = permutationRow[digit]!;
    const multiplicationRow = VERHOEFF_D[checksum]!;
    checksum = multiplicationRow[permuted]!;
  }
  return String(VERHOEFF_INV[checksum]!);
}

// ─────────────────────────────────────────────────────────────────────────────
// Entropy
// ─────────────────────────────────────────────────────────────────────────────

export function shannonEntropy(value: string): number {
  if (value.length === 0) return 0;
  const counts = new Map<string, number>();
  for (const char of value) counts.set(char, (counts.get(char) ?? 0) + 1);
  let entropy = 0;
  for (const count of counts.values()) {
    const p = count / value.length;
    entropy -= p * Math.log2(p);
  }
  return entropy;
}

// ─────────────────────────────────────────────────────────────────────────────
// T2 — structural validators (REQ-DATA-001 section 4.3)
// ─────────────────────────────────────────────────────────────────────────────

/** REQ-DATA-001 4.3: PAN's fourth character is a holder-type code. */
const PAN_HOLDER_TYPES: ReadonlySet<string> = new Set('PCFHATBLJG');

/** REQ-DATA-001 4.3: UPI handles must appear in a maintained PSP allowlist. */
export const UPI_HANDLES: ReadonlySet<string> = new Set([
  'okhdfcbank', 'okicici', 'oksbi', 'okaxis', 'ybl', 'apl',
  'ibl', 'axl', 'paytm', 'postbank', 'barodampay', 'upi',
]);

const PAN_RE = /^[A-Z]{5}[0-9]{4}[A-Z]$/;
const IFSC_RE = /^[A-Z]{4}0[A-Z0-9]{6}$/;
const UPI_RE = /^([A-Za-z0-9._-]{2,256})@([A-Za-z0-9]{2,32})$/;
const MOBILE_IN_RE = /^(?:\+91[ -]?|0)?([6-9]\d{4}[ -]?\d{5})$/;
const POSTAL_RE = /^[1-9]\d{5}$/;

export function panValid(candidate: string): boolean {
  const value = candidate.trim().toUpperCase();
  if (!PAN_RE.test(value)) return false;
  return PAN_HOLDER_TYPES.has(value[3]!);
}

export function ifscValid(candidate: string): boolean {
  return IFSC_RE.test(candidate.trim().toUpperCase());
}

export function upiVpaValid(candidate: string): boolean {
  const match = UPI_RE.exec(candidate.trim());
  if (match === null) return false;
  return UPI_HANDLES.has(match[2]!.toLowerCase());
}

export function mobileInValid(candidate: string): boolean {
  return MOBILE_IN_RE.test(candidate.trim());
}

export function postalCodeInValid(candidate: string): boolean {
  return POSTAL_RE.test(candidate.trim());
}

export function entropyMeets(value: string, floorBits: number): boolean {
  return shannonEntropy(value) >= floorBits;
}

