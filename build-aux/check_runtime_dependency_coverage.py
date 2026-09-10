#!/usr/bin/env python3
# build-aux/check_runtime_dependency_coverage.py
"""Check that every Python runtime dependency in uv.lock is represented in the Flatpak manifests.

This checker closes F-005: it guarantees that a new transitive dependency that
appears in ``uv.lock`` can not silently remain absent from both Flatpak
manifests.

Pipeline under test::

    pyproject.toml   (runtime direct deps)
          |
          v
        uv.lock      (version + dependency graph + markers)
          |
          v
      runtime closure (deps needed at runtime on the Flatpak target)
          |
          v
      python3-* Flatpak manifest modules
          |
          v
      manifest coverage (presence in BOTH manifests)

Responsibilities are deliberately kept separate:

- build-aux/sync_dependencies.py            -> version/url/hash synchronization
- build-aux/check_manifest_consistency.py   -> main manifest <-> local manifest
- this checker                              -> uv.lock runtime closure <-> manifest modules

Direction 1 (HARD FAILURE): every runtime package that must be packaged in the
Flatpak must have a corresponding ``python3-*`` module in both manifests.

Direction 2 (WARNING ONLY): ``python3-*`` modules that map to a PyPI package
which is not required at runtime (stale / dev-only module) are reported but do
not fail the check, so an optional extra module can never break CI while a
genuinely missing runtime module still does.

Intentional exceptions handled without false positives:

- certifi (FEDC-owned): presence is enforced, but the *version* is owned by
  FEDC and is deliberately never compared here (that decision belongs to
  sync_dependencies.py + flatpak-dependencies.yml).
- Build-only modules (python3-pybind11, python3-scikit-build-core): never
  required as runtime uv.lock packages.
- Dev/test dependencies and their transitives: never required in the manifests.
- System / externally-provided dependencies (tesseract, tessdata, leptonica,
  imlib2, scrot, libportal): not part of the Python check.

Only the Python standard library is used, so no extra install is required.

Exit code: 0 when coverage is complete, 1 when a runtime dependency is missing.
"""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
import json
import os
import platform
import re
import sys
import tomllib

# The next line reuses the single source of truth of sync_dependencies.py so the
# mapping (PyPI name <-> Flatpak python3-* module) is not duplicated.
from sync_dependencies import BUILD_DEPS_OVERRIDES, MODULE_TO_PYPI, REPO_ROOT

PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"
UV_LOCK = REPO_ROOT / "uv.lock"
MANIFEST_MAIN = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.json"
MANIFEST_LOCAL = REPO_ROOT / "flatpak" / "io.github.d3msudo.anura.local.json"

# PyPI name -> corresponding python3-* Flatpak module (reversed MODULE_TO_PYPI).
_PYPI_TO_MODULE: dict[str, str] = {pypi: module for module, pypi in MODULE_TO_PYPI.items()}

# FEDC-owned runtime modules: the module MUST be present (coverage), but its
# version is owned exclusively by FEDC and must not be verified here.
FEDC_OWNED_PYPI: dict[str, str] = {
    "certifi": "python3-certifi",
}

# Runtime packages intentionally provided by the Flatpak runtime/platform that
# require no dedicated python3-* module. Currently empty; extend only when a
# runtime closure member is genuinely shipped by the GNOME runtime.
EXTERNALLY_PROVIDED_PYPI: frozenset[str] = frozenset()

# Target environment used to evaluate dependency markers. This mirrors the
# Flatpak build target: Linux, CPython, x86_64 (the CI runner hardware).
TARGET_ENV: dict[str, str] = {
    "os_name": os.name,
    "sys_platform": sys.platform,
    "platform_machine": platform.machine(),
    "platform_system": platform.system(),
    "platform_release": platform.release(),
    "platform_version": platform.version(),
    "python_version": ".".join(str(v) for v in sys.version_info[:2]),
    "python_full_version": platform.python_version(),
    "implementation_name": sys.implementation.name,
    "platform_python_implementation": platform.python_implementation(),
}

