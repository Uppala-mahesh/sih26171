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
| **Phase 1 — Requirements** | 🟡 **Baseline written, counts corrected, RTM incomplete** — 99 FR + 53 NFR + 7 EI = **159**; RTM lists 99/99, **80 implemented** · *awaiting Product Owner sign-off on Gate G1* |
| **Phase 2 — Design** | 🟡 **Partial** — C4 architecture · privacy boundary · threat model ✅ · **class model, sequences, data contracts and state-machine spec still owed** |
| **Sprint 1 — Privacy core** | ✅ **Complete** — detector · vault · sanitizer · pixel redactor · egress guard, on **both** Python and TypeScript, parity-locked |
| **Sprint 2 — Runtime** | 🟡 **Partial** — MV3 Chrome extension loads and runs · Z1 is the service worker · end-to-end pipeline live · **pixel capture unbuilt**, so painted content is declared uninspected |
| **Production code** | ✅ **Shipping** — 328 tests, 4 benchmarks, 1 loadable extension · worker harness 7/7 · real-browser check |

### 6.1 The requirements baseline

| Artifact | Content |
|---|---|
| `REQ-SRS-001` | **99** functional requirements across 13 groups, plus 7 external interfaces (EI-*) |
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


---

## 7. Build and run

```bash
npm install
npm run verify        # typecheck + taxonomy check + parity build + extension build
```

**Load the extension**

1. `chrome://extensions` → enable **Developer mode**
2. **Load unpacked** → select `dist-extension/`

No bundler is used. The sources already use explicit `.js` import specifiers, so
Chrome's own module loader resolves them — **the code that runs in the browser is
the code in this repository, unmodified.** A bundler would be another program
rewriting the privacy core on its way to disk.

**Run the tests**

```bash
python -m pytest tests/contract -q
```

**Run the benchmarks**

```bash
python benchmarks/pii_quality.py            # detection quality
python benchmarks/redaction_precision.py   # redaction quality
```

Both exit non-zero if a target is missed, so they work as CI gates.

## 8. Where the privacy boundary actually is

```
page DOM ──content script──▶ SERVICE WORKER (Z1)
 (untrusted)  collector only     DOM-free · pixels unavailable · vault + guard + core
```

| Context | Can reach | Cannot reach |
|---|---|---|
| **Content script** | page text | vault, detector, guard — no imports at all |
| **Service worker (Z1)** | everything | the page DOM, and therefore page pixels |

Raw page content exists on exactly **one** side of the Z1 boundary. That is what
makes "no outbound payload can hold raw content" a structural property rather
than a review promise — and it is asserted by
`tests/contract/test_extension_artifact.py`, not merely documented.

### Why Z1 is the service worker and not an offscreen document

Originally Z1 was an offscreen document, on the assumption that pixel capture
requires a real `document`. It does — but nothing else does: the content script
extracts text, and every privacy operation after that is pure computation.

The offscreen route was **removed from the critical path** after it produced two
identical `Could not establish connection` failures from two different causes.
One was a race inherent to the API: `createDocument()` resolves when the document
*exists*, not when its module has *evaluated*, so any send afterwards can beat
the listener registration. **A security boundary should not be built on top of a
race.**

### What it costs — and how that is measured

A service worker has no `document`, so it cannot rasterise page pixels. Rather
than pretend otherwise, **the content script counts the surfaces that could
conceal text** — `canvas`, `img`, `video`, `svg`, `object`, `embed`, and CSS
`background-image` — and reports the number. It is the only context with a DOM,
so it is the only one that can answer.

That number decides the verdict:

| Page | Verdict | Behaviour |
|---|---|---|
| Text only, nothing painted | **`SANITIZED`** → `OK` | Transmits. Nothing painted can conceal anything. |
| Images / canvas / CSS backgrounds | **`DEGRADED`** → `DEG` | **Transmits**, with the uninspected-surface count declared in the payload so the receiver knows exactly what was not checked. |
| Surface count unavailable | **`NOT_INSTRUMENTED`** → `HOLD` | Withholds. An unknown count is never read as zero. |

`DEGRADED` is not a softened failure — it is a *different claim*. It asserts the
text channel was fully verified and states plainly that the pixel channel was not.
The verdict `ALLOW_DECLARED` carries that limitation to the receiver, which is
materially different from staying silent and materially different from claiming
full coverage.

### Two earlier versions of this decision, and why both were wrong

**v1 — withhold whenever any frame is missing.** Correct, and useless: it refused
to work on every page with a logo, an icon, or a background, which is
essentially every real website. A guard that blocks all traffic protects nothing
because it permits none.

**v2 — transmit when the painted-surface count is zero, withhold otherwise.**
Better, and still useless, because it kept the same threshold. Almost no real page
has a painted-surface count of zero.

The threshold was never the thing that needed fixing; the *state* was. The
question is not "were the pixels checked" but "what exactly do we promise, and can
the receiver see the promise?" `DEGRADED` answers it.

It is still true that the 25% visual weight is **not yet earned**: the pixel
redaction, IoU and irreversibility benchmarks measure the core algorithms, not a
Chrome integration. Painted content is *declared uninspected*, not scanned.

## 9. Measured results

Numbers below are produced by the committed harnesses. Nothing here is asserted.

| Claim | Measurement | Harness |
|---|---|---|
| PII detection | precision **100%**, recall **100%** (strict) | `benchmarks/pii_quality.py` |
| PII redaction | **0.0000%** residual leakage | `benchmarks/redaction_precision.py` |
| Pixel masking | **0** survivors, worst IoU **0.917** | `benchmarks/redaction_precision.py` |
| Utility | **1.0000** preserved outside masks | `benchmarks/redaction_precision.py` |
| Cross-runtime parity | Python ≡ TypeScript, 4 suites | `tests/contract/test_*_parity.py` |
| End-to-end | 6 scenarios, 3 must **withhold** | `tests/contract/test_pipeline_end_to_end.py` |

**Known gaps, stated rather than hidden.** The vision classifier is not built, so
the 25% visual-accuracy weight is unmeasured. Client-resource and latency budgets
are not yet instrumented. The extension's pixel route currently emits empty mask
boxes because detection boxes depend on the classifier (tracked as `CR-003`);
the pipeline treats that honestly and will not claim `SANITIZED` without at least
one verified frame.

| Engineering showcase | *(this repository)* | Owns the SDLC artifacts and the verifiable evidence |

The **evidence bridge** (`CR-002` §5) binds them: for every claim the demonstration makes, this
repository publishes an artifact that independently produces or verifies it. **v1 asserts, v2 proves.**
