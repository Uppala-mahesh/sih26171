# SOFTWARE REQUIREMENTS SPECIFICATION

| Field | Value |
|---|---|
| Document ID | `REQ-SRS-001` |
| Version | 1.0 — Draft for approval |
| Structure | ISO/IEC/IEEE 29148 (IEEE 830 organisation) |
| Status | 🟡 **Complete — awaiting Product Owner approval** |
| Owner | Technical Lead |
| Approver | Product Owner |
| Traces to | `../sih26171/IDEA.md` · `PROJECT-CHARTER.md` |
| Traced by | `REQ-RTM-001` → the five official rubric weights |

---

## 1. Introduction

### 1.1 Purpose

This document specifies the functional, interface, and data requirements for **SIH26171 v2**, a
privacy-preserving browser agent that performs visual perception and sensitive-data redaction
entirely on the user's device.

It is the **authoritative requirements baseline**. Design documents, source code, and tests trace
to it; it in turn traces to the five official evaluation weights. Where this document and any
other artifact disagree, this document governs.

### 1.2 Scope

The system comprises three cooperating surfaces:

| Surface | Responsibility |
|---|---|
| **Browser extension** | On-device perception, sensitive-data detection, redaction, action execution, user interface |
| **Local reasoning enclave** | Sanitized-context reasoning, local policy authority, task verification. Loopback only. |
| **Demo console** | Judge-facing presentation of live system state. Owns no domain logic. |

**In scope:** on-device vision with a capability ladder · PII detection and redaction ·
placeholder tokenisation · egress control · agentic action loop · local policy and human
confirmation · independent task verification · telemetry · rubric measurement harness.

**Out of scope** (binding — see `PROJECT-CHARTER.md` §4): Firefox port · cloud-primary reasoning ·
multi-user deployment · mobile browsers · model training · CAPTCHA solving or authentication
evasion.

*(Face/photo detection was previously listed here as pending `CR-001`. **`CR-001` is now
approved** — face detection is in scope as `FR-PII-FACE-1..3`, subject to the binding fallback
condition described in that CR.)*

### 1.3 Definitions, Acronyms and Abbreviations

| Term | Definition |
|---|---|
| **Perception** | Acquisition of page state through any modality (DOM, pixels, layout). |
| **Sanitization** | Transformation of raw perception into a form safe for transmission. |
| **Redaction** | Irreversible removal of sensitive content from a text or pixel buffer. |
| **Placeholder** | A stable token (`<AADHAAR_1>`) substituted for a sensitive value. |
| **Vault** | The in-memory, on-device, non-persisted map from placeholder to original value. |
| **Egress** | Any data leaving the device trust boundary. |
| **Agent step** | One complete observe → sanitize → plan → validate → decide → execute → verify cycle. |
| **Policy decision** | `ALLOW` · `CONFIRM` · `BLOCK` issued by the local trusted authority. |
| **Trust boundary** | The line across which data must be sanitized before crossing. |
| **`DEGRADED`** | A subsystem operating below full capability, **declared** as such. |
| **`NOT_INSTRUMENTED`** | A metric that has not been measured. The only permitted representation of it. |
| **v1** | The predecessor prototype at `../sih26171/`. Reference only. |

### 1.4 References

| ID | Document |
|---|---|
| — | SIH26171 problem statement — *On-device Visual Perception for Light-weight Browser Agents* (ISRO, Dept. of Space) |
| — | `../sih26171/IDEA.md` — v1 problem analysis and demo requirements |
| `GOV-CHTR-001` | Project Charter |
| `GOV-LEDG-001` | Reuse & Departure Ledger |
| `CR-001` | Change Request — Face / Photo PII Detection |

### 1.5 Document overview

§1 Introduction. §2 Overall description — the trust gradient, function groups, constraints, and
the ten verified v1 gaps this baseline must close. §3 Functional requirements — 99 requirements
across 13 groups, plus external interface requirements. §4 Verification methods and traceability.
§5 Summary and counts.

Non-functional requirements are specified separately in `REQ-NFR-001`; the sensitive-data
taxonomy in `REQ-DATA-001`; requirement-to-rubric traceability in `REQ-RTM-001`; use cases in
`REQ-UC-001`.

## 2. Overall Description

### 2.1 Product perspective

The system is a **self-contained product**, not a component of a larger system, but it is
constrained by a strict internal trust gradient:

```
USER
 └─ BROWSER + EXTENSION          ← TRUSTED      (perception, detection, redaction, execution)
     └─ LOCAL REASONING ENCLAVE  ← SEMI-TRUSTED (receives sanitized context only)
         └─ EXTERNAL REASONING   ← UNTRUSTED    (optional; receives sanitized context only)
```

**The privacy boundary is the product.** Every requirement in this document exists to preserve
one invariant: raw sensitive content must never cross the trust boundary, in any modality, in
any direction.

