# Drishti — Improvement Backlog

Status legend: `[x]` done · `[~]` partial · `[ ]` not started

This file started as a forward-looking plan before the project ran. It is now a
record of what shipped and what remains. Every `[x]` has a check behind it.

---

## 1. Honest-degradation verdict — ✅ shipped

**The gap it closed:** the agent degraded *silently*. If OCR failed, CLIP was
unavailable, or the offscreen document died, a step still looked successful in
the cockpit. A judge could not tell "it worked" from "it was degraded and we did
not notice" — the exact failure that sank v1 and v2.

**Shipped:**
- Four-state verdict derived on `Observation` as a `@property`, so it cannot be
  set to a comfortable answer and cannot drift from what was observed.
  `SANITIZED` / `ALLOW_DECLARED` / `DEGRADED` / `WITHHOLD`, fail-closed.
- `WITHHOLD` dominates on aggregation (`worse()`).
- Emitted on `OBSERVATION_RECEIVED`; rendered in the cockpit with a plain-language
  explanation and the exposure meter.
- **G13** grades all eight perception states using real `Observation` objects.

- [x] Define the verdict enum in `server/schemas.py`
- [x] Derive it from measured fields, never store it
- [x] Emit from every observation
- [x] Render per-step in the cockpit
- [x] Test that a degraded path never reports `SANITIZED`
- [x] Mutation-test the gate — a **grep** version passed while the verdict was
      hardcoded to `SANITIZED`; 3 of 5 mutations slipped through. Behavioural
      version catches all of them.

---

## 2. Harden the gates — ✅ partially shipped

- [x] Mutation-test the gates (G13 and G14 both mutation-tested; results
      published in the test strategy rather than claimed)
- [x] Behavioural gates where a grep would be theatre (G13 grades objects,
      G14 parses the served cockpit with `html.parser`)
- [ ] **Machine-check the PII parity pair.** `server/redaction.py` and
      `public/agent-content.js` still carry two copies of the pattern table,
      joined only by one assertion in `test_engine.py`. Promote it to a gate so
      drift cannot ship. *(next sprint)*
- [ ] Assert gate coverage is complete — fail if `check_gates.py` targets a file
      that no longer exists
- [ ] Fix the 16 pre-existing `eslint` errors (unchanged from upstream)

---

## 3. Client-side resource instrumentation — ⬜ not started

**Why:** PS 26171 weights client-side resource utilisation at **20%**, and the
project currently reports no number for it. It is a claim, not a measurement.

- [ ] WASM heap high-water mark and bytes of model weights actually loaded
- [ ] Per-stage inference latency (OCR, CLIP) with p50/p95
- [ ] Main-thread responsiveness during a step (`requestAnimationFrame` lag)
- [ ] Emit `RESOURCE_SAMPLE` on the bus; render a cockpit panel
- [ ] Persist a real run to `docs/06-evidence/` — no hand-written numbers

---

## 4. Real pixel / vision capture — ⬜ not started

**Why:** visual context accuracy is **25%** of the PS score — the largest single
metric — and today the system mostly *counts* visual surfaces rather than
scanning them. This is the biggest remaining gap.

- [ ] Capture frames on demand rather than every N steps, budgeted per step
- [ ] OCR regions the DOM walk cannot see (canvas, `background-image`, `<img>`
      text, shadow DOM)
- [ ] Route OCR findings through the **same** redaction + verification path, so
      painted PII gets the identical fail-closed guarantee
- [ ] Report per step how much of the page was covered by DOM vs pixel
      perception — and what was **not** covered, stated rather than implied
- [ ] Publish the honest recall ceiling of each detector separately

*Partially addressed:* the exposure meter now shows DOM % / pixels % / not
covered % per observation, so the gap is visible. The capture path is not built.

---

## 5. Firefox parity — ⬜ not started

PS 26171 explicitly asks for Chrome **and** Firefox. The manifest is Chrome-only.

- [ ] `browser_specific_settings.gecko` id
- [ ] Split the service worker so the shared core is environment-neutral
- [ ] `chrome.*` → `browser.*` shim for the ~6 APIs actually used
- [ ] `chrome.sidePanel` has no Firefox equivalent; ship a popup fallback
- [ ] CI job that loads the build in Firefox

---

## 6. Team surface — ⬜ needs the team

- [ ] Replace the operator placeholders in the cockpit header
- [ ] Fill the operator/contact fields in `server/templates/privacy.html`
      (currently points at "the project team listed in the repository README")
- [ ] Add the team name and repo URL to the README header
- [ ] Regenerate `public/icons/*` via `npm run generate:icons`

---

## 7. Defects found and fixed during this cycle

Recorded because each was found by real use, not by inspection.

| ID | Severity | Finding | Fix |
|---|---|---|---|
| CR-V3-001 | **Critical** | Input `.value` never earned a mask box, so a saved phone number reached the vision reasoner through the screenshot while the DOM payload was clean | Fold the field value into the mask decision; record the region by kind. 7 regression tests |
| CR-V3-002 | **Critical** | `/ws/cockpit` demanded an `auth.` subprotocol the page never sent — the cockpit could never connect | Server mints a session token when serving the page |
| CR-V3-003 | **Critical** | Cockpit and extension had separate `BrowserBridge`s, so every cockpit task failed with "extension not connected" | `operator_runtime()` binds the operator UI to the live agent runtime |
| CR-V3-004 | Medium | `.env.example` placeholders read as configured providers | `_clean_key()` treats `...` as unset |
| CR-V3-005 | Medium | The agent opened a new tab for every command, hijacking the window | Reuse a safe existing tab; never the cockpit. 9 tests |
| CR-V3-006 | Medium | `gemini-2.5-flash-lite` in the model ladder returns 404, burning a fallback every task | Removed from `.env` |

---

## 8. Inherited debt (unchanged from upstream)

- `npm run lint` reports 16 errors / 6 warnings, byte-identical to upstream
- `settingsStorage` defaulted to a `/reason` endpoint that does not exist on the
  server; retargeted at `/health`
- `src/shared/types/netrashield.ts` was still on disk while every import already
  pointed at `drishti`; renamed to `drishti.ts`
- Two dead legacy content scripts and two dead Python modules removed, along with
  an unrouted template
- Two prompt tests asserted exact line-wrapping; rewritten to assert content

---

## Definition of "done" for v3

A fresh clone passes all four with no credentials beyond one API key:

```bash
npm install
python -m pip install -r server/requirements.txt
npm run build
npm run gates      # 14/14
npm test           # 145
npm run test:py    # 235
npm run server     # then open http://127.0.0.1:8787/cockpit
```

**Current status: met**, except the last live step, which needs a human to click
"Load unpacked" because Chrome no longer accepts `--load-extension`.