# PRIVACY BOUNDARY SPECIFICATION

| Field | Value |
|---|---|
| Document ID | `SEC-BOUND-001` |
| Version | 1.0 — Draft |
| Status | 🟡 **Complete — awaiting Product Owner approval** |
| Owner | Technical Lead |
| **Authority** | **This is the governing design artifact.** Every other design document shall be consistent with it. Where any design artifact conflicts with this one, this one prevails. |
| Traces to | `PROJECT-CHARTER.md` §2 · `REQ-SRS-001` §2.1, `FR-EGR`, `FR-RED`, `FR-VLT`, `NFR-PRIV` |
| Traced by | `DES-ARCH-001` (derived from this document) · `SEC-THREAT-001` (attacks this document) |

---

## 1. Purpose and ordering rationale

### 1.1 Why this document is written first

The problem statement §32 states plainly: *"The privacy boundary is the heart of the system."*
This document is therefore placed **before** the architecture, not after it.

| If architecture comes first | If the boundary comes first *(chosen)* |
|---|---|
| The boundary is a constraint retrofitted onto existing structures. | The architecture becomes a **derivation** from the invariant. |
| Modules exist for implementation convenience; the boundary is enforced by convention at each call site. | Modules exist **because** a crossing required an enforcement point. |
| A reviewer must take the security claim on faith. | A reviewer can trace every container back to the crossing it defends. |

**This ordering is a direct response to the v1 failure mode.** In v1, `SafeContextGateway` was a
well-designed chokepoint — but a second endpoint (`/agent/run-step`) was written alongside it and
**bypassed it entirely** until an external audit caught the omission. The boundary was correct in
isolation and absent in practice, because nothing forced every path through it.

This document exists to make that failure structurally impossible: **every crossing is
enumerated, and an unenumerated crossing is a build failure.**

---

## 2. The core invariant

> ### **Raw sensitive content shall never cross the device trust boundary — in any modality, in any direction, at any time.**

### 2.1 Corollaries

The invariant is absolute. These are its consequences, each independently testable.

| # | Corollary | Closing requirement |
|---|---|---|
| **I-1** | Not in text, in any encoded form — raw, base64, URL-encoded, hex, or hash of a small space. | `FR-PII`, `FR-EGR-2` |
| **I-2** | Not in pixels — no raw or partially-obscured screenshot, in any format. | `FR-RED-2`, `FR-EGR-2` |
| **I-3** | Not in metadata — not in attributes, accessible names, alt text, titles, or placeholders. | `FR-PII-5` |
| **I-4** | Not in telemetry, logs, audit records, error messages, or stack traces. | `NFR-PRIV-1`, `NFR-SEC-5` |
| **I-5** | Not in the placeholder reverse mapping (the vault). | `FR-VLT-1` |
| **I-6** | Not in any persisted artifact — no page data at rest, ever. | `NFR-PRIV-2` |
| **I-7** | **No caller assertion substitutes for verification at the boundary.** A payload claiming to be sanitized is re-verified. | **`FR-EGR-4`**, `DC-5` |
| **I-8** | The invariant holds regardless of the active capability rung. A degraded system redacts *more*, never *less*. | **`NFR-PORT-5`** |

> **I-7 is the corollary v1 violated.** v1 accepted an `is_sanitized: true` boolean from the
> extension on trust. When the vision pipeline silently failed, it produced a 1×1 transparent image
> carrying that same boolean — and the backend accepted it as sanitized.
>
> **The boundary cannot be enforced by the sender; only the receiver can enforce it.** This is why
> verification at each crossing is mandatory rather than optional.

## 3. Trust zones

### 3.1 Zone definitions

| Zone | Name | Trust posture | Contents |
|---|---|---|---|
| **Z0** | **Untrusted Page** | **Hostile** | Target page DOM, scripts, frames, and all page-authored content. May attempt indirect prompt injection. |
| **Z1** | **Device — Perception & Privacy** | **Trusted** | Content script, on-device runtime, vision engine, vault, redactor. **Owns the boundary.** |
| **Z2** | **Device — Reasoning Enclave** | **Semi-trusted** | Loopback-only service. Receives sanitized context only. **Re-verifies; does not trust Z1's assertions.** |
| **Z3** | **External Reasoning** | **Untrusted** | Optional cloud provider. Receives sanitized context only, gated by the egress chokepoint. |
| **Z4** | **Device — Presentation** | **Unprivileged** | Side panel and demo console. Renders sanitized telemetry. Owns no domain logic and no raw data. |
| **Z5** | **Device — At-Rest Storage** | **Restricted** | Settings only. **No user page data may ever enter this zone.** |

