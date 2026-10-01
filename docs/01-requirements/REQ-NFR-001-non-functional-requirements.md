# NON-FUNCTIONAL REQUIREMENTS SPECIFICATION

| Field | Value |
|---|---|
| Document ID | `REQ-NFR-001` |
| Version | 1.0 — Draft for approval |
| Status | 🟡 **Complete — awaiting Product Owner approval** |
| Owner | Technical Lead |
| Approver | Product Owner |
| Traces to | `PROJECT-CHARTER.md` §5 · `REQ-SRS-001` |
| Rubric weights served | Client resources **20%** · Latency **15%** · all others indirectly |

---

## 1. Purpose and scope

`REQ-SRS-001` states what the system must **do**. This document states how well it must do it —
the measurable budgets that separate a working demo from a defensible product.

Two of the five official rubric weights are **entirely** non-functional:

| Weight | Governed by |
|---|---|
| **Client resources 20%** | §4 of this document |
| **Latency 15%** | §3 of this document |

The remaining 60% (visual accuracy, PII precision/recall, redaction precision) is functional, but
is only *credible* if the non-functional budgets hold — a system that redacts perfectly but blocks
the browser for two seconds per step does not pass evaluation.

---

## 2. NFR conventions

| Element | Convention |
|---|---|
| **ID** | `NFR-<CATEGORY>-<n>`. Permanent; withdrawn requirements are marked, never renumbered. |
| **Budget** | A hard limit. Exceeding it is a **defect**, not a trade-off. |
| **Target** | The design goal. Exceeding it is acceptable but noted. |
| **Measurement** | The artifact that produces the number. If none exists, the NFR is unverifiable and therefore void. |
| **VM** | Verification method: `T` test · `D` demonstration · `A` analysis · `I` inspection |

> **Rule N-1.** No non-functional claim may be published without a named measurement artifact.
> This is charter gate C-1 applied to non-functional requirements.

---

## 3. Performance — `NFR-PERF`

Latency is measured **per phase**, never as a single end-to-end mean. A mean hides the tail, and
the tail is what a user experiences as "the agent hung".

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-PERF-1` | Perceive → sanitize shall complete within budget at p95. | **Budget: p95 ≤ 800 ms** · Target: p50 ≤ 400 ms | `benchmarks/latency` | T |
| `NFR-PERF-2` | A full agent step (observe → … → verify) shall complete within budget at p95. | **Budget: p95 ≤ 3.0 s** · Target: p50 ≤ 1.5 s | `benchmarks/latency` | T |
| `NFR-PERF-3` | The step path shall contain **no artificial latency floor**. Pacing shall be event-driven or token-bucket, never a fixed sleep. | Zero unconditional sleeps in the step path | Static analysis + `benchmarks/latency` | A/T |
| `NFR-PERF-4` | UI element classification shall complete within budget per frame on the selected rung. | **Budget: ≤ 250 ms** per frame on WASM SIMD | `benchmarks/latency` | T |
| `NFR-PERF-5` | No operation shall stall the main thread beyond the responsiveness threshold. | **Budget: no single stall > 100 ms** | In-browser frame-timing harness | T |
| `NFR-PERF-6` | Cold start — extension loaded to first completed perception. | **Budget: ≤ 2.0 s** | `benchmarks/latency` | T |
| `NFR-PERF-7` | Every phase shall report **p50 and p95**, not a mean. | Percentiles present for all six phases | `benchmarks/latency` | T |
| `NFR-PERF-8` | Cancellation shall take effect promptly. | **Budget: ≤ 150 ms** from cancel to quiescence | `FR-AGT-7` test | T |

> **Why `NFR-PERF-3` exists.** v1 enforced provider pacing with a fixed `STEP_DELAY_MS = 1500`
> plus `ACTION_DELAY_MS = 400`, giving every step a ~1.9 s floor **before any model call** — while
> the README advertised `< 500 ms` average latency. The two claims could not both be true.
> A fixed sleep is a self-inflicted latency budget violation.

---

## 4. Resource consumption — `NFR-RES`

> **Measured on the extension stack, not the local Python stack.** v1's
> `model_resource_benchmark.py` measured `tracemalloc` on Python YOLO while rubric credit is
> awarded for in-browser WASM inference — measuring the wrong system entirely. `NFR-RES-7` exists
> to prevent that mistake recurring.

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-RES-1` | Packaged extension size. | **Budget: ≤ 15 MB** | Build artefact measurement | T |
| `NFR-RES-2` | Resident memory growth during a perception cycle. | **Budget: ΔRSS ≤ 150 MB** | In-browser `performance.memory` harness | T |
| `NFR-RES-3` | Idle CPU when no task is running. | **Budget: ≤ 1% sustained** | Chrome Task Manager sampling | T |
| `NFR-RES-4` | Memory shall return to baseline after task completion. | **Budget: no monotonic growth across 50 sequential tasks** | Extended-run soak harness | T |
| `NFR-RES-5` | A single OCR core and a single model shall be shipped, selected by runtime probe. | Exactly one of each in the package | Build manifest inspection | I |
| `NFR-RES-6` | Local enclave resident memory under load. | **Budget: ≤ 500 MB** | Process sampling | T |
| `NFR-RES-7` | All resource figures shall be produced by the **in-browser** harness. | Python-side resource figures may not be published as client-resource evidence | Inspection of `benchmarks/client_resources` | I |
| `NFR-RES-8` | No unbounded growth in any long-lived collection. | Bounded under the 10,000-entity stress fixture | Stress test | T |
| `NFR-RES-9` | Every disposable resource shall expose disposal, and disposal shall be invoked. | No leaked model handle, worker, or offscreen document after task end | Lifecycle test | T |

