# Drishti — Software Requirements Specification

| Field | Value |
|---|---|
| Project | Drishti (SIH 2026, Problem Statement 26171) |
| Organisation | Department of Space / ISRO |
| Version | 3.0 |
| Status | Implemented (see §7 for what is measured vs. declared) |
| Supersedes | v1 `sih26171`, v2 `sih-agent-v2` |

---

## 1. Purpose

Drishti is a closed-loop computer-use agent that drives the operator's **own
Chrome profile**, and performs visual perception **on-device**. It exists to
satisfy one requirement: sensitive data must be detected and redacted locally,
and only sanitised context may ever be transmitted.

## 2. Definitions

| Term | Meaning |
|---|---|
| **Sanitised context** | The observation after in-page redaction: placeholders, box masks, and no raw sensitive value. |
| **Perception** | Everything the agent learns about a page: DOM walk, OCR of a redacted capture, CLIP grounding. |
| **Verdict** | What a perception step *proved*, one of `SANITIZED`, `ALLOW_DECLARED`, `DEGRADED`, `WITHHOLD`. |
| **Outbound** | Any byte leaving the machine: HTTP, WebSocket, or an API call to a model provider. |
| **Closed loop** | Observe → reason → policy → execute → verify-against-a-fresh-observation → repeat. |

## 3. Actors

| Actor | Description |
|---|---|
| **Operator** | The human. Gives commands from the cockpit, approves or denies high-risk actions. |
| **Drishti agent** | The autonomous process. Proposes actions; never executes without policy approval. |
| **Extension** | MV3 content/service worker running inside Chrome. Owns perception, redaction, execution. |
| **Reasoner** | An external LLM (Gemini/Groq/OpenRouter/OpenAI). Sees sanitised context only. |
| **Page** | Untrusted. May attempt prompt injection. Has no authority over the agent. |

## 4. Functional requirements

### 4.1 Perception (local)

| ID | Requirement | Verified by |
|---|---|---|
| **FR-PER-01** | The content script shall walk the live DOM and return interactive elements, each with a stable identity. | G4, `test_engine.py` |
| **FR-PER-02** | Every element shall carry both an ephemeral `eid` (what the model names) and a stable `nid` (FNV-1a of tag/id/label/text/size). | `test_engine.py` |
| **FR-PER-03** | Element resolution shall attempt, in order: `eid` → `nid` → text signature → CSS path, and report `stale_element` on a miss. | `test_engine.py` |
| **FR-PER-04** | The agent shall capture the visible tab and black out every sensitive region **before** encoding. | G6, G10 |
| **FR-PER-05** | On-device OCR shall read only the already-redacted capture. | G8 |
| **FR-PER-06** | On-device CLIP grounding shall be local-only and shall score `eid`s, never emit a click. | G9 |
| **FR-PER-07** | QR codes shall be located by bounding box; decoded payloads shall never be read or forwarded. | G11 |
| **FR-PER-08** | Every observation shall carry a derived `perception_verdict` and a human-readable explanation. | **G13** |

### 4.2 Privacy enforcement

| ID | Requirement | Verified by |
|---|---|---|
| **FR-PRV-01** | PII shall be redacted **in the page**, before serialisation — never after transmission. | G7 |
| **FR-PRV-02** | Field values (`.value`, not text nodes) shall contribute mask boxes. *(Fixed in v3 — see §6.1.)* | `fieldValueMasking.test.ts` |
| **FR-PRV-03** | Password/OTP/CVV/card values shall never leave the page at all; only `[PROTECTED INPUT] len=N`. | `test_engine.py` |
| **FR-PRV-04** | A re-OCR pass that detects a surviving PII shape shall withhold the screenshot entirely. | G10 |
| **FR-PRV-05** | The content script shall have no direct path to the server. | G7 |
| **FR-PRV-06** | A DPDP Act 2023 technical-controls report shall be derivable from the hash-chained audit. | `test_compliance.py` |
| **FR-PRV-07** | Placeholder credentials in `.env` shall read as *unset*, not as configured providers. | `config._clean_key` |

### 4.3 Reasoning

| ID | Requirement | Verified by |
|---|---|---|
| **FR-RSN-01** | The planner shall produce goals and `done_when` evidence, never clicks or selectors. | `test_engine.py` |
| **FR-RSN-02** | The reasoner shall emit exactly one `ActionProposal`, Pydantic-validated. | `schemas.py` |
| **FR-RSN-03** | A malformed proposal shall receive exactly one corrective retry, then fail the step. | `reasoner.py` |
| **FR-RSN-04** | The real UTF-8 byte size of every payload shall be measured against a budget. | G12 |
| **FR-RSN-05** | Provider fallback shall be visible, with `fallbacks_before` reported per call. | `MODEL_CALL_COMPLETED` |