### 2.2 Product functions (summary)

| # | Function group | Requirement prefix | Primary rubric weight |
|---|---|---|---|
| 1 | On-device perception | `FR-PER` | Visual 25% |
| 2 | UI element understanding | `FR-VIS` | Visual 25% |
| 3 | Sensitive-data detection | `FR-PII` | PII precision & recall 20% |
| 4 | Redaction | `FR-RED` | Redaction precision 20% |
| 5 | Placeholder vault | `FR-VLT` | Redaction precision 20% |
| 6 | Egress control | `FR-EGR` | PII 20% (zero-leakage claim) |
| 7 | Agent pipeline | `FR-AGT` | Latency 15% |
| 8 | Policy authority & confirmation | `FR-POL` | — (security-critical) |
| 9 | Action execution | `FR-EXE` | Latency 15% |
| 10 | Task verification | `FR-VER` | Visual 25% (completion) |
| 11 | Vision capability ladder | `FR-CAP` | Client resources 20% |
| 12 | User surfaces | `FR-UI` | — (usability) |
| 13 | Telemetry & measurement | `FR-TEL` | All weights |

### 2.3 User characteristics

| Persona | Characteristics | Design implication |
|---|---|---|
| **Citizen / end user** | Non-technical. Uses government, banking, healthcare portals. Expects the agent to *not* leak data. | Defaults must be safe; degradation must be explained in plain language |
| **SIH evaluator / jury** | Technical. Will probe the privacy claim and inspect outbound payloads. | Every claim must be inspectable live, in the UI |
| **Developer / maintainer** | Needs to add entity types and detectors. | Extension must never require editing an existing module |

### 2.4 Operating environment

- Chrome (MV3) on desktop. WebGPU where available, WASM SIMD otherwise, DOM-only as last resort.
- Python 3.11+ for the local enclave; binds `127.0.0.1` only.
- Node 18+ for console tooling and extension helper tests.
- No GPU assumed. No network assumed for core perception and privacy functions.

### 2.5 Design and implementation constraints

| ID | Constraint |
|---|---|
| DC-1 | Perception and redaction execute on-device. No exception. |
| DC-2 | The system must function with **zero API keys** configured. |
| DC-3 | The enclave never binds beyond loopback. |
| DC-4 | Only the egress module may perform network transmission. |
| DC-5 | No component may trust a caller-supplied "already sanitized" flag without independent verification. |
| DC-6 | Extension package ≤ **15 MB**. |
| DC-7 | A **single** entity taxonomy drives both Python and TypeScript runtimes. |

### 2.6 Assumptions and dependencies

| ID | Statement |
|---|---|
| AD-1 | Chrome Prompt API availability varies by profile → must degrade, never hard-fail. |
| AD-2 | Model licences permit redistribution for a hackathon submission. |
| AD-3 | The evaluator's machine has no discrete GPU. |

### 2.7 Known gaps inherited from v1

Recorded here so they are **requirements**, not surprises. Each is addressed by a requirement in
Part 2. Every gap below was verified against v1 source during the Phase 1 audit.

| # | v1 gap (verified) | Addressed by |
|---|---|---|
| G-1 | Python engine detects none of Aadhaar / PAN / UPI / IFSC / OTP | `FR-PII` + `REQ-DATA-001` |
| G-2 | `is_sanitized=True` set unconditionally; no independent re-scan on ingest | `FR-RED` · `FR-EGR` |
| G-3 | No UI-element understanding — the 25% weight is entirely unaddressed | `FR-VIS` |
| G-4 | No WebGPU / ONNX-Runtime-Web anywhere in the extension or console | `FR-CAP` |
| G-5 | No checksum validation → card and Aadhaar false positives | `REQ-DATA-001` §2.2 |
| G-6 | A fail-closed path masquerades as success (1×1 PNG flagged `is_sanitized: true`) | `FR-CAP` (declared `DEGRADED`) |
| G-7 | 42.9 MB vendor payload contradicts the "light-weight" claim | `FR-CAP` (package budget) |
| G-8 | No face detection, though the demo script promises it | `CR-001` → `FR-PII-FACE-*` |
| G-9 | Two UIs duplicate domain logic; three reasoning cores duplicate security wiring | `FR-AGT` · `FR-UI` |
| G-10 | Unmeasured rubric weights reported as fabricated zeros | `FR-TEL` (charter C-1) |

## 3. Functional Requirements

### 3.0 Requirement conventions

| Element | Convention |
|---|---|
| **ID** | `FR-<GROUP>-<n>`. IDs are permanent — a withdrawn requirement is marked `Withdrawn`, never renumbered. |
| **Statement** | Uses "shall". One capability per requirement. |
| **Acceptance criterion** | Must be objectively measurable. A requirement without a measurable criterion is not a requirement. |
| **MoSCoW** | `Must` — baseline fails without it · `Should` — expected in this delivery · `Could` — desirable, first to be cut |
| **Status** | `Approved` · `Pending CR-nnn` |

