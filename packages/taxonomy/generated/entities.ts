/**
 * SIH26171 — Entity registry (GENERATED — DO NOT EDIT).
 *
 * Generated from packages/taxonomy/entities.yaml by
 * infra/generate_taxonomy.py. Edit the YAML and re-run; hand edits here are
 * overwritten, and `generate_taxonomy.py --check` fails the build when this
 * file is stale.
 *
 * Regeneration is the enforcement of AD-6 and REQ-DATA-001 rule X-1: both
 * runtimes consume one source, so they cannot drift.
 *
 * Parity is proven BEHAVIOURALLY by tests/contract/test_parity.py, which
 * compares detected findings rather than declared constants — two registries
 * can agree on paper and disagree in practice.
 *
 * @generated
 */

export const SENSITIVITY_CLASSES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;
export type SensitivityClass = (typeof SENSITIVITY_CLASSES)[number];

export const VERIFICATION_TIERS = {
  "T1": "Verified - arithmetic checksum or cryptographic shape",
  "T2": "Structured - strict format expression",
  "T3": "Contextual - shape AND a local context cue",
  "T4": "Semantic - NER or classifier above a confidence threshold",
} as const;
export type VerificationTier = keyof typeof VERIFICATION_TIERS;

export interface EntitySpec {
  readonly id: string;
  readonly display: string;
  readonly sensitivity: SensitivityClass;
  readonly tier: VerificationTier;
  readonly validator: string | null;
  readonly requiresContext: boolean;
  readonly contextCues: readonly string[];
  readonly placeholder: string;
  /** Source expression, or null for model-backed entities. */
  readonly pattern: string | null;
}

