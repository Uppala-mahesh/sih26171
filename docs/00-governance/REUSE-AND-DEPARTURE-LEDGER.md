# REUSE & DEPARTURE LEDGER — v1 → v2

| Field | Value |
|---|---|
| Document ID | `GOV-LEDG-001` |
| Version | 1.0 |
| Status | **Active** |
| Source of truth for | Which v1 artifacts (`../sih26171/`) may enter `sih-agent-v2` |

---

## 1. Purpose

The v1 prototype contains genuine engineering assets and genuine structural debt, often in the
same file. This ledger records the **disposition of every material artifact** so that reuse is a
deliberate, evidence-backed decision rather than a reflex.

This is the **only sanctioned channel** for v1 code entering v2. "We already have it" is not a
justification. A ledger row with a stated reason is.

## 2. Disposition codes

| Code | Meaning | Behaviour preserved? |
|---|---|---|
| **LIFT** | Copy with minimal change (imports, paths, style). | Yes — interface and semantics intact |
| **REWORK** | Take the idea or algorithm; rewrite to satisfy the v2 contract. | Intent only — implementation replaced |
| **REWRITE** | The v1 attempt informs requirements; **no code** is carried. | No |
| **RETIRE** | Explicitly abandoned. Recorded so it is never reintroduced. | No |

## 3. LIFT — carried across, minimal change

These are the parts of v1 that are genuinely well built. Preserve them; do not "improve" them
in Sprint A, or you will break working behaviour for no measurable gain.