### 3.1 Perception — `FR-PER`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-PER-1` | The system shall perceive page state through the DOM modality, extracting for each element: stable identity, tag, role, accessible name, visible text, value, and bounding geometry. | ≥ 95% of fixture elements extracted with correct role; geometry within ±2 px of ground truth | Must |
| `FR-PER-2` | The system shall perceive page state through the visual modality by capturing the visible viewport. | Capture succeeds on 100% of fixture pages; recorded dimensions match the viewport exactly | Must |
| `FR-PER-3` | The system shall exclude non-visible elements (zero size, `display:none`, `visibility:hidden`, off-viewport, fully occluded) from the perceived surface. | Zero non-visible elements present in sanitized context across the fixture set | Must |
| `FR-PER-4` | The system shall detect the presence of iframes and **declare** whether their contents were perceivable. | Cross-origin frame blindness is reported as an explicit `frame_blind` marker, never silently omitted | Must |
| `FR-PER-5` | Perception shall be free of observable side effects on the page (no focus change, no scroll, no mutation, no event dispatch). | Page DOM hash unchanged across 20 consecutive perceptions | Must |
| `FR-PER-6` | Each perception shall produce a versioned observation carrying a stable, unique observation identifier and a monotonically increasing context version. | Two observations of an unchanged page share content but differ in identifier; a changed page increments the version | Must |
| `FR-PER-7` | Regions that cannot be inspected (canvas, video, cross-origin image, embedded plugin) shall be flagged as **opaque regions** in the perception result. | Every such region appears in the result with `opaque: true` and its geometry | Should |

> **Rationale for `FR-PER-4`.** Content scripts do not run inside cross-origin frames by default.
> A page can therefore present sensitive content in a frame that the agent cannot see. v1 was
> silently blind here. Declaring the blindness is the difference between a bounded system and a
> system that merely *appears* complete.

### 3.2 UI Element Understanding — `FR-VIS`

> This group addresses the **heaviest rubric weight (Visual, 25%)**. v1 had **no**
> element-understanding capability at all — its vision path existed solely to locate text for
> redaction. These are new capability requirements, not a refactor.

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-VIS-1` | The system shall classify each visible interactive region into a declared **UI role taxonomy**: `BUTTON`, `TEXT_INPUT`, `PASSWORD_INPUT`, `CHECKBOX`, `RADIO`, `SELECT`, `LINK`, `MENU_ITEM`, `TAB`, `DIALOG`, `TABLE`, `FORM`, `NAVIGATION`, `IMAGE`, `TEXT_REGION`, `UNKNOWN`. | Taxonomy is closed and versioned; every classified element carries exactly one role | Must |
| `FR-VIS-2` | Classification accuracy shall be measured against a held-out ground-truth fixture set. | **Macro-F1 ≥ 0.90** on the held-out set, reported per class, with the confusion matrix published | Must |
| `FR-VIS-3` | Classification shall execute **on-device**. No page pixel or element descriptor may leave the device to obtain a classification. | Network trace during classification shows zero outbound requests | Must |
| `FR-VIS-4` | Every classification shall carry a confidence score. Below the configured threshold the element shall be labelled `UNKNOWN` rather than guessed. | No element is ever emitted with a role but without a confidence value | Must |
| `FR-VIS-5` | Visual classification shall be **fused** with DOM signals. Where DOM semantics and visual classification disagree, the fusion policy shall resolve deterministically and record which source won. | Reconciliation decision recorded per element; identical inputs always yield identical output | Must |
| `FR-VIS-6` | The classification model shall be loadable through the capability ladder (§3.11) and compatible with quantization. | Model loads under every ladder rung the ladder declares available | Must |
| `FR-VIS-7` | The system shall report per-class accuracy so weak classes are visible rather than averaged away. | Per-class precision, recall, and F1 produced by the benchmark harness | Should |

### 3.3 Sensitive-Data Detection — `FR-PII`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-PII-1` | All entity definitions shall originate from `REQ-DATA-001`. No detector, in any runtime, shall declare its own entity list. | Build fails if a detector defines an entity absent from the taxonomy | Must |
| `FR-PII-2` | `T1` entities shall be admitted only on **passing checksum** validation (Luhn for payment cards, Verhoeff for Aadhaar). | Synthetic 13–19 digit non-Luhn strings produce zero `CREDIT_CARD` detections | Must |
| `FR-PII-3` | `T3` entities shall be admitted only when both shape **and** context cue match. | Bare 12-digit strings without Aadhaar context produce zero `AADHAAR` detections | Must |
| `FR-PII-4` | `T4` entities shall be admitted only above a configured confidence threshold. | Threshold is configurable, and the precision/recall trade-off at the chosen operating point is published | Must |
| `FR-PII-5` | Detection shall cover every modality in the perceived surface: visible text, input values, element attributes, accessible names, placeholders, and OCR text recovered from pixels. | A planted entity of each class is detected in each modality it appears in | Must |
| `FR-PII-6` | Any `input` whose type is `password` shall be redacted **unconditionally**, without requiring a pattern match. | Password values never appear in sanitized output regardless of content | Must |
| `FR-PII-7` | Detection quality shall be reported as **both** precision and recall against the labelled corpus, with a published confusion matrix. | Recall ≥ 0.98 and Precision ≥ 0.95, reported per entity class and not only in aggregate | Must |
| `FR-PII-8` | The Python and JavaScript runtimes shall expose an **identical** entity set. | Cross-runtime parity test fails the build on any divergence | Must |
| `FR-PII-9` | A detection that cannot reach the confidence threshold shall emit `UNCERTAIN` and fail closed by redacting, never by passing through. | Ambiguous inputs are redacted and marked `UNCERTAIN` in the sanitized output | Must |
| `FR-PII-FACE-1` | The system shall detect faces within the perceived viewport. | ≥ 90% recall on the ≥ 40-fixture labelled face set | Should |
| `FR-PII-FACE-2` | Detected face regions shall be redacted with the same verification guarantees as `FR-RED`. | Independent re-scan finds zero residual faces in redacted output | Should |
| `FR-PII-FACE-3` | Face detection cost shall be reported and shall not push the extension package above 15 MB. | Measured package size ≤ 15 MB with the detector present | Should |

