# SOFTWARE REQUIREMENTS SPECIFICATION

| Field | Value |
|---|---|
| Document ID | `REQ-SRS-001` |
| Version | 1.0 — Draft for approval |
| Structure | ISO/IEC/IEEE 29148 (IEEE 830 organisation) |
| Status | 🟡 Draft — **Part 1 of 3** (Introduction, Overall Description) |
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
evasion · face/photo detection pending `CR-001`.

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

Part 1 (this document): introduction and overall description. Part 2: functional requirements
`FR-*`. Part 3: external interface requirements and verification criteria. Non-functional
requirements are specified separately in `REQ-NFR-001`; the sensitive-data taxonomy in
`REQ-DATA-001`; requirement-to-rubric traceability in `REQ-RTM-001`.

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

<!-- APPEND-POINT -->