### 4.4 Policy and execution

| ID | Requirement | Verified by |
|---|---|---|
| **FR-POL-01** | Policy shall be deterministic Python, with no model involvement. | `policy.py` |
| **FR-POL-02** | Actions shall be classified `allow` / `confirm` / `deny`. | `test_policy_attendance.py` |
| **FR-POL-03** | Typing into a protected field shall always require a *live* human, never pre-approval. | `test_security.py` |
| **FR-POL-04** | The agent shall close only tabs it opened. | `test_engine.py` |
| **FR-POL-05** | The agent shall reuse an existing safe tab rather than always spawning a new one. *(v3)* | `test_tab_reuse.py` |
| **FR-POL-06** | Composers shall be typed via `execCommand('insertText')` with readback verification. | `test_engine.py` |

### 4.5 Verification and recovery

| ID | Requirement | Verified by |
|---|---|---|
| **FR-VER-01** | Every action shall be verified against a **fresh** observation, not the pre-action one. | G5 |
| **FR-VER-02** | A vacuous prediction shall be discarded rather than counted as success. | `verifier.py` |
| **FR-VER-03** | Recovery handlers shall be deterministic: overlay, stale element, slow load, error page, JS dialog. | `recovery.py` |

### 4.6 Audit

| ID | Requirement | Verified by |
|---|---|---|
| **FR-AUD-01** | Every event shall be written to a SHA-256 hash-chained JSONL audit. | `events.py` |
| **FR-AUD-02** | The chain shall be independently verifiable after the fact. | `GET /tasks/{id}/audit/verify` |

## 5. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| **NFR-01** | Steps per task | ≤ 60 |
| **NFR-02** | Wall clock per task | ≤ 600 s |
| **NFR-03** | Reasoner payload | ≤ 50 KB (measured, not estimated) |
| **NFR-04** | Consecutive verification failures | ≤ 3 before failing honestly |
| **NFR-05** | Service worker keepalive | ping at 20 s (MV3 30 s window) |
| **NFR-06** | Detection: sensitive recall | 100% — a miss is a leak |
| **NFR-07** | Detection: benign precision | ≥ 95% — over-masking destroys usability |
| **NFR-08** | Outbound raw PII leakage | 0% |

## 6. v3 defect corrections

### 6.1 CR-V3-001 — Input values were never masked (Critical)

**Found:** reported from a live Flipkart account page, where a saved phone
number was visible while non-PUI was masked.

**Cause:** the mask-box sweep read only text nodes. An `<input>`'s value lives
in `.value`, so every form field contributed no text, earned no box, and no box
was drawn — while the DOM payload was correctly redacted. The leak reached the
vision reasoner through the screenshot.

**Fix:** fold the raw field value into the mask decision; record the masked
region by kind. 7 regression tests added.

### 6.2 CR-V3-002 — The cockpit could never connect (Critical)

`/ws/cockpit` demanded an `auth.<token>` subprotocol that the page never sent,
so it closed `4401` forever. Fixed: the server mints a session token when
serving the page.

### 6.3 CR-V3-003 — Cockpit and extension never shared state (Critical)

Each token created its own `BrowserBridge`, so a task started from the cockpit
reached an empty bridge and failed with "extension not connected" while the
extension sat connected on another runtime. Fixed: `operator_runtime()` binds an
operator UI to the live agent runtime.

## 7. Traceability summary

| Area | Requirements | Automated checks | Gates |
|---|---|---|---|
| Perception | FR-PER-01…08 | 145 JS + 220 Python tests | G1–G13 |
| Privacy | FR-PRV-01…07 | redaction, compliance, masking suites | G6–G11 |
| Reasoning | FR-RSN-01…05 | engine suite | G12 |
| Policy | FR-POL-01…06 | policy, security, attendance suites | G1, G2 |
| Verification | FR-VER-01…03 | engine suite | G5 |
| Audit | FR-AUD-01…02 | compliance suite | — |

## 8. Known limitations (stated, not hidden)

- One browser, one task at a time — the registry refuses concurrent tasks.
- Single frame; cross-origin iframes are invisible (`all_frames: false`).
- `chrome://`, the Web Store and PDF viewers block extensions entirely.
- The login gate detects a wall; it cannot sign in, by design.
- Verification is behavioural, not semantic — it cannot confirm a recipient was
  the person you meant. That is what the approval modal is for.
- Anti-bot walls stop the agent. It reports them and does not attempt to solve.
- Firefox is not yet supported (Chrome-only manifest).