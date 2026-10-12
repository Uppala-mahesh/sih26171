# Drishti — UML Diagram Set

All diagrams are Mermaid, renderable in GitHub, VS Code and most Markdown
viewers. Each is derived from shipped code; the source file is named beneath
each diagram so a reviewer can check it.

---

## 1. Use-case diagram

Actors are the five in the SRS. Note that **Page** is drawn as an actor because
it is untrusted and actively attempts injection — it is not a participant the
system trusts.

```mermaid
graph LR
  Op((Operator))
  Ext[Extension<br/>content + service worker]
  Reasoner[Reasoner<br/>Gemini / Groq / OpenRouter]
  Page((Page<br/>untrusted))
  Audit[(Audit JSONL<br/>hash-chained)]

  Op -->|"command"| UC1[/"Give a command"/]
  Op -->|"approve / deny"| UC4[/"Approve high-risk action"/]
  Op -->|"read"| UC7[/"Watch live run"/]
  Op -->|"request"| UC8[/"DPDP compliance report"/]

  UC1 --> UC2[/"Observe page locally"/]
  UC2 --> UC3[/"Redact before transmit"/]
  UC3 --> UC4
  UC3 --> UC5[/"Propose next action"/]
  UC5 --> UC6[/"Execute against real DOM"/]
  UC6 --> UC9[/"Verify on fresh observation"/]
  UC9 -->|not achieved| UC5
  UC9 -->|achieved| UC1

  Reasoner -.->|"sanitised context only"| UC5
  Page -.->|"attempts prompt injection"| UC2
  Ext --> Audit
  UC4 --> Audit

  classDef trust fill:#1c1c1a,stroke:#ef6461,color:#ef6461
  class Page trust
```

**Source:** `server/loop.py` (FSM), `server/policy.py` (UC4 branch).

---

## 2. Class diagram — server core

```mermaid
classDiagram
  class Task {
    +task_id
    +state
    +step
    +plan : Plan
    +command : str
    +keep_terms
    +privacy_mode
    +observe(screenshot) Observation
    +execute(action) dict
    +run() str
    +set_state(s, detail)
    -_land_on(url)
    -_first_observation() Observation
    -_read_by_sight(obs) Observation
  }

  class Observation {
    +url, title, page_kind
    +interactive_elements : List
    +page_text : str
    +screenshot : str
    +sensitive_boxes : List
    +ocr_regions, ocr_error, ocr_leak_detected
    +visual_scores : Dict
    +pii_redactions : Dict
    +perception_verdict : str $
    +perception_notes : List $
  }

  class ActionProposal {
    +action_id
    +action : str
    +target : Target
    +params : Params
    +reason : str
    +confidence : float
    +perception_source : str
  }

  class PolicyDecision {
    +decision : allow|confirm|deny
    +risk : low|high
    +rules_fired : List
    +reason : str
  }

  class BrowserBridge {
    +connected : bool
    +request(op, args, task_id) dict
    +observe(task_id, screenshot) Observation
    +resolve(req_id, payload)
  }

  class EventBus {
    +emit(type, payload, task_id, step)
    +subscribe() Queue
    +replay(n) List
    +verify_audit_chain() bool
  }

  class Registry {
    +active_task_id
    +start(command) Task
    +get(task_id) Task
  }

  class Knowledge {
    +hints_for(url) str
    +start_url_for(command) str$
    +known_hosts() List
  }

  Task --> Observation : produces
  Task --> ActionProposal : requests
  Task --> PolicyDecision : governed by
  Task --> BrowserBridge : talks through
  Task --> EventBus : reports to
  Task --> Registry : registered in
  Task --> Knowledge : hints from
  Registry o-- Task
  EventBus --> Observation
```

**Source:** `server/schemas.py`, `server/loop.py`, `server/browser_bridge.py`,
`server/events.py`, `server/knowledge.py`.

---

## 3. Sequence — one closed-loop step

This is the diagram that matters most: it shows that **verification reads a
fresh observation**, not the one the action was planned against.

