# Drishti — Agile Delivery Record

Sprints reflect what actually shipped. Each closes with its verification
evidence, not an opinion.

---

## 1. Product backlog

### Epic A — Privacy boundary (the core)
| ID | Story | Points | State |
|---|---|---|---|
| A-1 | In-page PII redaction before serialisation | 8 | ✅ |
| A-2 | Screenshot box-masking before encode | 8 | ✅ |
| A-3 | QR location detection without reading payloads | 3 | ✅ |
| A-4 | On-device re-OCR verification, fail closed | 5 | ✅ |
| A-5 | DPDP compliance report from hash-chained audit | 5 | ✅ |
| A-6 | **Input `.value` contributes a mask box** | 5 | ✅ *(v3 — CR-V3-001)* |
| A-7 | Painted/canvas text through the same redaction path | 8 | ⬜ |

### Epic B — Agent loop
| ID | Story | Points | State |
|---|---|---|---|
| B-1 | Closed loop with fresh-observation verification | 13 | ✅ |
| B-2 | Loop + cycle breakers (repeat / oscillation) | 8 | ✅ |
| B-3 | Recovery handlers | 5 | ✅ |
| B-4 | Login-wall gate that resumes at the same step | 5 | ✅ |
| B-5 | **Reuse a safe existing tab instead of spawning one** | 3 | ✅ *(v3 — CR-V3-005)* |

### Epic C — Trust & safety
| ID | Story | Points | State |
|---|---|---|---|
| C-1 | Deterministic policy layer | 8 | ✅ |
| C-2 | Prompt-injection neutralisation + capability gate | 8 | ✅ |
| C-3 | Quoter: only role allowed to author outgoing text | 5 | ✅ |
| C-4 | Anti-pretence gates G1–G13 | 8 | ✅ |
| C-5 | Mutation-test the gates | 5 | ✅ (G13 behavioural) |

### Epic D — Honesty & evidence
| ID | Story | Points | State |
|---|---|---|---|
| D-1 | **Derived perception verdict, four states** | 8 | ✅ *(v3)* |
| D-2 | Cockpit renders verdict + coverage meter | 5 | ✅ *(v3)* |
| D-3 | Placeholder credentials must read as unset | 2 | ✅ *(v3)* |
| D-4 | On-device resource instrumentation (20% PS weight) | 8 | ⬜ |
| D-5 | Firefox parity | 8 | ⬜ |

### Epic E — Operator surface
| ID | Story | Points | State |
|---|---|---|---|
| E-1 | Cockpit socket auth | 2 | ✅ *(v3 — CR-V3-002)* |
| E-2 | Cockpit and extension share one runtime | 3 | ✅ *(v3 — CR-V3-003)* |
| E-3 | Design system: type, colour, density | 8 | ✅ *(v3)* |
| E-4 | Real SVG iconography, no font-glyph dependency | 3 | ✅ *(v3)* |
| E-5 | Responsive down to 1100px, reduced-motion respected | 3 | ✅ *(v3)* |

---

## 2. Sprint history

### Sprint 0 — Rebrand & inherit (v3.0)
**Goal:** land a working agent, remove the previous author's identity.

| Story | Result |
|---|---|
| Rename NetraShield → Drishti across manifest, WS subprotocol, TS types, CSS | ✅ |
| Remove the hardcoded deployment URL → localhost only | ✅ |
| Strip personal name, email and live college host from prompts and privacy policy | ✅ |
| Delete dead code: 2 legacy content scripts, 2 unused modules, 1 unrouted template | ✅ |
| Fix G1/G2, which shipped **red** upstream (10/12) | ✅ → **12/12** |

**Velocity:** 26 pts · **Verification:** 138 JS, 194 Python, 12/12 gates

---

### Sprint 1 — Correctness (v3.1)
**Goal:** fix what live use exposed. No new surface area.

