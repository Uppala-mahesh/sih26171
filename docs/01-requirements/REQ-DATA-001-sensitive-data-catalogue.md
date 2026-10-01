# SENSITIVE DATA CATALOGUE

| Field | Value |
|---|---|
| Document ID | `REQ-DATA-001` |
| Version | 1.0 — Draft |
| Status | 🟡 Draft — **Part 1 of 2** (purpose, classification model, entity registry) |
| Owner | Technical Lead |
| **Authority** | **This document is the single source of truth for the PII entity taxonomy.** |
| Generates | `packages/taxonomy/entities.yaml` → `entities.py` + `entities.ts` |

---

## 1. Purpose and authority

### 1.1 Why this document exists

The v1 prototype contained **two independent PII engines with non-overlapping vocabularies**:

| Entity | v1 JavaScript engine | v1 Python engine |
|---|---|---|
| Aadhaar | ✅ detected | ❌ absent |
| PAN | ✅ detected | ❌ absent |
| UPI VPA | ✅ detected | ❌ absent |
| IFSC | ✅ detected | ❌ absent |
| OTP | ✅ detected | ❌ absent |
| Synthetic secrets | ❌ absent | ✅ detected |

Worse, v1's `EntityType` enum had **no members** for Aadhaar, PAN, UPI, OTP, IFSC, or student
IDs — so those detections could not even be *represented* once they reached the backend. A page's
most India-sensitive data was caught on-device and then silently lost at the boundary.

This document eliminates that class of defect permanently.

### 1.2 Governing rules

| Rule | Statement |
|---|---|
| **D-1** | No detector, in any runtime, may define its own entity list. All entity definitions originate here. |
| **D-2** | Every runtime consumes the **generated** output of this catalogue. Hand-edited duplicates are a build failure. |
| **D-3** | Adding an entity type requires editing **this catalogue only** — never an existing detector module. |
| **D-4** | A cross-runtime parity test asserts that Python and TypeScript expose identical entity sets. Divergence fails the build. |

---

## 2. Classification model

### 2.1 Sensitivity classes

| Class | Meaning | Default handling |
|---|---|---|
| **CRITICAL** | Immediate harm on disclosure — credentials, one-time codes, payment cards, national IDs | Always redact; never transmitted under any mode |
| **HIGH** | Directly identifies an individual | Always redact |
| **MEDIUM** | Quasi-identifier — identifying only in combination | Redact when present in the perceived surface |
| **LOW** | Weak identifier | Redact when correlated with a MEDIUM or higher entity |

### 2.2 Verification tiers

Verification tier determines how much evidence is required before a match is trusted. **This is
the primary defence of the 20% precision score** — v1 matched on shape alone, so any 13–19 digit
run was treated as a card number.

| Tier | Method | Behaviour on match |
|---|---|---|
| **T1 — Verified** | Checksum (Luhn, Verhoeff) or cryptographic shape | High confidence; auto-redact |
| **T2 — Structured** | Strict format regular expression | Medium-high confidence; redact |
| **T3 — Contextual** | Keyword **and** shape must both match | Redact if context present; otherwise emit `UNCERTAIN` |
| **T4 — Semantic** | NER or classifier above a confidence threshold | Redact above threshold; otherwise emit `UNCERTAIN` |

### 2.3 Detection outcome states

Every detection resolves to exactly one state. These states are part of the public contract —
downstream components branch on them, so they may never be inferred or assumed.

| State | Meaning | Downstream behaviour |
|---|---|---|
| `SANITIZED` | Detection and redaction completed **and independently verified** | Context may be transmitted |
| `DEGRADED` | A required capability was unavailable; redaction applied conservatively | Transmitted, but **declared** — may not be presented as full capability |
| `UNCERTAIN` | Ambiguous match below the confidence threshold | Fail closed: redact, and declare |
| `NOT_INSTRUMENTED` | The check could not run at all | Fail closed: withholds the context |

> **Charter C-5:** a degraded or failed subsystem must declare itself; it may never masquerade as
> success. This table is how that rule is enforced in code.

## 3. Entity registry

This is the authoritative registry, and the direct input to `packages/taxonomy/entities.yaml`.

**Column semantics.** *Tier* refers to §2.2 · *Context required* means a keyword or structural cue
must also be present, or the match degrades to `UNCERTAIN` · *Placeholder* is the token form
substituted into sanitized output.

