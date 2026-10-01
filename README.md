# SIH26171 — On-Device Visual Perception Browser Agent

> Industry-grade rebuild of the SIH26171 prototype. **Greenfield architecture, evidence-based code reuse.**

| | |
|---|---|
| **Problem Statement** | SIH26171 — *On-device Visual Perception for Light-weight Browser Agents* |
| **Organisation** | Indian Space Research Organisation (ISRO) · Department of Space |
| **Track / Theme** | Software / Smart Automation |
| **Build model** | Waterfall-governed inception → Agile iterative delivery (Scrum-flavoured) |
| **Predecessor** | `../sih26171/` (v1 prototype) — **reference only, never a dependency** |

---

## 1. What this repository is

A governed rebuild of a privacy-preserving browser agent. The agent perceives a web page
**locally** (DOM + pixels), detects and redacts sensitive data **on the device**, and only then
transmits a sanitized context to a reasoning system. It then validates the proposed action
against a trusted local policy, executes it, re-perceives, and independently verifies completion.

The **privacy boundary is the product**. Every architectural decision is subordinate to one
invariant:

```
PERCEIVE LOCALLY  →  DETECT LOCALLY  →  REDACT LOCALLY  →  VERIFY LOCALLY
                  →  TRANSMIT ONLY SANITIZED CONTEXT
                  →  REASON  →  VALIDATE ACTION LOCALLY  →  EXECUTE LOCALLY
```

## 2. Product surfaces (three, all in scope)

The system is deliberately a hybrid — this was a scoping decision, not an accident:

| Surface | Role | Trust posture |
|---|---|---|
| `apps/extension` | **On-device perception + privacy enforcement** (Chrome MV3) | Trusted. Owns the privacy boundary. |
| `apps/backend` | **Local reasoning enclave** (FastAPI, loopback only) | Semi-trusted. Receives sanitized context only. |
| `apps/console` | **Judge-facing demo console** (React) | Presentation only. Owns zero domain logic. |

## 3. Relationship to the v1 prototype

v1 is a working 12k-LOC proof of concept built from multiple AI outputs. It contains genuine
engineering assets and genuine structural debt.

We do **not** patch v1. We rebuild against explicit contracts and **lift specific proven assets**.
Every artifact received a disposition (`LIFT` / `REWORK` / `REWRITE` / `RETIRE`) — see
[`docs/00-governance/REUSE-AND-DEPARTURE-LEDGER.md`](docs/00-governance/REUSE-AND-DEPARTURE-LEDGER.md).
That ledger is the **only** sanctioned channel for v1 code entering this repository.

## 4. Engineering process (SDLC map)

| Phase | Artifacts | Gate |
|---|---|---|
| **0 · Inception** | Project Charter, Reuse & Departure Ledger, Delivery Plan | ✅ Complete |
| **1 · Requirements** | SRS, Use-Case Model, NFR Spec, Requirements Traceability Matrix | Sign-off required |
| **2 · Design** | Solution Architecture, Class Model, Sequence Diagrams, Data Contracts, Threat Model, ADRs | Sign-off required |
| **3 · Agile Delivery** | Product Backlog, Sprint Plans A–E, Definition of Done, Increment Reviews | Per-sprint demo |
| **4 · Verification** | Test Strategy, Rubric Scoring Harness, Benchmark Protocol, Traceability Audit | Evidence over claims |
| **5 · Hardening** | Failure-mode analysis, fallback ladder, resource-lifecycle audit | Zero open criticals |

**Rule:** no artifact is marked complete unless it is implemented and verified. No placeholders,
no fabricated metrics, no "TODO". A metric that has not been measured is reported as
`NOT_INSTRUMENTED`, never as `0`.

## 5. Target repository layout

```
sih-agent-v2/
├─ docs/                     # every SDLC artifact; the process lives here
│  ├─ 00-governance/         # charter, ledger, delivery plan, ADR index
│  ├─ 01-requirements/       # SRS, use cases, NFRs, traceability matrix
│  ├─ 02-design/             # architecture, class model, sequences, contracts
│  ├─ 03-agile/              # backlog, sprint plans, DoD
│  ├─ 04-quality/            # test strategy, rubric mapping, benchmark protocol
│  └─ 05-security/           # privacy-boundary spec, threat model, data-flow map
├─ packages/                 # isomorphic shared kernel — the contract layer
│  ├─ contracts/             # single source of truth for every DTO
│  ├─ taxonomy/              # PII entity registry → drives Python + TS codegen
│  └─ telemetry/             # metric names + units shared by all three surfaces
├─ apps/
│  ├─ extension/             # PRODUCT 1 — on-device perception + privacy
│  ├─ backend/               # PRODUCT 2 — local reasoning enclave
│  └─ console/               # PRODUCT 3 — judge-facing demo console
├─ services/vision/          # on-device vision engine (WebGPU → WASM ladder)
├─ benchmarks/               # rubric scoring harness, 1:1 with the five weights
├─ testdata/                 # fixtures, labelled PII corpus, ground-truth boxes
├─ tests/                    # contract / unit / e2e
└─ infra/                    # task runner, dev scripts, CI
```

## 6. Current status

| Phase | State |
|---|---|
| **Phase 0 — Inception** | ✅ **Complete** — Charter · Reuse Ledger · Executive Brief · Isolation Protocol · `CR-001` · `CR-002` |
| **Phase 1 — Requirements** | ✅ **Complete** — 155 requirements across 5 artifacts · *awaiting Product Owner sign-off on Gate G1* |
| **Phase 2 — Design** | ⬜ **Next** — C4 architecture · class model · sequences · data contracts · state machines · threat model |
| **Sprint 0 — Design artifacts + backlog** | ⬜ Pending Phase 2 |
| **Production code** | **None written** — correct for this phase |

### 6.1 The requirements baseline

| Artifact | Content |
|---|---|
| `REQ-SRS-001` | **102** functional requirements across 13 groups, plus 7 external interfaces |
| `REQ-NFR-001` | **53** non-functional requirements across 8 categories |
| `REQ-DATA-001` | **20** PII entities · 4 sensitivity classes · 4 verification tiers · validation, context-gating, and cross-runtime parity rules |
| `REQ-UC-001` | **16** use cases · 3 primary + 3 supporting actors · **1 adversarial actor** |
| `REQ-RTM-001` | Bidirectional traceability · all **5 of 5** rubric weights mapped · all **10 of 10** audit defects mapped to closing requirements |

**Every count above is verified against the documents themselves during the build, not asserted.**
Gate G1 stands at 9 of 10 criteria met.

### 6.2 Definition of the submission

Per `CR-002`, the submission has two **deliberate** components:

| Component | Repository | Role |
|---|---|---|
| Working prototype | `../sih26171/` | Owns the live demonstration |
| Engineering showcase | *(this repository)* | Owns the SDLC artifacts and the verifiable evidence |

The **evidence bridge** (`CR-002` §5) binds them: for every claim the demonstration makes, this
repository publishes an artifact that independently produces or verifies it. **v1 asserts, v2 proves.**
