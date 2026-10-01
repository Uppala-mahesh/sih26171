# PROJECT CHARTER — SIH26171 On-Device Visual Perception Browser Agent

| Field | Value |
|---|---|
| Document ID | `GOV-CHTR-001` |
| Version | 1.0 |
| Status | **Approved (baseline)** |
| Owner | Product Owner / Technical Lead |
| Supersedes | v1 prototype `../sih26171/IDEA.md`, `../sih26171/README.md` |

---

## 1. Purpose

Authorise and bound an industry-grade rebuild of the SIH26171 solution: a browser agent that
performs visual perception, sensitive-data detection, and redaction **entirely on the user's
device**, transmitting only sanitized context to any reasoning system, and executing only
locally-validated actions.

The rebuild exists because the v1 prototype, while functionally broad, accumulated structural
debt that prevents it from being defended under evaluation: duplicated privacy engines with
non-overlapping PII vocabularies, a 1,738-line service worker, global mutable state, and
**45% of the official rubric unmeasured**.

### 1.1 Role within the submission

Per `CR-002`, the submission comprises two **deliberate, complementary** components:

| Component | Repository | Role |
|---|---|---|
| **Working prototype** | `../sih26171/` | Owns the live demonstration. |
| **Engineering showcase** | `../sih-agent-v2/` *(this repository)* | Owns the SDLC artifacts, and the verifiable evidence behind every demonstrated claim. |

v2 is therefore optimised for **engineering depth and verifiable evidence**, not feature breadth.
Its code exists to prove what the demonstration asserts — see the **evidence bridge** in
`CR-002` §5. A claim made in the demonstration for which v2 publishes no proving artifact is
removed from the demo script rather than softened.

## 2. Problem statement (authoritative, condensed)

AI browser agents require screen-state access to act. Current pipelines ship screenshots, DOM,
and page content to remote models — unacceptable on government portals, banking, Aadhaar/PAN
services, healthcare, authentication pages, and enterprise applications.

The solution must bridge **local/on-device computation** with **server-side reasoning**, while
guaranteeing sensitive information is protected **before any network transmission**.

**Core requirement:** the browser extension itself contains the local perception and privacy
layer, running a lightweight vision model via WebGPU / WASM / ONNX-Runtime-Web, and covering
UI element understanding (buttons, fields, links, forms, text regions, images, navigation,
dialogs, tables, menus, controls).

## 3. Vision

> A browser agent that can act on any page — including the most sensitive ones — because it
> never has to trust the network with what it sees.

## 4. Scope

### In scope
- Chrome MV3 extension: perception, PII detection, redaction, action execution, side-panel UI
- On-device vision engine with an explicit capability ladder (WebGPU → WASM SIMD → WASM → DOM-only)
- Isomorphic entity taxonomy + DTO contracts shared across all three surfaces
- Local Python reasoning enclave (loopback only) + egress chokepoint with audit
- Judge-facing demo console with live telemetry
- Rubric scoring harness measuring all five official weights against ground truth
- Threat model covering indirect prompt injection, stale targets, egress bypass, vault leakage

### Out of scope (deliberate, recorded)
- **Firefox port** — deferred. Scores 0% of the rubric; costs a full compatibility layer. Revisit post-submission.
- Cloud-primary reasoning — on-device/perception remains local; cloud is optional fallback only.
- Multi-user server deployment, accounts, persistence of user data at rest.
- Mobile browsers, Safari.
- Training or fine-tuning custom models (inference-only integration).
- Solving CAPTCHA, bypassing authentication, or any evasion of site controls.

## 5. Success criteria — mapped 1:1 to the official rubric

Evaluation weights are fixed by the problem statement. Every criterion names the artifact that
measures it. **A criterion with no measurement is not a criterion.**

| Weight | Criterion | Target | Measured by |
|---|---|---|---|
| **25%** | Visual perception accuracy | Element-role classification **F1 ≥ 0.90** on held-out fixtures; redaction mask IoU ≥ 0.90 vs ground-truth boxes | `benchmarks/visual_accuracy` |
| **20%** | PII detection precision & recall | Recall **≥ 0.98**, Precision **≥ 0.95** on the labelled corpus (Aadhaar, PAN, UPI, OTP, IFSC, card, email, phone, password, API key, person) | `benchmarks/pii_quality` |
| **20%** | Redaction precision | **0.00%** residual pixel leakage, verified by independent re-OCR of the redacted image; utility preservation ≥ 0.95 | `benchmarks/redaction_precision` |
| **20%** | Client resources | Perception-phase RSS delta **≤ 150 MB**; extension package **≤ 15 MB**; no sustained idle CPU | `benchmarks/client_resources` (Chrome APIs, measured on the **extension** stack) |
| **15%** | End-to-end latency | Perceive→sanitize p95 **≤ 800 ms**; full agent step p95 **≤ 3.0 s** | `benchmarks/latency` |

### Credibility criteria (gate — non-negotiable)