```mermaid
sequenceDiagram
  autonumber
  participant C as Cockpit
  participant L as Loop / Task
  participant B as BrowserBridge
  participant X as Extension
  participant R as Reasoner (cloud)
  participant P as Policy (pure Python)

  C->>L: TASK_CREATE
  L->>R: plan(command)
  R-->>L: Plan(objective, steps, start_url)
  L->>B: _land_on(start_url)
  B->>X: tabs
  X-->>B: tab list
  Note over L: reuse a safe existing tab;<br/>never the cockpit
  L->>B: navigate(url, tab_id)
  B->>X: tabs.update + waitForLoad

  rect rgb(28,28,26)
    Note over L,X: OBSERVE — entirely on-device
    L->>B: observe(screenshot=true)
    B->>X: COLLECT
    X->>X: walk DOM, stamp eid/nid
    X->>X: redact in page (text + field values)
    X->>X: captureVisibleTab
    X->>X: black out sensitive_boxes + QR
    X->>X: runOcr(redacted capture)
    X->>X: verifyRedaction(ocr) → leak?
    alt leak detected
      X-->>B: screenshot = null, ocr_leak_kinds
    end
    X->>X: runClipScore → eid scores
    X-->>B: Observation
  end

  L->>L: perception_verdict (derived, never stored)
  L->>R: propose(sanitised observation)
  R-->>L: ActionProposal (Pydantic-validated)
  L->>P: evaluate(action, observation)
  P-->>L: allow | confirm | deny

  alt deny
    L-->>C: POLICY_DENIED
  else confirm
    L-->>C: CONFIRMATION_REQUESTED
    C->>L: granted | denied
  end

  L->>B: execute(verb, target, params)
  B->>X: ACT (real DOM event)
  X-->>B: result + readback

  rect rgb(20,34,28)
    Note over L,X: VERIFY — fresh observation
    L->>B: observe(screenshot=false)
    B->>X: COLLECT
    X-->>B: Observation#2
    L->>L: check_freshness(obs#2 vs action)
    L->>L: verify(expected, obs#2)
  end
  alt verified
    L-->>C: ACTION_VERIFIED → next step
  else not verified
    L->>L: recovery handler → re-observe → re-reason
  end
```

**Source:** `server/loop.py:step_once()`, `server/verifier.py`.

---

## 4. Activity — decision on a proposed action

```mermaid
flowchart TD
  S([Action proposed]) --> P{Policy evaluate}
  P -->|deny| D[POLICY_DENIED<br/>task halts]
  P -->|confirm| Q{Protected field?}
  Q -->|yes| L[requires live human<br/>pre-approval cannot cover]
  Q -->|no| R{Task pre-armed?}
  R -->|yes| X[execute, logged]
  R -->|no| W[ask the operator]
  W -->|deny| D
  W -->|grant once| X
  W -->|grant task| X
  P -->|allow| X
  X --> V{Verified on a<br/>fresh observation?}
  V -->|yes| N([next step])
  V -->|no, retry < 3| C[recovery: re-ground,<br/>wait, dismiss overlay]
  C --> V
  V -->|no, 3 strikes| F([TASK_FAILED — honestly])

  classDef deny fill:#2a1616,stroke:#ef6461,color:#ef6461
  classDef human fill:#2a2416,stroke:#e3b341,color:#e3b341
  classDef ok fill:#16261f,stroke:#57d9a3,color:#57d9a3
  class D,F deny
  class L,W human
  class N,X ok
```

**Source:** `server/policy.py`, `server/loop.py:_request_confirmation`.

---

## 5. Component diagram

