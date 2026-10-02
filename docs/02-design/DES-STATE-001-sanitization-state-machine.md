# DES-STATE-001 — Sanitization State Machine

| | |
|---|---|
| **Status** | ✅ Written, and **derived from the code that implements it** |
| **Implements** | DES-ARCH-001 rules DP-6, DP-7 · SEC-BOUND-001 §5.2–5.4, S-1…S-4 |
| **Requirements** | FR-RED-5, FR-EGR-2, FR-PER-4 |
| **Enforced in** | `packages/contracts/sanitization.ts`, `apps/backend/app/contracts/sanitization.py`, `packages/pipeline/orchestrator.ts` |
| **Verified by** | `tests/contract/test_sanitization_contract.py`, `test_pipeline_end_to_end.py` |

> **Why this artifact is worth writing when the code already implements it.**
> The state machine exists twice, in two runtimes, and it is the most
> load-bearing policy in the system. A design document that merely restates code
> earns its place only by catching something the code does not say — so §6
> records where the two disagreed, because those are the interesting findings.

---

## 1. The problem this solves

A sanitization result is a claim: *"this artefact is clean enough to leave the
device."* v1's claim was a boolean, `is_sanitized: true`, supplied by the sender.
When its vision pipeline failed it produced a 1×1 image and still reported that
boolean, and the backend believed it (v1 defects **G-2**, **G-6**).

A boolean has exactly two states, and one of them is wrong. It cannot express
*"I checked, found nothing, but my capability was reduced"* — which is neither a
pass nor a failure. Collapsing that middle ground into `false` trains operators
to ignore `false`; collapsing it into `true` leaks.

So the result is not a boolean. It is one of **four states, each carrying the
evidence that justifies it.**

---

## 2. The four states

| State | Meaning | May cross? |
|---|---|---|
| `SANITIZED` | Verified clean. Carries a `VerificationProof` naming the verifiers that ran. | ✅ `ALLOW` |
| `DEGRADED` | Verified clean **at reduced capability**; the reduction is declared. | ✅ `ALLOW_DECLARED` |
| `UNCERTAIN` | Some entity types fell below the detection threshold and were redacted by default. | ✅ `ALLOW_DECLARED` |
| `NOT_INSTRUMENTED` | A required check **could not run**. | ❌ `WITHHOLD` |

### The asymmetry that matters

`DEGRADED` and `UNCERTAIN` both fail in the **safe** direction: the system knows
less, so it redacts *more*. Over-redaction costs utility, never privacy — so they
may cross, provided the state travels with the payload and the receiver can see
it.

`NOT_INSTRUMENTED` fails in the **unsafe** direction: the system does not know
what it is missing. There is no degraded substitute for not knowing, so it is
withheld entirely.

---

## 3. DP-6 — a state cannot exist without its evidence

```ts
export type SanitizationEvidence =
  | { state: 'SANITIZED';   proof: VerificationProof; rung; declaredAt }
  | { state: 'DEGRADED';    reason: DegradationReason; rung; declaredAt }
  | { state: 'UNCERTAIN';   unresolved: readonly string[]; declaredAt }
  | { state: 'NOT_INSTRUMENTED'; missingCheck: string; declaredAt };
```

`proof` is **not optional**. `{ state: 'SANITIZED' }` without it does not
typecheck — it is not a runtime check that might be skipped, it is an
*unrepresentable value*. That is what DP-6 means in practice.

`VerificationProof` also refuses to certify a dirty artefact: constructing one
with `residualFindings > 0` throws, so a proof cannot be forged by supplying it
with a non-zero residual count.

### Where it bites in practice

The Python text pass returns **`SANITIZED_TEXT`**, not `SANITIZED` — a
deliberately narrower label. It has verified text content and *not one pixel*, so
it cannot know whether the same value was also rendered as an image or a CSS
background. A component must never upgrade its own scope into a system-wide
claim; that is the failure SEC-BOUND-001 exists to prevent.

---

## 4. DP-7 — the forbidden transitions do not exist

Illegal edges are **absent from the table**, not guarded at runtime:

```
SANITIZED         → (nothing)
DEGRADED          → NOT_INSTRUMENTED
UNCERTAIN         → NOT_INSTRUMENTED
NOT_INSTRUMENTED  → (nothing)
```

```
NOT_INSTRUMENTED → SANITIZED   ILLEGAL   ← v1 defect G-2, expressed as a type
DEGRADED         → SANITIZED   ILLEGAL
UNCERTAIN        → SANITIZED   ILLEGAL
```