### 3.2 Zone diagram

```
  Z0  UNTRUSTED PAGE  ──────┐  may inject instructions
                            │
                            ▼
 ╔══════════════════════════════════════════════════════════════════╗
 ║  Z1  DEVICE — PERCEPTION & PRIVACY            ★ OWNS BOUNDARY    ║
 ║      content script · vision engine · detectors · vault · redactor║
 ╚═══════════════════════╤══════════════════════════════════════════╝
                         │  ONLY sanitized context may cross  ⇓ B-2
                         ▼
 ╔══════════════════════════════════════════════════════════════════╗
 ║  Z2  DEVICE — REASONING ENCLAVE          loopback 127.0.0.1 only ║
 ║      pipeline · policy · verifier · egress chokepoint            ║
 ╚═══════╤═════════════════════╤═══════════════════╤════════════════╝
         │                     │                   │
   ⇓ B-3 │               ⇓ B-4 │             ⇓ B-5 │
         ▼                     ▼                   ▼
   Z3  EXTERNAL          Z4  PRESENTATION     Z5  AT-REST
   REASONING             side panel · console  SETTINGS ONLY
   sanitized only        sanitized telemetry   no page data
```

**Z1 is the only zone permitted to hold raw content, and only transiently.** Raw content enters Z1
from Z0, is sanitized *within* Z1, and only sanitized output leaves. No other zone ever sees raw
content — including Z5, which never sees page data at all.

---

## 4. Boundary crossing inventory

Every crossing is enumerated. **A crossing not listed here is a defect**, and the build fails on
its detection (`NFR-MAIN-2`). This is the mechanism that would have caught v1's `/run-step` bypass.

| ID | Crossing | Dir | Permitted | **Forbidden** | Enforcement point | Verified by |
|---|---|---|---|---|---|---|
| **B-1** | Z0 → Z1 | IN | Page content, consumed as **data only** | Treating page content as instruction | Content-script isolation; untrusted block marked and wrapped | Injection corpus (`NFR-SEC-7`) |
| **B-2** | Z1 → Z2 | OUT | Sanitized context in state `SANITIZED`, `DEGRADED`, or `UNCERTAIN` | Raw text · raw pixels · vault · reverse map · `NOT_INSTRUMENTED` payloads | Egress chokepoint **and** receiver-side re-verification | Contract test + payload capture |
| **B-3** | Z2 → Z3 | OUT | Sanitized context with declared state | Anything raw, anything `NOT_INSTRUMENTED` | Egress chokepoint | Payload capture (`FR-EGR-6`) |
| **B-4** | Z2 → Z4 | OUT | Counts, states, timings, rung, decisions | Raw values · reverse maps · screenshots | Telemetry contract | Payload inspection (`NFR-PRIV-1`) |
| **B-5** | Z1 · Z2 → Z5 | OUT | **Settings only** | Any page-derived data | Storage contract | Filesystem diff (`NFR-PRIV-2`) |
| **B-6** | Z1 vault → Z0 element | OUT | The original value, into **its originally bound element only**, just-in-time | Injection into any other element · any inclusion in a network-bound payload | Target-binding revalidation (`FR-AGT-5`) | Binding + vault tests |
| **B-7** | Z1 → Z0 mutations | OUT | Action effects — clicks, typed values, focus | Bulk data written into the page | Action allowlist (`FR-EXE-3`) | Executor tests |
| **B-8** | Z2 → logs | OUT | Metadata, counts, identifiers | Raw values in any form | Logging contract | Log inspection (`NFR-SEC-5`) |
| **B-9** | Z4 → anywhere | OUT | Presentation only | *(nothing raw — Z4 never holds raw data by construction)* | Architectural | `NFR-MAIN-2` import rule |

### 4.1 The three crossings that carry the real risk

| Crossing | Why it is dangerous | Control |
|---|---|---|
| **B-2** | This is the boundary the whole problem statement is about. Everything else is secondary. | Dual enforcement: the sender sanitizes, **and the receiver re-verifies** (I-7). Neither is trusted alone. |
| **B-6** | The **only** path where raw values legitimately move after sanitization — the just-in-time detokenization that makes the agent useful. | Value may only enter the element it was originally extracted from. Any other destination is a violation, even though the destination is local. |
| **B-1** | Ingress, not egress — and therefore easy to overlook. The threat is not data *leaving*; it is instruction *entering*. | Page content is never authority. It is data, marked as untrusted, wrapped, and incapable of altering policy (`FR-POL-6`). |

