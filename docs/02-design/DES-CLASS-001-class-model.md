# DES-CLASS-001 — Class model

**Status:** written
**Governed by:** SEC-BOUND-001 §3 (zone boundary), REQ-DATA-001 (cross-runtime parity)
**Covers:** the types that make the privacy boundary structural rather than documentary.

---

## 1. Why this artifact exists

The audit's central finding was not that the code was wrong. It was that the
*claims* about the code were wrong — a 1×1 frame reported as a clean scan, a page
instruction carried "for logging". Every one of those was a **type** that
permitted it.

So this document is not a UML diagram. It records which types exist and — more
importantly — **which types deliberately do not**, because an absent field is a
stronger control than a present one with a comment beside it.

---

## 2. Zone map

```
page DOM ──content script──▶ SERVICE WORKER (Z1) ──▶ vault · detector · guard
(untrusted)  collector only     DOM-free, pixels unavailable
```

| Zone | Types | May reach | May NOT reach |
|---|---|---|---|
| Content script | `CollectRequest` (producer) | page text, DOM | vault, detector, guard — **zero imports** |
| Z1 (worker) | everything below | all packages | the page DOM, therefore page pixels |

The content script holds **no runtime imports**. That is asserted by
`tests/contract/test_extension_artifact.py`, not merely documented.

---

## 3. The core types

### 3.1 Perception input

| Type | Runtime | Purpose |
|---|---|---|
| `CollectRequest` | both | What the collector sends inward. The only type that can carry raw text. |
| `PageAdapters` | TypeScript | Everything the pipeline reads: text, frames, capability, clock. |
| `PerceptionSnapshot` | both | What the **verifier** may see. No actor report — that field is not reachable. |
| `visualSurfaces` | TypeScript | Count of painted surfaces. `undefined` when unknown, never defaulted to 0. |

### 3.2 Privacy core

| Type | Role | Note |
|---|---|---|
| `PlaceholderVault` | Issues and resolves placeholders | Reverse mapping lives here and nowhere else |
| `Sanitizer` | detect → tokenise → redact → re-inspect | Never returns text it has not re-read |
| `PixelFrame` | uncompressed `width×height×channels` buffer | Deliberately not an image-library type |
| `PixelRedactor` | irreversible region overwrite | Verified by IoU ≥ 0.90 |
| `EgressGuard` | re-derives the verdict from payload contents | Never trusts the sender's verdict |
| `CapabilityResolver` | rung ladder | A probe that throws is UNAVAILABLE |

### 3.3 The action plane

| Type | Role | Note |
|---|---|---|
| `ActionProposal` | a proposed action | **No page text field. See §4.1.** |
---

## 4. Types that deliberately do not exist

### 4.1 `ActionProposal.pageInstruction` — removed

An earlier design carried a free-text field on the proposal "for logging". It was
**deleted**, not deprecated.

The chain: a field that exists can be read → a string that can be read can be
pattern-matched by a rule → a rule that reads page text is a channel the page
controls. SEC-THREAT-001 §7 (PI-7) is exactly that attack.

> **Python caveat.** In TypeScript, `readonly` is what stops you re-adding this
> field. Python has no equivalent — nothing prevents a future author adding
> `page_instruction: str`. The docstring in `policy/engine.py` is the only guard.
> That asymmetry is a real reduction in structural enforcement, recorded here
> rather than discovered later.

### 4.2 No outbound type can hold the reverse mapping

No payload type has a field capable of holding vault contents. Segregation is
recorded as `vault_segregation` in the verifier list — enforced by *type*, not by
a runtime scan that could not fail.

### 4.3 No boolean "sanitized" flag

`SanitizationEvidence` is a discriminated union of four states. A state cannot
exist without its evidence (DP-6):

```ts
type SanitizationEvidence =
  | { state: 'SANITIZED';        proof: VerificationProof; rung; declaredAt }
  | { state: 'DEGRADED';         reason: DegradationReason; rung; declaredAt }
  | { state: 'UNCERTAIN';        unresolved: readonly string[]; declaredAt }
  | { state: 'NOT_INSTRUMENTED'; missingCheck: string; declaredAt };
```

`SANITIZED` **cannot** be constructed without a `VerificationProof` that only the
re-inspector may mint.

### 4.4 The forbidden transitions do not exist

```
NOT_INSTRUMENTED → SANITIZED    illegal
DEGRADED         → SANITIZED    illegal
UNCERTAIN        → SANITIZED    illegal
```

These edges are **absent**, not guarded at runtime. The first is the v1 defect
expressed as a type.

---

## 5. States map to verdicts

| State | Verdict | Meaning |
|---|---|---|
| `SANITIZED` | `ALLOW` | Every declared check ran and held |
| `DEGRADED` | `ALLOW_DECLARED` | Text verified; a declared capability was below full |
| `UNCERTAIN` | `ALLOW_DECLARED` | Some entity types below threshold; redacted anyway |
| `NOT_INSTRUMENTED` | `WITHHOLD` | A named check could not run |

`DEGRADED` is a **different claim**, not a softened failure: it asserts what *was*
checked, states what was not, and carries the limitation to the receiver.

---

## 6. Known limitations of this model

1. **`UNCERTAIN` and painted surfaces cannot both be represented.** A page with
   unresolved entity types *and* uninspected painted content reports `DEGRADED`,
   and the unresolved list is dropped, because the union carries one state. Both
   transmit with `ALLOW_DECLARED`, so nothing unsafe follows — but the receiver
   loses which entity types were uncertain. **Open, not patched.**

2. **Pixel capture has no producer.** `PixelFrame` and `PixelRedactor` are
   implemented and benchmarked, but nothing in the browser constructs a
   `PixelFrame`: a service worker has no `document` and cannot rasterise. The
   `visualSurfaces` count stands in for it, and pages with painted content are
   `DEGRADED` rather than scanned. **The 25% visual weight is therefore not
   earned.**

3. **`readonly` is TypeScript-only.** See §4.1.

---

## 7. Cross-runtime status

| Area | Status |
|---|---|
| Privacy core | **Both runtimes**, parity-locked (`test_parity.py`) |
| Pixel redaction | **Both runtimes**, parity-locked (`test_pixel_guard_parity.py`) |
| Action plane | **Both runtimes**, parity-locked (`test_policy_parity.py`) |
| Extension runtime (Z1 worker, collector) | TypeScript only — it is browser code |

99 of 99 functional requirements are implemented on both runtimes.
| `PolicyRule` | permitted (action, origins) | An empty rule set permits nothing |
| `ApprovalScope` | one (action, target, origin) triple | Expires; an old one is not a current one |
| `Approval` | operator grant | `granted_by` is set by the UI, never the page |
| `PolicyDecisionDetail` | exactly one verdict | Never a list |
| `ExecutionRecord` | FR-EXE-5 audit record | Every execution produces one |
| `TaskGoal` + `Postcondition` | declares its own success criteria | A goal declaring nothing cannot complete |