### 3.4 Redaction — `FR-RED`

> **This group closes v1 defect G-2.** In v1, `is_sanitized=True` was set **unconditionally**
> (`privacy_pipeline.py:438`) and no component re-examined the redacted artefact. A 1×1
> fully-failed image was therefore accepted downstream as "sanitized". These requirements make
> redaction a *verified* claim instead of a *declared* one.

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-RED-1` | Sensitive spans in text shall be replaced by their catalogue placeholder, and the original span shall not be recoverable from the sanitized output. | Raw value is absent from serialized sanitized output by substring search | Must |
| `FR-RED-2` | Sensitive pixel regions shall be covered by an **opaque, irreversible** mask. Blur, pixelation, mosaicking, inversion, or partial obscuring are prohibited. | Attempted reconstruction from the redacted image cannot recover any character of the original content | Must |
| `FR-RED-3` | Applied mask geometry shall be verified against the detection bounding box, not assumed. | Mask-to-detection **IoU ≥ 0.90** for every redacted region | Must |
| `FR-RED-4` | Every redacted artefact shall be **independently re-inspected** before it is accepted as sanitized — the redacted image is re-analysed, and the sanitized text is re-scanned. | A deliberately under-sized mask is detected and the artefact is rejected, demonstrating the check actually runs | Must |
| `FR-RED-5` | Redaction state shall be one of exactly `SANITIZED`, `DEGRADED`, `UNCERTAIN`, `NOT_INSTRUMENTED`. It shall never be inferred from a boolean flag alone. | No code path sets `SANITIZED` without the verification step of `FR-RED-4` having passed | Must |
| `FR-RED-6` | Redaction shall preserve non-sensitive content without alteration. | Utility preservation ≥ **0.95** — non-sensitive text and pixels unchanged outside masked regions | Must |
| `FR-RED-7` | Redaction shall be idempotent. | Applying redaction to an already-redacted artefact produces a byte-identical result | Should |
| `FR-RED-8` | Redacted artefacts shall carry provenance identifying the producing component, the model versions used, and the timestamp. | Provenance present on 100% of redacted artefacts; a redaction with absent provenance is rejected | Must |

### 3.5 Placeholder Vault — `FR-VLT`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-VLT-1` | The placeholder-to-original mapping shall exist **only in memory on the device**. It shall never be written to disk, to extension storage, to logs, or to any network payload. | Serialized outbound payloads contain an empty mapping; storage inspection shows no vault keys | Must |
| `FR-VLT-2` | Placeholder tokens shall be stable within a single observation — the same original value shall always map to the same token. | Repeated sanitization of an identical value yields an identical placeholder | Must |
| `FR-VLT-3` | Placeholders shall be collision-free and numbered per entity type (`<AADHAAR_1>`, `<AADHAAR_2>`, `<CARD_1>`). | Distinct values never share a token; token reuse never occurs for distinct values | Must |
| `FR-VLT-4` | The vault shall be explicitly cleared on task completion, origin navigation, and user-initiated reset. | Post-clear, no placeholder resolves to any value; a resolution attempt returns the placeholder unchanged | Must |
| `FR-VLT-5` | Detokenization shall be permitted **only** for just-in-time dispatch of a value into its originally bound target element. Model-bound and network-bound payloads shall never be detokenized. | No detokenized value appears in any outbound payload, in any mode | Must |
| `FR-VLT-6` | A safe summary — entity counts and categories only — may be exported for telemetry. | Summary contains no original values and no reverse mapping | Must |
| `FR-VLT-7` | Vault size shall be bounded, with eviction that invalidates the corresponding placeholders rather than leaving stale tokens resolvable. | Bounded operation under a 10,000-entity stress fixture without unbounded growth | Should |