> **Why `NFR-RES-9` exists.** v1 shipped no `dispose()` contract on any vision component and never
> closed its offscreen document. Model handles and workers therefore accumulated for the life of
> the browser session — invisible in a short demo, fatal in a 30-minute evaluation.

## 5. Reliability & robustness — `NFR-REL`

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-REL-1` | Malformed, truncated, or adversarial input shall not crash any component. | Zero uncaught exceptions on the fuzz corpus | Fuzz harness | T |
| `NFR-REL-2` | A subsystem failure shall be **contained and declared**. It may never be silently ignored. | Every failure produces a declared state (`DEGRADED` / `NOT_INSTRUMENTED`) | Fault-injection suite | T |
| `NFR-REL-3` | Degradation shall preserve operation where possible rather than aborting. | With every rung above DOM-only forced unavailable, a task still completes | Fault-injection suite | T |
| `NFR-REL-4` | Identical inputs shall produce identical outputs (determinism). | Repeated runs are byte-identical for verification and redaction | Repeat-run harness | T |
| `NFR-REL-5` | Every task shall terminate in a declared terminal state within its bounds. | No task remains non-terminal beyond the configured limit | `FR-AGT-3` test | T |
| `NFR-REL-6` | No unbounded retry or loop. | Every retry path has a declared attempt ceiling | Static analysis + tests | A/T |
| `NFR-REL-7` | Error and alternate paths shall be tested, not only success paths. | Every alternate flow in `REQ-UC-001` §5 has a test | Coverage report | T |

## 6. Security — `NFR-SEC`

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-SEC-1` | The enclave shall bind to loopback only and be unreachable from the network. | Zero non-loopback listeners | Port scan during runtime | T |
| `NFR-SEC-2` | No secret, key, token, or browser-profile artefact shall exist in version control. | Zero matches on a credential scan | `infra/` credential scan | T |
| `NFR-SEC-3` | Dependencies shall be pinned, and free of known critical advisories. | Zero unpatched critical advisories at release | Dependency audit | T |
| `NFR-SEC-4` | Approvals shall be cryptographically signed, time-boxed, and bound to action, target, and origin. | Forged, replayed, and expired tokens are rejected | `FR-POL-3` test | T |
| `NFR-SEC-5` | No raw sensitive value shall appear in any log, telemetry record, or audit entry. | Zero raw values in log output under the planted-PII fixture | Log inspection | T |
| `NFR-SEC-6` | Extension permissions shall be least-privilege, each citing the requirement that justifies it. | Every permission has a cited requirement (`EI-6`) | Manifest inspection | I |
| `NFR-SEC-7` | Indirect prompt injection shall be contained. | **Zero privilege escalations** on the adversarial page corpus | Injection corpus harness | T |

## 7. Portability & compatibility — `NFR-PORT`

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-PORT-1` | No discrete GPU shall be required for any declared capability. | Every rung operates on CPU-only hardware | CI on a GPU-less runner | T |
| `NFR-PORT-2` | The extension shall operate on current stable Chrome and the preceding major version. | Both versions pass the smoke suite | Cross-version CI | T |
| `NFR-PORT-3` | No capability shall depend on the on-device model API being available. | With the Prompt API absent, tasks still complete | `EI-4` test | T |
| `NFR-PORT-4` | No OS-specific path, shell, or filesystem assumption in shipped code. | Zero platform-conditional paths in product code | Static analysis | A |
| `NFR-PORT-5` | Observable outcomes shall be **identical across capability rungs**; only performance may differ. | Same sanitization verdict on every rung for the same fixture | Cross-rung conformance suite | T |

> **`NFR-PORT-5` is the subtle one.** It is easy to let a degraded rung also become *less correct*
> — redacting less, or classifying differently. That would make the security guarantee depend on
> the evaluator's hardware. Only speed and classification fidelity may vary; **the privacy verdict
> must not.**

## 8. Maintainability & extensibility — `NFR-MAIN`

| ID | Requirement | Budget / Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-MAIN-1` | Adding an entity type shall require editing **only** the taxonomy. | One-file change; no detector edited | `UC-15` test | T |
| `NFR-MAIN-2` | The layer dependency rule shall be enforced mechanically. | Build fails on a violating import | Import-linter in CI | T |
| `NFR-MAIN-3` | No source module shall exceed **400 lines**. | Zero modules above the threshold | Line-count check | T |
| `NFR-MAIN-4` | No module-global mutable state in product code. | Static analysis finds none | Static analysis | A |
| `NFR-MAIN-5` | Security-critical paths shall be fully covered. | **100%** statement coverage on redaction, egress, policy, and vault | Coverage report | T |
| `NFR-MAIN-6` | Every approved requirement shall trace to at least one test or benchmark. | Zero untraced requirements in `REQ-RTM-001` | Traceability audit | A |
| `NFR-MAIN-7` | Every public interface shall carry a stated contract and its pre/postconditions. | Zero undocumented public interfaces | API surface review | I |

