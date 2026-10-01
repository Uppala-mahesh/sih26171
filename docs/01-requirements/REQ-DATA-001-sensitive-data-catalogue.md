# SENSITIVE DATA CATALOGUE

| Field | Value |
|---|---|
| Document ID | `REQ-DATA-001` |
| Version | 1.0 — Draft |
| Status | 🟡 **Complete — awaiting Product Owner approval** |
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

## 4. Validation rules

Structural shape alone is not evidence. Each `T1` entity must pass an arithmetic check, and every
entity must be normalised before validation. **This section is how the 20% precision weight is
defended** — v1 admitted any 13–19 digit run as a card number.

### 4.1 Normalisation (applies before every check)

| Step | Rule |
|---|---|
| N-1 | Strip whitespace, `-`, and `.` from numeric-shaped candidates |
| N-2 | Uppercase alphabetic-shaped candidates (`PAN`, `IFSC`) |
| N-3 | Reject any candidate containing a character outside its declared alphabet |
| N-4 | Reject candidates whose length falls outside the declared bounds |

### 4.2 Arithmetic validators

| Entity | Validator | Definition |
|---|---|---|
| `CREDIT_CARD` | **Luhn** | Doubling every second digit from the right; subtract 9 where the result exceeds 9; the total must be ≡ 0 (mod 10). |
| `AADHAAR` | **Verhoeff** | Dihedral D₅ checksum over the 12 digits. **This is the actual Aadhaar checksum** — it is not Luhn, and using Luhn here produces both false positives and false negatives. |
| `API_KEY` | Prefix + entropy | Must match a provider prefix (`AIza…`, `ghp_`/`gho_`/`ghu_`/`ghs_`/`ghr_`, `sk-`) **and** exceed a Shannon-entropy floor. |
| `JWT` | Structure | Exactly three base64url segments; the first two must decode to valid JSON. |
| `SECRET_GENERIC` | Entropy + context | Shannon entropy above the configured floor **and** a secret keyword in context. |

### 4.3 Structural validators

| Entity | Rule |
|---|---|
| `PAN` | `[A-Z]{5}[0-9]{4}[A-Z]`; the 4th character must be a recognised holder-type code (`P`, `C`, `H`, `F`, `A`, `T`, `B`, `L`, `J`, `G`) |
| `IFSC` | `[A-Z]{4}0[A-Z0-9]{6}`; the 5th character is always literally `0` |
| `UPI_VPA` | `localpart@handle`, where `handle` must appear in the maintained PSP allowlist |
| `MOBILE_IN` | 10 digits, first digit in `6–9`; optional `+91` or `0` prefix stripped in normalisation |
| `POSTAL_CODE_IN` | 6 digits, first digit `1–9` (a leading `0` is invalid) |

### 4.4 Validation outcome discipline

| Situation | Outcome |
|---|---|
| Validator **passes** | Detector may emit a positive finding at high confidence |
| Validator **fails** | Finding is **discarded** — never downgraded to a lower-confidence positive |
| Validator **errors** | Emit `NOT_INSTRUMENTED` and fail closed (`FR-PII-9`) |

> A failing checksum is *evidence against* the match. Downgrading it to "probably still a card"
> is the exact behaviour that destroys precision.

---

## 5. Context gating

`T3` entities require a context cue in addition to shape. Context must be **local** — a keyword
anywhere on the page is not evidence.

| Rule | Statement |
|---|---|
| G-1 | The cue must appear within a bounded window of the candidate (default: same text node or an immediately adjacent one). |
| G-2 | The cue must be matched **whole-word** and case-insensitively. |
| G-3 | The cue list is defined per entity in the catalogue and may not be extended by a detector at runtime. |
| G-4 | Absence of a cue yields `UNCERTAIN`, which fails closed by redacting (`FR-PII-9`) — it never yields a silent pass-through. |
| G-5 | A cue that appears **inside** the candidate value does not count as context (prevents self-justifying matches). |

### 5.1 Worked example — why whole-word matching matters

| Input | Correct outcome | Rationale |
|---|---|---|
| `account no: 123456789012` | `BANK_ACCOUNT` | Cue present, shape valid |
| `Pinterest board 123456789` | Not a match | `Pin` inside `Pinterest` is not a whole-word cue |
| `1234 5678 9012` with no context | `UNCERTAIN` | 12 digits alone is ambiguous between Aadhaar and a phone grouping |

---

## 6. Placeholder convention

| Rule | Statement |
|---|---|
| P-1 | Format is `<TYPE_n>`, where `TYPE` is the entity ID and `n` is a per-observation counter starting at 1. |
| P-2 | Numbering is **per entity type**, so `<AADHAAR_1>` and `<CARD_1>` coexist. |
| P-3 | Identical original values within one observation receive identical placeholders, even across modalities (`FR-VLT-2`). |
| P-4 | Distinct original values never share a placeholder (`FR-VLT-3`). |
| P-5 | Only uppercase alphanumerics and underscore are permitted inside the token — no spaces, no punctuation. |
| P-6 | **Collision guard.** If the source page already contains text matching a placeholder pattern, the placeholder namespace shall be offset until no collision exists, because a page must not be able to forge a token that later detokenizes to attacker-chosen content. |

> **P-6 is a security control, not a formatting rule.** Without it, a hostile page could embed the
> literal string `<EMAIL_1>` in its own content, and any downstream detokenization would treat
> page-authored text as vault-authoritative.

---

## 7. Cross-runtime parity

| Rule | Statement |
|---|---|
| X-1 | This catalogue generates `packages/taxonomy/entities.yaml`, which generates `entities.py` and `entities.ts`. Hand-editing generated output is prohibited. |
| X-2 | Generated files carry a content hash and the catalogue version. |
| X-3 | A parity test asserts that Python and TypeScript expose an **identical** entity set, class, tier, and context requirement. |
| X-4 | Any divergence **fails the build**. There is no warning-only mode. |
| X-5 | Adding, renaming, or removing an entity is a versioned change requiring a catalogue version bump and a parity re-run. |

---

## 8. Catalogue summary

| Metric | Value |
|---|---|
| Active entities | **19** |
| Pending `CR-001` | 1 (`FACE_IMAGE`) |
| Sensitivity classes | 4 (CRITICAL, HIGH, MEDIUM, LOW) |
| Verification tiers | 4 (T1 verified · T2 structured · T3 contextual · T4 semantic) |
| Arithmetic validators | 2 (Luhn, Verhoeff) + 2 structural/entropy checks |
| Outcome states | 4 (`SANITIZED`, `DEGRADED`, `UNCERTAIN`, `NOT_INSTRUMENTED`) |
| Consuming runtimes | 2 (Python, TypeScript) — kept in parity by X-3 |

*End of `REQ-DATA-001`.*