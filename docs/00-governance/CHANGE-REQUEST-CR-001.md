# CHANGE REQUEST CR-001 — Face / Photo PII Detection

| Field | Value |
|---|---|
| CR ID | `CR-001` |
| Raised by | Technical Lead |
| Status | 🔴 **OPEN — awaiting Product Owner decision** |
| Affects | `REQ-SRS-001` (`FR-PII-*`), `DES-ARCH-001`, `SEC-BOUND-001`, `AGL-BKLG-001` |
| Blocking | **Nothing** — the requirements baseline proceeds with the gap formally recorded |

---

## 1. Statement of the gap

The v1 demonstration script (`../sih26171/IDEA.md` §30, *Final Demo Requirements*) lists
**"Face"** among the sensitive items present in the BEFORE state of the demo page.

**Verified fact — v1 contains zero face or photo detection.** An exhaustive search across
`backend/app`, `extension/shared`, `extension/content`, and `extension/background` for
`face`, `blazeface`, `faceDetector`, and `mediapipe` returns **no matches**. Both v1 privacy
engines are regex-over-text plus Tesseract OCR. Neither can detect a face in an image.

Two consequences:

- If the demo proceeds exactly as scripted, it will **claim a capability the system does not have**.
- Charter credibility gate **C-1** forbids presenting an unimplemented capability as a guarantee.

## 2. Options considered

### Option A — Implement face detection *(in scope)*

| Dimension | Assessment |
|---|---|
| **Benefit** | Demo script honoured; addresses a genuine PS requirement; strong visual differentiator |
| **Cost** | One additional detector in the on-device vision engine |
| **Rubric impact** | Positive on **Visual 25%** — *if* element classification is already at target |
| **Risks** | Model size vs the ≤ 15 MB extension budget · latency vs the 800 ms p95 target · needs ≥ 40 ground-truth face fixtures |
| **Candidate approach** | BlazeFace short-range or MediaPipe Face Detection via ONNX Runtime Web — both ≈ 0.3–1.1 MB and CPU-capable, so constraint C-4 (no GPU assumed) is not violated |

### Option B — Remove face from the demo script *(out of scope)*

| Dimension | Assessment |
|---|---|
| **Benefit** | Zero engineering cost; every claim defensible; removes all rubric risk |
| **Cost** | Weaker demo visual; the "photo" category goes unaddressed |
| **Rubric impact** | **Neutral** — the rubric does not itemise face detection; it itemises PII precision/recall |
| **Risks** | A jury member may ask about photo redaction, and the honest answer is "not implemented" |

### Option C — Defer, with a declared limitation

| Dimension | Assessment |
|---|---|
| **Benefit** | Honest; demonstrates engineering maturity — a *declared* limitation is far stronger than a hidden gap |
| **Cost** | Same demo weakness as B, offset by a credibility gain |
| **Rubric impact** | Neutral |

## 3. Technical impact assessment

| Dimension | Option A | Option B | Option C |
|---|---|---|---|
| New SRS requirements | 3 (`FR-PII-FACE-1..3`) | 0 | 0 |
| New module | `services/vision/sources/face-detector` | — | — |
| Extension size delta | **+0.3 – 1.1 MB** | 0 | 0 |
| Latency delta (p95) | **+60 – 180 ms** | 0 | 0 |
| Ground-truth fixtures required | ≥ 40 labelled faces | 0 | 0 |
| Sprint placement | Sprint A (engine) + Sprint B (redaction) | — | — |
| Risk to the 25% visual weight | **Medium** — model and attention budget contention | None | None |

## 4. Recommendation — Technical Lead

> **Option A, conditional on Sprint A exit criteria.**

Rationale:

1. **Face redaction is a memorable demo moment.** Juries remember what they *see* demonstrated,
   not what they read in a document.
2. **The size and latency risk is genuinely manageable** — modern face detectors are small and
   CPU-capable, so constraint C-4 is respected.
3. **PS171 is fundamentally about *visual* PII.** A "visual perception" system that cannot see a
   face is an incomplete answer to the problem statement.

**Condition (binding):** if Sprint A's element-classification F1 lands below target, this CR
automatically falls back to **Option C**.

> **Element classification wins any budget conflict.** It carries 25% of the rubric directly;
> face redaction carries none directly. This condition is not negotiable at implementation time.

## 5. Escalation clause

Sprint A planning will record the measured runtime cost of whichever detector is chosen. If the
measured cost exceeds the §3 estimate by more than **50%**, this CR is re-opened for review rather
than absorbed silently into the sprint.

## 6. Decision

| Role | Decision | Date |
|---|---|---|
| Product Owner | ✅ **APPROVED — Option A** (implement face detection), with the binding fallback to Option C | 2026-10-01 |
| Technical Lead | Recommended **A**; condition accepted | 2026-10-01 |

**Status: 🔒 CLOSED — APPROVED (Option A).**

### 6.1 Consequences of approval

1. `FR-PII-FACE-1..3` are promoted from *pending* to **active**, MoSCoW **`Should`**.
2. `FACE_IMAGE` becomes an **active** entity in `REQ-DATA-001` — 20 active entities.
3. Sprint A must publish the measured runtime cost of the chosen detector alongside the
   element-classification F1 result.
4. **The fallback condition remains binding and automatic.** If Sprint A exits with element
   classification below macro-F1 0.90, this CR reverts to Option C **without further approval**:
   face detection is dropped and `SEC-BOUND-001` records it as a declared limitation.
5. Ground-truth fixtures — ≥ 40 labelled faces in `testdata/` — must exist before Sprint B may
   claim `FR-PII-FACE-2`.

### 6.2 Why Option A

Face redaction is the only requirement in this baseline that a jury **sees** rather than reads.
The detector is small (0.3–1.1 MB) and CPU-capable, so it respects constraint C-4 and the 15 MB
package budget. PS171 is fundamentally about **visual** PII — a visual system that cannot see a
face is an incomplete answer to the problem statement.

The risk is real but bounded, and the automatic fallback means the 25% visual weight is never
exposed to it.
