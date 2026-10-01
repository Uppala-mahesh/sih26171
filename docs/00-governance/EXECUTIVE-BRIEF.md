# EXECUTIVE BRIEF — SIH26171 (read this, not the 25 KB)

| | |
|---|---|
| Document ID | `GOV-BRIEF-001` |
| Audience | Product Owner (you) + SIH jury |
| Reading time | ~4 minutes |

---

## 1. Where things stand

Your v1 prototype **works** — it is a genuinely capable system (12,000 lines, 204 tests, a real
privacy gateway, a real policy engine). I audited it in full. The honest finding:

> **v1's security boundaries and data contracts are good. Its perception, privacy, and UI code
> were built piecemeal and need rebuilding.**

That is not a criticism of the effort — it is the normal result of assembling a system from many
separate AI outputs. Each piece worked; the seams between them are where the risk lives.

## 2. The three findings that actually matter

**Finding 1 — You have two privacy engines that disagree.**
The JavaScript engine detects Aadhaar, PAN, UPI, IFSC and OTP. The Python engine detects none of
them. So a page's most India-sensitive data is caught on-device and then **cannot even be
represented** when it reaches the backend. The problem statement names exactly these data types.

**Finding 2 — 45% of the scoring is unmeasured.**
The official scoring is Visual 25% · PII 20% · Redaction 20% · Resources 20% · Latency 15%.
v1 has **no UI-understanding model at all** (the 25% item), no false-positive measurement, and its
resource benchmark measures the *Python* stack while the score is awarded for the *browser* stack.
Also — v1 contains **no face detection**, yet the demo script promises to redact faces.

**Finding 3 — There is no WebGPU anywhere.**
The problem statement explicitly names WebGPU, WebAssembly, ONNX-Runtime-Web and Transformers.js.
v1 uses none of them — it uses Tesseract only, and ships **42.9 MB** of OCR files for a
"light-weight" agent.

## 3. What we are building instead

Three surfaces, all intentional:

| | |
|---|---|
| **Browser extension** | Does the seeing and the hiding, on your machine. Nothing sensitive leaves it. |
| **Local backend** | Does the thinking. Runs on loopback only — never exposed to the network. |
| **Demo console** | Shows the jury what happened, live. Displays numbers, owns no logic. |

And one rule that everything obeys: **perceive → detect → redact → verify, all locally, before
anything is transmitted.**

## 4. How we are building it (the process you asked for)

Governed inception, then Agile sprints:

```
Phase 0  Governance      ── DONE  (charter, reuse ledger, this brief)
Phase 1  Requirements    ── next  (SRS, use cases, data catalogue, traceability)
Phase 2  Design          ── then  (architecture, class model, sequence diagrams, contracts)
Phase 3  Delivery        ── Sprints A–E, one working increment each
Phase 4  Verification    ── benchmark every rubric weight against ground truth
Phase 5  Hardening       ── fallbacks, edge cases, memory lifecycle
```

**Sprint map:** A = shared kernel + vision engine · B = PII detection & redaction ·
C = agent pipeline · D = consoles + scoring harness · E = hardening.

## 5. What we must be able to prove to the jury

1. The vision actually understands the page (25%).
2. Sensitive data is found, with few false alarms (20%).
3. What is hidden is really hidden — verified by re-scanning, not by trusting a flag (20%).
4. It runs on an ordinary laptop without eating the machine (20%).
5. It responds fast enough to feel like an agent, not a script (15%).

Plus one credibility rule: **we never print a number we did not measure.** v1 printed hardcoded
`0.00%` and `"SECURE"`; that is the fastest way to lose a jury's trust. Unmeasured values now
display as `—`.

## 6. What I need from you

| # | Decision | Why it's yours |
|---|---|---|
| 1 | **Approve the blueprint?** | It sets the whole build. |
| 2 | ~~Face/photo redaction — build it or drop it?~~ **✅ DECIDED: BUILD** | `CR-001` **approved**. The demo script promised it, so we build it — with an automatic fallback to a declared limitation if it ever threatens the 25% visual weight. |
| 3 | **Confirm the reuse ledger.** | It says what we keep from v1 and what we rewrite. ~10 minutes to skim; it prevents re-arguing later. |

## 7. Where to look if you want detail

| If you want to know… | Read |
|---|---|
| What we're keeping vs rewriting | `REUSE-AND-DEPARTURE-LEDGER.md` §3, §4 |
| What we're building and what "win" means | `PROJECT-CHARTER.md` §4, §5 |
| What we're deliberately *not* doing | `PROJECT-CHARTER.md` §4 out-of-scope |

Everything else can wait until you need it.
