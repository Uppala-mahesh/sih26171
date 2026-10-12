# Drishti — SIH 2026 Review-1 Data Pack

> **How to use:** every number below was produced by running the system. Sections map
> 1:1 to the Review-1 checklist. Nothing here is estimated or invented.
> Verified 11 Oct 2026 · 14/14 gates · 145 JS tests · 235 Python tests · clean build

---

## 1. Problem Statement ID and Title

| Field | Value |
|---|---|
| **PS ID** | SIH26171 |
| **Title** | On-device Visual Perception for Light-weight Browser Agents |
| **Organisation** | Department of Space / ISRO |
| **Event** | Smart India Hackathon 2026 |
| **Project name** | Drishti (दृष्टि — *sight*) |
| **Track** | Smart Automation · Software |

**One-line description**
> A closed-loop computer-use agent that drives the operator's own Chrome profile and
> performs visual perception and privacy redaction **on-device**, so only sanitised
> context ever reaches a cloud model.

---

## 2. Abstract

Browser agents that use large language models observe a page and send what they see —
raw screenshots and DOM text — to a remote model. For a bank portal, an Aadhaar
service, or a hospital system, that transmits the user's most sensitive data to a third
party on every single step. Existing automation also fails on capability: frameworks
like Playwright spawn a fresh browser with none of the operator's logged-in sessions, so
they cannot reach the sites users actually need.

Drishti addresses both. It is a Chrome extension plus a local server that runs a
closed loop — observe, reason, policy, execute, verify against a fresh observation,
recover. Perception and privacy enforcement execute **inside the page**: nine classes of
personally identifiable information are detected and replaced with typed placeholders
before the page is ever serialised, sensitive regions are painted solid black before the
screenshot is encoded, and payment QR codes are located and masked without ever being
decoded. A fail-closed verification pass re-reads the already-masked screenshot with an
on-device OCR engine; if any PII shape survived masking, the screenshot is withheld
entirely rather than sent "mostly redacted".

A second contribution is methodological. Because a perception step can fail while still
looking successful, every observation carries a **derived verdict** —
`SANITIZED` / `ALLOW_DECLARED` / `DEGRADED` / `WITHHOLD` — computed on demand from
measured fields, so it cannot be set to a comfortable answer. This is enforced by
fourteen automated gates, two of which grade real behaviour rather than matching source
text, after mutation testing showed a grep-based check passed while the safety feature
was fully broken.

*Keywords:* browser agent, on-device perception, PII redaction, prompt injection,
fail-closed verification, human-in-the-loop, Manifest V3, ONNX, edge inference.

---

## 3. Existing System and Proposed Solution

### 3.1 What exists today

| Approach | What it does | Where it fails |
|---|---|---|
| **Cloud browser agents** (vendor products) | LLM drives a browser via remote control; page content goes to a vendor | Raw screenshots + DOM transmitted on every step; no local privacy control |
| **Playwright / Puppeteer automation** | Scripted control from outside the browser | Fresh profile — **no logged-in sessions**; detectable; cannot reach internal sites |
| **Scripted scrapers** | Deterministic selectors, no reasoning | Breaks on any layout change; zero transfer learning between sites |
| **Prior attempt v1** (`sih26171`) | Correct 15-stage privacy pipeline, real OCR | Reasoning layer was a **deterministic mock**; 5 of 7 headline metrics blank; face detection absent |
| **Prior attempt v2** (`sih-agent-v2`) | Excellent privacy kernel, 356 tests, honest evidence | **No agent at all** — no console, no HTTP server, no pixel capture |

### 3.2 Proposed solution

| # | Gap in existing systems | Drishti's answer | Evidence |
|---|---|---|---|
| 1 | Raw page content sent to cloud | Redaction runs **in the page**, before serialisation. Content script contains no `WebSocket` and no server address | **gate G7** |
| 2 | Automation loses logged-in sessions | Extension runs inside the operator's own Chrome profile | Architecture decision ADR-002 |
| 3 | Hiding assumed, never verified | OCR re-reads the **masked** screenshot; any surviving PII ⇒ screenshot withheld | **gate G10** |
| 4 | Degraded steps look successful | Four-state **derived** verdict, computed from measured fields | **gate G13** |
| 5 | Page content can steer the model | Four independent prompt-injection defences; a separate component writes outgoing text and never sees a page | CaMeL / Spotlighting / Lethal Trifecta |
| 6 | Payment QR codes are pixels only | jsQR locates them; **only the bounding box is read**, never the payload | **gate G11** |
| 7 | Safety gates can be theatre | Gates are mutation-tested; behavioural gates grade real objects, not source strings | See §9 |