### 3.6 Egress Control — `FR-EGR`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-EGR-1` | All network transmission shall pass through a **single** egress chokepoint. No other module may transmit. | Static analysis finds zero network calls outside the egress module | Must |
| `FR-EGR-2` | Every outbound payload shall be inspected for raw sensitive content **immediately before** transmission. | Inspection runs on 100% of egress attempts, including retries | Must |
| `FR-EGR-3` | On detecting raw sensitive content, egress shall be **blocked**, fail closed, and the attempt shall be audited. | A deliberately contaminated payload is blocked and produces an audit record | Must |
| `FR-EGR-4` | No component shall accept a caller-supplied sanitization assertion as proof. Sanitization shall be re-verified at the boundary. | A payload falsely claiming sanitized status is rejected | Must |
| `FR-EGR-5` | Every egress attempt shall produce an audit record containing: timestamp, destination, entity counts, verification outcome, and allow/block decision. No raw values. | Audit records exist for both allowed and blocked attempts, and contain no original sensitive values | Must |
| `FR-EGR-6` | The exact outbound payload shall be **inspectable live** by the user, and by the jury during evaluation. | Console displays the literal transmitted payload, byte-for-byte | Must |
| `FR-EGR-7` | Egress shall be denied by default. Transmission requires an explicit permitting policy decision. | With no policy loaded, all egress is denied | Should |

### 3.7 Agent Pipeline — `FR-AGT`

> **This group closes v1 defect G-9.** v1 had three separate reasoning cores — `BrowserAgent`,
> `TaskOrchestrator`, and `ChatOrchestrator` — each independently re-wiring the privacy pipeline,
> egress gateway, policy engine, validator, and verifier. Two divergent copies of the security
> pipeline is a defect waiting to become a vulnerability.

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-AGT-1` | There shall be exactly **one** agent pipeline implementation. Every driver (conversational, closed-loop) shall invoke that same pipeline. | Only one module implements the sanitize → plan → validate → decide → execute → verify sequence; drivers contain no security logic | Must |
| `FR-AGT-2` | The pipeline shall implement an **explicit state machine** with declared states and terminal states. | State transitions are enumerated; terminal states are unreachable-from by any transition | Must |
| `FR-AGT-3` | Execution shall be bounded by step count, elapsed wall-clock time, and consecutive-failure count. Exceeding any bound terminates the task. | A task on a non-progressing page terminates within the configured bound rather than looping | Must |
| `FR-AGT-4` | After every executed action the system shall **re-perceive and re-sanitize** before the next reasoning step. | No reasoning step consumes an observation that predates the most recent action | Must |
| `FR-AGT-5` | Every proposed action shall be re-bound against the **fresh** observation before execution. A proposal referencing an element absent from the current observation shall be rejected. | A proposal bound to a stale element identifier is rejected and audited, never executed | Must |
| `FR-AGT-6` | Session state shall be held in an explicit store with a declared lifecycle (create, read, evict, clear). No pipeline state shall live in process-global mutable variables. | Two concurrent tasks cannot observe each other's state; store instances are injectable | Must |
| `FR-AGT-7` | Cancellation shall propagate to all in-flight work. User stop or origin navigation shall abort perception, inference, and dispatch. | After cancel, no further transmission or DOM mutation occurs | Must |
| `FR-AGT-8` | Pacing of provider calls shall use a **token-bucket** limiter, not fixed sleeps in the critical path. | No unconditional sleep appears in the step path; measured p95 step latency excludes any artificial floor | Must |
| `FR-AGT-9` | Each step shall emit a machine-readable telemetry record with per-phase timings. | Timings available for perceive, sanitize, plan, decide, execute, verify | Should |

### 3.8 Policy Authority & Confirmation — `FR-POL`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-POL-1` | Action authority shall rest **locally**. Every proposed action shall receive exactly one decision: `ALLOW`, `CONFIRM`, or `BLOCK`. | No action reaches execution without a recorded decision | Must |
| `FR-POL-2` | The policy shall **deny by default**. Absent an explicit permitting rule, no action executes. | With an empty policy, all proposals are denied | Must |
| `FR-POL-3` | Actions with irreversible or externally-visible side effects shall require explicit **human confirmation**. The resulting approval shall be a signed, time-boxed token bound to the specific action, target, and origin. | A token for one action cannot authorise a different action, target, or origin; expired tokens are rejected | Must |
| `FR-POL-4` | A `BLOCK` decision shall halt the task immediately. The executor shall not be invoked. | No execution call occurs on a blocked task, verified by instrumentation | Must |
| `FR-POL-5` | The set of permitted origins shall be operator-configurable, and shall be enforced for every action. | Actions on non-permitted origins are blocked; the configuration is inspectable | Must |
| `FR-POL-6` | Untrusted page content shall be **unable to influence policy**. Instructions embedded in page text, attributes, or accessible names shall not alter a decision, grant privilege, or bypass confirmation. | A page containing adversarial instructions produces no privilege change; a containment test proves the untrusted block is treated as data | Must |
| `FR-POL-7` | Every decision shall be recorded with its reason, risk classification, and the evidence that produced it. | Audit records exist for all three decision types | Must |
| `FR-POL-8` | Risk classification shall be **monotonic** — adding a higher-risk attribute shall never lower the resulting risk level. | Property-based test over generated action combinations finds no inversion | Should |