A failure may never be upgraded into a success. Because the table has no such
edge, `assertLegalTransition` throws `IllegalTransitionError` rather than
permitting the move.


---

## 5. How the state is derived

`packages/pipeline/orchestrator.ts` evaluates in this order; the **first
matching branch wins**.

| # | Condition | Result | Rationale |
|---|---|---|---|
| 1 | `capability.canVerifyPixels === false` | `NOT_INSTRUMENTED` | The pixel route cannot run at all |
| 2 | pixel verification **ran and failed**, or residuals > 0 | `NOT_INSTRUMENTED` | No valid proof is obtainable, so there is no certificate |
| 3 | **zero frames captured** | `NOT_INSTRUMENTED` | see below |
| 4 | any `UNCERTAIN` finding | `UNCERTAIN` | Known ambiguity, redacted by default |
| 5 | `rung !== 'webgpu'` | `DEGRADED` | Clean, but at reduced capability |
| 6 | otherwise | `SANITIZED` + proof | Everything ran; everything was clean |

### Branch 3 is the one that was wrong first

Claiming `pixel_rescan` as a verifier that ran over **zero regions** is the v1
lie one level down. The proof would be internally honest — `verifiersRun` really
would list `pixel_rescan` — and still mean nothing, because `regionsChecked`
would read 1 from the text segments and a reader would reasonably conclude pixels
were covered.

The system cannot distinguish *"this page has no pixels"* from *"capture
failed"*, so it fails closed. An adapter that genuinely has nothing to verify
must say so via `canVerifyPixels: false` — a claim the pipeline can reason about
rather than a silent absence.

Found by `test_pipeline_end_to_end.py::test_claiming_pixel_verification_with_no_frames_is_withheld`,
i.e. by **writing the scenario**, not by reading the code.

---

## 6. Where the code and this document disagreed

| Disagreement | Resolution |
|---|---|
| The Python text pass returned `SANITIZED_TEXT` — a **fifth** label outside the four-state contract | Both ports now return it deliberately, documented here as *narrower than* `SANITIZED` rather than as a contract state. Adding a fifth state to the contract would weaken the exhaustiveness guard in `transmissionVerdict`. |
| A capability claim with no captured frames produced `SANITIZED` | Fixed as branch 3 above. Both runtimes parity-tested. |

---

## 7. Sequence: a single observation

```
content script ──COLLECT──▶ service worker ──OBSERVE──▶ Z1 (offscreen)
                                                        │
                          ┌─────────────────────────────┘
                          ▼
                  resolve capability rung        absence always declared
                          │
                          ▼
                  sanitize text                   detect → tokenize → redact
                          │                         → re-inspect (FR-RED-4)
                          ▼
                  rasterise frames ──▶ bind boxes  text-runs.ts
                          │
                          ▼
                  redact pixels ──▶ VERIFY        opaque fill; fail withholds
                          │
                          ▼
                  EARN evidence                   re-inspection RECOMPUTES the
                          │                        verdict; it is not inherited
                          ▼
                  build envelope                  DP-5: no field holds raw data
                          │
                          ▼
                  EgressGuard.transmit            DP-2: the only egress path
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
      re-inspection clean      residual found
              │                       │
              ▼                       ▼
      ALLOW / ALLOW_DECLARED    WITHHOLD — sender never invoked
```

The receiver **re-derives** the verdict from the payload rather than reading the
declared state. That step is what v1 lacked entirely.

---

## 8. Verification obligations

| Check | Obligation | Where |
|---|---|---|
| V-1 | Re-inspection finds zero residuals in the produced artefact | `test_sanitizer_and_vault.py`, `redaction_precision.py` |
| V-2 | Receiver-side independent re-verification | `test_egress_guard.py`, `test_pixel_guard_parity.py` |
| V-10 | No original pixel recoverable inside a mask | `redaction_precision.py`, `test_pixel_redaction.py` |
| V-11 | Mask geometry matches the detection box, IoU ≥ 0.90 | `redaction_precision.py`, `vision_quality.py` |

---

## 9. Traceability

| Requirement | Clause |
|---|---|
| FR-RED-5 | §3 — state is never inferred from a boolean flag |
| FR-EGR-2 | §2, §7 — transmission decision follows the state |
| FR-PER-4 | §5 branch 1, §7 — frame blindness is declared, never omitted |
| DP-6 / DP-7 | §3, §4 |
