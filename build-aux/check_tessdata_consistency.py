#!/usr/bin/env python3
# build-aux/check_tessdata_consistency.py
"""Check tessdata commit SHA consistency across configuration files.

Verifies that the tessdata commit SHAs are consistent between:
- anura/config.py (TESSDATA_BEST_URL)
- flatpak/io.github.d3msudo.anura.json (tessdata module sources)
- flatpak/io.github.d3msudo.anura.local.json (tessdata module sources)

The tessdata module in the Flatpak manifests uses tessdata_fast URLs
with a specific commit SHA that must match TESSDATA_BEST_URL in config.py.
"""

import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PY = REPO_ROOT / "anura" / "config.py"
MANIFEST_MAIN = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.json"
MANIFEST_LOCAL = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.local.json"

# Regex to extract commit SHA from tessdata GitHub URLs
# Matches patterns like: tessdata_fast/raw/<commit_sha>/filename
TESSDATA_URL_PATTERN = re.compile(
    r"github\.com/tesseract-ocr/tessdata[^/]*/raw/([a-f0-9]{40})/"
)

# Regex to extract commit SHA from config.py TESSDATA_BEST_URL
CONFIG_TESSDATA_PATTERN = re.compile(
    r"TESSDATA_BEST_URL\s*=\s*[\"']https?://[^\"']*/raw/([a-f0-9]{40})/"
)


def extract_sha_from_config(config_path: Path) -> str | None:
    """Extract the tessdata commit SHA from config.py TESSDATA_BEST_URL."""
    content = config_path.read_text()
    match = CONFIG_TESSDATA_PATTERN.search(content)
    return match.group(1) if match else None


def extract_shas_from_manifest(manifest_path: Path) -> list[str]:
    """Extract tessdata commit SHAs from manifest tessdata module sources."""
    data = json.loads(manifest_path.read_text())
    shas = []

    for module in data.get("modules", []):
        if module.get("name") != "tessdata":
            continue
        for source in module.get("sources", []):
            url = source.get("url", "")
            match = TESSDATA_URL_PATTERN.search(url)
            if match:
                shas.append(match.group(1))

    return shas


def main() -> int:
    """Check tessdata consistency. Returns 0 if consistent, 1 if drift detected."""
    errors: list[str] = []

    # Extract SHAs from config.py
    config_sha = extract_sha_from_config(CONFIG_PY)
    if config_sha is None:
        print(f"ERROR: Could not extract TESSDATA_BEST_URL SHA from {CONFIG_PY}", file=sys.stderr)
        return 2

    # Extract SHAs from manifests
    main_shas = extract_shas_from_manifest(MANIFEST_MAIN)
    local_shas = extract_shas_from_manifest(MANIFEST_LOCAL)

    if not main_shas:
        print(f"ERROR: No tessdata SHAs found in {MANIFEST_MAIN}", file=sys.stderr)
        return 2

    if not local_shas:
        print(f"ERROR: No tessdata SHAs found in {MANIFEST_LOCAL}", file=sys.stderr)
        return 2

    # Get unique SHAs from each source
    unique_main = set(main_shas)
    unique_local = set(local_shas)

    # Check consistency
    if unique_main != unique_local:
        errors.append("Main vs Local manifest tessdata SHA mismatch:")
        errors.append(f"  main:  {unique_main}")
        errors.append(f"  local: {unique_local}")

    if config_sha not in unique_main:
        errors.append(f"config.py TESSDATA_BEST_URL SHA ({config_sha}) not found in main manifest tessdata sources")

    if config_sha not in unique_local:
        errors.append(f"config.py TESSDATA_BEST_URL SHA ({config_sha}) not found in local manifest tessdata sources")

    if errors:
        print("FAIL: Tessdata consistency check failed")
        for error in errors:
            print(f"  {error}")
        return 1

    print(f"PASS: Tessdata SHAs are consistent (commit: {config_sha[:12]}...)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