```mermaid
graph TB
  subgraph Browser["Chrome (untrusted host)"]
    direction TB
    CS["agent-content.js<br/><b>perception · redaction · execution</b>"]
    SW["agent-background.js<br/><b>service worker · WS · tabs · capture</b>"]
    OFF["offscreen.js<br/><b>Tesseract OCR · MobileCLIP</b>"]
    SW -->|chrome.tabs.sendMessage| CS
    SW -->|runtime message| OFF
  end

  subgraph Server["127.0.0.1:8787 — the enclave"]
    direction TB
    API["main.py — FastAPI<br/>/ws/agent · /ws/cockpit · REST"]
    LOOP["loop.py — FSM + Registry"]
    PLN["planner.py · reasoner.py · quoter.py"]
    POL["policy.py — pure Python"]
    VER["verifier.py · recovery.py"]
    SAN["sanitizer.py · redaction.py · vault.py"]
    BUS["events.py — bus + hash-chained audit"]
    KN["knowledge.py — the only file naming a site"]
    CAP["capability_gate.py — prompt-injection defence"]
    COMP["compliance.py — DPDP report"]
  end

  subgraph Cloud["External (sees sanitised context only)"]
    LLM["Gemini · Groq · OpenRouter · OpenAI"]
  end

  UI["cockpit.html + cockpit.css<br/>operator surface"]

  CS <-->|"BridgeRequest / Response<br/>envelope v1"| SW
  SW <-->|"WebSocket"| API
  API --> LOOP
  LOOP --> PLN
  LOOP --> SAN
  LOOP --> POL
  LOOP --> VER
  LOOP --> BUS
  PLN -.->|hints only| KN
  PLN --> LLM
  LOOP --> COMP
  BUS --> UI
  API --> UI

  classDef priv fill:#16261f,stroke:#57d9a3,color:#57d9a3
  classDef cl fill:#20182a,stroke:#b58bef,color:#b58bef
  class CS,SW,OFF,SAN priv
  class LLM cl
```

**The trust boundary is the line between `Browser` and `Server`.** Redaction
happens on the `Browser` side of it. Nothing raw crosses.

**Source:** `public/`, `server/`.

---

## 6. State machine — task lifecycle

```mermaid
stateDiagram-v2
  [*] --> PLANNING
  PLANNING --> OBSERVING
  OBSERVING --> REASONING
  REASONING --> POLICY_CHECK
  POLICY_CHECK --> WAITING_FOR_CONFIRMATION : confirm
  POLICY_CHECK --> EXECUTING : allow
  WAITING_FOR_CONFIRMATION --> EXECUTING : granted
  WAITING_FOR_CONFIRMATION --> FAILED : denied or timeout
  EXECUTING --> VERIFYING
  VERIFYING --> OBSERVING : not yet, recover
  VERIFYING --> RECOVERING : 1-2 failures
  RECOVERING --> OBSERVING
  VERIFYING --> [*] : task complete
  OBSERVING --> WAITING_FOR_LOGIN : login wall
  WAITING_FOR_LOGIN --> OBSERVING : wall gone
  WAITING_FOR_LOGIN --> FAILED : 300s timeout
  POLICY_CHECK --> SECURITY_BLOCKED : capability gate
  SECURITY_BLOCKED --> FAILED
  REASONING --> FAILED : max steps / wall clock
  PLANNING --> CANCELLED
  OBSERVING --> CANCELLED
  EXECUTING --> CANCELLED
  FAILED --> [*]
  CANCELLED --> [*]
```

**Source:** `server/loop.py` module docstring + `set_state` call sites.

---

## 7. Deployment diagram

```mermaid
graph LR
  subgraph Host["Operator's machine (trust zone ends here)"]
    direction LR
    CH["Chrome 116+<br/>profile: logged-in sessions"]
    PY["Python 3.11+<br/>uvicorn 127.0.0.1:8787"]
    FS[("~/.drishti/<br/>audit JSONL +<br/>credential vault")]
    CH <-->|ws 127.0.0.1| PY
    PY <-->|read/write| FS
  end
  subgraph Remote["Internet — sanitised context only"]
    G["Gemini / Groq /<br/>OpenRouter / OpenAI"]
  end
  PY -->|"WSS, after redaction"| G
```

**Single-operator, single-machine.** The server binds loopback only.

---

## 8. Perception verdict state (v3)

```mermaid
stateDiagram-v2
  [*] --> Grade
  Grade --> SANITIZED : everything attempted succeeded
  Grade --> ALLOW_DECLARED : visual path incomplete / not covered
  Grade --> DEGRADED : OCR, CLIP or capture failed
  Grade --> WITHHOLD : leak caught, or unmaskable page
  WITHHOLD --> [*] : fail closed
  DEGRADED --> WITHHOLD : aggregated
  ALLOW_DECLARED --> DEGRADED : aggregated
  SANITIZED --> DEGRADED : aggregated
```

`WITHHOLD` dominates every other state when steps are aggregated. The verdict is
**derived** from measured fields — it cannot be set to a comfortable answer.
Enforced behaviourally by **G13**.