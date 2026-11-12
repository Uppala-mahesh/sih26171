"""Smoke evaluation harness.

Drives the real server over its real cockpit WebSocket, runs each task in
smoke_tasks.json against the real browser, and decides success from the audit
trail using programmatic criteria only. The model is never asked to grade
itself.

    python -m server.eval.run_smoke            # run everything
    python -m server.eval.run_smoke nav-and-click
    python -m server.eval.run_smoke --file server/eval/demo_tasks.json --list
    python -m server.eval.run_smoke --file server/eval/demo_tasks.json demo-pii-redaction

Requires: the server running on 8787 and the extension connected. The cockpit
token is read from the public /cockpit page; set DRISHTI_COCKPIT_TOKEN to
override it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx
import websockets

HERE = Path(__file__).parent
BASE_HTTP = "http://127.0.0.1:8787"
BASE_WS = "ws://127.0.0.1:8787"
TASK_TIMEOUT_S = 300.0

# The cockpit socket and every task/audit endpoint are authenticated. The
# cockpit page mints a short-lived token and embeds it; the harness reads the
# same page as an operator would, instead of disabling the boundary for tests.
COCKPIT_TOKEN = ""


def _auth_headers() -> Dict[str, str]:
    return {"Authorization": "Bearer " + COCKPIT_TOKEN} if COCKPIT_TOKEN else {}


def _ws_protocols() -> List[str]:
    return ["drishti.v1", "auth." + COCKPIT_TOKEN] if COCKPIT_TOKEN else ["drishti.v1"]


async def resolve_cockpit_token() -> str:
    token = os.getenv("DRISHTI_COCKPIT_TOKEN", "").strip()
    if token:
        return token
    async with httpx.AsyncClient(timeout=10.0) as c:
        page = (await c.get(BASE_HTTP + "/cockpit")).text
    match = re.search(r"COCKPIT_TOKEN = '([^']+)'", page)
    return match.group(1) if match else ""



class Metrics:
    def __init__(self) -> None:
        self.steps = 0
        self.actions_proposed = 0
        self.actions_executed = 0
        self.actions_failed = 0
        self.proposed_actions: List[str] = []
        self.executed_actions: List[str] = []
        self.verified = 0
        self.verify_failed = 0
        self.grounding_failures = 0
        self.recoveries = 0
        self.recoveries_handled = 0
        self.model_calls = 0
        self.model_latency_ms: List[float] = []
        self.human_interventions = 0
        self.policy_confirms = 0
        self.login_waits = 0

    def as_dict(self) -> Dict[str, Any]:
        lat = self.model_latency_ms
        return {
            "steps": self.steps,
            "actions_proposed": self.actions_proposed,
            "actions_executed": self.actions_executed,
            "actions_failed": self.actions_failed,
            "proposed_actions": self.proposed_actions,
            "executed_actions": self.executed_actions,
            "action_success_rate": _pct(self.actions_executed, self.actions_proposed),
            "verifications_passed": self.verified,
            "verifications_failed": self.verify_failed,
            "verification_rate": _pct(self.verified, self.verified + self.verify_failed),
            "grounding_failures": self.grounding_failures,
            "recoveries_started": self.recoveries,
            "recoveries_handled": self.recoveries_handled,
            "model_calls": self.model_calls,
            "model_latency_ms_avg": round(sum(lat) / len(lat), 1) if lat else None,
            "human_interventions": self.human_interventions,
            "policy_confirmations": self.policy_confirms,
            "login_waits": self.login_waits,
        }


def _pct(num: int, den: int) -> str:
    return "n/a" if den == 0 else "%.0f%% (%d/%d)" % (100.0 * num / den, num, den)


TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


async def wait_until_idle(timeout_s: float = 90.0) -> None:
    """Block until the server has no task in flight."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    async with httpx.AsyncClient(timeout=10.0, headers=_auth_headers()) as c:
        while asyncio.get_running_loop().time() < deadline:
            try:
                health = (await c.get(BASE_HTTP + "/health")).json()
                active = health.get("active_task")
                if not active:
                    return
                snap = (await c.get("%s/tasks/%s" % (BASE_HTTP, active))).json()
                if snap.get("state") in TERMINAL_STATES:
                    return
                # Still going: ask it to stop, then keep waiting.
                async with websockets.connect(
                    BASE_WS + "/ws/cockpit", subprotocols=_ws_protocols()
                ) as ws:
                    await asyncio.wait_for(ws.recv(), 10)
                    await ws.send(json.dumps({
                        "v": 1, "type": "TASK_CANCEL", "payload": {"task_id": active},
                    }))
            except (httpx.HTTPError, OSError, ValueError, asyncio.TimeoutError):
                return
            await asyncio.sleep(1.5)