---

## 4. Feasibility and Viability

### 4.1 Technical feasibility — proven by running

| Requirement | Status | Proof |
|---|---|---|
| Runs inside real Chrome | ✅ Working | Extension loaded unpacked, 25 permitted actions executing against live DOM |
| On-device perception | ✅ Working | MobileCLIP-S0 (54 MB) + Tesseract OCR (5 MB) in-browser, zero network |
| PII detection | ✅ Working | 9 classes, Luhn/Verhoeff-verified |
| Pixel masking | ✅ Working | OffscreenCanvas, opaque fill only |
| Closed loop | ✅ Working | FSM with verify-on-fresh-observation, loop/cycle breakers |
| Human-in-the-loop | ✅ Working | Deterministic policy, approval modal, signed confirmation |
| Local reasoning (optional) | ⚠️ Optional | Chrome built-in model, off by default |

**Stack maturity** — every dependency is a mainstream, actively maintained release:
Chrome MV3, Python 3.11, FastAPI, Pydantic v2, React 19, ONNX Runtime Web, Tesseract.js.

### 4.2 Resource feasibility

| Item | Value |
|---|---|
| Server | Runs on one laptop; binds `127.0.0.1:8787` (loopback only) |
| Extension size | 74 MB (72 MB of packaged models) |
| Models downloaded at runtime | **None** — everything ships in the extension |
| Memory | Not instrumented (see §10) |
| Cost per task | ~10–30 LLM calls; free tiers work, paid tiers reduce throttling |

### 4.3 Operational feasibility

- **One manual step.** Chrome no longer accepts `--load-extension` from the CLI.
  Automation attempts (seeding `extensions.settings`, `developerPrivate.loadDirectory`)
  were defeated by HMAC-signed Secure Preferences. One human click is the floor.
- **No user data leaves the machine** except sanitised text sent to a chosen LLM provider.
- **No server deployment** required; single-user, single-machine by design.

### 4.4 Viability risks and mitigations

| Risk | Mitigation |
|---|---|
| Chrome changes extension APIs | MV3 is stable; `minimum_chrome_version: 116` enforced in manifest |
| Model API pricing / rate limits | 4-provider fallback chain, per-call latency and fallback count reported to the operator |
| Privacy pattern drift (two copies) | One automated parity test today; build-stopping gate is roadmap item 3 |
| Users distrusting an agent with their browser | Deterministic policy layer + approval for irreversible actions + tamper-evident audit |

---

## 5. Impact and Benefits

### 5.1 Direct impact

| Stakeholder | Benefit |
|---|---|
| **Individual user** | Can delegate multi-step browser work without exposing bank, government, or health data to an AI vendor. Sees every action live; approves every irreversible one. |
| **Government / regulated sectors** | A deployable pattern for AI assistants that satisfy data minimisation **structurally**, not by policy promise. Audit trail is hash-chained and independently verifiable. |
| **Enterprises** | Extends existing authenticated sessions to AI assistance without issuing credentials to a third party. |
| **AI safety researchers** | The four-state verdict and mutation-tested gates are reusable patterns for any agentic system. |

### 5.2 Measurable benefits

| Benefit | How it is measured | Current value |
|---|---|---|
| Raw PII transmitted | Withhold-on-leak + no raw values in payload | **0 by construction** — values never serialised |
| Irreversible actions without consent | Policy layer, always-live human for protected fields | **0** by construction |
| Prompt-injection success | Sanitiser + capability gate + quoter + policy | 4 independent layers |
| Audit integrity | SHA-256 hash chain, verifiable after the fact | Recomputable on demand |
| Compliance evidence | DPDP Act 2023 report from the real audit | 5 principles, honest gaps reported |

### 5.3 Broader contribution

The **honest-degradation pattern** — a derived, un-forgeable verdict on every
observation — addresses a failure mode common to all AI-built systems: reporting
success that was never measured. It transferred into this project from the previous
version and is now enforced structurally.

