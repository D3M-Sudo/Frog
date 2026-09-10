#!/usr/bin/env python3
"""
build-aux/sync_dependencies.py

Synchronize the Python dependencies declared in the Flatpak manifests with the
canonical dependency sources of the project (pyproject.toml + uv.lock).

The Flatpak manifests (flatpak/*.json) hardcode Python packages (URL + sha256)
so that the sandboxed app can install them without network access. This script
guarantees zero drift between those hardcoded versions and the versions that
`uv` actually resolves for the project.

Usage:
    python3 build-aux/sync_dependencies.py --check    # detect drift (exit 1 if any)
    python3 build-aux/sync_dependencies.py --update   # fix drift by editing the manifests

Only the Python standard library is used, so no extra install is required.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = [
    REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.json",
    REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.local.json",
]
UV_LOCK = REPO_ROOT / "uv.lock"

PYPI_JSON_URL = "https://pypi.org/pypi/{name}/{version}/json"

# Flatpak module name → PyPI project name.
#
# NOTE: python3-certifi is intentionally NOT in this mapping.
# certifi is a transitive dependency of requests and is managed
# exclusively by FEDC via .github/workflows/flatpak-dependencies.yml.
# Adding it here would create dual ownership and potential drift.
MODULE_TO_PYPI: dict[str, str] = {
    "python3-charset-normalizer": "charset-normalizer",
    "python3-click": "click",
    "python3-gTTS": "gtts",
    "python3-idna": "idna",
    "python3-loguru": "loguru",
    "python3-packaging": "packaging",
    "python3-pathspec": "pathspec",
    "python3-pillow": "pillow",
    "python3-psutil": "psutil",
    "python3-pybind11": "pybind11",
    "python3-pytesseract": "pytesseract",
    "python3-requests": "requests",
    "python3-scikit-build-core": "scikit-build-core",
    "python3-urllib3": "urllib3",
    "python3-zxing-cpp": "zxing-cpp",
}

# Modules that are build-time only (not runtime) and therefore NOT present in
# uv.lock. They are managed by flatpak-external-data-checker (x-checker-data)
# instead of the uv.lock-based sync.
BUILD_DEPS_OVERRIDES: frozenset[str] = frozenset(
    {
        "python3-pybind11",
        "python3-scikit-build-core",
    }
)

_STATUS_OK = "OK"
_STATUS_DRIFT = "DRIFT"
_STATUS_UPDATE = "UPDATE"
_STATUS_SKIP = "SKIP"
_STATUS_ERROR = "ERROR"


def parse_uv_lock(path: Path) -> dict[str, str]:
    """Return {package name: version} from a uv.lock file."""
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return {pkg["name"]: pkg["version"] for pkg in data.get("package", [])}


def extract_version_from_url(url: str, pypi_name: str) -> str | None:
    """Extract the pinned version from a Flatpak source URL.

    Handles both sdist archives (``charset_normalizer-3.4.7.tar.gz``) and
    wheels (``packaging-3.29.0-py3-none-any.whl``), tolerating either ``-``
    or ``_`` as a name separator.
    """
    basename = url.rstrip("/").rsplit("/", 1)[-1]
    name_norm = pypi_name.replace("-", "_")
    # Names like "gTTS" appear with case variations in filenames.
    pattern = re.compile(
        rf"^{re.escape(name_norm)}[_-]([0-9][0-9a-zA-Z_.]*?)"
        r"(?:[_-]py3(?:[_-]none[_-]any)?)?"
        r"\.(?:tar\.gz|tar\.bz2|tar\.xz|zip|whl)$",
        re.IGNORECASE,
    )
    match = pattern.match(basename)
    return match.group(1) if match else None


def fetch_pypi_release(name: str, version: str) -> dict[str, Any]:
    """Query the PyPI JSON API for a specific release."""
    url = PYPI_JSON_URL.format(name=name, version=version)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"PyPI returned HTTP {exc.code} for {name}=={version}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot reach PyPI for {name}=={version}: {exc.reason}") from exc


def select_release_file(release: dict[str, Any], *, prefer_wheel: bool) -> dict[str, Any] | None:
    """Pick the artifact that best matches the manifest source type."""
    files = release.get("urls") or []
    if prefer_wheel:
        pure_wheels = [
            f
            for f in files
            if f.get("filename", "").endswith(".whl") and "py3-none-any" in f["filename"]
        ]
        if pure_wheels:
            return sorted(pure_wheels, key=lambda f: f["filename"])[0]
        any_wheels = [f for f in files if f.get("filename", "").endswith(".whl")]
        if any_wheels:
            return sorted(any_wheels, key=lambda f: len(f["filename"]))[0]
    sdists = [f for f in files if f.get("filename", "").endswith(".tar.gz")]
    if sdists:
        return sorted(sdists, key=lambda f: f["filename"])[0]
    return None


def module_uses_wheel(module: dict[str, Any]) -> bool:
    sources = module.get("sources") or []
    return bool(sources and sources[0].get("type") == "file")


def current_source_filename(module: dict[str, Any]) -> str:
    sources = module.get("sources") or []
    if not sources:
        return ""
    url = sources[0].get("url", "")
    return url.rstrip("/").rsplit("/", 1)[-1]


def has_x_checker_data(module: dict[str, Any]) -> bool:
    sources = module.get("sources") or []
    return bool(sources and "x-checker-data" in sources[0])


def ensure_x_checker_data(module: dict[str, Any], pypi_name: str) -> bool:
    """Add x-checker-data to a module that lacks it. Returns True if a change was made."""
    if has_x_checker_data(module):
        return False
    sources = module.get("sources") or []
    if not sources:
        return False
    sources[0]["x-checker-data"] = {
        "type": "pypi",
        "name": pypi_name,
    }
    return True


def sync_manifest(
    manifest_path: Path,
    uv_pkgs: dict[str, str],
    *,
    check_only: bool,
) -> dict[str, int]:
    """Verify or update a single Flatpak manifest. Returns a status counter."""
    stats = {
        _STATUS_OK: 0,
        _STATUS_DRIFT: 0,
        _STATUS_UPDATE: 0,
        _STATUS_SKIP: 0,
        _STATUS_ERROR: 0,
    }
    print(f"\n=== {manifest_path.relative_to(REPO_ROOT)} ===")
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[{_STATUS_ERROR}] Cannot read manifest: {exc}")
        stats[_STATUS_ERROR] += 1
        return stats

    changed = False
    for module in manifest.get("modules", []):
        name = module.get("name", "")
        pypi_name = MODULE_TO_PYPI.get(name)
        if pypi_name is None:
            continue  # Not a Python module (leptonica, tesseract, imlib2, ...)

        # ── Build-time-only dependencies (not tracked by uv.lock) ────────────
        if name in BUILD_DEPS_OVERRIDES:
            if has_x_checker_data(module):
                print(f"[{_STATUS_OK}]   {name:<30} build dep (managed by FEDC)")
                stats[_STATUS_OK] += 1
            elif check_only:
                print(
                    f"[{_STATUS_DRIFT}] {name:<30} build dep without x-checker-data "
                    "(run --update to add it)"
                )
                stats[_STATUS_DRIFT] += 1
            else:
                ensure_x_checker_data(module, pypi_name)
                print(f"[{_STATUS_UPDATE}] {name:<30} added x-checker-data")
                stats[_STATUS_UPDATE] += 1
                changed = True
            continue

        # ── Runtime / transitive dependencies (tracked by uv.lock) ───────────
        expected = uv_pkgs.get(pypi_name)
        if expected is None:
            print(f"[{_STATUS_ERROR}] {name:<30} {pypi_name} not found in uv.lock")
            stats[_STATUS_ERROR] += 1
            continue

        sources = module.get("sources") or []
        if not sources:
            print(f"[{_STATUS_ERROR}] {name:<30} has no sources")
            stats[_STATUS_ERROR] += 1
            continue
        source = sources[0]
        url = source.get("url", "")
        current = extract_version_from_url(url, pypi_name)
        if current is None:
            print(f"[{_STATUS_ERROR}] {name:<30} cannot parse version from {url}")
            stats[_STATUS_ERROR] += 1
            continue

        if current == expected:
            print(f"[{_STATUS_OK}]   {name:<30} {current} ✓")
            stats[_STATUS_OK] += 1
            continue

        if check_only:
            print(f"[{_STATUS_DRIFT}] {name:<30} manifest={current} uv.lock={expected}")
            stats[_STATUS_DRIFT] += 1
            continue

        # ── Perform the update ───────────────────────────────────────────────
        prefer_wheel = module_uses_wheel(module)
        try:
            release = fetch_pypi_release(pypi_name, expected)
        except RuntimeError as exc:
            print(f"[{_STATUS_ERROR}] {name:<30} {exc}")
            stats[_STATUS_ERROR] += 1
            continue
        artifact = select_release_file(release, prefer_wheel=prefer_wheel)
        if artifact is None:
            print(
                f"[{_STATUS_ERROR}] {name:<30} no matching artifact for "
                f"{pypi_name}=={expected} ({'wheel' if prefer_wheel else 'sdist'})"
            )
            stats[_STATUS_ERROR] += 1
            continue

        old_filename = current_source_filename(module)
        new_filename = artifact["filename"]
        source["url"] = artifact["url"]
        source["sha256"] = artifact["digests"]["sha256"]

        # Update any build-command that references the old file name (wheels).
        build_commands = module.get("build-commands", [])
        for i, cmd in enumerate(build_commands):
            if old_filename and old_filename in cmd:
                build_commands[i] = cmd.replace(old_filename, new_filename)

        print(f"[{_STATUS_UPDATE}] {name:<30} {current} → {expected} ({new_filename})")
        stats[_STATUS_UPDATE] += 1
        changed = True

    if changed:
        with manifest_path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(manifest, indent=4) + "\n")
        print(f"   → {manifest_path.relative_to(REPO_ROOT)} updated")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check or update the Flatpak Python dependencies against "
            "uv.lock / pyproject.toml."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="detect drift, exit non-zero if found")
    mode.add_argument("--update", action="store_true", help="apply updates to the manifests")
    args = parser.parse_args()

    if not UV_LOCK.exists():
        print(f"ERROR: {UV_LOCK} not found. Run `uv lock` first.", file=sys.stderr)
        return 2

    uv_pkgs = parse_uv_lock(UV_LOCK)

    totals: dict[str, int] = {}
    for manifest_path in MANIFESTS:
        if not manifest_path.exists():
            print(f"[{_STATUS_ERROR}] {manifest_path} not found", file=sys.stderr)
            totals[_STATUS_ERROR] = totals.get(_STATUS_ERROR, 0) + 1
            continue
        stats = sync_manifest(manifest_path, uv_pkgs, check_only=args.check)
        for key, value in stats.items():
            totals[key] = totals.get(key, 0) + value

    print("\n=== Summary ===")
    print(f"  OK:        {totals.get(_STATUS_OK, 0)}")
    print(f"  Drift:     {totals.get(_STATUS_DRIFT, 0)}")
    print(f"  Updated:   {totals.get(_STATUS_UPDATE, 0)}")
    print(f"  Errors:    {totals.get(_STATUS_ERROR, 0)}")

    if totals.get(_STATUS_ERROR, 0) or totals.get(_STATUS_DRIFT, 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
