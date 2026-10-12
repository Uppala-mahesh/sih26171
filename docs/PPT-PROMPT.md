# Prompt — generate an accurate Drishti / SIH26171 presentation

> **How to use:** paste everything below into a capable AI (Claude, GPT, Gemini)
> and **also attach your TBP deck**. Add one line at the top:
> *"Use my attached TBP deck for theme terminology and branding. Use the brief
> below for all technical facts. Never invent a number or a capability."*

---

## ROLE

You are a senior technical presenter and slide designer preparing a mentor
review of a working software project. You will produce a slide deck.

**Accuracy is the single most important requirement.** Every claim must come from
the brief below. If a number is not in the brief, do not state it — say it is not
yet measured. A slide that overstates the project is worse than a slide that
understates it, because the mentor can open the code.

---

## 1. PROJECT IDENTITY

- **Name:** Drishti ( Sanskrit *drishti* — "sight")
- **Track:** Smart India Hackathon 2026
- **Problem statement:** SIH26171
- **Organisation:** Department of Space / ISRO
- **Category:** On-device Visual Perception for Light-weight Browser Agents
- **Repository:** `sih26171-v3`

One-line description:
> A closed-loop computer-use agent that drives the operator's own Chrome profile,
> and performs visual perception and privacy redaction **on-device**, so that only
> sanitised context ever reaches a cloud model.

---

## 2. THE PROBLEM (use this framing)

Modern agentic AI pipelines send **raw screenshots, DOM and page content** to a
remote model. That is unacceptable for: government portals, banking apps,
Aadhaar/PAN services, healthcare portals, authentication pages, enterprise apps,
or any page containing personal data.

Existing agentic browser tools make this worse, not better — they usually drive a
*fresh* Playwright/Puppeteer browser, which discards the operator's logged-in
sessions and therefore cannot do real work.

**Drishti's position:** the browser is a **zero-trust privacy boundary**. Visual
perception and redaction happen locally; only sanitised context is transmitted.

The required invariant:

```
RAW PAGE ──▶ LOCAL DETECTION ──▶ LOCAL REDACTION ──▶ SANITIZED ──▶ NETWORK
              (in the page)       (in the page)       placeholders,
              before serialising  before capture      box masks
```

**Redacting *after* transmission defeats the purpose** and is the architecture
the problem statement explicitly rejects. State this clearly — it is the core
argument of the project.

---

## 3. EVALUATION CRITERIA THE PROJECT IS BUILT AGAINST

PS 26171 is scored on five weighted criteria. Present these — they are the
rubric your mentor will judge against:

| # | Criterion | Weight | Current status (be precise) |
|---|---|---|---|
| 1 | Accuracy of visual context from screen | **25%** | Partial — DOM walk is complete; painted-pixel scanning is not built |
| 2 | Recall and precision of sensitive-data detection | **20%** | Pattern-based detection implemented and tested; NER/face detection not built |
| 3 | Precision of redaction (redact only the sensitive region) | **20%** | Implemented — in-page box masking, checksum-verified counts |
| 4 | Client-side resource utilisation | **20%** | **Not yet instrumented** — say so plainly |
| 5 | End-to-end latency | **15%** | Measured per call (model latency, walk time, OCR/CLIP ms) |

**Do not claim criterion 4.** It is currently a design goal with no measurement.

---

## 4. SYSTEM ARCHITECTURE

Two processes, both on the operator's machine.

### 4.1 Browser side (Chrome MV3 extension)

| Component | Responsibility |
|---|---|
| **Content script** | DOM walk, in-page PII redaction, page execution (real clicks, real typing). Has **no** network access. |
| **Service worker** | WebSocket to the server, 20-second keepalive, tab management, screenshot capture and masking. |
| **Offscreen document** | On-device inference: **Tesseract.js OCR** and **MobileCLIP** (ONNX Runtime / WebAssembly). **72 MB** of models and runtimes packaged inside the extension — nothing is downloaded at runtime. |

### 4.2 Server side (Python 3.11 + FastAPI, binds `127.0.0.1:8787`)

| Module | Responsibility |
|---|---|
| `loop.py` | The FSM, the task registry, all guardrails |
| `planner.py` / `reasoner.py` | The two model roles (plan goals; propose one action) |
| `policy.py` | Deterministic allow / confirm / deny — pure Python, no model |
| `verifier.py` | Checks the action worked against a **fresh** observation |
| `recovery.py` | Overlay dismissal, stale-element re-grounding, slow loads, JS dialogs |
| `sanitizer.py` | Prompt-injection neutralisation |
| `capability_gate.py` | Refuses actions that quote the page verbatim |
| `quoter.py` | The only role allowed to author outgoing text — and it never sees the page |
| `vault.py` | Credential store, values never returned or logged, site-bound |
| `events.py` | Event bus + SHA-256 hash-chained JSONL audit |
| `compliance.py` | DPDP Act 2023 technical-controls report from the real audit |
| `knowledge.py` | **The only file permitted to name a website** — advisory hints only |