### 3.9 Action Execution — `FR-EXE`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-EXE-1` | The executor shall act **only** on actions that are both structurally valid and policy-permitted. | An invalid or unpermitted action never reaches a dispatch call | Must |
| `FR-EXE-2` | Where the decision was `CONFIRM`, execution shall require a valid, unexpired approval token bound to that action, target, and origin. | Execution without a token, or with a mismatched token, is refused | Must |
| `FR-EXE-3` | The executable action set shall be a closed, declared allowlist. Actions outside it shall be unreachable. | No code path can dispatch an undeclared action type | Must |
| `FR-EXE-4` | Every action shall be bounded in time. A timeout shall be reported as an explicit failure, never as success. | Timeout produces a failure outcome in telemetry and the task state machine | Must |
| `FR-EXE-5` | Each execution shall record the action type, the bound target, the decision that permitted it, and the observed outcome. | Records exist for both successful and failed executions | Must |
| `FR-EXE-6` | Execution shall not modify page state outside the intended target element. | DOM diff after a `TYPE_SAFE_VALUE` action is confined to the target field | Should |

### 3.10 Task Verification — `FR-VER`

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-VER-1` | Task completion shall be established by **independent verification**, never by the reasoning model's own claim of success. | A model asserting completion without supporting page evidence does not complete the task | Must |
| `FR-VER-2` | Verification shall be deterministic and model-independent — the same observation and goal always yield the same verdict. | Repeated verification of identical inputs returns identical results | Must |
| `FR-VER-3` | Verification shall consume **fresh** post-action perception, not the pre-action observation. | Verifier input carries an observation identifier newer than the last executed action | Must |
| `FR-VER-4` | The false-completion rate shall be measured against a ground-truth task set. | **0.00%** false completions on the benchmark set; the measurement is published | Must |
| `FR-VER-5` | A task shall reach a completed state only on positive verification. Otherwise it shall terminate as failed, blocked, or bounded-out — never ambiguously complete. | Every task terminates in exactly one declared terminal state | Must |

### 3.11 Vision Capability Ladder — `FR-CAP`

> **This group closes v1 defects G-4, G-6, and G-7.** v1 contained **no** WebGPU or
> ONNX-Runtime-Web code anywhere (verified by exhaustive search), shipped a **42.9 MB** vendor
> payload, and — most seriously — a total vision failure produced a 1×1 image flagged
> `is_sanitized: true`, making failure **indistinguishable from success**.

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-CAP-1` | The engine shall resolve an inference backend at runtime from an ordered ladder: **WebGPU → WASM SIMD → WASM → DOM-only**. | On a host without WebGPU the system selects the next available rung and continues operating | Must |
| `FR-CAP-2` | The active rung shall be reported in telemetry and visible in the user interface. | The user can see which backend is in use without opening developer tools | Must |
| `FR-CAP-3` | The system **shall declare** `DEGRADED` whenever it operates below full capability. | Degraded operation is labelled as such in every artefact it produces | Must |
| `FR-CAP-4` | No failure path shall ever produce an artefact asserting `SANITIZED`. A capability failure shall yield `DEGRADED` or `NOT_INSTRUMENTED`. | Forced failure of every rung yields no `SANITIZED` artefact under any condition | Must |
| `FR-CAP-5` | The packaged extension shall not exceed **15 MB**. A single OCR core and a single model shall be selected by probe rather than shipping every variant. | Measured package size ≤ 15 MB | Must |
| `FR-CAP-6` | Model artefacts shall be quantization-compatible and shall not require a discrete GPU. | All declared rungs run on CPU-only hardware | Must |
| `FR-CAP-7` | Capability probing shall be cached for the session and re-evaluated when the execution context changes. | Probe cost is not paid per perception | Should |
| `FR-CAP-8` | Resource consumption shall be measured **on the extension stack**, not on the local Python stack. | The published resource figures are produced by an in-browser harness | Must |
| `FR-CAP-9` | Vision work shall not block the main thread. | Perceived UI frame rate during perception shows no sustained stall | Should |