@dataclass
class CheckResult:
    """Outcome of a runtime dependency coverage check."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    good: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when coverage is complete (no errors)."""
        return not self.errors


def normalize_name(name: str) -> str:
    """Normalize a distribution name to PEP 503 canonical form."""
    return re.sub(r"[-_.]+", "-", name).lower()


def read_toml(path: str) -> dict:
    """Read a TOML file (binary mode is required by tomllib)."""
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def parse_runtime_direct_deps(pyproject_path: str) -> set[str]:
    """Extract the runtime direct dependency names from ``[project].dependencies``."""
    data = read_toml(pyproject_path)
    project = data.get("project", {})
    deps = project.get("dependencies")
    if deps is None:
        raise ValueError(f"[project].dependencies not found in {pyproject_path}")
    names: set[str] = set()
    for req in deps:
        match = re.match(r"([A-Za-z0-9_.-]+)", str(req))
        if not match:
            raise ValueError(f"cannot parse dependency requirement: {req!r}")
        names.add(normalize_name(match.group(1)))
    return names


def parse_uv_lock_graph(path: str) -> tuple[dict[str, str], dict[str, list[tuple[str, str | None]]]]:
    """Return (name -> version) and (name -> list[(dep_name, marker)]) from uv.lock."""
    data = read_toml(path)
    versions: dict[str, str] = {}
    edges: dict[str, list[tuple[str, str | None]]] = {}
    for pkg in data.get("package", []):
        name = normalize_name(pkg["name"])
        versions[name] = pkg.get("version", "?")
        deps: list[tuple[str, str | None]] = []
        for dep in pkg.get("dependencies") or []:
            if isinstance(dep, dict):
                dep_name = dep.get("name")
                marker = dep.get("marker")
            else:
                dep_name = dep
                marker = None
            if dep_name:
                deps.append((normalize_name(dep_name), marker))
        edges[name] = deps
    return versions, edges