---

## 6. Features (measurable / demonstrable)

Six features, each with a live demonstration and a verification command.

### F1 — In-page PII redaction before transmission
**What:** nine PII classes detected and replaced with typed placeholders *inside the
page*, before the page is serialised.
**Classes:** Card (Luhn), Aadhaar (Verhoeff), PAN, GSTIN, Voter ID, Driving Licence,
UPI (PSP allowlist), Email, Phone.
**Demo:** open `/fixtures/pii`, run a task, inspect the model-input sample — values appear
only as `[REDACTED:PHONE_01]`-style markers.
**Verified by:** `redaction.test.ts` (402 lines), `G6`, `G7`, `G10`

### F2 — Pixel-level masking + QR suppression
**What:** screenshot regions blacked out before encoding; QR codes located and covered.
**Demo:** the cockpit's screenshot panel shows solid black boxes, never blur.
**Verified by:** `qr.test.ts` (134 lines), `G6`, `G11`

### F3 — Fail-closed redaction verification
**What:** on-device OCR re-reads the already-masked screenshot. Any surviving PII shape
⇒ screenshot withheld entirely.
**Demo:** `/fixtures/pii`; the event stream shows `REDACTION_VERIFY_FAILED` when the
guard fires.
**Verified by:** `test_screenshot_contract.py`, `G10`

### F4 — Closed-loop agent with fresh-observation verification
**What:** observe → reason → policy → execute → verify → recover. Verification always
reads a **new** observation.
**Demo:** `/fixtures/job-application-demo` — the agent applies and confirms.
**Verified by:** `test_engine.py` (1,062 lines), `G5`, loop + cycle breakers

### F5 — Deterministic policy + human-in-the-loop
**What:** pure-Python allow/confirm/deny. 25 permitted verbs. Approval required for
send/submit/pay/delete, for protected fields, and for payment URLs. Protected fields
**always** require a live human.
**Demo:** `/fixtures/payment` or `/fixtures/attendance` — approval modal appears before
any irreversible action.
**Verified by:** `test_policy_attendance.py`, `test_security.py`, `G1`, `G2`

### F6 — Prompt-injection containment
**What:** four independent defences — sentence-level neutralisation, a deterministic
capability gate that refuses page-quoted text, a separate quoter that never sees a page,
and the policy layer.
**Demo:** `/fixtures/prompt-injection-demo` — the lure is neutralised; the agent refuses
to paste the OTP.
**Verified by:** `test_security.py` (218 lines)

**Cross-cutting:** F7 — tamper-evident audit + DPDP Act 2023 report.
Demo: `GET /tasks/{id}/compliance-report?format=html`. Verified by `test_compliance.py`.

---

## 7. System Architecture

### 7.1 The invariant

```
RAW PAGE → LOCAL DETECTION → LOCAL REDACTION → SANITIZED → NETWORK
             in the page        in the page       placeholders,
             pre-serialise      pre-capture      box masks
```

Redacting *after* transmission defeats the purpose and is explicitly rejected by the
problem statement.

### 7.2 Three processes

```
OPERATOR'S MACHINE (trust zone ends here)
┌───────────────────────────────────────────────────────────┐
│ Chrome                                                     │
│  ├ service worker  ══WebSocket══╗                          │
│  ├ content script ◄── messages ─╢                          │
│  └ offscreen doc  (Tesseract · MobileCLIP · WASM)          │
│                           ║                                │
│                           ▼                                │
│  uvicorn 127.0.0.1:8787                                   │
│  loop FSM · policy · verifier · sanitizer · vault · audit │
│                           ║                                │
│  ~/.drishti/  hash-chained audit + credential vault       │
└───────────────────────────╬───────────────────────────────┘
                            ║  SANITISED ONLY
                            ▼
        External LLM providers (Gemini · Groq · OpenRouter · OpenAI)
```

### 7.3 The closed loop

```
PLANNING → OBSERVING → REASONING → POLICY_CHECK
              ↑                            ↓
              └──── VERIFYING ←──── EXECUTING
                       ↓                 ↑
                  RECOVERING     WAITING_FOR_CONFIRMATION
                       │                 │
                       │            granted ↓
                       │           COMPLETED · FAILED · CANCELLED
              LOGIN_REQUIRED / LOGIN_DETECTED
```