| Story | Finding | Result |
|---|---|---|
| **CR-V3-001** | Phone number visible on a live account page while non-PUI was masked — input `.value` never earned a mask box, so the leak reached the vision reasoner through the screenshot | ✅ + 7 regression tests |
| **CR-V3-002** | Cockpit stuck on "reconnecting" forever — `/ws/cockpit` demanded an `auth.` subprotocol the page never sent | ✅ |
| **CR-V3-003** | Tasks from the cockpit failed with "extension not connected" — cockpit and extension had separate `BrowserBridge`s | ✅ |
| **CR-V3-004** | `.env.example` placeholders (`gsk_...`) read as real credentials, so the server advertised providers it could not call | ✅ |
| **CR-V3-005** | Agent opened a new tab for every command, hijacking the window | ✅ + 9 tests |

**Velocity:** 25 pts · **Verification:** 145 JS, 220 Python, 13/13 gates

---

### Sprint 2 — Honesty (v3.2)
**Goal:** make degradation visible.

| Story | Result |
|---|---|
| D-1 Derived four-state perception verdict | ✅ |
| D-2 Cockpit verdict banner + coverage meter | ✅ |
| G13 behavioural gate | ✅ |
| Mutation testing of G13 | ✅ — caught that a **grep-based** G13 passed while the verdict was hardcoded to `SANITIZED`; 3 of 5 mutations slipped through, now 0 |

**Velocity:** 21 pts · **Verification:** 13/13 gates

---

### Sprint 3 — Operator surface (v3.3)
**Goal:** an instrument, not a dashboard.

| Story | Result |
|---|---|
| Design system extracted to `cockpit.css` | ✅ |
| Warm graphite palette, colour reserved for meaning | ✅ |
| Inter + JetBrains Mono, tabular numerals on every metric | ✅ |
| 6 stage icons → inline SVG | ✅ |
| Perception coverage meter (DOM % / pixels % / not covered %) | ✅ |
| Inline-style hacks removed | ✅ (3 → 0) |

**Velocity:** 22 pts · **Verification:** 13/13 gates, 145 JS, 220 Python

---

## 3. Definition of Done

A story is **done** only when all of these hold:

1. Implementation shipped, no dead code left behind.
2. Automated test exists that **fails without the change**.
3. `npm run gates`, `npm test`, `npm run test:py` all green.
4. No new unlabelled placeholder, and no measurement reported that was not taken.
5. Documented in the SRS if it adds or changes a requirement.

> Rule 2 is the one that matters. Several gates in this repo were green while
> protecting nothing; that is why G13 grades real objects instead of strings.

---

## 4. Velocity

| Sprint | Committed | Delivered | Carry-over |
|---|---|---|---|
| 0 — Rebrand | 26 | 26 | 0 |
| 1 — Correctness | 25 | 25 | 0 |
| 2 — Honesty | 21 | 21 | 0 |
| 3 — Surface | 22 | 22 | 0 |
| **Total** | **94** | **94** | **0** |

---

## 5. Impediments and how they were removed

| Impediment | Removal |
|---|---|
| "It works but I can't tell if it *worked*" | Four-state derived verdict (D-1) + behavioural G13 |
| Gates that pass while protecting nothing | Mutation testing; behavioural gates |
| A test asserting exact prompt line-wrapping | Assert content, normalise whitespace |
| Gates grepping literal strings that any rename breaks | G13 imports and grades real objects |
| Chromium refuses `--load-extension` from the command line | Ship as an unpacked extension; one human click is unavoidable |

## 6. Next sprint (proposed)

| Story | Points | Why first |
|---|---|---|
| A-7 Painted/canvas text through the redaction path | 8 | Largest remaining privacy gap |
| D-4 On-device resource instrumentation | 8 | 20% of the PS score, currently a claim |
| G14 Machine-check the PII pattern parity pair | 3 | Two copies of the pattern table, joined by one assertion |
| A-5′ Firefox parity spike | 5 | Explicit PS requirement, currently unmet |