| v1 artifact | Why it survives | v2 target |
|---|---|---|
| `gateway/schema.py` — `SafePageContext`, `SafeVisualContext` with `extra="forbid"` | Strongest contract in v1. Structurally prevents field injection across the boundary — an attacker literally cannot add a raw-screenshot field. | `packages/contracts` (ported onto the shared taxonomy) |
| `gateway/gateway.py` — `SafeContextGateway` | Correct "sole egress" chokepoint, with audit records. The design is right. | `apps/backend/app/gateway` |
| `policy/confirmation.py` — HMAC approval tokens | Sound: signed, time-boxed, bound to action + target + origin. | `apps/backend/app/policy` |
| `agent/validator.py` — `ActionValidator` | Correct posture: model output is untrusted input. | `apps/backend/app/agent` |
| `agent/task_state.py` — state machine + `TERMINAL_STATES` | Bounded, explicit, terminal states are correct. | `apps/backend/app/agent` |
| `agent/task_verifier.py` | Deterministic, model-independent completion verification — the right idea (never trust the model's claim of success). | `apps/backend/app/agent` |
| `extension/shared/action-contract.js` | Provider-neutral proposal normalizer. Correct boundary between provider output and trusted shape. | `packages/contracts` |
| `extension/shared/action-binding.js` | Fresh-observation revalidation before acting on a target. | `services/vision` (binding sub-module) |
| `evaluation/measured_metrics.py` | The **honesty pattern**: returns `null`, never a fabricated `0`. This single file protects the project's credibility. | `benchmarks/` shared reporter |
| `tests/conftest.py` harness | Reusable fixture scaffolding. | `tests/` |
| `docs/audit/per-file-ledger.md` | Trust-boundary ledger methodology. | `docs/05-security/` (methodology adopted, content regenerated) |

## 4. REWORK — take the intent, rewrite to the v2 contract

| v1 artifact | Verified defect | v2 target design |
|---|---|---|
| `on-device-runtime.js` `PII_PATTERNS` | Format-only regexes with **no checksum validation**, so 13–19 digit order IDs match `CARD` and any 12 digits match `AADHAAR`. Vocabulary diverges from the Python engine. | `packages/taxonomy`-driven registry; one strategy per entity type; Luhn / Verhoeff validators; context gating |
| `pattern_detector.py` | Contains **none** of Aadhaar / PAN / UPI / IFSC / OTP — the India-specific PII the problem statement explicitly names. | Same taxonomy as above — one registry, two runtimes |
| `privacy_pipeline.py` | Sets `is_sanitized=True` **unconditionally** (line 438); holds mutable per-run results on the instance, forcing two "fresh pipeline" workarounds elsewhere in the codebase. | Pure transform over injected detectors; explicit `SANITIZED` / `DEGRADED` state; no per-run mutable state |
| `visual_redactor.py` | Opaque fill only. Region matching is a ±5 px comparison on **x/y only**, ignoring width and height — mismatches when a token spans two lines. | Box-IoU matching; mask verification by independent re-scan |
| `vision-engine.js` | OCR text redaction only; no UI-element understanding. | Full vision engine with capability ladder + element classifier |
| `service-worker.js` (1,738 lines) | Holds 12+ responsibilities and module-level mutable state (`agentState`, `pendingConfirmation`, `sessionConversationHistory`). | Decomposed role modules + an explicit session store with lifecycle |
| `content-script.js` (597 lines) | Monolithic — observation, extraction, and action dispatch are coupled. | Observer / extractor / dispatcher split |
| `gemini-provider.js` (549 lines) | Nano, backend, and cloud paths all inside one class. | Provider strategy + capability negotiation |
| `ChatOrchestrator` + `TaskOrchestrator` | Both are legitimately needed, but each re-wires privacy + gateway + policy + validator + verifier. Two copies of the security pipeline. | One shared `AgentPipeline`; two thin drivers of it |
| `Dashboard.tsx` | 7 `useState`, 3-second polling, stale-closure bug in the confirm handlers. | Feature slices + pushed telemetry |
| Side-panel `app.js` (674 lines) | Duplicates domain display logic already present in the console. | Presentation-only; renders shared telemetry |
| `evaluation/model_resource_benchmark.py` | Measures `tracemalloc` on **Python YOLO**, while rubric credit is awarded for in-browser WASM/Tesseract — measuring the wrong stack. | Re-pointed at the extension stack |
| `evaluation/hybrid_perception_benchmark.py` | `use_dom` / `use_ocr` ablation flags are accepted but never branch — only `use_visual` works. The comparison table misleads. | Real branching, or the flags are removed |
| `perception/visual/adapter.py` — `LocalOCRAdapter` | `process_and_redact()` returns bytes **unchanged**, and it is the ABC's default implementation. A redaction method that redacts nothing. | Deleted, or implemented for real. No method may be named for behaviour it does not perform. |

## 5. REWRITE — requirement understood, no v1 code carried

| Concern | v1 state (verified) | v2 approach |
|---|---|---|
| **UI element understanding (25% weight)** | Does not exist. All planning comes from DOM; there is no button/field/dialog classifier and no accuracy benchmark. | Dedicated classifier in `services/vision`, with a ground-truth fixture set |
| **WebGPU / ONNX-Runtime-Web / Transformers.js** | **Absent everywhere** — exhaustive grep for `navigator.gpu`, `requestAdapter`, `onnxruntime`, `ort.` returns zero hits in both extension and console, despite the problem statement naming these technologies explicitly. | Capability-laddered inference: WebGPU → WASM SIMD → WASM → DOM-only |
| **Shared entity taxonomy (Python ↔ TypeScript)** | Absent. `perception/base.py` `EntityType` has no AADHAAR / PAN / UPI / OTP / IFSC / STUDENT_ID members, so those detections cannot cross the boundary without lossy coercion. | `packages/taxonomy` single registry → code generation for Python and TypeScript |
| **Network-inspection demo proof** | Exists only as markdown prose (`docs/audit/egress-map.md`). No runtime, judge-visible payload inspector. | Live outbound-payload inspector in the console |
| **Face / photo PII** | Absent — zero face detectors in either engine, yet `IDEA.md §30` lists "Face" in the promised demo. | **Built new** — `CR-001` approved (Option A). Nothing is carried from v1; the detector is new capability, subject to that CR's automatic fallback condition. |
| **Rubric scoring harness** | Partial and misaligned; 45% of the rubric unmeasured. | `benchmarks/` designed 1:1 against the five weights |

## 6. RETIRE — must not be reintroduced

| Artifact | Reason |
|---|---|
| `backend/scratch/` | Contains a **live Chrome user-data-dir**: `Cookies`, `Login Data`, `History`, `Web Data`. Not currently gitignored — one `git add -A` commits a browser profile. |
| `.kilo/worktrees/cooperative-cheque/` | Stale **complete duplicate** of backend and frontend. Corrupts every future search and build. |
| `main.py` `/agent/run-step` compat endpoint | Duplicate route shadowing `/api/agent/run-step`. |
| `LEGACY_DEFAULT_ALLOWED_DOMAINS` migration shim | Pre-release data migration with no deployed users to migrate. |
| `LocalOCRAdapter` as ABC default | Misleading contract — see REWORK. |
| `backend/yolov8n.pt` | PyTorch checkpoint shipped alongside `models/yolov8n.onnx`, while the ONNX detector defaults to `None` and is therefore never active. Ship one, or neither. |
| 8 `tesseract-core*` variants + 2 `traineddata` models | ≈ **42.9 MB** of vendor payload, all exposed via `web_accessible_resources`, with no capability probe. Retain one core and one model, selected at runtime. |
| Tautological tests (`test_ui_api_integration` asserting hardcoded `"SECURE"`; `test_prompt_injection_containment` asserting its own f-string) | Manufacture false confidence. |
| Hardcoded test counts (README `99`, plan `155`, console `57`; actual collection **204**) | Three mutually contradictory figures. Replace with one generated number. |
| `.map` source maps in the production extension | Deployment noise. |
| `docs/audit/*` and `.kilo/plans/*` as *authorities* | Useful as audit input — already mined into this ledger. Superseded as sources of truth by the v2 artifact set. |

## 7. Enforcement

1. **No file may be copied from `../sih26171/` without a ledger row.** Unlisted reuse is a review failure.
2. Every LIFT or REWORK target file cites its ledger row in its header comment.
3. RETIRE entries are checked by a forbidden-pattern scan in `infra/` — the build fails if one reappears.
4. The ledger is reviewed at every Sprint Review. New rows require Product Owner acknowledgement.

## 8. Ledger summary

| Disposition | Count | Headline |
|---|---|---|
| **LIFT** | 11 | Contracts, egress gateway, HMAC confirmation, validator, verifier, honesty pattern |
| **REWORK** | 14 | Both PII engines, both pipelines, service worker, both orchestrators, both UIs, 2 misleading benchmarks |
| **REWRITE** | 6 | UI-element understanding, WebGPU ladder, shared taxonomy, payload inspector, face PII, rubric harness |
| **RETIRE** | 11 | Live browser profile, stale worktree, vendor bloat, duplicate route, tautological tests |

**Bottom line.** v1's *contracts and security boundaries* are worth keeping. v1's *perception,
privacy, and UI implementations* are worth rewriting. This ledger makes that split explicit so
the decision never has to be re-argued mid-sprint.
