"""The built Chrome extension must be loadable — verified, not assumed.

`infra/build-extension.cjs` already gates this at build time. These tests exist
because a build script that is correct today can be broken tomorrow by an
ordinary edit, and the failure mode is silent: Chrome loads a directory whose
manifest points at files that are not there, or whose imports escape the
artifact, and the extension simply does nothing.

That is not a hypothetical here. The first build of this extension emitted
`../../../packages/...` from `offscreen/offscreen.js`, which resolved fine in a
developer's checkout and pointed outside `dist-extension` once loaded. The build
reported success. These assertions are the ones that would have caught it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "dist-extension"

pytestmark = pytest.mark.skipif(
    not (ARTIFACT / "manifest.json").exists(),
    reason="extension not built. Run: npm run build:extension",
)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_targets_manifest_version_3(manifest: dict) -> None:
    assert manifest["manifest_version"] == 3


def test_every_file_the_manifest_names_exists(manifest: dict) -> None:
    """The load-blocking failure: a manifest pointing at a missing file."""
    targets = [
        manifest["background"]["service_worker"],
        *manifest["content_scripts"][0]["js"],
        # The worker statically imports the privacy core, so every module it
        # reaches must ship. A missing one is a load-blocking 404 that only
        # appears when Chrome evaluates the worker.
        "packages/gateway/guard.js",
        "packages/privacy/vault.js",
        "packages/privacy/detector.js",
        "packages/pipeline/orchestrator.js",
    ]
    missing = [t for t in targets if not (ARTIFACT / t).exists()]
    assert not missing, f"manifest names files that are absent: {missing}"


def test_service_worker_is_declared_as_a_module(manifest: dict) -> None:
    """The worker imports the message protocol, so it must load as ESM."""
    assert manifest["background"]["type"] == "module"


def test_content_script_is_a_classic_script_with_no_imports() -> None:
    """SEC-BOUND-001 §3: the content script must have no module graph at all.

    It runs in the page's world. If it could import anything, it would have a
    channel back toward the vault, and the B-6 binding would stop being a
    boundary.
    """
    source = (ARTIFACT / "content" / "content.js").read_text(encoding="utf-8")
    assert "import " not in source
    assert "require(" not in source


def test_the_service_worker_is_the_single_privacy_boundary() -> None:
    """Z1 is the service worker, and it is the ONLY runtime importer of the core.

    This test previously asserted the opposite -- that the worker had zero
    runtime imports and reached the privacy core by message. That design put the
    core behind an offscreen document, whose module evaluation races
    `createDocument()`, and it produced two separate "Receiving end does not
    exist" failures.

    The invariant that actually protects privacy is UNCHANGED and is what is
    asserted here: the content script must still import nothing, so page content
    has exactly one route inward and one owner.
    """
    content = (ARTIFACT / "content" / "content.js").read_text(encoding="utf-8")
    content_specs = [
        s
        for group in re.findall(r"""from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)""", content)
        for s in group
        if s
    ]
    assert content_specs == [], (
        f"the content script must import nothing; found {content_specs}"
    )

    # And the worker must be the only place the core is reached from.
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    assert "packages/gateway/guard.js" in worker, (
        "the worker is no longer the privacy boundary; something else is, and "
        "this test is asserting a stale design"
    )


def test_pixel_blindness_is_declared_not_hidden() -> None:
    """A worker has no `document`, so it cannot rasterise page pixels.

    The honest behaviour is to hand the pipeline no frames, let it derive the right
    state from `visualSurfaces`, and tell the operator which state it landed on and
    why. The dishonest behaviour - and the v1 defect - is to pass an empty scan off
    as verified.

    Asserted on substance rather than an exact phrase. Matching a literal string
    meant a harmless rewording of the tooltip broke the test, which is precisely
    the wrong incentive to hand a test.
    """
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    assert "captureFrames: () => []" in worker, (
        "the worker fabricates frames; a service worker has no document and "
        "cannot produce pixels"
    )
    lowered = worker.lower()
    # Concepts, not phrases. Checking for a contiguous sentence is brittle by
    # construction: TypeScript splits these across adjacent string literals, so
    # the phrase never appears verbatim in the built file even when the tooltip
    # reads perfectly in the UI.
    for concept in ("painted", "inspected", "degraded"):
        assert concept in lowered, (
            f"pixel blindness is not disclosed to the operator ({concept})"
        )


def test_the_offscreen_document_is_gone() -> None:
    """The offscreen route was removed deliberately, not by accident.

    A half-removed offscreen path is worse than either design: it looks present
    and still races. Its absence from the artifact is the thing to assert.
    """
    assert not (ARTIFACT / "offscreen").exists(), (
        "an offscreen directory remains in the artifact; the offscreen route was "
        "removed because its module evaluation races createDocument()"
    )
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    assert "offscreen" not in manifest["permissions"], (
        "the offscreen permission is still requested but nothing uses it"
    )


def test_extension_declares_no_network_egress() -> None:
    """The egress guarantee is a property of the CODE, not of a CSP string.

    This test used to assert `connect-src 'none'` was present. That directive is
    NOT valid in an MV3 `extension_pages` policy: Chrome rejects such a manifest
    outright at install time with "Invalid value for
    'content_security_policy.extension_pages'". Edge accepted the same manifest,
    so a local run looked perfectly healthy while the extension would not load in
    Chrome at all.

    The guarantee is therefore asserted where it can actually hold: no network API
    appears anywhere in the shipped code. That is stronger than the CSP string was
    - the CSP forbade connections the code never attempted anyway.
    """
    banned = ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "navigator.sendBeacon", "importScripts")
    offenders = []
    for path in ARTIFACT.rglob("*.js"):
        source = path.read_text(encoding="utf-8")
        for needle in banned:
            if needle in source:
                offenders.append(f"{path.relative_to(ARTIFACT)} references {needle}")
    assert not offenders, f"network egress is reachable in the artifact: {offenders}"


def test_the_csp_uses_only_directives_mv3_permits() -> None:
    """MV3 permits exactly `script-src` and `object-src` for extension pages.

    Any other directive is an install-time manifest error in Chrome, which reads
    as "the extension will not load" rather than as a CSP problem. This is
    asserted so the exact mistake that caused a long debugging detour cannot come
    back unnoticed.
    """
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    csp = manifest["content_security_policy"]["extension_pages"]
    directives = [d.split()[0] for d in csp.split(";") if d.strip()]
    permitted = {"script-src", "object-src"}
    assert set(directives) <= permitted, (
        f"MV3 extension_pages permits only {sorted(permitted)}; found {directives}"
    )


def test_nothing_is_exposed_to_web_pages() -> None:
    """web_accessible_resources must stay empty: no page may script our code."""
    manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["web_accessible_resources"] == []


def test_every_relative_import_resolves_inside_the_artifact() -> None:
    """The check that would have caught the escaping-specifier defect."""
    specifier = re.compile(r"""from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)""")
    problems: list[str] = []

    for path in ARTIFACT.rglob("*.js"):
        for match in specifier.finditer(path.read_text(encoding="utf-8")):
            spec = match.group(1) or match.group(2)
            if not spec or not spec.startswith("."):
                continue
            resolved = (path.parent / spec).resolve()
            try:
                resolved.relative_to(ARTIFACT.resolve())
            except ValueError:
                problems.append(f"{path.relative_to(ARTIFACT)} imports {spec} (escapes)")
                continue
            if not resolved.exists():
                problems.append(f"{path.relative_to(ARTIFACT)} imports {spec} (missing)")

    assert not problems, problems


def test_the_privacy_core_ships_with_the_extension() -> None:
    """The offscreen document cannot import what was not packaged."""
    for required in (
        "packages/pipeline/orchestrator.js",
        "packages/gateway/guard.js",
        "packages/privacy/vault.js",
        "packages/privacy/detector.js",
        "packages/privacy/pixels.js",
        "packages/privacy/sanitizer.js",
        "packages/vision/capability/ladder.js",
        "packages/taxonomy/generated/entities.js",
    ):
        assert (ARTIFACT / required).exists(), f"{required} did not ship"


def test_only_one_copy_of_the_privacy_core_is_packaged() -> None:
    """Two copies invite loading the wrong one."""
    stray = list(ARTIFACT.glob("apps/**/*.js"))
    assert not stray, f"tsc's intermediate tree was not removed: {stray}"


# -- message routing, which only fails at runtime ─────────────────────────────


def test_the_worker_asks_the_content_script_to_collect() -> None:
    """The bug that made the extension do nothing on first load.

    `chrome.action.onClicked` called `chrome.tabs.sendMessage`, which reaches
    CONTENT SCRIPTS - and the content script had no listener. Chrome threw
    "Could not establish connection. Receiving end does not exist" and the
    extension silently did nothing.

    Two halves: the worker must ASK, and the content script must ANSWER.
    """
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    content = (ARTIFACT / "content" / "content.js").read_text(encoding="utf-8")

    assert "tabs.sendMessage" in worker, (
        "the worker never asks the content script to collect; clicking the "
        "toolbar cannot reach page content"
    )
    assert "onMessage" in content, (
        "the content script has no message listener, so the worker's request "
        "has no receiving end"
    )
    # And the message it asks for must be the one the script handles.
    assert "COLLECT" in worker and "COLLECT" in content


def test_the_worker_does_not_collect_on_page_load() -> None:
    """FR-AGT-7: a content script that reads every visited page is the opposite
    of a privacy tool. Collection must begin only on an explicit user action."""
    content = (ARTIFACT / "content" / "content.js").read_text(encoding="utf-8")
    assert "onMessage" in content
    # The collection must be inside the listener, not at top level. A top-level
    # sendMessage on load is the defect this replaced.
    assert "runtime.onMessage" in content


def test_no_message_is_sent_to_a_context_that_does_not_exist() -> None:
    """The remaining message hop must be one that provably has a receiver.

    `runtime.sendMessage` from the worker reaches EXTENSION PAGES. With the
    offscreen document gone there are none, so every such send is a guaranteed
    "Receiving end does not exist". `tabs.sendMessage` reaches CONTENT SCRIPTS,
    which do exist and are asserted to have a listener.
    """
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    # Match the CALL, not the words. The file's own documentation explains the
    # runtime/tabs distinction, so a naive substring check matches the comment
    # describing the thing it is trying to prove absent. A test that fails on
    # its own documentation teaches everyone to ignore it.
    assert "chrome.runtime.sendMessage(" not in worker, (
        "the worker still messages extension pages, but no extension page "
        "exists to receive them"
    )
    assert "chrome.tabs.sendMessage(" in worker, (
        "the worker must reach the content script, which is the only remaining "
        "message target"
    )


def test_a_missing_collector_is_injected_not_merely_reported() -> None:
    """A tab open before the install must be recoverable, not just explained.

    Declarative content scripts are injected at PAGE LOAD, so a stale tab has no
    receiver and `tabs.sendMessage` fails with the same generic sentence Chrome
    uses for every unreachable context. Telling the user to press F5 is a
    workaround; injecting the collector is the fix.
    """
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    assert "scripting.executeScript" in worker, (
        "the worker cannot inject the collector into a stale tab"
    )
    assert "'content/content.js'" in worker, (
        "injection does not name the collector file the artifact actually ships"
    )
    # And the refusal case must be named, not guessed at.
    assert "cannot be scripted" in worker, (
        "an unscrutable page type is not reported as such"
    )


def test_a_rejected_badge_cannot_mask_the_real_error() -> None:
    """Reporting a failure must not become a second, louder failure.

    A `setBadgeText` rejection inside a catch block produces a NEW unhandled
    rejection, which replaces the real diagnostic with "Uncaught (in promise)".
    That is how a collection failure presented as a message-routing failure.
    """
    worker = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    assert "reportFailure" in worker, "failures are not funnelled through one helper"
    # The helper must guard its own chrome calls.
    assert worker.count("could not set the badge") >= 1, (
        "the badge path is unguarded, so a failure there masks the real error"
    )