## 5. The sanitization contract

What "sanitized" means must be **precise**, because this single word is the entire product claim.

### 5.1 Definition

> A payload is **sanitized for a declared destination** if and only if **all four** conditions hold:

| # | Condition | Enforced by |
|---|---|---|
| **S-1** | Every sensitive span has been replaced by its catalogue placeholder, or covered by an opaque irreversible mask. | `FR-RED-1`, `FR-RED-2` |
| **S-2** | The redaction has been **independently re-verified after application** — not asserted by the producer. | **`FR-RED-4`** |
| **S-3** | The payload's declared state matches what actually occurred. | `FR-RED-5` |
| **S-4** | The payload contains no vault reverse mapping, no raw screenshot, and no undeclared degradation. | `FR-VLT-1`, `FR-RED-8` |

**If any one condition fails, the payload is not sanitized for that destination.** There is no
partial credit and no destination-specific exemption.

### 5.2 The four states, and which may cross

| State | Meaning | May cross **B-2 / B-3**? | Receiver obligation |
|---|---|---|---|
| `SANITIZED` | All four conditions satisfied, S-2 independently verified | **Yes**, no caveat | Accept; record state |
| `DEGRADED` | A capability was unavailable. Redaction applied **conservatively** — *more* redaction than required | **Yes**, but state **must be declared** | Accept; record state; may request reduced fidelity |
| `UNCERTAIN` | One or more detections fell below the confidence threshold; resolved by redacting | **Yes**, but state **must be declared** | Accept; record state |
| `NOT_INSTRUMENTED` | A required check **could not run at all** | 🔴 **NO — payload is withheld** | *(It never arrives)* |

> **Why two states may cross and one may not.** `DEGRADED` and `UNCERTAIN` both fail in the
> **safe direction** — the system knows less, so it redacts *more*. Over-redaction costs utility,
> never privacy, and utility is a scored criterion rather than a safety property.
>
> `NOT_INSTRUMENTED` fails in the **unsafe direction** — the system does not know what it is
> missing. It is therefore withheld entirely, with no degraded substitute.

### 5.3 A state is a claim with evidence

A state may be declared **only together with its evidence**: which detectors ran, which validators
passed, which capability rung was active, and what the re-verification returned.

> **A state presented without evidence is `NOT_INSTRUMENTED` by definition.** There is no
> "probably sanitized" state.

This is the mechanism that makes I-7 (`FR-EGR-4`) enforceable at the type level rather than by
convention: a payload that cannot attach its evidence cannot declare a passing state.

### 5.4 Prohibited state transitions

| Transition | Verdict | Rationale |
|---|---|---|
| `NOT_INSTRUMENTED` → `SANITIZED` | 🔴 **Forbidden** | A failure may never be upgraded into a success. This is precisely the v1 defect: a fully-failed vision run was reported as sanitized. |
| `DEGRADED` → `SANITIZED` | 🔴 **Forbidden** | Degradation is permanent for that artefact. A later rerun producing a clean artefact does not retroactively clean this one. |
| `UNCERTAIN` → `SANITIZED` | 🔴 **Forbidden** | Ambiguity resolved by redaction stays resolved by redaction. |
| `*` → `NOT_INSTRUMENTED` | ✅ **Permitted** | Always safe. Any component may report its own failure. |

---

## 6. Data handling matrix

Raw values exist in **exactly one zone**, transiently.

| Sensitivity class | **Z1** (perception) | **Z2** (enclave) | **Z3** (external) | **Z4** (presentation) | **Z5** (at-rest) | Crosses **B-2** as |
|---|---|---|---|---|---|---|
| **CRITICAL** | Raw + placeholder | Placeholder only | Placeholder only | Counts only | **Never** | Placeholder only |
| **HIGH** | Raw + placeholder | Placeholder only | Placeholder only | Counts only | **Never** | Placeholder only |
| **MEDIUM** | Raw + placeholder | Placeholder | Placeholder | Counts | **Never** | Placeholder |
| **LOW** | Raw + placeholder | Placeholder | Placeholder | Counts | **Never** | Placeholder |
| **Vault (reverse map)** | In-memory only | **Never** | **Never** | **Never** | **Never** | **Never** |
| **Raw screenshot** | Transient only | **Never** | **Never** | **Never** | **Never** | **Never** |