### 4.3 External

Cloud LLM providers (Gemini, Groq, OpenRouter, OpenAI). They receive **sanitised
context only**. Provider fallback is logged and visible per call.

---

## 5. THE AGENT LOOP

```
PLANNING → OBSERVING → REASONING → POLICY_CHECK
              ↑                            ↓
              └──── VERIFYING ←──── EXECUTING
                       ↓                 ↑
                  RECOVERING         WAITING_FOR_CONFIRMATION
                                         ↓
                              COMPLETED / FAILED / CANCELLED
```

Explain each stage in one line. Key properties to emphasise:

- The reasoner proposes **one** action per step, validated by a Pydantic schema —
  the model cannot invent a verb.
- The policy layer is **deterministic Python**. No model is involved in deciding
  whether an action is allowed.
- Verification always uses a **fresh observation**, never the one the action was
  planned against. A verification that reads its own pre-action state is
  meaningless.
- Loop and cycle breakers detect repeated and oscillating actions.

---

## 6. PRIVACY MECHANISMS (the heart of the pitch)

### 6.1 Detection — nine PII classes
Card · Aadhaar · PAN · GSTIN · Voter ID · Driving Licence · UPI · Email · Phone

- Card numbers are **Luhn**-validated; Aadhaar numbers are **Verhoeff**-validated.
  Checksum-verified counts are reported separately from raw matches — a precision
  signal, not a safety gate.
- Password / OTP / CVV / card / UPI-PIN values **never leave the page at all** —
  the server receives only `[PROTECTED INPUT] len=N`.

### 6.2 Redaction — two channels
1. **Text**: values become typed placeholders, e.g. `[REDACTED:PHONE_01]`.
2. **Pixels**: every sensitive region is blacked out on the screenshot
   **before** the image is encoded.

### 6.3 Fail-closed verification (the strongest single idea)
After masking, the on-device OCR engine re-reads the **already-redacted** image.
If it finds any surviving PII shape, the screenshot is **withheld entirely** — it
is never sent "mostly redacted". This is enforced by an automated gate.

### 6.4 QR codes
Payment and UPI QR codes exist only as pixels — no DOM text pattern can catch
them. The system locates QR bounding boxes and blackens them. **The decoded
payload is never read or forwarded** — enforced by a gate that checks the QR
function body never touches the decoded field.

### 6.5 Prompt-injection defence
The page is treated as **untrusted and actively hostile**. Four independent layers:
sentence-level neutralisation of injection patterns; a capability gate that
refuses to type or paste text quoting the page; a quoter that authors outgoing
text without ever seeing the page; and a policy layer that always requires a
human for destructive actions.

---

## 7. ANTI-HALLUCINATION ENGINEERING (this is the differentiator)

This project's real lesson is that **AI-built systems fail by claiming things
work that were never measured.** Drishti treats that as a design constraint.

### 7.1 The perception verdict
Every observation carries a verdict describing what that step **proved**, not
what it attempted. It is a derived property computed from measured fields, so it
cannot be set to a comfortable answer.

| Verdict | Meaning |
|---|---|
| `SANITIZED` | Everything attempted succeeded; nothing left uncertain |
| `ALLOW_DECLARED` | Text path clean, but the visual path was incomplete or uncovered |
| `DEGRADED` | A capability was unavailable; the step continued anyway |
| `WITHHOLD` | A guarantee could not be verified — **fail closed**, nothing is claimed |

`WITHHOLD` dominates when steps are aggregated.

### 7.2 Anti-pretence gates
**14 automated gates** (currently 14/14 passing) enforce invariants that must not
regress — for example:
- Canvas is used **only** to black out regions, never to draw
- OCR reads **only** the already-redacted screenshot, fully offline
- CLIP grounding is local-only and scores element IDs, never invents a click
- The content script has **no** path to the server
- No website names in the engine — site knowledge is confined to one file
- A caught redaction leak withholds the screenshot
- Every observation carries a derived verdict
- The cockpit is keyboard- and screen-reader operable

### 7.3 Gates must be able to fail
Several gates are **behavioural, not grep-based**, because the first grep-based
version of the verdict gate was proven worthless: under mutation testing, 3 of 5
deliberate sabotages passed silently — including hard-coding the verdict to
always return "sanitized". The shipped gate constructs real observation objects
and grades all eight perception states.

State this openly. It is an honest and unusual engineering position.

---

## 8. VERIFIED NUMBERS (use exactly these)

| Measure | Value |
|---|---|
| Automated gates | **14 / 14 passing** |
| JavaScript tests | **145 passing** |
| Python tests | **235 passing** |
| Production build | clean |
| Distinct event types emitted | 31 |
| On-device model weights packaged | **72 MB** — MobileCLIP-S0 54 MB, ONNX runtime 13 MB, Tesseract 5 MB |
| Built extension size | **74 MB** |
| Service-worker keepalive | 20 s (MV3 30 s window) |
| Max steps per task | 60 |
| Wall-clock budget per task | 600 s |
| Reasoner payload budget | 50 KB (measured, not estimated) |