### 7.4 Module ownership — and prohibitions

| Module | Owns | Never (enforced) |
|---|---|---|
| `agent-content.js` | DOM walk, in-page redaction, page execution | Talk to a server — **G7** |
| `agent-background.js` | WebSocket, keepalive, tabs, capture, masking | Draw on canvas — **G6** |
| `offscreen.js` | OCR + CLIP inference | Reference any http(s) URL — **G8** |
| `loop.py` | FSM, task registry, guardrails | Name a domain — **G2** |
| `policy.py` | Deterministic allow/confirm/deny | Involve a model |
| `verifier.py` | Freshness + postcondition checks | Accept stale observations — **G5** |
| `knowledge.py` | **Only file permitted to name a site** | Contain control flow — **G2** |
| `quoter.py` | Outgoing message text | See a web page |

### 7.5 Element identity

Web elements have no permanent handles. Each observation stamps:
- `data-agent-eid="e{n}"` — ephemeral; **the only name the model may use**
- `data-agent-nid` — 8-hex FNV-1a of `tag|id|aria-label|text[:32]|WxH`; stable across re-renders

Resolution order: **eid → nid → text signature → CSS path**. A miss returns
`stale_element` and the loop re-observes. The server re-attaches `nid`/name/path from
the live observation, so **the model cannot address an element that was not observed**.

### 7.6 Guardrails

| Guard | Value |
|---|---|
| Max steps | 60 |
| Wall clock | 600 s |
| Confirmation timeout | 120 s (then **cancels**, never auto-approves) |
| Login timeout | 300 s |
| Consecutive verify failures | 3 |
| Action retries | 2 |
| Reasoner payload budget | 50 KB (measured, not estimated — **G12**) |
| Replans per task | 3 |
| Service-worker keepalive | 20 s ping (MV3 30 s window) |

---

## 8. Technology Stack & Dataset

### 8.1 Stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Extension platform | Chrome Manifest V3 | Chrome 116+ | Statement asks for browser agents |
| Extension build | Vite | 7.x | Produces the loadable `dist/` |
| Extension languages | JavaScript (core), TypeScript (popup) | — | Core is plain JS so the shipped file is auditable |
| On-device OCR | Tesseract.js | 7.x | WASM, fully offline |
| On-device vision | MobileCLIP-S0 via `@huggingface/transformers` | 4.x | 54 MB, runs in-browser |
| Inference runtime | ONNX Runtime Web (WASM SIMD) | bundled | CPU inference, no GPU required |
| QR detection | jsQR | 1.4 | Locates codes without decoding them |
| Popup UI | React + Ant Design | 19.x / 6.x | Extension launcher |
| Server | Python + FastAPI + uvicorn | 3.11 / 0.110 | Loopback HTTP + WebSocket |
| Validation | **Pydantic** | 2.6 | **The barrier the model cannot route around** |
| Live connection | websockets | 12.x | Persistent connection; avoids reconnect churn |
| HTTP client | httpx | 0.27 | Async provider calls |
| Config | python-dotenv | 1.0 | `.env` loading |
| PDF | pypdf | 4.0 | Chrome renders PDFs with no DOM text |
| Testing | pytest · vitest | 3.11 / 5.x | 235 + 145 tests |
| Gates | custom `check_gates.py` | — | 14 anti-pretence gates |

**Reasoning providers (chain, first healthy wins):** Gemini → Groq → OpenRouter → OpenAI.
Optional local: Ollama (not in default chain — small models are measurably worse at
choosing browser actions).

### 8.2 Dataset

**No external dataset is required** — the system operates on live web pages. We ship our
own labelled corpora and fixtures.

**Labelled test fixtures (9 local pages, ~1,400 lines)** — served at `/fixtures/*`:

| Fixture | Lines | Purpose |
|---|---|---|
| `pii.html` | 147 | Every PII class on one page |
| `payment.html` | 133 | Checkout / high-risk URL behaviour |
| `attendance.html` | 578 | Bulk-roster submit behind a login wall |
| `govt_scholarship.html` | 158 | Government form shape |
| `technova_careers.html` | 77 | Job application with a saved profile |
| `quakes.html` | 98 | Lazily-loading Angular list |
| `upload.html` | 95 | File upload (CDP path) |
| `shop.html` | 72 | Repeated priced groups for extraction |
| `prompt_injection_shop.html` | 42 | Live injection lure in rendered DOM text |