async def run_task(spec: Dict[str, Any]) -> Dict[str, Any]:
    m = Metrics()
    events: List[Dict[str, Any]] = []
    task_id = None
    outcome = "TIMEOUT"
    summary = ""
    error = ""
    started = time.monotonic()
    timeout_s = float(spec.get("timeout_s", TASK_TIMEOUT_S))
    effort = str(spec.get("effort") or "balanced")
    answer_only = bool(spec.get("answer_only", False))
    privacy_mode = str(spec.get("privacy_mode") or "balanced")
    confirmation = spec.get("confirmation") or {}
    confirm_decision = str(confirmation.get("decision") or "deny").lower()
    confirm_scope = confirmation.get("scope")

    async with websockets.connect(
        BASE_WS + "/ws/cockpit", max_size=16 * 1024 * 1024,
        subprotocols=_ws_protocols(),
    ) as ws:
        await asyncio.wait_for(ws.recv(), 10)  # HELLO
        await ws.send(json.dumps({
            "v": 1, "type": "TASK_CREATE", "payload": {
                "command": spec["command"],
                "effort": effort,
                "answer_only": answer_only,
                "privacy_mode": privacy_mode,
            },
        }))

        while time.monotonic() - started < timeout_s:
            try:
                raw = await asyncio.wait_for(ws.recv(), 20)
            except asyncio.TimeoutError:
                continue
            ev = json.loads(raw)
            t = ev.get("type")
            p = ev.get("payload") or {}
            if ev.get("task_id"):
                task_id = ev["task_id"]
            events.append(ev)
            m.steps = max(m.steps, ev.get("step", 0))

            if t == "ACTION_PROPOSED":
                m.actions_proposed += 1
                if p.get("action"):
                    m.proposed_actions.append(str(p["action"]))
            elif t == "ACTION_EXECUTED":
                m.actions_executed += 1
                if p.get("action"):
                    m.executed_actions.append(str(p["action"]))
            elif t == "ACTION_FAILED":
                m.actions_failed += 1
                if "stale_element" in str(p.get("error", "")):
                    m.grounding_failures += 1
            elif t == "ACTION_VERIFIED":
                m.verified += 1
            elif t == "VERIFICATION_FAILED":
                m.verify_failed += 1
            elif t == "RECOVERY_STARTED":
                m.recoveries += 1
            elif t == "RECOVERY_COMPLETED" and p.get("handled"):
                m.recoveries_handled += 1
            elif t == "MODEL_CALL_COMPLETED":
                m.model_calls += 1
                if p.get("latency_ms"):
                    m.model_latency_ms.append(p["latency_ms"])
            elif t == "LOGIN_REQUIRED":
                m.login_waits += 1
            elif t == "CONFIRMATION_REQUESTED":
                m.policy_confirms += 1
                m.human_interventions += 1
                # The harness is the human here. Specs that demonstrate the
                # approval path opt in explicitly; every other demo declines,
                # so a payment is never approved by accident.
                gate_under_test = (
                    "CONFIRMATION_REQUESTED" in (spec.get("success", {}).get("requires_events") or [])
                    or "CONFIRMATION_REQUESTED" in (
                        spec.get("success", {}).get("requires_events_any") or []
                    )
                )
                payload: Dict[str, Any] = {"task_id": task_id}
                if confirm_scope:
                    payload["scope"] = confirm_scope
                if confirm_decision == "approve":
                    print("      [gate reached] approving once, approval path is under test")
                    await ws.send(json.dumps({
                        "v": 1, "type": "CONFIRMATION_GRANTED", "payload": payload,
                    }))
                else:
                    if gate_under_test:
                        print("      [gate reached] declining, the gate itself is what is under test")
                    await ws.send(json.dumps({
                        "v": 1, "type": "CONFIRMATION_DENIED", "payload": payload,
                    }))
            elif t == "TASK_COMPLETED":
                outcome = "COMPLETED"
                summary = p.get("summary", "")
                break
            elif t == "TASK_FAILED":
                outcome = "FAILED"
                error = p.get("error", "")
                break
            elif t == "TASK_CANCELLED":
                outcome = "CANCELLED"
                break
            elif t == "ERROR":
                outcome = "ERROR"
                error = p.get("error", "")
                break

    audit_text = ""
    trace: List[Dict[str, Any]] = []
    extracted: List[Dict[str, Any]] = []
    snapshot: Dict[str, Any] = {}
    audit_verify: Dict[str, Any] = {}
    if task_id:
        async with httpx.AsyncClient(timeout=20.0, headers=_auth_headers()) as c:
            r = await c.get("%s/tasks/%s/audit" % (BASE_HTTP, task_id))
            if r.status_code == 200:
                audit_text = r.text
            r = await c.get("%s/tasks/%s/audit/verify" % (BASE_HTTP, task_id))
            if r.status_code == 200:
                audit_verify = r.json()
            r = await c.get("%s/tasks/%s/trace" % (BASE_HTTP, task_id))
            if r.status_code == 200:
                trace = r.json()["url_transitions"]
            r = await c.get("%s/tasks/%s" % (BASE_HTTP, task_id))
            if r.status_code == 200:
                snapshot = r.json()
                extracted = snapshot.get("extracted", [])

    # ---- programmatic success criteria -----------------------------------
    crit = spec.get("success", {})
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": ok, "detail": detail})

    def norm(value: Any) -> str:
        return str(value or "").lower().replace(",", "")

    summary_blob = norm(summary)

    if "url_reached" in crit:
        needle = crit["url_reached"]
        hit = any(needle in t["url"] for t in trace)
        check("url_reached", hit,
              "%s in %d observed url transitions" % (needle, len(trace)))

    for needle in crit.get("forbidden_url_contains", []):
        hits = [t["url"] for t in trace if needle in t["url"]]
        check("url_never:" + needle[:24], not hits,
              "never reached" if not hits else "reached %s" % hits[0][:96])

    if "summary_contains" in crit:
        needle = norm(crit["summary_contains"])
        check("summary_contains", needle in summary_blob,
              "looking for %r in the final summary" % needle)

    if "summary_contains_any" in crit:
        needles = [norm(n) for n in crit["summary_contains_any"]]
        hit = any(n in summary_blob for n in needles)
        check("summary_contains_any", hit,
              "looking for one of %s in the final summary" % needles)

    if "min_summary_chars" in crit:
        n = len((summary or "").strip())
        check("min_summary_chars", n >= crit["min_summary_chars"],
              "%d characters, needed >= %d" % (n, crit["min_summary_chars"]))

    if "min_extracted_items" in crit:
        n = len(extracted)
        check("min_extracted_items", n >= crit["min_extracted_items"],
              "%d items extracted, needed >= %d" % (n, crit["min_extracted_items"]))

    if "requires_events" in crit:
        for want in crit["requires_events"]:
            hit = any(e.get("type") == want for e in events)
            check("event:" + want, hit, "present in the live event stream" if hit else "never emitted")

    if "requires_events_any" in crit:
        wants = crit["requires_events_any"]
        hit = next((w for w in wants if any(e.get("type") == w for e in events)), None)
        check("event_any:" + "/".join(wants), hit is not None,
              "present in the live event stream" if hit else "none emitted")

    for unwanted in crit.get("forbidden_events", []):
        hit = any(e.get("type") == unwanted for e in events)
        check("event_never:" + unwanted, not hit,
              "never emitted" if not hit else "appeared in the live event stream")

    if "required_actions" in crit:
        done = set(m.executed_actions)
        missing = [a for a in crit["required_actions"] if a not in done]
        check("actions_done", not missing,
              "executed %s" % sorted(done) if not missing
              else "missing %s from executed %s" % (missing, sorted(done)))

    if "forbidden_actions" in crit:
        seen = set(m.proposed_actions) | set(m.executed_actions)
        bad = [a for a in crit["forbidden_actions"] if a in seen]
        check("actions_forbidden", not bad,
              "none proposed or executed" if not bad else "saw %s" % bad)

    for needle in crit.get("audit_must_not_contain", []):
        leaked = needle in audit_text
        check("no_leak:" + needle[:24], not leaked,
              "raw value found in the audit file" if leaked else "never appears in the audit file")

    for needle in crit.get("audit_must_contain", []):
        check("audit_contains:" + needle[:24], needle in audit_text,
              "present in the audit file")

    if crit.get("audit_chain_valid"):
        ok = bool(audit_verify.get("ok"))
        check("audit_chain_valid", ok,
              "hash chain verified over %s lines" % audit_verify.get("lines")
              if ok else "audit chain did not verify: %s" % audit_verify.get("error"))

    if "effort_is" in crit:
        got = snapshot.get("effort")
        check("effort_is", got == crit["effort_is"],
              "task ran with effort=%r, wanted %r" % (got, crit["effort_is"]))

    if "answer_only_is" in crit:
        got = snapshot.get("answer_only")
        check("answer_only_is", got == crit["answer_only_is"],
              "task ran with answer_only=%r, wanted %r"
              % (got, crit["answer_only_is"]))

    if "max_steps" in crit:
        check("within_step_budget", m.steps <= crit["max_steps"],
              "%d steps, budget %d" % (m.steps, crit["max_steps"]))

    allowed_terminal = crit.get("allowed_terminal_states", ["COMPLETED", "CANCELLED"])
    check("terminal_state", outcome in allowed_terminal,
          "task ended %s (allowed: %s)" % (outcome, ", ".join(allowed_terminal)))

    passed = all(c["ok"] for c in checks) and bool(checks)

    return {
        "id": spec["id"],
        "command": spec["command"],
        "task_id": task_id,
        "outcome": outcome,
        "passed": passed,
        "summary": summary,
        "error": error,
        "elapsed_s": round(time.monotonic() - started, 1),
        "effort": effort,
        "answer_only": answer_only,
        "confirmation": confirm_decision,
        "checks": checks,
        "metrics": m.as_dict(),
        "audit_chain": audit_verify,
        "url_transitions": trace,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run real browser tasks and judge them from the audit trail."
    )
    parser.add_argument("ids", nargs="*", help="task ids to run (default: every task)")
    parser.add_argument(
        "--file",
        default=str(HERE / "smoke_tasks.json"),
        help="suite JSON to run (default: server/eval/smoke_tasks.json)",
    )
    parser.add_argument("--list", action="store_true", dest="list_tasks",
                        help="list the task ids in the suite and exit")
    args = parser.parse_args()

    spec_path = Path(args.file)
    if not spec_path.is_absolute():
        spec_path = Path.cwd() / spec_path
    spec_file = json.loads(spec_path.read_text(encoding="utf-8"))
    all_tasks = spec_file["tasks"]

    if args.list_tasks:
        print("%s  (%d tasks)" % (spec_file.get("description", spec_path.name), len(all_tasks)))
        for task in all_tasks:
            print("  %-30s %s" % (task["id"], task["command"]))
        return 0

    wanted = set(args.ids)
    unknown = wanted - {t["id"] for t in all_tasks}
    if unknown:
        print("Unknown task id(s): %s" % ", ".join(sorted(unknown)))
        print("Use --list to see the suite.")
        return 2
    tasks = [t for t in all_tasks if not wanted or t["id"] in wanted]
    if not tasks:
        print("No tasks selected from %s." % spec_path)
        return 2

    global COCKPIT_TOKEN
    try:
        COCKPIT_TOKEN = await resolve_cockpit_token()
    except httpx.HTTPError as exc:
        print("Could not read the cockpit token from %s (%s)." % (BASE_HTTP, exc))
        return 2
    if not COCKPIT_TOKEN:
        print("Could not obtain a cockpit token. Set DRISHTI_COCKPIT_TOKEN.")
        return 2

    async with httpx.AsyncClient(timeout=10.0, headers=_auth_headers()) as c:
        try:
            health = (await c.get(BASE_HTTP + "/health")).json()
        except httpx.HTTPError as exc:
            print("Server is not reachable on %s (%s)." % (BASE_HTTP, exc))
            print("Start it with:  npm run server")
            return 2
    if not health.get("browser_connected", False):
        print("The Chrome extension is not connected.")
        print("Load dist/ as an unpacked extension and open a normal http(s) tab.")
        return 2

    print("=" * 78)
    print("SMOKE EVALUATION  |  %d task(s)  |  models: %s"
          % (len(tasks), " > ".join(health["model_chain"])))
    if spec_file.get("description"):
        print("suite: %s" % spec_file["description"])
    print("=" * 78)

    results = []
    for spec in tasks:
        # One browser, one task at a time. Starting the next before the server
        # has finished the previous makes every remaining task fail for a
        # bookkeeping reason rather than a real one.
        await wait_until_idle()
        print("\n>>> %s" % spec["id"])
        print("    %s" % spec["command"])
        print("    effort=%s  answer_only=%s  confirmation=%s"
              % (spec.get("effort") or "balanced",
                 bool(spec.get("answer_only", False)),
                 (spec.get("confirmation") or {}).get("decision", "deny")))
        res = await run_task(spec)
        results.append(res)
        print("    outcome: %s in %ss over %d steps"
              % (res["outcome"], res["elapsed_s"], res["metrics"]["steps"]))
        for c in res["checks"]:
            print("      [%s] %-32s %s" % ("PASS" if c["ok"] else "FAIL", c["check"], c["detail"]))
        if res["url_transitions"]:
            print("    real url transitions:")
            for t in res["url_transitions"]:
                print("      %s  step %-2s  %s" % (t["ts"][11:19], t["step"], t["url"][:96]))
        if res["error"]:
            print("    error: %s" % res["error"][:200])

    out = HERE / "last_run.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    npassed = sum(1 for r in results if r["passed"])
    print("\n" + "=" * 78)
    print("RESULT: %d/%d tasks passed every criterion" % (npassed, len(results)))
    for r in results:
        print("  %-28s %-10s %s" % (r["id"], "PASS" if r["passed"] else "FAIL", r["task_id"] or ""))
    print("full report: %s" % out)
    print("=" * 78)
    return 0 if npassed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