These numbers are reproducible: `npm run gates`, `npm test`, `npm run test:py`,
`npm run build`. Say so — reproducibility is part of the claim.

---

## 9. DEFECTS FOUND AND FIXED (good slide — shows real testing)

These were found by real use, not inspection:

| Severity | Defect | Fix |
|---|---|---|
| Critical | A saved phone number was **visible on a live account page while non-PII was masked**. Cause: form-field values live in `.value`, not in the DOM text, so they never earned a mask box — the DOM payload was clean but the screenshot leaked. | Field values now participate in mask-box decisions. 7 regression tests added. |
| Critical | The operator UI could never connect — the socket demanded an auth subprotocol the page never sent. | Server mints a session token when serving the page. |
| Critical | UI and extension held separate browser connections, so every task failed with "extension not connected". | Both now bind to one live session. |
| Medium | Placeholder keys in the sample config were read as configured providers. | Placeholders now read as unset. |
| Medium | The agent opened a **new tab for every command**, hijacking the operator's window. | It now reuses a safe existing tab. |
| Medium | One configured model returned HTTP 404, burning a failed fallback on every task. | Removed from the ladder. |

---

## 10. LIMITATIONS — STATE THESE, DO NOT HIDE

A mentor values a team that knows its own system's edges:

1. **Client-side resource utilisation is not instrumented** (20% of the score).
2. **Painted-pixel content is counted, not scanned.** Text inside canvas, images
   and CSS backgrounds is not yet OCR'd through the full redaction path (25% of
   the score).
3. **Chrome only.** PS 26171 asks for Chrome *and* Firefox; the Firefox manifest
   is not written.
4. **Cross-origin iframes are invisible** to the content script.
5. **The agent cannot solve CAPTCHAs** or bypass anti-bot walls — by design.
6. **One task at a time.**
7. **The login gate detects a login wall; it cannot sign in** — by design.

---

## 11. SLIDE STRUCTURE (14–16 slides)

1. **Title** — name, PS number, organisation, team
2. **The problem** — raw page content going to the cloud
3. **Why existing agents fail here** — fresh browser, no sessions; no privacy boundary
4. **The invariant** — the RAW → SANITIZED pipeline diagram (this is the thesis)
5. **System architecture** — the three-part diagram (browser / server / cloud)
6. **The agent loop** — FSM with the verification arrow emphasized
7. **Perception on-device** — MobileCLIP + Tesseract in the extension
8. **Privacy mechanisms** — the nine classes, two redaction channels, fail-closed
9. **What makes it trustworthy** — deterministic policy, human-in-the-loop, hash-chained audit, DPDP report
10. **Anti-hallucination engineering** — perception verdict + 14 gates + mutation testing
11. **Measured results** — the verified numbers table
12. **Defects found and fixed** — the table in §9
13. **Limitations** — §10, stated plainly
14. **Roadmap** — instrument resources; painted-pixel scanning; Firefox parity; NER and face detection
15. **Closing** — what is proven today vs. what is next
16. *(Optional)* **Appendix** — architecture detail, UML, API surface

---

## 12. DESIGN DIRECTION

- **Dark, instrument-like** — this is a measuring device, not a consumer app.
  Warm graphite surfaces, hairline dividers, tight 8px grid, small radii.
- **Typography:** Inter for UI; **JetBrains Mono for every number, timestamp, URL
  and model name**, so data is visually distinct from prose.
- **Colour carries meaning only** — mint = verified, amber = waiting on a human,
  red = withheld/denied, blue = the agent acting now. Never decorative.
- **One signature element:** a **perception coverage meter** showing what fraction
  of a page was covered by DOM text vs pixels vs *not covered at all*. This is the
  25%-weighted metric made visible.
- Diagrams: use Mermaid or clean vector boxes. Keep one idea per slide.
- Avoid: stock-photo heroes, generic gradient blobs, dense paragraphs, and any
  claim not supported by §8 or §10.

---

## 13. HARD RULES

1. **Never invent a metric.** If a number is not in §8, either omit it or label it
   "not yet measured".
2. **Never claim criterion 4** (client-side resource utilisation) is achieved.
3. **Never claim Firefox support.**
4. **Never claim CAPTCHA solving or anti-bot bypass.**
5. **Never say "face detection" or "personal photograph redaction" works** — it is
   built for text-pattern classes, not biometric detection.
6. Do not describe the product as autonomous-without-supervision: every
   irreversible action requires a human decision unless explicitly pre-armed.
7. Keep the tone of §10 — confident about what works, precise about what does not.

---

## 14. WHAT I NEED BACK

1. The complete slide deck, slide by slide, with **speaker notes**.
2. A one-paragraph executive summary for the mentor's email.
3. A list of any claim in this brief you think is unclear, so I can correct it
   rather than you guessing.