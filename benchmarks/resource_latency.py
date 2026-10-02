"""SIH26171 — Resource and latency benchmark.

Scores the 20% "client resources" and 15% "latency" rubric weights together,
because on this system they are the same measurement: the privacy core's cost is
both what it spends and how long it takes.

── What these numbers are, and are not ───────────────────────────────────────
They are Node.js numbers for the CPU privacy core, produced by
`tests/vision/run-resources.cjs`. They are NOT Chrome extension-process numbers
and NOT inference numbers. The benchmark prints both gaps in its output.

That distinction matters because the obvious mistake here is to quote a CPU
figure as if it were the client's latency. A pixel mask over a 320x120 region
taking ~31 ms says nothing about a WebGPU model over a 4K frame, and claiming it
would be the v1 pattern of measuring the wrong stack.

── What it already found ────────────────────────────────────────────────────
The first run showed the pixel path costs ~300x the text path (31.5 ms versus
0.1 ms median). That is not a defect - it is the shape of the system, and it
means the latency budget is a PIXEL budget. The per-stage breakdown exists so
that claim stays checkable instead of becoming folklore.

Usage
-----
    python benchmarks/resource_latency.py
    python benchmarks/resource_latency.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "vision" / "run-resources.cjs"
ORCHESTRATOR_JS = ROOT / "dist" / "packages" / "pipeline" / "orchestrator.js"

# Budgets are deliberately GENEROUS. They exist to catch an order-of-magnitude
# regression, not to certify a performance target that was never baselined on
# real hardware. Publishing a tight number here would be inventing a target.
BUDGET_E2E_P95_MS = 250.0
BUDGET_STAGE_P95_MS = 150.0
BUDGET_ENVELOPE_KB = 64.0
BUDGET_FRAME_KB = 4096.0

NOT_MEASURED = [
    {
        "route": "chrome_extension_process",
        "why": "heap here is Node's. A Chrome extension has a separate JS heap, "
        "a renderer process per tab, and an offscreen document; none of that is "
        "represented by this harness.",
        "status": "UNIMPLEMENTED - needs chrome://memory or the DevTools "
        "Performance panel against the loaded extension",
        "affects": "the 20% client-resources weight, in full",
    },
    {
        "route": "inference_latency",
        "why": "CR-003 ships no model weights, so there is no WebGPU or WASM "
        "inference to time. The ladder reports webgpu as UNAVAILABLE on this "
        "host rather than assuming it.",
        "status": "UNIMPLEMENTED - blocked on weight acquisition (see "
        "DES-ARCH-001 acquisition plan)",
        "affects": "the 15% latency weight, for any rung above dom-only",
    },
    {
        "route": "dom_and_range_cost",
        "why": "collectTextRuns() calls Range.getClientRects(), whose cost is "
        "layout-dependent and only meaningful in a browser. The benchmark "
        "measures the binder on supplied rectangles instead.",
        "status": "PROXY - binding logic is measured, layout cost is not",
        "affects": "both weights, for pages with many text nodes",
    },
]


def run_harness() -> dict:
    if not ORCHESTRATOR_JS.exists():
        raise SystemExit(f"{ORCHESTRATOR_JS} is missing. Run: npm run build:parity")
    # --expose-gc makes the heap-delta figure meaningful. Without it the number
    # is dominated by uncollected garbage and would be noise dressed as data.
    completed = subprocess.run(
        ["node", "--expose-gc", str(RUNNER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if completed.returncode != 0:
        raise SystemExit(f"resource harness failed:\n{completed.stderr}")
    return json.loads(completed.stdout)


def to_scorecard(raw: dict) -> dict:
    def ms(sample: dict, key: str) -> float:
        return round(sample[key] / 1000.0, 3)

    stages = {
        name: {
            "median_ms": ms(sample, "median_us"),
            "p95_ms": ms(sample, "p95_us"),
            "max_ms": ms(sample, "max_us"),
        }
        for name, sample in raw["components"].items()
    }
    e2e = {
        rung: {
            "median_ms": ms(sample, "median_us"),
            "p95_ms": ms(sample, "p95_us"),
            "max_ms": ms(sample, "max_us"),
        }
        for rung, sample in raw["end_to_end"].items()
    }

    # Which stage dominates, stated rather than left for the reader to find.
    slowest = max(stages.items(), key=lambda kv: kv[1]["p95_ms"])

    fp = raw["footprint"]
    return {
        "benchmark": "resource_latency",
        "environment": raw["environment"],
        "end_to_end": e2e,
        "stages": stages,
        "ladder_probe": {
            "median_ms": ms(raw["ladder_probe"], "median_us"),
            "p95_ms": ms(raw["ladder_probe"], "p95_us"),
            "resolved_rung": raw["ladder_probe"]["resolved_rung"],
        },
        "dominant_stage": {"stage": slowest[0], "p95_ms": slowest[1]["p95_ms"]},
        "footprint": {
            **fp,
            "frame_buffer_kb": fp["frame_buffer_kb"],
            "envelope_kb": round(fp["envelope_bytes"] / 1024, 2),
            "vault_heap_kb_per_observation": round(fp["heap_delta_kb"] / 50, 2),
        },
        "budgets": {
            "e2e_p95_ms": BUDGET_E2E_P95_MS,
            "stage_p95_ms": BUDGET_STAGE_P95_MS,
            "envelope_kb": BUDGET_ENVELOPE_KB,
            "frame_kb": BUDGET_FRAME_KB,
        },
        "not_measured": NOT_MEASURED,
    }



def render(card: dict) -> str:
    out: list[str] = []
    add = out.append
    env = card["environment"]
    add("=" * 78)
    add("SIH26171 - RESOURCE & LATENCY BENCHMARK")
    add("=" * 78)
    add(
        f"host: node {env['node']}  {env['platform']}/{env['arch']}  "
        f"{env['cpu_count']} cpus"
    )
    add(f"iterations: {env['iterations']} (warmup {env['warmup']})")
    add("")
    add("NOTE: these are Node numbers for the CPU privacy core. They are NOT")
    add("Chrome extension numbers and NOT inference numbers. See NOT MEASURED.")
    add("")

    add("--- END-TO-END PIPELINE (ms) ---")
    add("  rung         median      p95      max   budget(p95)")
    for rung, s in card["end_to_end"].items():
        flag = "ok" if s["p95_ms"] <= card["budgets"]["e2e_p95_ms"] else "OVER"
        add(
            f"  {rung:<12}{s['median_ms']:>7.2f}{s['p95_ms']:>9.2f}"
            f"{s['max_ms']:>9.2f}{card['budgets']['e2e_p95_ms']:>14.0f}  {flag}"
        )
    add("")

    add("--- PER-STAGE (ms) ---")
    add("  stage                median      p95      max   budget(p95)")
    for name, s in card["stages"].items():
        flag = "ok" if s["p95_ms"] <= card["budgets"]["stage_p95_ms"] else "OVER"
        add(
            f"  {name:<20}{s['median_ms']:>7.2f}{s['p95_ms']:>9.2f}"
            f"{s['max_ms']:>9.2f}{card['budgets']['stage_p95_ms']:>14.0f}  {flag}"
        )
    dom = card["dominant_stage"]
    add("")
    add(f"  dominant stage: {dom['stage']} at {dom['p95_ms']:.2f} ms p95.")
    add("  The latency budget on this system is a PIXEL budget, not a text one.")
    add("")

    probe = card["ladder_probe"]
    add("--- CAPABILITY LADDER ---")
    add(
        f"  probe p95 {probe['p95_ms']:.3f} ms; resolved "
        f"{probe['resolved_rung']!r} on this host (webgpu correctly UNAVAILABLE)"
    )
    add("")

    fp = card["footprint"]
    add("--- FOOTPRINT ---")
    add(
        f"  frame buffer      {fp['frame_buffer_kb']} KB "
        f"(budget {card['budgets']['frame_kb']:.0f})"
    )
    add(
        f"  outbound envelope {fp['envelope_kb']} KB "
        f"(budget {card['budgets']['envelope_kb']:.0f})"
    )
    add(f"  vault entries/obs {fp['vault_entries_per_observation']}")
    add(
        f"  heap/observation  {fp['vault_heap_kb_per_observation']} KB "
        f"(Node heap, NOT Chrome)"
    )
    add(f"  model weights     {fp['model_weights_bytes']} bytes  (no weights shipped)")
    add("")

    add("--- NOT MEASURED (declared, not omitted) ---")
    for item in card["not_measured"]:
        add(f"  {item['route']}")
        add(f"    status : {item['status']}")
        add(f"    affects: {item['affects']}")
    add("=" * 78)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SIH26171 resource/latency")
    parser.add_argument("--json", action="store_true", help="emit a scorecard")
    args = parser.parse_args(argv)

    card = to_scorecard(run_harness())
    print(json.dumps(card, indent=2) if args.json else render(card))

    budgets = card["budgets"]
    over_budget = [
        s["p95_ms"] > budgets["e2e_p95_ms"] for s in card["end_to_end"].values()
    ] + [s["p95_ms"] > budgets["stage_p95_ms"] for s in card["stages"].values()]
    ok = (
        not any(over_budget)
        and card["footprint"]["envelope_kb"] <= budgets["envelope_kb"]
        and card["footprint"]["frame_buffer_kb"] <= budgets["frame_kb"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
