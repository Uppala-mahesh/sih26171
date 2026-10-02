# REQUIREMENTS TRACEABILITY MATRIX

| Field | Value |
|---|---|
| Document ID | `REQ-RTM-001` |
| Version | 1.0 — Draft |
| Status | 🟡 **Complete — awaiting Product Owner approval** |
| Owner | Technical Lead |
| Scope | 99 functional + 53 non-functional + 7 external interfaces = **159 requirements** |

---

## 1. Purpose

This matrix is what turns a requirements document into an **enforceable contract**. It provides
bidirectional traceability across five columns:

```
REQ id  →  design artifact  →  implementing module  →  test / benchmark  →  rubric weight
```

### 1.1 The two rules this matrix enforces

| Rule | Statement | Consequence of violation |
|---|---|---|
| **T-1 · No orphan requirements** | Every approved requirement must map to a design artifact, a module, and at least one test or benchmark. | The requirement is **unverifiable** and cannot be claimed as met. |
| **T-2 · No orphan code** | Every product module must map back to at least one requirement. | The module is removed. It is scope the customer never asked for. |

> **T-2 is the rule that keeps the codebase honest.** In v1, `LocalOCRAdapter` sat in the tree as
> the ABC's default implementation with a method named `process_and_redact()` that returned its
> input unchanged. It traced to no requirement, served no caller, and actively misled readers about
> what the system did. Under T-2 it would have been deleted the day it appeared.

### 1.2 Maintenance rule

The matrix is **living**. A change that alters a requirement, a module boundary, or a benchmark
must update this matrix **in the same commit**. This is `NFR-MAIN-6` ("zero untraced requirements")
made mechanical.

---

## 2. Functional requirement mapping

Rubric column shows the official weight the group feeds.

| Req group | Design artifact | Implementing module | Verification | Rubric |
|---|---|---|---|---|
| `FR-PER-1…7` | `DES-ARCH-001` §5 | `services/vision/sources/dom` · `…/ocr` | `tests/e2e/perception` · `benchmarks/visual_accuracy` | Visual 25% |
| `FR-VIS-1…7` | `DES-ARCH-001` §6 · `DES-CLASS-001` | `services/vision/sources/ui-classifier` | `benchmarks/visual_accuracy` (macro-F1, confusion matrix) | **Visual 25%** |
| `FR-PII-1…12` | `REQ-DATA-001` · `DES-CLASS-001` §4 | `apps/backend/app/privacy/detectors/*` + `packages/taxonomy` | `benchmarks/pii_quality` (per-class P/R) | **PII 20%** |
| `FR-RED-1…8` | `DES-CLASS-001` §5 | `apps/backend/app/privacy/visual_redactor` + re-inspection | `benchmarks/redaction_precision` · IoU harness | **Redaction 20%** |
| `FR-VLT-1…7` | `DES-CLASS-001` §5 | `apps/backend/app/privacy/vault` | `tests/unit/vault` · storage inspection | Redaction 20% |
| `FR-EGR-1…7` | `DES-ARCH-001` §7 · `SEC-BOUND-001` | `apps/backend/app/gateway/*` | `tests/contract/egress` · payload inspector | PII 20% |
| `FR-AGT-1…9` | `DES-STATE-001` · `DES-SEQ-001` | `apps/backend/app/agent/pipeline` + `drivers/*` | `tests/e2e/closed_loop` · `benchmarks/latency` | Latency 15% |
| `FR-POL-1…8` | `SEC-BOUND-001` · `DES-CLASS-001` §7 | `apps/backend/app/policy/*` | `tests/unit/policy` · injection corpus | Credibility |
| `FR-EXE-1…6` | `DES-SEQ-001` | `apps/backend/app/execution/*` | `tests/e2e/execution` | Latency 15% |
| `FR-VER-1…5` | `DES-CLASS-001` §8 | `apps/backend/app/agent/verifier` | `benchmarks/false_completion` | Visual 25% |
| `FR-CAP-1…9` | `DES-ARCH-001` §6 · `DES-STATE-001` | `services/vision/capability-resolver` | Cross-rung conformance suite · `benchmarks/client_resources` | **Resources 20%** |
| `FR-UI-1…8` | `DES-ARCH-001` §8 | `apps/extension/sidepanel` · `apps/console` | UI integration tests · demo walkthrough | — |
| `FR-TEL-1…9` | `DES-DATA-001` | `packages/telemetry` · `benchmarks/` | `benchmarks/scorecard` (generated) | **All weights** |
| `EI-1…7` | `DES-ARCH-001` §9 · `DES-DATA-001` | `apps/backend/app/api/*` · `packages/contracts` | `tests/contract/*` | Credibility |

