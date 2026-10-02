# DES-SEQ-001 — Sequence specifications

**Status:** written
**Governed by:** SEC-BOUND-001 §5 (state transitions), FR-EXE-1…6, FR-VER-1…5
**Covers:** the three sequences that carry risk.

---

## 1. Scope

Three sequences, each chosen because it contains a step where a reasonable
implementation could lie:

| Sequence | The lie it must prevent |
|---|---|
| **SEQ-1 Observe** | reporting a page sanitised when pixels were never inspected |
| **SEQ-2 Act** | performing an action that policy refused |
| **SEQ-3 Verify** | reporting completion against pre-action perception |

All three are executed: SEQ-1 by `tests/runtime/worker_harness.mjs` (7
scenarios), SEQ-2/3 by `tests/contract/test_policy_parity.py` on **both**
runtimes.

---

## 2. SEQ-1 — Observe and sanitise

```
operator     Z1 worker          collector        vault / guard
   │ click       │                  │                  │
   ├────────────►│                  │                  │
   │             │ COLLECT ────────►│                  │
   │             │◄─────────────────┤ segments         │
   │             │   + visualSurfaces                  │
   │             │                  │                  │
   │             │── capability ladder (webgpu → wasm → dom-only)
   │             │── detect → tokenise ───────────────►│ placeholders
   │             │── re-inspect ─────────────────────►│ residual count
   │             │                  │                  │
   │             │   derive evidence from:                     │
   │             │     frames captured?  visualSurfaces?     │
   │             │     residuals zero?                        │
   │             │                  │                  │
   │             │◄────── verdict: ALLOW / ALLOW_DECLARED / WITHHOLD
   │◄────────────┤ badge + plain-language tooltip
```

### 2.1 Deriving the evidence

This is the step the whole design exists to get right.

| Condition | State | Verdict | Badge |
|---|---|---|---|
| a check could not run (`canVerifyPixels: false`, or a residual failure) | `NOT_INSTRUMENTED` | `WITHHOLD` | `HOLD` |
| unresolved entity types — **before** every SANITIZED branch | `UNCERTAIN` | `ALLOW_DECLARED` | `UNC` |
| `visualSurfaces === 0`, residuals zero | `SANITIZED` | `ALLOW` | `OK` |
| `visualSurfaces > 0`, residuals zero | `DEGRADED` | `ALLOW_DECLARED` | `DEG` |
| `visualSurfaces === undefined` | `NOT_INSTRUMENTED` | `WITHHOLD` | `HOLD` |

**Two orderings are part of the spec, and both were learned the hard way.**

1. `visualSurfaces === undefined` is evaluated **before** `> 0`. Reading unknown as
   zero is precisely the optimistic failure the four-state model prevents.
2. `unresolved` is evaluated **before** every `SANITIZED` branch. `unresolved` does
   *not* contribute to `residualFindings` — an entity below threshold is redacted
   anyway, so no raw value survives and the residual count stays zero. A `SANITIZED`
   branch testing residuals alone therefore swallowed `UNCERTAIN` and declared the
   page clean. That regression shipped with 333 green tests, because no scenario
   combined an uncertain detection with zero painted surfaces.

---

## 3. SEQ-2 — Propose, decide, execute

```
actor        PolicyEngine         ActionExecutor       handler
   │ proposal    │                      │                 │
   ├────────────►│                      │                 │
   │             │ 1 closed action set? BLOCK               │
   │             │ 2 rule permits?     BLOCK               │
   │             │ 3 payload ≤ ceiling? BLOCK              │
   │             │ 4 DETOKENIZE ⇒ B-6 binding? BLOCK       │
   │             │ 5 irreversible / externally visible      │
   │             │      ⇒ CONFIRM ────────────────────────►│
   │◄────────────┤ decision + approvalScope                 │
   │             │                      │                 │
   │             │ decision ───────────►│                 │
   │             │                      │ BLOCK ⇒ stop    │
   │             │                      │ CONFIRM ⇒ scope │
   │             │                      │   must match and│
   │             │                      │   be unexpired  │
   │             │                      │ ALLOW ─────────►│ dispatch
   │◄───────────────────────── ExecutionRecord ───────────┤
```

### 3.1 Invariants

1. **The decision is a parameter.** The executor never re-derives policy. A second
   opinion is how two policy implementations drift, and the more permissive one
   wins.
2. **A `BLOCK` never reaches a handler** (FR-POL-4).
3. **Dispatch is a closed table**, copied at construction keyed by the closed
   action set. `getattr` is deliberately unused — it would resolve `__init__` and
   every other dunder, turning a closed table into an open one.
4. **Elapsed past the bound is `TIMEOUT`**, never `EXECUTED` (FR-EXE-4).
5. **Every path produces an `ExecutionRecord`**, including the ones that did
   nothing.

---

## 4. SEQ-3 — Verify completion

```
actor          verifier                      perception
   │ goal + claimed observation id             │
   ├──────────────────────────────────────────►│
   │  1 blocked?       ⇒ BLOCKED              │
   │  2 bounded out?   ⇒ BOUNDED_OUT          │
   │  3 fresh?         ⇒ FAILED               │
   │  4 no postconditions? ⇒ FAILED           │
   │  5 all checks pass? ⇒ COMPLETED           │
   │◄──────────────────────────────────────────┤
```

### 4.1 Invariants

1. **Staleness is checked BEFORE the postconditions** (FR-VER-3). Verifying
   against pre-action perception produces a verdict about the wrong moment in
   time.
2. **Positive verification only** (FR-VER-5). `COMPLETED` requires every declared
   postcondition to hold; anything else terminates as failed, blocked or bounded
   out — never a soft success.
3. **The actor's report is unreachable.** It is not a field on
   `PerceptionSnapshot`.
4. **Text comparison strips punctuation and whitespace on both sides.** A literal
   substring check was caught by a benchmark reporting `COMPLETED` while the page
   still displayed `4532 0151 1283 0366`: the needle was unspaced, the haystack
   carried separators. Matching *more* aggressively is the correct direction — a
   false failure costs nothing, a disclosure costs everything.
5. **An unhandled postcondition kind raises.** Defaulting it to "passed" would
   convert a programming error into a security error.

---

## 5. Sequences deliberately not specified

- **Retry and backoff for collection.** The retry is a single injection attempt;
  more attempts would multiply surface without changing the honest outcome.
- **Offscreen / DOM-based capture.** Removed from the critical path — see
  README §8. Reinstating it would need its own spec, because
  `createDocument()` resolving before module evaluation is a race, and a security
  boundary should not be built on one.
reintroduce the exact optimistic failure the four-state contract prevents.

### 2.2 Failure paths

| Failure | Response |
|---|---|
| No receiver in tab | Inject the collector via `chrome.scripting.executeScript`, retry once |
| Injection refused (`chrome://`, Web Store, other extensions) | `ERR`, named as a platform limit rather than blamed on the collector |
| `visualSurfaces()` throws mid-count | Return `undefined`, **never** a partial count — understating risk is the one direction this number must not err in |
| Badge API rejects | Swallow with a warning. A rejected `setBadgeText` inside a catch produces a *new* unhandled rejection that masks the real error. |