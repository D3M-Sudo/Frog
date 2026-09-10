#!/usr/bin/env python3
# build-aux/check_manifest_consistency.py
"""Check dependency consistency between Flatpak manifests.

Detects drift between anura.json and anura.local.json for all
shared Python modules. Exits non-zero if inconsistencies are found.

Intentional differences are ignored:
- anura application module (source differs: git vs dir)
- x-checker-data fields
"""

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_MAIN = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.json"
MANIFEST_LOCAL = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.local.json"

# Fields that may intentionally differ between manifests
IGNORED_FIELDS = {"x-checker-data"}

# Modules that are intentionally different
IGNORED_MODULES = {"anura"}


def get_python_modules(manifest_path: Path) -> dict[str, dict]:
    """Extract Python modules with their normalized sources.

    Returns {module_name: normalized_source_dict}.
    """
    data = json.loads(manifest_path.read_text())
    modules: dict[str, dict] = {}

    for module in data.get("modules", []):
        name = module.get("name", "")
        if not name.startswith("python3-") or name in IGNORED_MODULES:
            continue

        sources = module.get("sources", [])
        if not sources:
            continue

        # Normalize source by removing intentionally different fields
        source = {k: v for k, v in sources[0].items() if k not in IGNORED_FIELDS}
        modules[name] = source

    return modules


def main() -> int:
    """Check consistency. Returns 0 if consistent, 1 if drift detected."""
    if not MANIFEST_MAIN.exists():
        print(f"ERROR: {MANIFEST_MAIN} not found", file=sys.stderr)
        return 2
    if not MANIFEST_LOCAL.exists():
        print(f"ERROR: {MANIFEST_LOCAL} not found", file=sys.stderr)
        return 2

    main_modules = get_python_modules(MANIFEST_MAIN)
    local_modules = get_python_modules(MANIFEST_LOCAL)

    errors: list[str] = []

    # Check for modules only in main
    only_main = sorted(set(main_modules.keys()) - set(local_modules.keys()))
    if only_main:
        errors.append(f"Modules only in main manifest: {', '.join(only_main)}")

    # Check for modules only in local
    only_local = sorted(set(local_modules.keys()) - set(main_modules.keys()))
    if only_local:
        errors.append(f"Modules only in local manifest: {', '.join(only_local)}")

    # Check for source drift in shared modules
    for name in sorted(set(main_modules.keys()) & set(local_modules.keys())):
        if main_modules[name] != local_modules[name]:
            errors.append(f"\nDrift detected in '{name}':")
            errors.append(f"  main:  {main_modules[name]}")
            errors.append(f"  local: {local_modules[name]}")

    if errors:
        print("FAIL: Manifest consistency check failed")
        for error in errors:
            print(error)
        return 1

    shared = len(set(main_modules.keys()) & set(local_modules.keys()))
    print(f"PASS: Manifests are consistent ({shared} shared Python modules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