> **The single most important row is the vault.** It is the only structure that maps a safe token
> back to a real secret. It exists in Z1, in memory, for the duration of a task, and reaches no
> other zone — not even the presentation zone, which receives counts only.

## 7. Retention & lifecycle

| Data | Zone | Maximum retention | Cleared by |
|---|---|---|---|
| Raw perception buffer | Z1 | **< 1 second** | Immediately on sanitization completion |
| Placeholder vault | Z1 | Task duration | Task end · origin navigation · user reset (`FR-VLT-4`) |
| Redacted screenshot | Z1 | One step | Step completion |
| Sanitized context | Z1 · Z2 | One step | Step completion |
| Session state | Z2 | Task duration | Terminal state reached |
| Audit records | Z2 · Z4 | Session | In-memory only; repository instance discarded |
| Telemetry | Z4 | Render lifetime | Memory only — never persisted |
| Settings | Z5 | Indefinite | Explicit user action |
| Benchmark results | — | Deliberate commit | Contains no page data by construction |

> **Zero retention is the target.** Every row above is a *maximum*, not an expected duration. The
> only category permitted to persist is user settings — which contain no page-derived data, and
> therefore cross no boundary (B-5 permits settings and forbids page data).

---

## 8. Forbidden data inventory

This is the **explicit never-list**. Each item is separately testable, and each appears in a test
assertion rather than only in a test title.

| # | Forbidden artefact | Forbidden where | Test assertion |
|---|---|---|---|
| **F-1** | Raw sensitive values, any entity class, **any encoding** — raw, base64, URL-encoded, hex, or hash of a small space | B-2, B-3, B-4, B-8 | Planted-PII capture across every provider returns **0 matches** |
| **F-2** | The vault reverse mapping | Every zone but Z1 memory | Storage and payload inspection returns **0 occurrences** |
| **F-3** | Raw or partially-obscured screenshots | Every zone but Z1 transient | Redaction reconstruction attempt recovers **0 characters** |
| **F-4** | Raw perception buffers | Every zone but Z1 | No raw-buffer type is constructible outside Z1 |
| **F-5** | Page-derived data at rest | Z5 | Filesystem diff across a task shows **0 page-derived artefacts** |
| **F-6** | API keys, tokens, credentials | Version control | Credential scan across **full history** returns **0 matches** |
| **F-7** | Browser-profile artefacts — Cookies, Login Data, History | Version control and any payload | Pattern scan returns **0 matches** |
| **F-8** | Reverse-mappable telemetry | B-4 | Telemetry payload carries **counts only** |
| **F-9** | Model prompts containing raw context | B-3 | Prompt capture returns **0 raw values** |
| **F-10** | Raw payload content in error messages or stack traces | B-8 | Fault-injection log inspection returns **0 raw values** |

> **F-7 is not hypothetical.** The v1 repository contains a live Chrome user-data directory —
> `Cookies`, `Login Data`, `History`, `Web Data` — inside `backend/scratch/`, untracked but not
> gitignored. One `git add -A` from an agent or a teammate would have committed live session
> credentials. It is now gitignored. This entry exists so the failure cannot recur unnoticed.

---

## 9. Enforcement architecture

Where each rule actually lives, and whether a violation fails the build.

| Rule | Enforced in | Mechanism | **Build-enforced** |
|---|---|---|---|
| **S-1** redaction applied | Redaction module | Pure function with no bypass path | ✅ Yes |
| **S-2** independent re-verification | Verification module | Producer **cannot supply** the result — it is recomputed | ✅ Yes |
| **S-3** state matches reality | State type | Exhaustive enum; a bare boolean cannot be constructed | ✅ Yes |
| **S-4** no vault/raw in payload | Payload constructors | The types physically cannot hold these fields | ✅ Yes |
| **Crossing enumeration** | Egress chokepoint | Single permitted import for network I/O | ✅ Yes (import-linter) |
| **Zone isolation** | Module boundaries | Directed import rules; upward and lateral imports rejected | ✅ Yes (import-linter) |
| **Prohibited transitions** | State machine | Exhaustive transition table; the forbidden edges are unrepresentable | ✅ Yes (types) |
| **Retention limits** | Disposal lifecycle | Explicit `dispose()` required on every owned resource | ⚠️ Partially (`NFR-RES-9`) |

> **Eight of nine rules are enforced by the compiler or the linter, not by review.** This is the
> difference between a boundary that is *documented* and one that is *real*. A reviewer can be
> wrong, tired, or rushed. A type error is not.

