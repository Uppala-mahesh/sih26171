# Drishti — System Architecture

## 1. The one invariant everything else serves

```
RAW PAGE ──▶ LOCAL DETECTION ──▶ LOCAL REDACTION ──▶ SANITIZED ──▶ NETWORK
              in the page,        in the page,        placeholders,
              before serialise    before capture      box masks
```

Redaction happening *after* transmission would defeat the entire purpose of
PS 26171. So the trust boundary is drawn at the **page**, not at the server.

Two consequences follow, and both are enforced mechanically rather than by
convention:

1. **The content script has no path to the server** (gate G7 — it contains no
   `WebSocket` and no server address). The only egress is the service worker.
2. **The screenshot is masked before it is encoded** (G6 — canvas is used only
   to `drawImage`/`fillRect`/`getImageData`, never to draw).

## 2. Why an extension and not Playwright

Playwright or Puppeteer spawns a *fresh* browser. That discards the logged-in
sessions in the operator's own profile — which, for a chat or mail task, is the
entire capability rather than a detail. It also adds a relay hop on every call
and is more fingerprintable.

Running inside the operator's own Chrome preserves those sessions, looks like an
ordinary profile, and keeps every action visible on screen. `chrome.debugger`
(CDP) is escalated for exactly two things: capturing screenshots and dismissing
native JavaScript dialogs.

## 3. Process topology

```
┌─ operator's machine ───────────────────────────────────────┐
│                                                            │
│  Chrome                                                  │
│   ├── service worker ─── WebSocket ──┐                     │
│   ├── content script  ◄── messages ─┤                     │
│   └── offscreen doc                 │  Tesseract, MobileCLIP│
│                                     │  (WASM, packaged)    │
│                                     ▼                     │
│  uvicorn 127.0.0.1:8787  ◄────────────────────────────┐   │
│    FastAPI · loop FSM · policy · verifier            │   │
│    redaction · vault · bus · hash-chained audit     │   │
│                                        │            │   │
│  ~/.drishti/  audit JSONL + credentials              │   │
│                                        │            │   │
└────────────────────────────────────────┼────────────┼───┘
                                         │            │
                          SANITISED ONLY  ▼            │
                              external LLM providers ◄─┘
```

## 4. Module responsibilities

| Module | Owns | Must never |
|---|---|---|
| `public/agent-content.js` | DOM walk, in-page redaction, page execution | Talk to a server (G7) |
| `public/agent-background.js` | WebSocket, keepalive, tabs, capture, masking | Draw on a canvas (G6) |
| `public/offscreen.js` | OCR + CLIP inference | Reference any http(s) URL (G8) |
| `server/loop.py` | The FSM, the task registry, guards | Name a domain (G2) |
| `server/policy.py` | Deterministic allow/confirm/deny | Involve a model |
| `server/verifier.py` | Freshness + postcondition checks | Accept a stale observation (G5) |
| `server/knowledge.py` | **The only file permitted to name a site** | Contain control flow |
| `server/sanitizer.py` | Prompt-injection neutralisation | Be bypassed by page text |
| `server/compliance.py` | DPDP report from the audit | Assert anything unmeasured |

## 5. The element-identity problem

DOM elements do not have stable handles. Drishti stamps two identifiers on every
interactive element during each walk:

- `data-agent-eid="e{n}"` — **ephemeral**, regenerated per walk. This is the
  only identifier the model ever names.
- `data-agent-nid` — an 8-hex FNV-1a hash of `tag | id | aria-label |
  text-prefix32 | WxH`. **Stable across re-renders.**

The server re-attaches `nid`, accessible name and CSS path from the live
observation, so the model can never address an element the observation did not
contain. Resolution order is **eid → nid → text signature → CSS path**; a miss
is reported as `stale_element` and the loop re-observes and re-reasons.

## 6. Trust boundaries and prompt injection

The page is untrusted and can put text on screen that looks like an
instruction. Four independent defences:

| Defence | Where | What it does |
|---|---|---|
| `sanitizer.py` | server, before the prompt | Neutralises injection sentences per-sentence to `[NEUTRALIZED:KIND]`; inserts `·N·` markers so injection can't mimic prose |
| `capability_gate.py` | server, before execution | Refuses to type/paste text carrying sanitiser markers, unvouched links, or verbatim page runs |
| `quoter.py` | server | The **only** role allowed to author outgoing text — and it never sees the page |
| `policy.py` | server | Destructive actions require a human, always |

## 7. Why the service worker pings at 20 s

Chrome keeps an MV3 service worker alive while a WebSocket is open **only if
messages are exchanged inside every 30-second window**. `KEEPALIVE_MS = 20000`
keeps it inside that window. Reconnects use a 1.5–3 s jittered backoff and
**reuse the stored `agentSessionId`**, so the server treats a reconnect as the
same session and an in-flight task resumes rather than dying.

## 8. Session isolation

Each extension installation holds a high-entropy token; only its SHA-256 digest
is retained server-side, in memory. Each token maps to a `SessionRuntime` with
its own `EventBus`, `BrowserBridge` and `Registry`.

**Operator-UI binding (v3 fix).** A browser page cannot read the extension's
`chrome.storage`, so it can never present the extension's bearer token. Giving
the cockpit its own runtime looks correct — the socket opens, the bus flows —
but that runtime holds a *different* bridge, so every task it starts fails with
"the browser extension is not connected" while the extension sits connected on
another runtime. `RuntimeManager.operator_runtime()` therefore binds an operator
UI to the live agent runtime. This is sound for a loopback-bound,
single-operator tool driving one Chrome profile; with several extensions
connected, the most recently connected one is the operator's.

## 9. Degradation is stated, never silent

A perception step can fail in ways that still look like success from outside: a
capture that nothing could read, a page closed to content scripts so nothing was
masked, a re-OCR pass that found a surviving PII shape. Every observation
therefore carries a **derived verdict** — computed from measured fields, never
stored, never settable:

| Verdict | Meaning |
|---|---|
| `SANITIZED` | Everything attempted succeeded; nothing left uncertain |
| `ALLOW_DECLARED` | Text path clean; visual path incomplete or uncovered |
| `DEGRADED` | A capability was unavailable; the step continued anyway |
| `WITHHOLD` | A guarantee could not be verified. **Fail closed.** |

`WITHHOLD` dominates on aggregation. Enforced behaviourally by **G13**, which
grades real `Observation` objects rather than grepping for strings — a grep
version passed while the verdict was hardcoded to `SANITIZED`.

## 10. Test and gate strategy

| Layer | Count | Command |
|---|---|---|
| Gates (anti-pretence, grep + behavioural) | 13 | `npm run gates` |
| JavaScript (vitest) | 145 | `npm test` |
| Python (pytest) | 220 | `npm run test:py` |
| End-to-end smoke | — | `npm run smoke` |

Gates exist because the project's real failure mode is claiming something works
that was never measured. Several (`G13`, and the loop/cycle breakers) are
**behavioural** on purpose — see §9.