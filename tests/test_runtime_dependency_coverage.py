#!/usr/bin/env python3
# tests/test_runtime_dependency_coverage.py
"""Deterministic tests for build-aux/check_runtime_dependency_coverage.py (F-005).

These tests exercise the F-005 runtime dependency coverage checker entirely on
in-memory fixtures (tmp_path), so they never touch the real manifests.

Covered scenarios:
- Test 1 : all runtime dependencies represented -> PASS (exit 0)
- Test 2 : a new transitive dependency missing from manifests -> FAIL (exit != 0)
- Test 3 : dev-only dependencies are never required -> PASS
- Test 4 : certifi (FEDC-owned) with a differing version -> PASS
- Test 5 : build-only modules are never required as runtime -> PASS
- Test 6 : a dependency missing from BOTH manifests is still detected -> FAIL
"""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "build-aux"))

import check_runtime_dependency_coverage as checker  # noqa: E402

# Force a Linux, CPython, x86_64 target in every test so the win32-gated edges
# (colorama, win32-setctime) are deterministically excluded regardless of the
# host platform the tests happen to run on.
LINUX_ENV = {
    "os_name": "posix",
    "sys_platform": "linux",
    "platform_machine": "x86_64",
    "platform_system": "Linux",
    "platform_release": "6.8",
    "platform_version": "#1",
    "python_version": "3.12",
    "python_full_version": "3.12.0",
    "implementation_name": "cpython",
    "platform_python_implementation": "CPython",
}


def _uvlock_body(root_deps: list[str], extra_pkgs: str = "") -> str:
    """Build a small uv.lock TOML string.

    ``root_deps`` are the dependencies of the root package. ``extra_pkgs`` is
    the concatenated ``[[package]]`` blocks for the transitive graph.
    """
    live_deps = [f"    {{ name = \"{d}\" }}" for d in root_deps]
    return (
        "version = 1\n"
        "\n"
        "[[package]]\n"
        'name = "test"\n'
        'version = "0.0.1"\n'
        "dependencies = [\n" + ",\n".join(live_deps) + "\n]\n"
        "\n"
        f"{extra_pkgs}"
    )


def _pkg(name: str, version: str, deps: list[tuple[str, str | None]]) -> str:
    """Render a uv.lock [[package]] entry with optional marker-ed dependencies."""
    dep_lines = []
    for dep_name, marker in deps:
        if marker is None:
            dep_lines.append(f'{{ name = "{dep_name}" }}')
        else:
            dep_lines.append(f'{{ name = "{dep_name}", marker = "{marker}" }}')
    deps_body = ""
    if dep_lines:
        deps_body = "dependencies = [\n" + ",\n".join(f"    {d}" for d in dep_lines) + ",\n]\n"
    return (
        "[[package]]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        f"{deps_body}"
    )


# Runtime reachable graph: the set of packages a Flatpak/Linux build needs.
# colorama and win32-setctime are win32-gated and must be excluded.
RUNTIME_MODULES = {
    "python3-requests",
    "python3-gTTS",
    "python3-click",
    "python3-certifi",
    "python3-charset-normalizer",
    "python3-idna",
    "python3-urllib3",
    "python3-loguru",
}


def _write_manifest(path: Path, modules: set[str]) -> None:
    """Write a Flatpak manifest containing the given python3-* modules."""
    body = {
        "app-id": "io.github.d3msudo.anura",
        "modules": [
            {
                "name": module,
                "sources": [{"type": "file", "url": f"https://example.com/{module}.whl"}],
            }
            for module in sorted(modules)
        ],
    }
    path.write_text(json.dumps(body, indent=4))


def _base_files(tmp_path: Path):
    """Create pyproject.toml, uv.lock and both manifests for the happy path."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\n"
        'name = "test"\n'
        'version = "0.0.1"\n'
        "requires-python = \">=3.12\"\n"
        "dependencies = [\n"
        '    "gtts>=2.5.4",\n'
        '    "loguru>=0.7.3",\n'
        '    "requests>=2.34.2",\n'
        "]\n"
        "\n"
        "[dependency-groups]\n"
        "dev = [\"pytest>=9\", \"mypy>=2\", \"packaging>=26\"]\n"
    )

    pkgs = (
        _pkg("gtts", "2.5.4", [("click", None), ("requests", None)])
        + "\n"
        + _pkg("click", "8.1.8", [("colorama", "sys_platform == 'win32'")])
        + "\n"
        + _pkg(
            "requests",
            "2.34.2",
            [
                ("certifi", None),
                ("charset-normalizer", None),
                ("idna", None),
                ("urllib3", None),
            ],
        )
        + "\n"
        + _pkg("certifi", "2026.4.22", [])
        + "\n"
        + _pkg("charset-normalizer", "3.4.7", [])
        + "\n"
        + _pkg("idna", "3.15", [])
        + "\n"
        + _pkg("urllib3", "2.7.0", [])
        + "\n"
        + _pkg(
            "loguru",
            "0.7.3",
            [
                ("colorama", "sys_platform == 'win32'"),
                ("win32-setctime", "sys_platform == 'win32'"),
            ],
        )
        + "\n"
        + _pkg("colorama", "0.4.6", [])
        + "\n"
        + _pkg("win32-setctime", "1.2.0", [])
        + "\n"
        # dev-only (never reachable from runtime roots)
        + _pkg("pytest", "9.1.1", [])
        + "\n"
        + _pkg("mypy", "2.1.0", [("pathspec", None)])
        + "\n"
        + _pkg("pathspec", "1.1.1", [])
        + "\n"
        + _pkg("packaging", "26.2", [])
        + "\n"
    )
    uv_lock = tmp_path / "uv.lock"
    uv_lock.write_text(_uvlock_body(["gtts", "loguru", "requests"], pkgs))

    main = tmp_path / "main.json"
    local = tmp_path / "local.json"
    _write_manifest(main, RUNTIME_MODULES)
    _write_manifest(local, RUNTIME_MODULES)
    return pyproject, uv_lock, main, local


def test_1_all_runtime_dependencies_represented(tmp_path: Path) -> None:
    """Test 1: a complete manifest set passes (exit 0)."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)
    result = checker.check_runtime_coverage(pyproject, uv_lock, (main, local), env=LINUX_ENV)
    assert result.passed is True, result.errors
    assert result.errors == []
    # Windows-only modules must not be required on the Linux target.
    covered = result.good
    assert not any("colorama" in e for e in covered)
    assert not any("win32-setctime" in e for e in covered)
    # Every runtime module is accounted for.
    for module in sorted(RUNTIME_MODULES):
        assert any(module in e for e in result.good), f"missing {module} in good output"


