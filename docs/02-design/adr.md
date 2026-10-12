# Drishti — Architecture Decision Records

Each ADR records a decision that was **not** obvious, with what was rejected and
why. Decisions that merely followed from the problem statement are not here.

---

## ADR-001 — Redaction happens in the page, not on the server

**Status:** Accepted · **Date:** inherited, re-affirmed in v3

**Context.** PS 26171 requires that only sanitised context reaches a cloud model.

**Options.**
1. Capture raw, redact server-side before the model call.
2. Redact in the page, before serialisation.

**Decision.** Option 2.

**Reasoning.** Option 1 still *transmits* the raw page to our own server. That is
not the same guarantee, and it is the architecture the problem statement calls
out as violating the purpose. Option 2 means a raw sensitive value is never
serialised, never captured and never sent — so there is nothing to leak later.

**Consequences.** The content script cannot talk to the server (gate G7). All
PII logic exists twice — once in JS for the page, once in Python for the
screenshot fallback — and the two pattern tables must stay in step. That
divergence risk is tracked as backlog item G14 (machine-checked parity).

---

## ADR-002 — An extension, not Playwright

**Status:** Accepted

**Context.** We need to drive a browser.

**Decision.** A Chrome MV3 extension inside the operator's own profile.

**Reasoning.** Playwright spawns a *fresh* browser, which discards every logged-in
session. For "read the request in my inbox" or "apply for that job", those
sessions are the entire capability, not a detail. A driver that cannot reach a
logged-in site has not solved the problem, and a judge can fairly say it is just
a script driving a toy browser.

**Consequences.** One unavoidable human step: Chrome refuses `--load-extension`
from the command line, so "Load unpacked" requires a click. CI cannot exercise
the live loop headlessly, so the fixture-based Playwright-free smoke suite exists
alongside it. Chrome-only for now; Firefox is backlog epic D-5.

---

## ADR-003 — Site knowledge is confined to one module

**Status:** Accepted

**Context.** A generic agent should not need per-site scripts, but hints
dramatically improve reliability.

**Decision.** `server/knowledge.py` is the only file permitted to name a
domain, and its content is pasted into the reasoner's prompt as plain English.

**Reasoning.** Advice that a model *reads* cannot become control flow. Advice
that the *loop* branches on can: delete a hint pack and the agent stops working
on that site entirely. The distinction is the whole point.

**Enforcement.** Gate G2 greps the engine files for site names. Because one
legitimate case existed (brand names in the redaction vocabulary, so a product
name is not redacted as a person), G2 supports an auditable `g2-exempt:
<reason>` marker, and **every exemption is printed in the gate report** so it
stays visible rather than silently disappearing.

---

## ADR-004 — The perception verdict is derived, never stored

**Status:** Accepted (v3) · **Supersedes:** silent degradation

**Context.** A perception step can fail in ways that look like success: a
capture nothing could read, a page closed to content scripts, a re-OCR pass that
found a surviving PII shape. This project already failed twice by reporting
numbers that were never measured.

**Decision.** Every observation carries a verdict computed from measured fields,
as a Python `@property`, never as a stored field.

**Reasoning.** A property cannot be set to a comfortable answer, and it cannot
drift from what was actually observed, because it is recomputed on every read
from the same evidence the verdict is about.

**The lesson that shaped the gate.** The first implementation of gate G13 was a
string check, and mutation testing showed 3 of 5 mutations sailed through it
while the verdict was hardcoded to `SANITIZED`. The shipped gate imports
`server.schemas`, builds real `Observation` objects for all eight perception
states, and fails if any grades wrong. **A gate that cannot fail is not a gate.**

---

## ADR-005 — An operator UI joins the live agent runtime

**Status:** Accepted (v3)

**Context.** Each session token creates its own `EventBus`, `BrowserBridge` and
`Registry`. The extension holds a token in `chrome.storage`; a cockpit page
cannot read that storage, so it can never present it.

**The bug this fixed.** Giving the cockpit its own runtime looks correct — the
socket opens, the bus flows, everything looks fine — but that runtime holds a
*different* bridge, so every task it starts fails with "the browser extension is
not connected" while the extension sits right there, connected, on another
runtime.

**Decision.** `RuntimeManager.operator_runtime()` binds an operator UI to the
most recently connected agent runtime.

**Reasoning.** This is a loopback-bound, single-operator tool driving one Chrome
profile. Isolating the operator's own cockpit from their own extension bought
nothing and broke the product.

**Limitation, stated rather than hidden.** With several extensions connected to
one server, "most recently connected" is a heuristic. Acceptable at this scope;
it would need a real pairing handshake before multi-tenant hosting.

---

## ADR-006 — Placeholder credentials must read as unset

**Status:** Accepted (v3)

**Context.** `.env.example` ships `gsk_...` and `AIza... or AQ....`. Those are
non-empty strings.

**Decision.** `config._clean_key()` treats a value containing `...` as absent.

**Reasoning.** A naive read treats documentation placeholders as configured
providers. The chain then advertises a model it cannot call, and every step dies
on an authentication error instead of the cockpit honestly reporting that no
provider is configured.

**A wrong claim, corrected.** `.env.example` asserted that an `AQ.`-prefixed
Google credential answers 401 on every call. **That is false** — the project's
own key works. Placeholder detection keys on the ellipsis, never on the prefix,
and a regression test pins exactly that.

---

## ADR-007 — Behavioral gates where a grep would be theatre

**Status:** Accepted (v3)

**Context.** `scripts/check_gates.py` is mostly grep over literal source
strings. Renaming a variable can make a gate stop matching what it was written
to match — it goes green while protecting nothing.

**Decision.** Any gate whose failure would be silent must grade real behaviour.
G13 constructs real `Observation` objects; G14 parses the served cockpit with
`html.parser` and asserts the live regions and dialog semantics exist.

**Standard.** Before a gate ships, deliberately break the thing it protects and
confirm it goes red. This is recorded in the Definition of Done, and the
mutation results are published in the test strategy rather than claimed in the
abstract.