## 10. Verification plan

Every boundary claim in this document maps to a test whose pass condition is an assertion, not a
review opinion.

| # | Boundary claim | Test | **Pass condition** |
|---|---|---|---|
| **V-1** | No raw value crosses B-2, B-3, B-4, or B-8 | Planted-PII capture across every provider and mode | **0** matches of any planted secret, in any encoding |
| **V-2** | The receiver re-verifies rather than trusting the sender | Forge a payload declaring `SANITIZED` while carrying a planted secret | **Rejected** at B-2 |
| **V-3** | The vault never leaves Z1 memory | Storage dump + payload inspection across a full task | **0** occurrences |
| **V-4** | No page data is persisted | Filesystem diff across a complete task | **0** page-derived artefacts |
| **V-5** | Degradation is always declared | Force each capability rung to fail in turn | **0** artefacts assert `SANITIZED` |
| **V-6** | A failure is never upgraded to a success | Attempt `NOT_INSTRUMENTED` → `SANITIZED` | **Rejected** at compile time |
| **V-7** | There is no unenumerated crossing | Import-linter + network-call scan over the whole codebase | **0** violations |
| **V-8** | Page content cannot influence policy | Indirect prompt-injection corpus | **0** privilege escalations |
| **V-9** | Detokenization is target-bound | Attempt to dispatch a vault value into any element other than its origin | **Rejected** |
| **V-10** | Redaction is genuinely irreversible | Reconstruction attempt on a redacted region | **0** characters recovered |
| **V-11** | Mask geometry matches the detection | Compare applied mask to detection box | **IoU ≥ 0.90** on every region |
| **V-12** | Redaction preserves utility | Compare non-sensitive regions pre/post | **≥ 0.95** preserved |

> **V-2 is the single most important test in the project.** It is the direct regression test for the
> v1 defect: a sender claiming success without evidence must be rejected. If the whole boundary
> reduces to one test, this is the one — because every other control assumes the receiver can
> refuse what the sender asserts.

---

## 11. Boundary violations are build failures

| Condition | Consequence |
|---|---|
| A network call exists outside the egress chokepoint | 🔴 **Build fails** |
| An import crosses a zone boundary in the prohibited direction | 🔴 **Build fails** |
| A payload type can be constructed holding raw or vault data | 🔴 **Type error** |
| A state is declared without evidence | 🔴 **Type error** |
| A prohibited state transition is attempted | 🔴 **Compile error** |
| A `SANITIZED` state is reachable when a capability is unavailable | 🔴 **Build fails** |
| A crossing is added without a row in §4 | 🔴 **Lint failure** |
| A new entity type is added outside the taxonomy | 🔴 **Build fails** |

---

## 12. Summary

### 12.1 What this document fixes

| Property | Value |
|---|---|
| Trust zones | 6 (Z0–Z5) |
| Enumerated crossings | 9 (B-1 – B-9) |
| Invariant corollaries | 8 (I-1 – I-8) |
| Sanitization conditions | 4 (S-1 – S-4) |
| States, with their permitted behaviour | 4 |
| Forbidden artefacts | 10 (F-1 – F-10) |
| Boundary rules enforced by the **build** | 8 of 9 |
| Boundary claims with assertion-backed tests | 12 (V-1 – V-12) |
| Conditions that fail the build | 8 |

### 12.2 Obligations this creates for `DES-ARCH-001`

The architecture must now satisfy all of the following. These are **derived constraints**, not
preferences:

| # | Obligation |
|---|---|
| **A-1** | Exactly one network-egress module. Every other module reaches the network only through it. |
| **A-2** | Directed imports only: Z1 → Z2 → {Z3, Z4, Z5}. No upward, no lateral. |
| **A-3** | Payload types are constructed so that raw and vault fields are **not representable**. |
| **A-4** | A `SanitizationState` enum carrying evidence — never a bare `is_sanitized: bool`. |
| **A-5** | The forbidden state transitions are unrepresentable in the state-machine type. |
| **A-6** | The receiver re-verifies at B-2 independently of the producer. |
| **A-7** | Every owned resource exposes disposal; disposal is invoked on task termination. |
| **A-8** | The capability rung and its declaration are first-class values in telemetry, not logs. |

### 12.3 The single sentence to remember

> **Z1 is the only zone that ever holds raw content, and only transiently.
> Z2 and Z3 receive only sanitized context, and Z2 refuses to take Z1's word for it.
> Z5 never sees page data at all.**

