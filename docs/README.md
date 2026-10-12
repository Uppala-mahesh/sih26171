# Drishti — Documentation Index

**SIH 2026 · Problem Statement 26171 · Department of Space / ISRO**

Drishti is a closed-loop computer-use agent that drives your own Chrome profile
and performs visual perception **on-device**, before anything reaches a cloud
reasoner.

---

## Read in this order

| # | Document | What it answers |
|---|---|---|
| 1 | [Software Requirements Specification](01-requirements/SRS.md) | What the system must do, and which check proves each requirement |
| 2 | [System Architecture](02-design/architecture.md) | How it is built, and where the trust boundary sits |
| 3 | [UML Diagram Set](05-uml/diagrams.md) | Use case, class, sequence, activity, component, state, deployment |
| 4 | [Backlog, Sprints & DoD](03-agile/backlog.md) | What shipped, in what order, and what is still open |
| 5 | [Test Strategy](04-quality/test-strategy.md) | What "tested" means here, and the known gaps |
| 6 | [Verification Evidence](06-evidence/verification.json) | Machine-produced numbers from a real run |

Improvements not yet started: [../V3-IMPROVEMENTS.md](../V3-IMPROVEMENTS.md)

---

## The one invariant

```
RAW PAGE ──▶ LOCAL DETECTION ──▶ LOCAL REDACTION ──▶ SANITIZED ──▶ NETWORK
```

The trust boundary is the **page**, not the server. A raw sensitive value is
never serialised, never captured, and never sent.

## Running it

```bash
npm install
python -m pip install -r server/requirements.txt
npm run build
npm run server          # 127.0.0.1:8787
```

Then load `dist/` as an unpacked extension (`chrome://extensions` →
Developer mode → Load unpacked) and open the cockpit at
<http://127.0.0.1:8787/cockpit>.

Put a model key in `.env` (`GEMINI_API_KEY`, `GROQ_API_KEY` or
`OPENROUTER_API_KEYS`). Placeholders such as `gsk_...` deliberately read as
*unset*, so the server never advertises a provider it cannot call.

## Verification

```bash
npm run gates      # 13/13 anti-pretence gates
npm test           # 145 JavaScript tests
npm run test:py    # 235 Python tests
npm run build      # clean
```

## Ground rules this project holds itself to

1. **No number without a run behind it.** An absent measurement says so.
2. **A gate that cannot fail is not a gate.** New gates are mutation-tested.
3. **Degradation is stated.** A step that could not verify something says
   `WITHHOLD` rather than looking clean.
4. **Site knowledge is advice, never control flow** — confined to
   `server/knowledge.py` and enforced by gate G2.
5. **The page is untrusted.** It gets no authority, ever.