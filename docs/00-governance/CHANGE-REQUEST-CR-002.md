# CHANGE REQUEST CR-002 — Definition of v2's Role in the Submission

| Field | Value |
|---|---|
| CR ID | `CR-002` |
| Raised by | Product Owner |
| Status | 🔒 **CLOSED — APPROVED** |
| Affects | `PROJECT-CHARTER.md` §1, §2, §4 · `REQ-SRS-001` §1.1 · `QUA-BENCH-001` |

---

## 1. Statement

A second development workstream runs concurrently on the v1 prototype at `../sih26171/`. The
Product Owner has confirmed that **both workstreams are deliberate**. This CR records the
resulting definition of v2's role so that no ambiguity remains in scope, priority, or acceptance.

Without this record, the project carried a real risk: two converging bodies of work producing
two charters and two traceability matrices with no declared relationship — which would read to an
evaluator as indecision rather than depth.

## 2. Decision

| Repository | Declared role |
|---|---|
| `../sih26171/` (**v1**) | **Working prototype.** Owns the live demonstration. |
| `../sih-agent-v2/` (**v2**) | **Engineering-process showcase and reference implementation.** Owns the SDLC artifacts and the verifiable evidence. |

Both are presented as **two components of one submission**. Presentation framing is owned by the
Product Owner.

## 3. What this changes for v2

| Dimension | Effect |
|---|---|
| **Primary deliverable** | The SDLC artifacts. These *are* the showcase. |
| **Code** | Still built, and still verifiable. A process that produces no working artefact is not a process — it is a document exercise, and juries discount it accordingly. |
| **Demonstration responsibility** | Moves to v1. v2 does not compete for the demo; it supplies the evidence behind it. |
| **Benchmark priority** | **Rises.** v2's principal job is to *prove* the numbers the demonstration asserts. |
| **Feature breadth** | Reduced in favour of engineering depth. |
| **Definition of Done** | Unchanged, and still binding in full. |

## 4. What this does **not** change

- The privacy invariant — raw sensitive content never crosses the trust boundary.
- The requirement set in `REQ-SRS-001` (102 requirements).
- The rubric-weight targets in `PROJECT-CHARTER.md` §5.
- Credibility gates C-1…C-5.

## 5. New obligation created — the evidence bridge

> **For every headline claim made during the demonstration, v2 shall publish an artifact that
> independently produces or verifies that claim.**

This is the concrete, measurable value v2 adds to the submission. It converts v2 from a parallel
effort into a **necessary** one: v1 *asserts*, v2 *proves*.

| Claim made during the demo | v2 artifact that proves it |
|---|---|
| "Raw PII leakage is zero" | `benchmarks/leakage` + `FR-EGR-2/3` tests |
| "Redaction is verified, not assumed" | `FR-RED-4` independent re-inspection harness |
| "The vision understands the page" | `benchmarks/visual_accuracy` (macro-F1 + confusion matrix) |
| "Detection precision and recall" | `benchmarks/pii_quality` (per-class, with FP rate) |
| "It runs on an ordinary laptop" | `benchmarks/client_resources`, measured **on the extension stack** |
| "It is fast enough to feel like an agent" | `benchmarks/latency` (p50/p95 per phase) |
| "Faces are redacted" | `FR-PII-FACE-2` re-scan fixture results (`CR-001`) |

**Rule:** no claim may appear in the demonstration for which no bridge row exists. A claim without
a proving artifact is removed from the demo script — not softened, not qualified.

## 6. Risk acknowledged

| Risk | Assessment | Mitigation |
|---|---|---|
| Two repositories dilute the submission | **Real** | The evidence bridge makes the relationship *complementary*: v1 asserts, v2 proves. Neither is redundant. |
| Effort duplication | **Real** | Territory rules in `GOV-ISO-001`; v2 reuses only via `GOV-LEDG-001` ledger rows. |
| Inconsistent numbers between repos | **Real** | Gate C-4 (`PROJECT-CHARTER` §5): every figure regenerable by one documented command. v2's numbers are the published ones. |
| Scope drift in v2 toward "docs only" | Low | §3 row 2: code is still built and verifiable. The showcase includes a working reference implementation. |

## 7. Decision record

| Role | Decision | Date |
|---|---|---|
| Product Owner | ✅ **APPROVED** — both components deliberate; v2 is the engineering-process showcase | 2026-10-01 |
| Technical Lead | Accepted; evidence-bridge obligation added to the v2 Definition of Done as item 7 | 2026-10-01 |