export const ENTITIES: readonly EntitySpec[] = [
  {
    id: "AADHAAR",
    display: "Aadhaar Number",
    sensitivity: "CRITICAL",
    tier: "T1",
    validator: "verhoeff",
    requiresContext: false,
    contextCues: [],
    placeholder: "AADHAAR",
    pattern: "\\b\\d{4}[ -]?\\d{4}[ -]?\\d{4}\\b",
  },
  {
    id: "PAN",
    display: "Permanent Account Number",
    sensitivity: "HIGH",
    tier: "T2",
    validator: "pan_structure",
    requiresContext: false,
    contextCues: [],
    placeholder: "PAN",
    pattern: "\\b[A-Z]{5}[0-9]{4}[A-Z]\\b",
  },
  {
    id: "UPI_VPA",
    display: "UPI Virtual Payment Address",
    sensitivity: "HIGH",
    tier: "T2",
    validator: "psp_allowlist",
    requiresContext: false,
    contextCues: [],
    placeholder: "UPI",
    pattern: "\\b[\\w.\\-]+@(?:okhdfcbank|okicici|oksbi|okaxis|ybl|apl|ibl|axl|paytm|postbank|barodampay|upi)\\b",
  },
  {
    id: "IFSC",
    display: "IFSC Bank Branch Code",
    sensitivity: "MEDIUM",
    tier: "T2",
    validator: "ifsc_structure",
    requiresContext: false,
    contextCues: [],
    placeholder: "IFSC",
    pattern: "\\b[A-Z]{4}0[A-Z0-9]{6}\\b",
  },
  {
    id: "MOBILE_IN",
    display: "Indian Mobile Number",
    sensitivity: "HIGH",
    tier: "T2",
    validator: "mobile_in_structure",
    requiresContext: false,
    contextCues: [],
    placeholder: "PHONE",
    pattern: "(?:\\+91[ -]?|0)?[6-9]\\d{4}[ -]?\\d{5}\\b",
  },
  {
    id: "PHONE_INTL",
    display: "International Phone Number",
    sensitivity: "MEDIUM",
    tier: "T2",
    validator: "e164_structure",
    requiresContext: false,
    contextCues: [],
    placeholder: "PHONE",
    pattern: "\\+\\d{1,3}[ -]?\\d{2,4}[ -]?\\d{3,4}[ -]?\\d{0,4}\\b",
  },
  {
    id: "BANK_ACCOUNT",
    display: "Bank Account Number",
    sensitivity: "HIGH",
    tier: "T3",
    validator: "none",
    requiresContext: true,
    contextCues: ["account", "acct", "a/c", "bank", "balance"],
    placeholder: "ACCOUNT",
    pattern: "\\b\\d{9,18}\\b",
  },
  {
    id: "CREDIT_CARD",
    display: "Payment Card Number",
    sensitivity: "CRITICAL",
    tier: "T1",
    validator: "luhn",
    requiresContext: false,
    contextCues: [],
    placeholder: "CARD",
    pattern: "\\b(?:\\d[ -]?){13,19}\\b",
  },
  {
    id: "EMAIL",
    display: "Email Address",
    sensitivity: "HIGH",
    tier: "T2",
    validator: "none",
    requiresContext: false,
    contextCues: [],
    placeholder: "EMAIL",
    pattern: "\\b[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}\\b",
  },
  {
    id: "PASSWORD",
    display: "Credential",
    sensitivity: "CRITICAL",
    tier: "T3",
    validator: "none",
    requiresContext: true,
    contextCues: ["password", "passwd", "pwd", "pass"],
    placeholder: "PASSWORD",
    pattern: null,
  },
  {
    id: "OTP",
    display: "One-Time Passcode",
    sensitivity: "CRITICAL",
    tier: "T3",
    validator: "none",
    requiresContext: true,
    contextCues: ["otp", "code", "verification", "pin", "token", "2fa"],
    placeholder: "OTP",
    pattern: "\\b\\d{4,8}\\b",
  },
  {
    id: "API_KEY",
    display: "Machine Credential",
    sensitivity: "CRITICAL",
    tier: "T2",
    validator: "entropy",
    requiresContext: false,
    contextCues: [],
    placeholder: "SECRET",
    pattern: "\\b(?:AIza[0-9A-Za-z_\\-]{35}|gh[opusr]_[A-Za-z0-9_]{36,}|sk-[A-Za-z0-9]{32,})\\b",
  },
  {
    id: "JWT",
    display: "Bearer Token",
    sensitivity: "CRITICAL",
    tier: "T2",
    validator: "jwt_structure",
    requiresContext: false,
    contextCues: [],
    placeholder: "SECRET",
    pattern: "\\beyJ[A-Za-z0-9_\\-]+\\.[A-Za-z0-9_\\-]+\\.[A-Za-z0-9_\\-]+\\b",
  },
  {
    id: "SECRET_GENERIC",
    display: "Unclassified Secret",
    sensitivity: "CRITICAL",
    tier: "T3",
    validator: "entropy",
    requiresContext: true,
    contextCues: ["secret", "token", "key", "password", "api_key", "apikey", "credential"],
    placeholder: "SECRET",
    pattern: "\\b[A-Za-z0-9+/]{24,}={0,2}\\b",
  },
  {
    id: "PERSON_NAME",
    display: "Person Name",
    sensitivity: "MEDIUM",
    tier: "T4",
    validator: "ner",
    requiresContext: true,
    contextCues: ["name", "holder", "account holder", "beneficiary", "applicant", "owner"],
    placeholder: "PERSON",
    pattern: null,
  },
  {
    id: "ADDRESS",
    display: "Postal Address",
    sensitivity: "MEDIUM",
    tier: "T4",
    validator: "ner",
    requiresContext: true,
    contextCues: ["address", "addr", "residence", "street", "city", "pin"],
    placeholder: "ADDRESS",
    pattern: null,
  },
  {
    id: "DOB",
    display: "Date of Birth",
    sensitivity: "MEDIUM",
    tier: "T3",
    validator: "none",
    requiresContext: true,
    contextCues: ["dob", "date of birth", "birth", "born"],
    placeholder: "DOB",
    pattern: "\\b\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}\\b",
  },
  {
    id: "POSTAL_CODE_IN",
    display: "Indian PIN Code",
    sensitivity: "LOW",
    tier: "T2",
    validator: "none",
    requiresContext: false,
    contextCues: [],
    placeholder: "PIN",
    pattern: "\\b[1-9]\\d{5}\\b",
  },
  {
    id: "STUDENT_ID",
    display: "Roll or Hall Ticket Number",
    sensitivity: "LOW",
    tier: "T3",
    validator: "none",
    requiresContext: true,
    contextCues: ["roll", "roll no", "hall ticket", "admission", "enrollment", "reg no"],
    placeholder: "ID",
    pattern: "\\b\\d{4}[-\\s]?\\d{2}[-\\s]?\\d{3}[-\\s]?\\d{3}\\b",
  },
  {
    id: "FACE_IMAGE",
    display: "Face in Image",
    sensitivity: "HIGH",
    tier: "T4",
    validator: "model",
    requiresContext: false,
    contextCues: [],
    placeholder: "FACE",
    pattern: null,
  },
];

export const ENTITY_IDS = ["AADHAAR", "PAN", "UPI_VPA", "IFSC", "MOBILE_IN", "PHONE_INTL", "BANK_ACCOUNT", "CREDIT_CARD", "EMAIL", "PASSWORD", "OTP", "API_KEY", "JWT", "SECRET_GENERIC", "PERSON_NAME", "ADDRESS", "DOB", "POSTAL_CODE_IN", "STUDENT_ID", "FACE_IMAGE"] as const;
export type EntityId = (typeof ENTITY_IDS)[number];

export const TAXONOMY_VERSION = "1.0.0";

/** Entities carrying an expression. The rest are model-backed (T4). */
export const PATTERN_BACKED: readonly EntitySpec[] = ENTITIES.filter(
  (entity) => entity.pattern !== null,
);