def _eval_marker_ast(node, env: dict[str, str]) -> bool:
    """Evaluate a marker AST node against the target environment.

    Only constants, names, boolean ops, comparisons and ``not`` are allowed;
    all other node types raise ValueError. This is a safe, ``exec``-free
    evaluator (``ast.literal_eval`` equivalent) restricted to markers.
    """
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.Name):
        value = env.get(node.id)
        if value is None:
            raise ValueError(f"unknown marker variable: {node.id!r}")
        return str(value)
    if isinstance(node, ast.BoolOp):
        values = [_eval_marker_ast(v, env) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_marker_ast(node.operand, env)
    if isinstance(node, ast.Compare):
        left = _eval_marker_ast(node.left, env)
        right = _eval_marker_ast(node.comparators[0], env)
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
    raise ValueError(f"unsupported marker node: {ast.dump(node)}")


def eval_marker(marker: str | None, env: dict[str, str]) -> bool:
    """Evaluate a PEP 508 marker against the target environment.

    Conservative fallback: if a marker can not be evaluated (unknown variable or
    unsupported syntax) the dependency is treated as *present*. This biases the
    check toward reporting rather than silently dropping a module that may be
    needed, which is the safe direction for F-005.
    """
    if marker is None:
        return True
    try:
        tree = ast.parse(marker, mode="eval")
        return bool(_eval_marker_ast(tree.body, env))
    except (SyntaxError, ValueError, TypeError):
        return True


def compute_runtime_closure(
    pyproject_path: str,
    uv_lock_path: str,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Compute the runtime dependency closure name -> version.

    The traversal starts from ``[project].dependencies`` (the authoritative
    runtime direct set) and follows uv.lock dependency edges, skipping any edge
    whose marker is false on the target environment. Dev/test/build dependencies
    are therefore never reachable from the runtime roots.
    """
    if env is None:
        env = TARGET_ENV
    roots = parse_runtime_direct_deps(pyproject_path)
    versions, edges = parse_uv_lock_graph(uv_lock_path)

    visited: set[str] = set()
    queue: deque[str] = deque()
    for root in roots:
        if root not in visited:
            visited.add(root)
            queue.append(root)

    while queue:
        current = queue.popleft()
        for dep_name, marker in edges.get(current, []):
            if not eval_marker(marker, env):
                continue
            if dep_name not in visited:
                visited.add(dep_name)
                queue.append(dep_name)

    return {name: versions.get(name, "?") for name in sorted(visited)}


def parse_manifest_modules(path: str) -> set[str]:
    """Return the set of ``python3-*`` module names declared in a Flatpak manifest."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        m.get("name", "")
        for m in data.get("modules", [])
        if m.get("name", "").startswith("python3-")
    }


def check_runtime_coverage(
    pyproject_path: str,
    uv_lock_path: str,
    manifests: Iterable,
    env: dict[str, str] | None = None,
) -> CheckResult:
    """Run the F-005 runtime dependency coverage check over the given manifests."""
    if env is None:
        env = TARGET_ENV
    runtime = compute_runtime_closure(pyproject_path, uv_lock_path, env=env)
    manifest_modules = {os.fspath(path): parse_manifest_modules(path) for path in manifests}

    result = CheckResult()

    # Direction 1: every runtime package must be covered in every manifest.
    for pkg, version in runtime.items():
        if pkg in EXTERNALLY_PROVIDED_PYPI:
            result.good.append(f"{pkg} ({version}) provided by Flatpak platform")
            continue

        module = _PYPI_TO_MODULE.get(pkg) or FEDC_OWNED_PYPI.get(pkg)
        if module is None:
            result.errors.append(
                f"runtime package '{pkg}' ({version}) has no Flatpak python module mapping"
                " - add a python3-* module to the manifests"
            )
            continue

        for manifest in manifest_modules:
            if module not in manifest_modules[manifest]:
                result.errors.append(
                    f"runtime package '{pkg}' ({version}) -> module '{module}' "
                    f"MISSING in {os.path.basename(manifest)}"
                )

        if pkg in FEDC_OWNED_PYPI:
            result.good.append(f"{pkg} ({version}) -> {module} (FEDC-owned, presence OK)")
        else:
            result.good.append(f"{pkg} ({version}) -> {module}")

    # Direction 2: surface stale / dev-only modules (non-blocking).
    for pypi, module in sorted(_PYPI_TO_MODULE.items()):
        if module in BUILD_DEPS_OVERRIDES:
            continue  # build-only modules are intentionally not runtime deps
        if pypi not in runtime:
            result.warnings.append(
                f"module '{module}' maps to '{pypi}' which is NOT a runtime dependency"
                " (stale / dev-only module)"
            )

    return result


def main() -> int:
    for path, label in ((PYPROJECT_TOML, "pyproject.toml"), (UV_LOCK, "uv.lock")):
        if not os.path.exists(path):
            print(f"ERROR: {label} not found at {path}", file=sys.stderr)
            return 2

    result = check_runtime_coverage(PYPROJECT_TOML, UV_LOCK, (MANIFEST_MAIN, MANIFEST_LOCAL))

    print("=== F-005 runtime dependency coverage ===")
    if result.good:
        print("Good:")
        for entry in sorted(result.good):
            print(f"  {entry}")
    if result.warnings:
        print("\nWarnings (non-blocking):")
        for entry in result.warnings:
            print(f"  {entry}")

    if not result.passed:
        print("\nERROR: runtime dependency coverage incomplete")
        print("Missing / unmapped Flatpak modules:")
        for entry in result.errors:
            print(f"  {entry}")
        return 1

    print("\nPASS: all runtime Python dependencies are represented in the Flatpak manifests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
