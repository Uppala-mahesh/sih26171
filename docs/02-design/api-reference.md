# Drishti — API Reference

Server binds `127.0.0.1:8787`. All private routes require
`Authorization: Bearer <token>`; the token is a high-entropy credential, and only
its SHA-256 digest is retained server-side.

---

## Public routes (no credential)

| Route | Returns |
|---|---|
| `GET /` | Redirect to `/cockpit` |
| `GET /cockpit` | Operator UI. Mints a session token and injects it into the page |
| `GET /cockpit.css` | Stylesheet |
| `GET /privacy` | Privacy policy |
| `GET /health` | Liveness, model chain, session count, guard values |
| `GET /agent-content.js` | The content script, so perception is testable in any page |
| `GET /fixtures/{name}` | Local demo pages (never impersonate a real employer) |

Fixture names: `payment`, `pii`, `job-application-demo`, `prompt-injection-demo`,
`shop`, `quakes`, `upload`, `govt-scholarship`, `attendance`,
`attendance/login`.

---

## Health

```http
GET /health
```
```json
{
  "ok": true,
  "model_chain": ["gemini"],
  "sessions": 1,
  "guards": {
    "max_steps": 60,
    "wall_clock_s": 600.0,
    "confirm_timeout_s": 120.0,
    "login_timeout_s": 300.0,
    "screenshot_every": 10
  }
}
```

`model_chain` lists **actually configured** providers. A placeholder key in
`.env` does not appear — see ADR-006.

`GET /health/models` probes every provider live and reports which answered.

---

## Tasks

### Create

```http
POST /tasks
Authorization: Bearer <token>
Content-Type: application/json

{"command": "Open https://example.com and read the heading"}
```
```json
{"task_id": "task_39d54826d3", "state": "PLANNING"}
```
`409` if a task is already running — the registry holds many tasks but refuses
concurrent ones, because they would fight over the same tabs.

| Route | Purpose |
|---|---|
| `GET /tasks` | Active task plus recent snapshots |
| `GET /tasks/{id}` | One snapshot: state, step, plan, last observation |
| `GET /tasks/{id}/audit` | The whole event stream as JSONL |
| `GET /tasks/{id}/audit/verify` | Recompute the SHA-256 hash chain |
| `GET /tasks/{id}/trace` | URL transitions only, derived from observations |
| `GET /tasks/{id}/compliance-report?format=json\|html` | DPDP Act 2023 controls report |

---

## Credentials vault

| Route | Purpose |
|---|---|
| `GET /credentials` | Slot names, bound sites, labels — **never values** |
| `POST /credentials` | Add a slot |
| `DELETE /credentials/{name}` | Remove a slot |

A slot is `<entry>.<field>`. Resolution requires the slot's `match_url` to be a
substring of the target host, so a credential bound to one site cannot be typed
into another. `describe()` returns `kind: secret|identifier` and never a value.

---

## WebSockets

### `/ws/agent` — extension

Auth is the subprotocol `auth.<token>`; also accepts `drishti.v1`. The browser
cannot set headers on a WebSocket, so the credential rides the subprotocol
rather than the URL.

Server → extension: `BRIDGE_REQUEST`
Extension → server: `BRIDGE_RESPONSE`, `PING`/`PONG`, `WS_CONNECTED`

Bridge ops handled: `ping`, `new_task`, `tabs`, `observe`, `local_reason`,
`capture_any`, `fetch_document`, `screenshot`, `navigate`, `open_tab`,
`switch_tab`, `close_tab`, `back`, `forward`, `handle_dialog`, `reload`,
`download`, `list_downloads`, `upload_file`, `act`.

### `/ws/cockpit` — operator UI

Same auth. Binds to the **live agent runtime** (ADR-005).

On connect the server sends `HELLO` with `browser_connected`, `model_chain`, a
500-event replay, the active task and a snapshot.

Inbound: `TASK_CREATE`, `CONFIRMATION_GRANTED`, `CONFIRMATION_DENIED`,
`TASK_CANCEL`, `PING`.

---

## Envelope

Every message, both directions:

```json
{
  "v": 1,
  "type": "<EventType>",
  "ts": "2026-10-11T09:41:22.104Z",
  "task_id": "task_39d54826d3",
  "step": 3,
  "seq": 118,
  "payload": {}
}
```

---

## Event types

**Lifecycle** `TASK_CREATED` · `PLAN_GENERATED` · `TASK_COMPLETED` ·
`TASK_FAILED` · `TASK_CANCELLED` · `STATE_CHANGED`

**Loop** `OBSERVATION_RECEIVED` · `ACTION_PROPOSED` · `ACTION_EXECUTING` ·
`ACTION_EXECUTED` · `ACTION_FAILED` · `ACTION_VERIFIED` · `VERIFICATION_FAILED`

**Policy** `POLICY_APPROVED` · `POLICY_DENIED` · `SECURITY_BLOCKED` ·
`CONFIRMATION_REQUESTED` · `CONFIRMATION_GRANTED` · `CONFIRMATION_DENIED`

**Privacy** `MASKING_APPLIED` · `REDACTION_VERIFY_FAILED`

**Perception** `PAGE_READ_BY_SIGHT` · `DOCUMENT_READ` · `LOCAL_REASON_UNAVAILABLE`

**Recovery** `RECOVERY_STARTED` · `RECOVERY_COMPLETED` · `LOGIN_REQUIRED` ·
`LOGIN_DETECTED`

**Transport** `MODEL_CALL_COMPLETED` · `WS_CONNECTED` · `WS_DISCONNECTED` ·
`ERROR` · `PAYLOAD_BUDGET_EXCEEDED`

---

## Reading `OBSERVATION_RECEIVED`

The fields an operator should check:

| Field | Meaning |
|---|---|
| `perception_verdict` | `SANITIZED` / `ALLOW_DECLARED` / `DEGRADED` / `WITHHOLD` |
| `perception_notes` | Plain-language reason for that verdict |
| `pii_redactions` | Distinct sensitive values hidden, by kind |
| `pii_verified` | Of those, how many passed a real checksum (Luhn/Verhoeff) |
| `sensitive_boxes` | Regions blacked out on the capture |
| `qr_detected` | QR codes located and masked; payloads never read |
| `ocr_regions` / `ocr_ms` | On-device OCR findings and cost |
| `visual_scores` / `visual_ms` | On-device CLIP grounding, as `eid` scores |
| `ocr_leak_detected` | True means a PII shape survived masking and the screenshot was withheld |

`pii_verified` is a precision signal, not a safety gate: a value is masked either
way.