### 3.12 User Surfaces — `FR-UI`

> **This group closes v1 defect G-9 (UI half).** v1 had two complete interfaces — a React console
> and a vanilla side panel — each independently implementing task entry, privacy display, policy
> display, and confirmation. Duplicate **presentation** is acceptable; duplicate **domain logic**
> is not.

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-UI-1` | The extension side panel shall be the **primary product surface** for perception, privacy status, and interaction. | A user can complete the full task loop from the side panel alone | Must |
| `FR-UI-2` | The demo console shall be a **presentation-only** surface for evaluation. It shall contain no domain logic. | Removing the console leaves all functional requirements satisfiable | Must |
| `FR-UI-3` | Both surfaces shall render from **identical** shared telemetry contracts. Neither shall re-implement privacy or policy computation. | The same telemetry payload drives both; no duplicated calculation exists in either surface | Must |
| `FR-UI-4` | The active capability rung and any `DEGRADED` state shall be visible in the interface. | The user can determine the operating mode without developer tools | Must |
| `FR-UI-5` | The literal outbound payload shall be inspectable in the interface (satisfies `FR-EGR-6`). | The jury can display the transmitted bytes live during the demonstration | Must |
| `FR-UI-6` | Unmeasured metrics shall display as `NOT_INSTRUMENTED`. No interface shall render a fabricated numeric value. | No hardcoded metric literal exists anywhere in either surface | Must |
| `FR-UI-7` | Human confirmation shall present the action, its target, its origin, and the reason it requires approval. | The user can make an informed decision without inspecting logs | Must |
| `FR-UI-8` | The interface shall remain responsive during perception and inference. | No sustained main-thread stall while a task runs | Should |

### 3.13 Telemetry & Measurement — `FR-TEL`

> **This group closes v1 defect G-10.** v1 shipped hardcoded `0.00%` leakage rates and a literal
> `"SECURE"` status across the API, the console, and the README, while reporting three mutually
> contradictory test counts (99 / 155 / 57 — actual collection was 204).

| ID | Requirement | Acceptance criterion | MoSCoW |
|---|---|---|---|
| `FR-TEL-1` | Metric names, units, and semantics shall be defined **once** in the shared kernel and consumed by every surface. | No surface defines its own metric name or unit | Must |
| `FR-TEL-2` | A metric that has not been measured shall report `NOT_INSTRUMENTED`. It shall never report `0`. | With no benchmark run present, every unmeasured metric renders as not-instrumented | Must |
| `FR-TEL-3` | No fabricated, hardcoded, or placeholder metric value shall appear in any interface, log, document, or API response. | Repository-wide search finds no hardcoded metric literal | Must |
| `FR-TEL-4` | Per-phase latency shall be reported as **p50 and p95** for perceive, sanitize, plan, decide, execute, and verify. | Percentiles produced by the benchmark harness; a mean alone is insufficient | Must |
| `FR-TEL-5` | All five rubric weights shall be instrumented and individually linkable to a producing benchmark. | Each weight maps to a named, runnable benchmark | Must |
| `FR-TEL-6` | The scorecard shall be **generated**, never hand-authored. | One documented command regenerates every published figure | Must |
| `FR-TEL-7` | Telemetry shall contain no raw sensitive values, no reverse mappings, and no raw screenshots. | Telemetry payload inspection finds no original values | Must |
| `FR-TEL-8` | Reported test counts shall be produced by an actual test run, not asserted in prose. | The published count matches a live collection run | Must |
| `FR-TEL-9` | Every published benchmark figure shall record the conditions under which it was produced. | Each result carries hardware, browser version, capability rung, and commit identifier | Should |

### 3.14 External Interface Requirements

| ID | Interface | Requirement | MoSCoW |
|---|---|---|---|
| `EI-1` | **Local enclave HTTP** | Shall bind to loopback only, expose versioned endpoints, and validate every request against a declared contract with unknown fields rejected. | Must |
| `EI-2` | **Extension ↔ enclave** | Shall use a declared message contract. The enclave shall re-verify sanitation rather than trusting extension-supplied assertions (`FR-EGR-4`). | Must |
| `EI-3` | **Reasoning provider** | Shall be selected at runtime from an ordered strategy: on-device model → local enclave → optional external provider. All providers shall receive an identical sanitized context shape. | Must |
| `EI-4` | **Provider capability negotiation** | Absence of an on-device model shall degrade to the next provider, never fail the task. | Must |
| `EI-5` | **Persistence** | No user page data, no placeholder mappings, and no raw perception shall be persisted at rest. | Must |
| `EI-6` | **Browser extension APIs** | Every requested permission shall be justified by a requirement. Permissions not required by a cited requirement shall not be requested. | Should |
| `EI-7` | **No interface** | No interface, internal or external, shall transmit raw perception, raw sensitive values, reverse mappings, or raw screenshots. | Must |

---

## 4. Verification & Traceability

### 4.1 Verification methods

Every requirement maps to exactly one primary verification method:

| Method | Meaning | Applies to |
|---|---|---|
| **T** — Test | Executed automatically; pass/fail is objective | Functional behaviour, thresholds, invariants |
| **D** — Demonstration | Shown operating on real input, observed by a human | End-to-end flows, interface visibility |
| **A** — Analysis | Verified by inspection of structure or static properties | Layering, module boundaries, absence of prohibited constructs |
| **I** — Inspection | Verified by review against a checklist | Documentation, configuration, permission justification |

### 4.2 Traceability

Full traceability is maintained in `REQ-RTM-001`, which maps every requirement through:

```
Requirement ID  →  Design artifact  →  Implementing module  →  Test/benchmark  →  Rubric weight
```

No requirement may be implemented without a corresponding design artifact, and no code may exist
without a corresponding requirement. Code that traces to no requirement is removed, not kept.

### 4.3 Acceptance

A requirement is **accepted** only when its stated acceptance criterion has been met and the
evidence is reproducible by a documented command. A criterion that cannot be reproduced on demand
is treated as unmet.

---

## 5. Requirements Summary

### 5.1 Counts by group

| Group | Count | Primary rubric weight |
|---|---|---|
| `FR-PER` — Perception | 7 | Visual 25% |
| `FR-VIS` — UI Element Understanding | 7 | Visual 25% |
| `FR-PII` — Sensitive-Data Detection | 12 | PII precision & recall 20% |
| `FR-RED` — Redaction | 8 | Redaction precision 20% |
| `FR-VLT` — Placeholder Vault | 7 | Redaction precision 20% |
| `FR-EGR` — Egress Control | 7 | PII 20% |
| `FR-AGT` — Agent Pipeline | 9 | Latency 15% |
| `FR-POL` — Policy & Confirmation | 8 | — |
| `FR-EXE` — Action Execution | 6 | Latency 15% |
| `FR-VER` — Task Verification | 5 | Visual 25% |
| `FR-CAP` — Capability Ladder | 9 | Client resources 20% |
| `FR-UI` — User Surfaces | 8 | — |
| `FR-TEL` — Telemetry | 9 | All weights |
| **Total** | **99 approved** | |

### 5.2 MoSCoW distribution

| Priority | Count | Note |
|---|---|---|
| **Must** | 87 | The baseline fails without these |
| **Should** | 15 | Expected within this delivery; first to be deferred under time pressure |
| **Could** | 0 | — |

> **There are no `Could` requirements.** The baseline is deliberately tight — every requirement
> either protects a rubric weight or protects the privacy invariant. Under schedule pressure the
> correct response is to reduce *quality within a requirement* or defer a `Should` — never to add
> scope.
>
> **First `Should` to be deferred:** the `FR-PII-FACE-*` group. `CR-001` pre-authorises this
> **automatically** if Sprint A exits with element classification below macro-F1 0.90, because the
> 25% visual weight must never be exposed to protect an unscored capability.

### 5.3 Requirements that deliberately exceed v1

| Requirement group | v1 state | Why it is a requirement, not an enhancement |
|---|---|---|
| `FR-VIS` (all) | Did not exist | Carries the heaviest rubric weight (25%) and is the literal subject of the problem statement |
| `FR-CAP` (all) | Did not exist | The problem statement names WebGPU / WASM / ONNX-Runtime-Web explicitly |
| `FR-PII` `T1/T3/T4` tiers | Format-only matching | Precision is a scored criterion; unchecked matching destroys it |
| `FR-RED-4` independent re-scan | Absent | v1 accepted a fully-failed image as sanitized |
| `FR-EGR-4` re-verification | Absent | v1 trusted a caller-supplied sanitized boolean |
| `FR-TEL-2/3` honesty rules | Violated | Fabricated metrics were the single largest credibility risk in v1 |

---

*End of `REQ-SRS-001`. Continued by:* `REQ-NFR-001` (non-functional requirements) ·
`REQ-DATA-001` (data catalogue) · `REQ-UC-001` (use cases) · `REQ-RTM-001` (traceability) ·
`DES-ARCH-001` (architecture).