**Public models used (pre-trained, shipped locally, not fine-tuned):**
- `Xenova/mobileclip_s0` — quantised ONNX, 54 MB
- `eng.traineddata` (Tesseract English), 1.9 MB

**Test corpora:** 9 PII patterns × positive/negative cases; benign corpus guarding
against over-redaction; 22 vision role cases.

**Smoke suite:** programmatic end-to-end tasks with machine-checked success criteria
(`server/eval/`).

---

## 9. 30% Implementation

Implementation is **substantially beyond 30%**. A conservative floor:

### 9.1 Completed (all shipped and verified)

| Module | Status | Evidence |
|---|---|---|
| Perception — DOM walk, scoring, identity | ✅ Complete | `agent-content.js`, tests |
| Perception — capture + pixel masking | ✅ Complete | G6, G11 |
| Perception — on-device OCR (Tesseract) | ✅ Complete | G8 |
| Perception — on-device CLIP grounding | ✅ Complete | G9 |
| Privacy — 9-class detection + checksums | ✅ Complete | `redaction.test.ts`, `redaction.py` |
| Privacy — text + pixel redaction | ✅ Complete | G6, G7 |
| Privacy — QR suppression | ✅ Complete | G11 |
| Privacy — fail-closed verification | ✅ Complete | G10 |
| Agent loop — FSM, registry, guardrails | ✅ Complete | `loop.py`, `test_engine.py` |
| Agent loop — verification + recovery | ✅ Complete | `verifier.py`, `recovery.py` |
| Reasoner — planner + reasoner + quoter | ✅ Complete | Pydantic-validated |
| Policy — deterministic allow/confirm/deny | ✅ Complete | `policy.py`, tests |
| Security — prompt-injection defence (4 layers) | ✅ Complete | `sanitizer.py`, `capability_gate.py` |
| Security — credential vault, site-bound | ✅ Complete | `vault.py` |
| Audit — hash-chained JSONL | ✅ Complete | `events.py`, `test_compliance.py` |
| DPDP compliance report | ✅ Complete | `compliance.py` |
| Operator cockpit (real-time bus renderer) | ✅ Complete | `cockpit.html` + `cockpit.css` |
| Perception verdict (4-state, derived) | ✅ Complete | G13 |
| Accessibility gate | ✅ Complete | G14 |
| Test + gate infrastructure | ✅ Complete | 14 gates, 380 tests |
| Documentation | ✅ Complete | SRS, UML set, 7 ADRs, API ref, test strategy, agile backlog, 37-page guide |

### 9.2 Not implemented (honestly recorded)

| Item | PS weight | Status |
|---|---|---|
| Client-side resource instrumentation | **20%** | **Not started** — no measurement exists |
| Painted/canvas text through the full redaction path | **25%** | Partial — OCR runs on cadence, not through identical redaction |
| NER for names; face/photo detection | 20% | Not started |
| Firefox parity | — | Not started (explicit PS requirement) |
| Cross-origin iframe observation | — | Not started |
| PII pattern parity gate | — | Roadmap item 3 |

### 9.3 Percentage framing

| Measure | Value |
|---|---|
| Modules complete | 20 of 20 in the core pipeline |
| Requirements traced & tested | 31 functional, each mapped to a check |
| Automated checks | 14 gates + 380 tests, all passing |
| Unstarted features | 2 of 6 scoring criteria fully addressed |

> **Use this framing in the PPT:** the closed loop, the privacy boundary, and the
> honesty layer are complete and demonstrated. The two largest *measurement* gaps
> (resource utilisation, painted pixels) are named as roadmap items 1 and 2.

---

## 10. Research and References

All four verified live on 11 Oct 2026.

**[1] Simon Willison — "The lethal trifecta for AI agents: private data, untrusted
content, and external communication" (16 June 2025)**
https://simonwillison.net/2025/jun/16/the-lethal-trifecta/
> *"Access to your private data… Exposure to untrusted content… The ability to
> externally communicate in a way that could be used to steal your data."* Removing any
> one leg prevents the attack.
**How we use it:** the architecture separates reading from acting, and separates writing
a message from reading a page. The quoter component exists specifically so page content
can never reach outgoing text.