- **C-1** No fabricated metric may appear in any UI, document, or log. `NOT_INSTRUMENTED` is the only permitted representation of an unmeasured value. *(v1 shipped hardcoded `0.00%` and `"SECURE"`; this charter forbids its return.)*
- **C-2** No secret, API key, or browser-profile artifact may be committed.
- **C-3** Every test asserting a guarantee must exercise the real production code path.
- **C-4** Every figure quoted in the README must be regenerable by one documented command.
- **C-5** A degraded or failed subsystem must declare itself (`DEGRADED`, `UNAVAILABLE`). It may never masquerade as success.

## 6. Stakeholders

| Stakeholder | Interest | Influence |
|---|---|---|
| SIH Evaluators / Jury | Rubric score, demonstrable privacy guarantee, engineering maturity | Decisive |
| End user (citizen / employee) | Task completion without data exposure | High |
| Product Owner | Scope, prioritisation, acceptance | Decisive |
| Technical Lead | Architecture integrity, delivery | Decisive |
| ISRO (problem owner) | Practical viability on government / enterprise portals | High |

## 7. Constraints & assumptions

| ID | Statement |
|---|---|
| C-1 | Perception and redaction must execute on-device. No exception. |
| C-2 | Extension must function with **zero API keys configured** (Gemini Nano / local enclave path). |
| C-3 | Backend binds to loopback only; never exposed beyond `127.0.0.1`. |
| C-4 | Target environment is the evaluator's laptop — **no GPU assumed**. WebGPU is an optimisation, never a prerequisite. |
| C-5 | Extension size must respect the "light-weight" claim in the problem title. |
| A-1 | Chrome Prompt API (Gemini Nano) availability varies by profile → must degrade, never hard-fail. |
| A-2 | All model licenses permit redistribution for a hackathon submission. |

## 8. Top risks

| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Visual accuracy carries **25%**, and v1 has **no** element-understanding model — vision is OCR-for-redaction only | Critical | UI-element classification is a first-class subsystem from Sprint A, not a bolt-on |
| R-2 | WebGPU unavailable on evaluator hardware | High | Capability ladder with a WASM-SIMD path validated in CI; WebGPU strictly additive |
| R-3 | Regex-only PII detection generates false positives, destroying precision (20%) | High | Checksum validation (Luhn / Verhoeff), context gating, confidence thresholds, measured FP rate in CI |
| R-4 | A "fail-closed" path masquerading as success — v1's exact defect (a 1×1 PNG flagged `is_sanitized: true` was accepted downstream) | Critical | `DEGRADED` becomes a first-class *declared* state; never an implicit success |
| R-5 | The two PII engines drift apart again | High | One taxonomy in `packages/taxonomy` drives both; contract tests fail the build on drift |
| R-6 | Scope creep into features scoring **0%** of the rubric | Medium | §4 out-of-scope list is binding; any change needs a CR |
| R-7 | Extension size (v1 vendor payload ≈ **42.9 MB**) contradicts "light-weight" | Medium | Prune to a single OCR core chosen by runtime capability probe |

## 9. Delivery model

**Waterfall-governed inception, Agile iterative delivery.**

- Phases 0–2 (Inception, Requirements, Design) are **sequential with formal sign-off** — no production code is written before design approval.
- Phase 3 (Delivery) runs as **timeboxed sprints**, each producing a demonstrable increment.
- Ceremonies: Sprint Planning · asynchronous daily sync · Sprint Review (demo against the Definition of Done) · Retrospective.
- Every sprint closes with a **rubric impact statement**: which weight moved, by how much, and the benchmark run that proves it.

| Sprint | Increment | Rubric weight addressed |
|---|---|---|
| **A** | Shared kernel (taxonomy + contracts) and the on-device vision engine with capability ladder | Client resources 20% · Visual 25% (partial) |
| **B** | PII detection and sanitization layer (strategies, checksums, redaction + verification) | PII quality 20% · Redaction 20% |
| **C** | Agent pipeline and action engine | Latency 15% · Visual 25% (completion) |
| **D** | Consoles, telemetry, and the rubric scoring harness | Makes **all** weights measurable |
| **E** | Hardening, fallback paths, edge-case defence | Protects all weights |

## 10. Definition of Done

An increment is `DONE` only when **all** of the following hold:

1. **Implemented** — zero placeholders, zero TODOs, no truncated code.
2. **Contracted** — every boundary crossing uses a declared contract from `packages/contracts`.
3. **Tested** — unit and contract tests pass; every guarantee is tested on the real production code path.
4. **Measured** — any claimed rubric-relevant number is produced by a benchmark run.
5. **Documented** — the owning SDLC artifact is updated in the same change.
6. **Reviewed** — passes the reviewer checklist in `infra/`.

## 11. Change control

Scope changes, contract changes, and rubric-target changes require a **Change Request** recorded
under `docs/00-governance/`, stating rationale and sprint-plan impact. Architecture decisions are
recorded as ADRs under `docs/02-design/adr/`.

Silent scope growth is the primary failure mode this charter exists to prevent. If a task is not
traceable to a requirement and a rubric weight, it does not enter a sprint.

## 12. Approval

| Role | Decision |
|---|---|
| Product Owner | Pending Phase 1 (Requirements) sign-off |
| Technical Lead | Baseline v1.0 issued |