### 2.1 Rubric coverage check

Every weight must map to at least one requirement group and one producing benchmark.

| Weight | Requirement groups | Producing benchmark | Status |
|---|---|---|---|
| **Visual accuracy 25%** | `FR-VIS`, `FR-PER`, `FR-VER` | `benchmarks/visual_accuracy` | ✅ mapped |
| **PII precision/recall 20%** | `FR-PII`, `FR-EGR` | `benchmarks/pii_quality` | ✅ mapped |
| **Redaction precision 20%** | `FR-RED`, `FR-VLT` | `benchmarks/redaction_precision` | ✅ mapped |
| **Client resources 20%** | `FR-CAP`, `NFR-RES` | `benchmarks/client_resources` | ✅ mapped |
| **Latency 15%** | `FR-AGT`, `FR-EXE`, `NFR-PERF` | `benchmarks/latency` | ✅ mapped |

**No weight is unmapped.** Contrast with v1, where the 25% visual weight had no implementing
module at all and two benchmarks measured the wrong stack.

## 3. Non-functional requirement mapping

| Req group | Design artifact | Measurement artifact | Budget |
|---|---|---|---|
| `NFR-PERF-1…8` | `DES-ARCH-001` §10 | `benchmarks/latency` | p95 ≤ 800 ms / 3.0 s |
| `NFR-RES-1…9` | `DES-ARCH-001` §11 | `benchmarks/client_resources` | ≤ 15 MB · ΔRSS ≤ 150 MB |
| `NFR-REL-1…7` | `DES-STATE-001` | Fault-injection + fuzz harnesses | Zero uncaught exceptions |
| `NFR-SEC-1…7` | `SEC-THREAT-001` · `SEC-BOUND-001` | `tests/contract/security` · injection corpus | Zero escalations |
| `NFR-PORT-1…5` | `DES-ARCH-001` §6 | Cross-rung + cross-version CI | Identical verdicts |
| `NFR-MAIN-1…7` | `DES-TREE-001` (module map) | Import-linter · line-count · coverage | ≤ 400 lines/module |
| `NFR-USA-1…5` | `DES-ARCH-001` §8 | Accessibility + contrast audits | WCAG AA |
| `NFR-PRIV-1…5` | `SEC-BOUND-001` | Payload · storage · filesystem inspection | Zero retention |

---

## 4. v1 defect closure traceability

Every gap identified in the Phase 1 audit maps to the requirement that closes it and the artifact
that **proves** it is closed. This is the table a reviewer uses to answer: *"you found these —
did you actually fix them?"*

| # | v1 defect (verified in the Phase 1 audit) | Closing requirement | Proving artifact |
|---|---|---|---|
| **G-1** | Python engine detected **none** of Aadhaar / PAN / UPI / IFSC / OTP; `EntityType` could not represent them | `FR-PII-1` · `REQ-DATA-001` | Cross-runtime parity test · `benchmarks/pii_quality` |
| **G-2** | `is_sanitized=True` set unconditionally; a 1×1 failed image accepted as sanitized | **`FR-RED-4`** | Under-sized mask detected → artefact rejected |
| **G-3** | **No UI-element understanding** — the 25% weight had no implementing module | `FR-VIS-1…7` | `benchmarks/visual_accuracy` macro-F1 + confusion matrix |
| **G-4** | No WebGPU / ONNX-Runtime-Web / Transformers.js anywhere | `FR-CAP-1` | Capability ladder demo · rung reported in telemetry |
| **G-5** | No checksum validation → 13–19 digit runs matched as cards | `FR-PII-2` · `REQ-DATA-001` §4 | Non-Luhn fixture yields zero `CREDIT_CARD` detections |
| **G-6** | Fail-closed path **masqueraded as success** | **`FR-CAP-4`** | Every rung forced to fail → no `SANITIZED` artefact produced |
| **G-7** | 42.9 MB vendor payload contradicts "light-weight" | `FR-CAP-5` · `NFR-RES-1` | Build artefact measurement ≤ 15 MB |
| **G-8** | No face detection, though the demo promises it | `FR-PII-FACE-1…3` | `CR-001` fixture harness, ≥ 40 labelled faces |
| **G-9** | Three reasoning cores duplicated security wiring; two UIs duplicated domain logic | `FR-AGT-1` · `FR-UI-3` | Import-linter · single-pipeline structure test |
| **G-10** | Fabricated metrics (`0.00%`, `"SECURE"`) and three contradictory test counts | `FR-TEL-2/3/8` | Repository-wide search for hardcoded metric literals |