> **Why `NFR-MAIN-3` is a hard number and not a guideline.** v1's `service-worker.js` reached
> **1,738 lines / 79 KB** carrying a dozen unrelated responsibilities. A hard ceiling makes that
> failure mode structurally impossible instead of merely discouraged.

## 9. Usability & accessibility — `NFR-USA`

| ID | Requirement | Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-USA-1` | Degradation and not-instrumented states shall be explained in plain language, not error codes. | No internal identifier appears in user-facing text | Copy review | I |
| `NFR-USA-2` | The side panel shall be fully keyboard navigable. | Every control reachable and operable without a pointer | Accessibility check | T |
| `NFR-USA-3` | The overlay shall meet WCAG AA contrast. | 4.5:1 for body text | Contrast audit | T |
| `NFR-USA-4` | Irreversible or externally-visible actions shall be visually distinguished before confirmation. | Destructive controls are visually distinct | Design inspection | I |
| `NFR-USA-5` | Confirmation shall be answerable without reading logs. | Action, target, origin, and reason all present (`FR-UI-7`) | Demo walkthrough | D |

## 10. Privacy — `NFR-PRIV`

| ID | Requirement | Target | Measurement | VM |
|---|---|---|---|---|
| `NFR-PRIV-1` | Telemetry shall contain no raw sensitive values, reverse mappings, or raw screenshots. | Zero under the planted-PII fixture | Payload inspection | T |
| `NFR-PRIV-2` | No user page data shall be persisted at rest. | Zero page-derived artefacts on disk | Filesystem diff across a task | T |
| `NFR-PRIV-3` | The placeholder vault shall exist in memory only. | Vault absent from all storage after a task | Storage inspection | T |
| `NFR-PRIV-4` | Data minimisation: only sanitized context may leave the device. | Zero raw values in any outbound payload | Egress capture | T |
| `NFR-PRIV-5` | Retention after task end shall be zero. | Vault, session state, and buffers cleared | Post-task inspection | T |

## 11. Budget summary

The consolidated sheet a reviewer checks first. Every row is binding.

| Domain | Binding budget | Weight served |
|---|---|---|
| Perceive → sanitize | p95 ≤ **800 ms** | Latency 15% |
| Full agent step | p95 ≤ **3.0 s** | Latency 15% |
| Classification per frame | ≤ **250 ms** (WASM SIMD) | Latency 15% |
| Main-thread stall | ≤ **100 ms** | Latency 15% |
| Cold start | ≤ **2.0 s** | Latency 15% |
| Cancellation latency | ≤ **150 ms** | Latency 15% |
| Extension package | ≤ **15 MB** | Resources 20% |
| Perception ΔRSS | ≤ **150 MB** | Resources 20% |
| Idle CPU | ≤ **1%** | Resources 20% |
| Enclave RSS | ≤ **500 MB** | Resources 20% |
| Module size ceiling | ≤ **400 lines** | Maintainability |
| Security-path coverage | **100%** | Credibility |
| Injection escalations | **0** | Credibility |
| Untraced requirements | **0** | Credibility |

### 11.1 NFR counts

| Category | Count | Primary weight served |
|---|---|---|
| `NFR-PERF` — Performance | 8 | Latency 15% |
| `NFR-RES` — Resources | 9 | Client resources 20% |
| `NFR-REL` — Reliability | 7 | Credibility |
| `NFR-SEC` — Security | 7 | Credibility |
| `NFR-PORT` — Portability | 5 | Client resources 20% |
| `NFR-MAIN` — Maintainability | 7 | Credibility |
| `NFR-USA` — Usability | 5 | Usability |
| `NFR-PRIV` — Privacy | 5 | Credibility |
| **Total** | **53** | |

### 11.2 The three NFRs that most change the engineering

| NFR | v1 behaviour | Effect on v2 |
|---|---|---|
| `NFR-PERF-3` — no artificial latency floor | `STEP_DELAY_MS = 1500` + `ACTION_DELAY_MS = 400` gave every step a ~1.9 s floor before any model call | Forces a token-bucket limiter. Removes ~1.9 s per step and makes the latency budget achievable at all. |
| `NFR-RES-7` — measure the extension stack | v1 measured `tracemalloc` on Python YOLO while credit is awarded for in-browser WASM | Forces the in-browser harness into existence. Without it the 20% resource weight is unmeasurable. |
| `NFR-PORT-5` — rungs differ in speed, never in verdict | No ladder existed, so no conformance question arose | Prevents the evaluator's hardware from silently weakening the privacy guarantee. |

*End of `REQ-NFR-001`.*