| ID | Category | Class | Tier | Context required | Placeholder | Notes |
|---|---|---|---|---|---|---|
| `AADHAAR` | Indian national ID | CRITICAL | T1 Verhoeff | No | `<AADHAAR_n>` | 12 digits; ignore spaces/dashes. **Verhoeff check digit mandatory.** |
| `PAN` | Indian tax ID | HIGH | T2 format | No | `<PAN_n>` | `[A-Z]{5}[0-9]{4}[A-Z]`; 4th character encodes holder type |
| `UPI_VPA` | Indian payment address | HIGH | T2 format | No | `<UPI_n>` | `user@handle`; handle must appear in the known PSP allowlist |
| `IFSC` | Indian bank branch code | MEDIUM | T2 format | No | `<IFSC_n>` | `[A-Z]{4}0[A-Z0-9]{6}` |
| `MOBILE_IN` | Indian mobile number | HIGH | T2 format | No | `<PHONE_n>` | 10 digits beginning 6–9; optional `+91` prefix |
| `PHONE_INTL` | International phone | MEDIUM | T2 format | No | `<PHONE_n>` | E.164-shaped |
| `BANK_ACCOUNT` | Bank account number | HIGH | T3 contextual | **Yes** | `<ACCOUNT_n>` | 9–18 digits; requires an account keyword nearby |
| `CREDIT_CARD` | Payment card number | CRITICAL | T1 Luhn | No | `<CARD_n>` | 13–19 digits; **Luhn check mandatory** |
| `EMAIL` | Email address | HIGH | T2 format | No | `<EMAIL_n>` | |
| `PASSWORD` | Credential | CRITICAL | T3 contextual | **Yes** | `<PASSWORD_n>` | Additionally: any `input[type=password]` value is redacted unconditionally |
| `OTP` | One-time passcode | CRITICAL | T3 contextual | **Yes** | `<OTP_n>` | 4–8 digits with keyword; never transmitted |
| `API_KEY` | Machine credential | CRITICAL | T2 format | No | `<SECRET_n>` | Provider prefixes (`AIza…`, `gh*_`, `sk-`) plus an entropy check |
| `JWT` | Bearer token | CRITICAL | T2 format | No | `<SECRET_n>` | Three base64url segments |
| `SECRET_GENERIC` | Unclassified secret | CRITICAL | T3 contextual | **Yes** | `<SECRET_n>` | High-entropy string adjacent to a secret keyword |
| `PERSON_NAME` | Person name | MEDIUM | T4 NER | **Yes** | `<PERSON_n>` | |
| `ADDRESS` | Postal address | MEDIUM | T3 + T4 | **Yes** | `<ADDRESS_n>` | |
| `DOB` | Date of birth | MEDIUM | T3 contextual | **Yes** | `<DOB_n>` | Requires a date-of-birth keyword |
| `POSTAL_CODE_IN` | Indian PIN code | LOW | T2 format | No | `<PIN_n>` | 6 digits, first digit 1–9 |
| `STUDENT_ID` | Roll / hall-ticket number | LOW | T3 contextual | **Yes** | `<ID_n>` | Institution-specific shapes; context mandatory |
| `FACE_IMAGE` | Face in image | HIGH | T4 classifier | No | `<FACE_n>` | ⚠️ **PENDING `CR-001`** — not scheduled until the CR is closed |

### 3.1 Registry statistics

| Class | Count | Entities |
|---|---|---|
| CRITICAL | 7 | `AADHAAR` · `CREDIT_CARD` · `PASSWORD` · `OTP` · `API_KEY` · `JWT` · `SECRET_GENERIC` |
| HIGH | 5 | `PAN` · `UPI_VPA` · `MOBILE_IN` · `BANK_ACCOUNT` · `EMAIL` |
| MEDIUM | 5 | `IFSC` · `PHONE_INTL` · `PERSON_NAME` · `ADDRESS` · `DOB` |
| LOW | 2 | `POSTAL_CODE_IN` · `STUDENT_ID` |
| *Pending CR-001* | *1* | *`FACE_IMAGE` — excluded from sprint scope until the CR is closed* |

**Active total: 19 entities** (20 including `FACE_IMAGE`, pending `CR-001`).

> **Note on scope growth.** v1 detected a subset of this registry. The additions — Aadhaar, PAN,
> UPI, IFSC, OTP, and student IDs — are precisely the India-specific identifiers the problem
> statement names, and precisely the ones v1 could not carry across the boundary. They are
> therefore **requirements**, not enhancements.

<!-- APPEND-POINT -->