### 4.1 Closure status

| Status | Count | Meaning |
|---|---|---|
| **Closed by requirement** | 10 of 10 | Every defect has a requirement that closes it |
| **Proving artifact exists** | 0 of 10 | *The artifacts are built in Sprints A–D. Until then, closure is **claimed**, not **proven**.* |

> **The honest reading.** All ten defects now have requirements. **None is yet proven closed**,
> because the proving artifacts do not exist. This document will be updated as each benchmark and
> harness lands, and the second row above will move from 0 to 10.
>
> Charter credibility gate **C-1** forbids marking a defect closed on the strength of a
> requirement alone. A requirement is an intention; a passing benchmark is evidence.

---

## 5. Gate G1 — requirements baseline acceptance

The baseline is accepted when **all** of the following hold:

| # | Criterion | State |
|---|---|---|
| 1 | `REQ-SRS-001` written, 99 requirements measurable | 🟡 baseline only; see coverage |
| 2 | `REQ-NFR-001` complete, all 53 requirements measurable | ✅ |
| 3 | `REQ-DATA-001` complete; taxonomy authoritative and parity-ruled | ✅ |
| 4 | `REQ-UC-001` complete; actors, use cases, include/extend, key flows | ✅ |
| 5 | `REQ-RTM-001` maps every requirement to module, test, and rubric weight | 🟡 this document |
| 6 | Every rubric weight has a producing benchmark identified | ✅ §2.1 |
| 7 | Every audit defect maps to a closing requirement | ✅ §4 |
| 8 | All open Change Requests resolved | ✅ `CR-001`, `CR-002` both closed |
| 9 | No requirement in `Could`; scope is tight | ✅ 87 Must / 15 Should / 0 Could |
| 10 | Product Owner sign-off | ⬜ **pending** |

---

## 6. Summary

> ### ⚠️ Coverage disclosure — read this before citing this matrix
>
> This matrix traces **19 / 99** functional requirements (**19.2%**). It is **not
> complete**, and it did not used to say so.
>
> Found by `infra/count_requirements.py`, which derives every count by reading
> the documents rather than trusting a typed figure. Three artifacts had claimed
> **"102 functional / 155 total"** while the SRS actually contains **99** and
> **152** (excluding the 7 `EI-*` interface requirements) — **159** including
> them. Those figures are corrected throughout.
>
> **Outstanding: 80 functional requirements have no row here.** That is the
> largest single gap in the SDLC and the next thing to close.
>
> `tests/contract/test_requirement_counts.py` fails if this coverage figure ever
> diverges from the documents, so the matrix can no longer silently overstate
> itself.
>
> **Correction to an earlier correction.** A first pass of the counter reported
> nine "phantom" requirement ids here. That was a bug in the counter, not a
> defect in this matrix: the pattern `FR-[A-Z]+-\d+` also matches *inside*
> `NFR-PERF-1`, so eight legitimate non-functional rows were misreported as
> fabricated functional traceability. There are no phantom ids. The pattern now
> anchors on a word boundary. This note is kept because a correction with no
> stated original is indistinguishable from never having been wrong.

| Dimension | Count |
|---|---|
| Functional requirements | **99** |
| Non-functional requirements | **53** |
| External interfaces | 7 |
| **Total requirements** | **159** |
| Requirement groups | 21 |
| Use cases | 17 |
| **Functional requirements traced** | **19 / 99 (19.2%) — incomplete** |
| Rubric weights mapped | **5 of 5** |
| Audit defects mapped | **10 of 10** |
| Change requests closed | 2 |
| Orphan requirements | 0 *(asserted; enforced by T-1)* |
| Orphan modules | 0 *(asserted; enforced by T-2)* |

### 6.1 What comes next

`REQ-RTM-001` is the **last requirements artifact**. On G1 acceptance, the project moves to
**Phase 2 — Design**, producing:

`DES-ARCH-001` (C4 architecture) · `DES-CLASS-001` (class and interface model) ·
`DES-SEQ-001` (sequence diagrams) · `DES-DATA-001` (data contracts) ·
`DES-STATE-001` (state machines) · `SEC-THREAT-001` (threat model) ·
`SEC-BOUND-001` (privacy boundary) · `AGL-BKLG-001` (product backlog)

and then, and only then, Sprint A writes its first line of production code.

*End of `REQ-RTM-001`. End of the Phase 1 requirements baseline — pending Product Owner sign-off.*