def test_2_missing_transitive_dependency_fails(tmp_path: Path) -> None:
    """Test 2: a new transitive (requests -> new-package) absent from the
    manifests must fail (exit != 0)."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)

    # Introduce a new transitive dependency: requests gains a dependency on
    # new-package (present in uv.lock, absent from the manifests).
    patched = uv_lock.read_text()
    # Add new-package to requests' dependency list.
    patched = patched.replace(
        '{ name = "urllib3" }',
        '{ name = "urllib3" },\n    { name = "new-package" }',
    )
    # Append the [[package]] entry for new-package at the end of the file.
    patched += "\n" + _pkg("new-package", "1.2.3", []) + "\n"

    new_uv = tmp_path / "uv_new.lock"
    new_uv.write_text(patched)

    result = checker.check_runtime_coverage(pyproject, new_uv, (main, local), env=LINUX_ENV)
    assert result.passed is False
    assert any(
        "new-package" in e and "no Flatpak python module mapping" in e for e in result.errors
    )


def test_3_dev_only_dependency_not_required(tmp_path: Path) -> None:
    """Test 3: dev-only dependencies and their transitives never fail the check."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)
    result = checker.check_runtime_coverage(pyproject, uv_lock, (main, local), env=LINUX_ENV)
    # pytest, mypy, pathspec and packaging are dev-only and not required.
    assert result.passed is True, result.errors
    assert not any("pytest" in e for e in result.errors)
    assert not any("mypy" in e for e in result.errors)
    assert not any("pathspec" in e for e in result.errors)
    assert not any("packaging" in e for e in result.errors)


def test_4_certifi_fedc_owned_version_divergence_passes(tmp_path: Path) -> None:
    """Test 4: certifi with a differing version passes (coverage, not ownership)."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)

    # Bump the uv.lock certifi version; the manifest source url stays the same.
    uv2 = tmp_path / "uv_certifi.lock"
    uv2.write_text(uv_lock.read_text().replace('version = "2026.4.22"', 'version = "2026.9.99"'))

    result = checker.check_runtime_coverage(pyproject, uv2, (main, local), env=LINUX_ENV)
    assert result.passed is True, result.errors
    # The FEDC-owned module presence is still validated.
    assert any("python3-certifi" in e and "FEDC-owned" in e for e in result.good)


def test_5_build_only_modules_not_required(tmp_path: Path) -> None:
    """Test 5: build-only modules (pybind11, scikit-build-core) are never
    required as runtime uv.lock packages."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)

    # Add the build-only modules to the manifests (they are not in uv.lock).
    modules = RUNTIME_MODULES | {"python3-pybind11", "python3-scikit-build-core"}
    _write_manifest(main, modules)
    _write_manifest(local, modules)

    result = checker.check_runtime_coverage(pyproject, uv_lock, (main, local), env=LINUX_ENV)
    assert result.passed is True, result.errors
    assert not any("pybind11" in e for e in result.errors)
    assert not any("scikit-build-core" in e for e in result.errors)


def test_6_missing_from_both_manifests_detected(tmp_path: Path) -> None:
    """Test 6: a dependency absent from BOTH manifests is still detected, and the
    main/local comparison can not hide it."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)

    # Drop urllib3 from both manifests.
    modules = RUNTIME_MODULES - {"python3-urllib3"}
    _write_manifest(main, modules)
    _write_manifest(local, modules)

    result = checker.check_runtime_coverage(pyproject, uv_lock, (main, local), env=LINUX_ENV)
    assert result.passed is False
    # Two errors: one per manifest.
    urllib3_errors = [e for e in result.errors if "urllib3" in e]
    assert len(urllib3_errors) == 2
    assert all("MISSING" in e for e in urllib3_errors)


def test_6b_missing_from_single_manifest_detected(tmp_path: Path) -> None:
    """A dependency present in only one manifest still fails."""
    pyproject, uv_lock, main, local = _base_files(tmp_path)
    _write_manifest(main, RUNTIME_MODULES - {"python3-click"})  # local still has it

    result = checker.check_runtime_coverage(pyproject, uv_lock, (main, local), env=LINUX_ENV)
    assert result.passed is False
    click_errors = [e for e in result.errors if "click" in e]
    assert len(click_errors) == 1
    assert "MISSING in main.json" in click_errors[0]