*End of `SEC-BOUND-001`. Next: `SEC-THREAT-001` (threat model — attacks this boundary), then `DES-ARCH-001` (architecture — derived from it).*

---

## 13. Enforcement status — what is built versus what is verified

Charter gate **C-1** forbids claiming what has not been measured. This section separates the two.

| Rule | Mechanism | Status |
|---|---|---|
| **S-1** spans replaced or masked | `Sanitizer` | ✅ built + tested |
| **S-2** independent re-verification | `EgressGuard.revalidate`, sanitizer residual scan | ✅ built + **mutation-verified** |
| **S-3** declared state matches reality | `SanitizedEvidence` (Pydantic, runtime-enforced) | ✅ built + tested |
| **S-4** no vault or raw data in a payload | `extra="forbid"`, no such field exists | ✅ built + tested |
| **B-1…B-9** crossing enforcement | Zones, import rules, typed payloads | ✅ specified; **import-linter not yet wired** |
| **B-6** target-bound detokenization | `PlaceholderVault.detokenize_for_target` | ✅ built + tested (4 refusal cases) |
| **D-5 / D-6 / D-7** | TS types + runtime Pydantic | ✅ 2 type-enforced; `D-7` corrected to runtime assert |
| **V-10** irreversible redaction | Text: sanitizer residual scan. Pixels: per-pixel survivor count | ✅ **mutation-verified on both paths** |
| **V-11** mask IoU ≥ 0.90 | `PixelRedactor`, clamped box measured against the requested one | ✅ built + tested |
| **V-12** utility preservation ≥ 0.95 | Pixels outside masks must be **byte-identical** | ✅ built + tested |
| **FR-RED-2** opaque only | `MaskStyle` enum has exactly one member | ✅ built + tested |
| **V-3** cross-origin frames | Declared, not solved | ⬜ structural (residual `R-1`) |
| **V-5** WebGPU→WASM ladder | Capability resolver | ⬜ **not built** |

### 13.1 Mutation verification — the control that matters most

`V-2` is the single most important control in this document, so it was tested the only way that
counts: by **removing the control and confirming the tests fail**.

| Mutation injected | Result |
|---|---|
| Replace `self.revalidate(envelope)` with a stub returning "clean" — i.e. **trust the sender** | **6 tests failed**, led by `test_v2_forged_sanitized_payload_is_refused` |

> That mutation is **precisely the v1 design**. v1 accepted an `is_sanitized: true` boolean from
> the sender, and when the vision pipeline silently failed it produced a 1×1 image carrying that
> boolean, which the backend accepted as sanitized (defects `G-2` and `G-6`).
>
> With this control in place, that mutation **breaks the build**. The guard does not trust the
> sender: it strips its own placeholder tokens, re-runs the full detector over everything that
> would go on the wire, and refuses when anything sensitive survives.
>
> A security test that has only ever passed is a decoration. This one has been shown to fail.

### 13.3 Mutation testing found a vacuous test in this very module

The pixel redaction verification was mutation-tested by making the mask a **no-op** — the
behaviour of a "blur that hides nothing", which is exactly the failure `FR-RED-2` prohibits.

| Check | Before mutation testing | After |
|---|---|---|
| Opacity (`FR-RED-2`) | caught it | ✅ |
| Irreversibility (`V-10`) | ❌ **passed vacuously** | ✅ now catches it |
| Utility (`V-12`) | caught it | ✅ |

**What the V-10 check got wrong.** It searched the output buffer for the masked region's byte
*string*. But `region_bytes()` concatenates row by row while the buffer interleaves the other
columns — so for any multi-row mask the string is **never contiguous**, and the search always
reported "gone". A no-op mask passed a check written specifically to catch it.

The corrected property is **per pixel**: a pixel survives only if it still carries its original
value *and* is not the fill colour. That is now what both the verifier and the test assert.

> This is the strongest argument for mutation testing in the whole project. The test was green,
> the requirement was unmet, and no amount of reading the code would have revealed it. The
> mutation did, in one run.

### 13.4 The remaining honest gap

`V-5` — the WebGPU → WASM SIMD → WASM → DOM-only capability ladder — is not built. Until it
exists there is no mechanism that reports *which* rung is active, so the system cannot yet
declare degradation truthfully for the vision path, which is where degradation actually happens.

Cross-origin frames remain structurally unreadable (`R-1`); that is declared, not solved.