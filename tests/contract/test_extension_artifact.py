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
        "offscreen/offscreen.html",
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


def test_the_service_worker_imports_no_privacy_module() -> None:
    """DP-2 / SEC-BOUND-001 §3: the coordinator reaches Z1 by message only.

    Asserted over IMPORT SPECIFIERS, not over the file's text. An earlier
    version of this test grepped for the word "vault" and failed on the
    docstring that says the worker holds no vault - a false positive that would
    have taught everyone to ignore it.
    """
    source = (ARTIFACT / "background" / "service-worker.js").read_text(encoding="utf-8")
    specifiers = re.findall(r"""from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)""", source)
    imported = [s for group in specifiers for s in group if s]

    assert imported == ["./messages.js"], (
        f"the service worker must import only its message protocol, found {imported}"
    )
    for forbidden in ("vault", "detector", "redactor", "sanitizer", "orchestrator", "pixels"):
        assert not any(forbidden in spec for spec in imported), (
            f"the service worker imports a Z1 module: {imported}"
        )


def test_extension_declares_no_network_egress() -> None:
    """connect-src 'none' means there is no code path to a remote origin."""
    csp = ARTIFACT_MANIFEST_CSP = json.loads(
        (ARTIFACT / "manifest.json").read_text(encoding="utf-8")
    )["content_security_policy"]["extension_pages"]
    assert "connect-src 'none'" in ARTIFACT_MANIFEST_CSP


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