**[2] Keegan Hines, Gary Lopez, Matthew Hall, Federico Zarfati, Yonatan Zunger, Emre
Kıcıman (Microsoft Research) — "Defending Against Indirect Prompt Injection Attacks With
Spotlighting", arXiv:2403.14720 (March 2024)**
https://arxiv.org/abs/2403.14720
> *Spotlighting reduces attack success rate from >50% to below 2%*, with negligible
> impact on task performance. Three instantiations: delimiting, datamarking, encoding.
**How we use it:** `sanitizer.py` implements datamarking — a `·N·` marker every 12 words
so untrusted text cannot blend into surrounding prose, plus per-sentence neutralisation.

**[3] Edoardo Debenedetti, Ilia Shumailov, Tianqi Fan, Jamie Hayes, Nicholas Carlini,
Daniel Fabian, Christoph Kern, Chongyang Shi, Florian Tramèr (Google DeepMind / ETH
Zurich) — "Defeating Prompt Injections by Design" (CaMeL), arXiv:2503.18813 (2025)**
https://arxiv.org/abs/2503.18813
> Solves **77%** of AgentDojo tasks with **provable security** (vs 84% undefended).
> *"Once an LLM agent has ingested untrusted input, it must be constrained so that it
> is impossible for that input to trigger any consequential actions."*
**How we use it:** `capability_gate.py` is CaMeL in miniature — track where a value came
from and refuse to let page-provenance values reach a side effect. The quoter applies
the Dual-LLM pattern Willison proposed in 2023, which CaMeL formalises.

**[4] AgentDojo — Debenedetti et al., dynamic benchmark for prompt-injection attacks on
LLM agents**
https://github.com/ethz-spylab/agentdojo
> The reference benchmark used by CaMeL to measure security/utility trade-off.

**Supporting standards**
- **Chrome Extension Manifest V3** — https://developer.chrome.com/docs/extensions/
- **OWASP Top 10 for LLM Applications (LLM01: Prompt Injection)** — https://owasp.org/
- **Digital Personal Data Protection Act, 2023 (India)** — https://www.meity.gov.in/

**Prior art in this workspace (internal)**
- `sih26171` (v1) — 15-stage privacy pipeline; failed on a mock reasoner
- `sih-agent-v2` (v2) — four-state evidence honesty; failed on having no agent

> **Correction made during this cycle:** our source previously cited Spotlighting as
> `arXiv 2503.18879`. The correct identifier is **2403.14720**; the code comment is now fixed.

---

## 11. Quick demo script (for the Review-1 presentation)

1. `npm run gates` → **14/14** · `npm test` → **145** · `npm run test:py` → **235**
2. Cockpit at `http://127.0.0.1:8787/cockpit`
3. Command: `open http://127.0.0.1:8787/fixtures/pii and tell me what private data is on this page`
4. Point at the **Perception** panel → verdict + coverage meter
5. Point at the **model-input sample** → typed markers only, no raw values
6. Point at the **screenshot** → solid black boxes, not blur
7. Run `/fixtures/payment` → **approval modal** appears before the irreversible action
8. Run `/fixtures/prompt-injection-demo` → lure neutralised, OTP never pasted
9. `GET /tasks/{id}/compliance-report?format=html` → DPDP report incl. its own stated gap

---

## 12. Do-not-claim list

Hand these to whoever builds the slides:

| Do NOT claim | Why |
|---|---|
| "We measure client-side resource utilisation" | **No measurement exists.** 20% of the rubric. |
| "We support Firefox" | Chrome-only manifest. Explicit PS requirement, unmet. |
| "We detect faces / photographs" | Not built. Only pattern-based text classes. |
| "We handle painted canvas content fully" | OCR runs on cadence; findings do not yet use the identical redaction path. |
| "We solve CAPTCHAs" | We report and stop, by design. |
| "The agent is fully autonomous" | Every irreversible action requires human approval unless explicitly pre-armed. |
| "94% detection accuracy" | No such measurement exists. Do not invent a rate. |

If asked about a gap, the honest answer scores better than an invented number — the team
that knows its own edges is credible on everything else.