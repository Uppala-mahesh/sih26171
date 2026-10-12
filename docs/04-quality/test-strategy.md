# Drishti — Test Strategy & Quality Plan

## 1. What "tested" means here

This project's real failure mode is **claiming something works that was never
measured**. Every policy below exists to make that failure hard rather than
easy. Where a number is reported anywhere — README, cockpit, compliance report —
it must come from a real run, and an absent measurement must say so rather than
show a zero.

## 2. Layers

| Layer | Tool | Count | Scope |
|---|---|---|---|
| Gates | `scripts/check_gates.py` | 14 | Anti-pretence invariants over shipped source |
| JavaScript | vitest | 145 | Content script, redaction, masking, manifest, storage |
| Python | pytest | 235 | Schemas, policy, verifier, knowledge, loop, config, compliance |
| Smoke | `server/eval/run_smoke.py` | — | End-to-end against the real browser |
| Live | manual | — | Real logged-in sites |

Run everything: `npm run gates && npm test && npm run test:py`

## 3. The gates

Gates are **grep-enforced invariants** except where a grep would be theatre.

| Gate | Enforces | Kind |
|---|---|---|
| G1 | No placeholder vocabulary in shipped code | grep |
| G2 | No site names in the engine; domains confined to `knowledge.py` | grep + auditable `g2-exempt:` marker |
| G3 | The cockpit's only timer is the keepalive ping | grep |
| G4 | Extracted URLs must exist as live `href`s | grep |
| G5 | The verifier rejects stale observations | grep |
| G6 | Canvas only blackens regions, never draws | grep (parse `ctx.*` calls) |
| G7 | The content script has no direct path to the server | grep |
| G8 | OCR reads only the redacted capture, fully offline | grep |
| G9 | CLIP is local-only and scores `eid`s | grep |
| G10 | A caught leak withholds the screenshot | grep |
| G11 | QR location only, never the decoded payload | grep (brace-matched function body) |
| G12 | Payload byte size is measured, not estimated | grep |
| **G13** | **Every observation carries a derived perception verdict** | **behavioural** |
| **G14** | **The cockpit is keyboard- and screen-reader operable** | **behavioural** |

### 3.1 Why G13 is behavioural

The first version of G13 was a string check. Mutation testing showed it was
worthless:

| Mutation | Grep gate | Behavioural gate |
|---|---|---|
| Verdict hardcoded to `SANITIZED` | ❌ passed | ✅ **caught** |
| Bus event hardcoded | ❌ passed | ✅ **caught** |
| Cockpit renders a fake verdict | ❌ passed | ✅ **caught** |
| WITHHOLD leak branch disabled | ✅ caught | ✅ caught |
| Unmaskable page downgraded | ❌ passed | ✅ **caught** |

3 of 5 mutations slipped through a grep. The shipped gate imports
`server.schemas`, constructs real `Observation` objects for all eight
perception states, and fails if any grades wrong, explains nothing, or if
`WITHHOLD` fails to dominate aggregation.

**Rule: any new gate must be able to fail.** Before it ships, break the thing it
protects and confirm it goes red.

## 4. Test data strategy

| Suite | Data | Notes |
|---|---|---|
| Redaction | Real PII shapes: Aadhaar, PAN, GSTIN, card (Luhn), UPI, phone, email | Checksum-verified counts tracked separately from raw matches |
| Precision | Benign corpus (dates, prices, order ids, nav chrome) | Guards against over-masking, which destroys usability |
| Policy | Roster, payment, checkout, credential shapes | 1280-case decision matrix |
| Fixtures | 9 local pages: pii, payment, shop, upload, quakes, scholarship, attendance, job-apply, injection | Served at `/fixtures/*`, never impersonating a real employer |
| Vision | Role/box corpora | 22 role cases |

## 5. Coverage priorities

Risk-ordered, highest first:

1. **Privacy leak** — any raw PII reaching the network. Covered by FR-PRV-01…07, gates G6–G11.
2. **Unauthorised action** — an action executing without policy approval. Covered by FR-POL-01…06.
3. **False completion** — claiming success without verification. Covered by FR-VER-01/02, G5.
4. **Degraded-but-silent** — a step looking clean while a capability failed. Covered by FR-PER-08, G13.
5. **Injection** — page text steering the agent. Covered by C-2/C-3 suites.

Deliberately **not** prioritised: UI pixel coverage. The cockpit is a pure
renderer of the event bus; its correctness is verified by G3 and by the fact
that it renders only events that arrived.

## 6. Manual verification before any demo

1. `npm run gates` → 13/13
2. `npm test` → 145
3. `npm run test:py` → 235
4. `npm run build` → clean
5. `npm run server`, load `dist/` unpacked
6. Run the job-application fixture; confirm **Submit Application** still pauses for a human
7. Open the privacy proof panel; confirm name/email/phone appear only as typed markers in the exact model-input sample
8. Open `/privacy` and confirm the DPDP report renders from the real audit
9. Reload the extension mid-task; confirm the cockpit reports the disconnect rather than inventing progress

## 7. Known gaps in coverage

| Gap | Why it exists | Plan |
|---|---|---|
| Cross-origin iframes | Content script runs `all_frames: false` | EPIC A-7 |
| Firefox | Chrome-only manifest | EPIC D-5 |
| Canvas/painted text | No in-browser frame capture path | EPIC A-7 |
| Client-side resource budget | Not instrumented | EPIC D-4 |
| Long real-site soak | Requires sustained live sessions | Manual |

Each is recorded as an unstarted backlog item rather than omitted.
### 3.2 G14 — mutation-tested

Same discipline as G13. Five deliberate regressions, five reds:

| Mutation | Result |
|---|---|
| Event stream loses `role="log"` | 13/14 — **caught** |
| Assertive live region removed | 13/14 — **caught** |
| Dialog stops being `aria-modal` | 13/14 — **caught** |
| Dialog loses its accessible name | 13/14 — **caught** |
| `prefers-reduced-motion` removed from CSS | 13/14 — **caught** |

G14 parses the served cockpit with `html.parser` rather than grepping, so it
catches a dialog that is present but unnamed, or a live region that exists on
the wrong element.