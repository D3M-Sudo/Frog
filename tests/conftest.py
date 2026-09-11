# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

# =============================================================================
# ARCHITECTURE NOTE — reading order matters
#
# pytest loads conftest.py BEFORE collecting any test file.  This means:
#
#   1. Module-level code here runs first (sys.path setup, env var reads).
#   2. Fixtures are registered but execute only when a test requests them.
#   3. Top-level imports inside *test* files run at collection time, i.e.
#      AFTER conftest module-level code but BEFORE any fixture body.
#
# Consequence for gi mocking (Pillar 2):
#   We cannot protect against `from gi.repository import X` at module level
#   inside test files using a fixture alone — the import fires during
#   collection, before any fixture activates.  The correct contract is:
#     - test files that need gi at module level use pytest.importorskip("gi")
#       (skip-on-absence, safe)
#     - test files that mock gi import nothing from gi at module level and
#       instead declare `headless_gi_mocks` as a fixture dependency
#     - anura.main is never imported directly by tests (it is not on the
#       ignore list but contains module-level gi.require_version calls that
#       would fire during collection)
#
# The ANURA_CI_TEST_MODE env var is therefore set HERE at module level so
# that any code that reads it at import time (e.g. anura.core.boot) sees it
# before it runs.
# =============================================================================

import os
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pillar 2 — Set CI mode flag early, at module level, so downstream code
# that reads os.environ at import time sees it before executing.
# ---------------------------------------------------------------------------
_CI_MODE: bool = bool(os.environ.get("ANURA_CI_TEST_MODE", "0").strip("'\" ") not in ("", "0", "false", "False"))

# Ensure the project root is on sys.path so `import anura` works without
# installing the package first.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Pillar 2 — Centralised, deterministic gi mock injection.
#
# Activated only when ANURA_CI_TEST_MODE=1.  Runs at module level (not inside
# a fixture) so the stubs are in sys.modules before pytest collects test files
# that import gi at module level.
#
# Keys are inserted only if absent so running in an environment where real gi
# IS installed remains transparent — the real binding wins.
# ---------------------------------------------------------------------------
_GI_KEYS: tuple[str, ...] = (
    "gi",
    "gi.repository",
    "gi.repository.Gio",
    "gi.repository.GLib",
    "gi.repository.GObject",
    "gi.repository.Xdp",
    "gi.repository.Adw",
    "gi.repository.Gtk",
    "gi.repository.GtkSource",
    "gi.repository.Gst",
    "gi.repository.Notify",
    "gi.repository.GdkPixbuf",
    "gi.repository.Gdk",
    "gi.repository.Pango",
)

_GI_INJECTED: list[str] = []

class PropertyStub:
    def __init__(self, fget=None, fset=None, **kwargs):
        self.fget = fget
        self.fset = fset
        self.default = kwargs.get("default")

    def setter(self, fset):
        self.fset = fset
        return self

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if self.fget:
            return self.fget(instance)

        # Simple GObject property storage
        if not hasattr(instance, "_property_values"):
            instance._property_values = {}
        return instance._property_values.get(self, self.default)

    def __set__(self, instance, value):
        if self.fset:
            self.fset(instance, value)
        else:
            if not hasattr(instance, "_property_values"):
                instance._property_values = {}
            instance._property_values[self] = value

    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            self.fget = args[0]
            return self
        return self


class StubMetaclass(type):
    def __getattr__(cls, name):
        if name == "get_default_for_uri_scheme":
            # Return a function that returns None so we fall back to the safe whitelist
            return lambda scheme: None
        if name == "Property":
            return lambda *args, **kwargs: PropertyStub(**kwargs)
        if name.startswith("_"):
            raise AttributeError(name)
        return MagicMock(name=name)


class UniversalStub(metaclass=StubMetaclass):
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        # Standard Python internals, private attributes, and non-existent link generators should raise AttributeError
        # so that hasattr() and getattr() with defaults work correctly.
        if name.startswith("_") or name.startswith("get_link_"):
            raise AttributeError(name)
        return MagicMock(name=name)

    def __call__(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return MagicMock()

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()


class MockModule(MagicMock):
    def __init__(self, name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__name__ = name
        import importlib.machinery
        self.__spec__ = importlib.machinery.ModuleSpec(name, loader=None)
        self.__loader__ = None
        self.__package__ = name.rsplit(".", 1)[0] if "." in name else name
        self.__path__ = []

    def __getattr__(self, name: str):
        if name == "Property":
            return lambda *args, **kwargs: PropertyStub()
        if name.startswith("_") or name.startswith("mock") or name in (
            "called", "call_count", "call_args", "call_args_list", "return_value", "side_effect"
        ):
            return super().__getattr__(name)
        # Dynamically return a class that inherits from UniversalStub to prevent metaclass conflicts
        return type(name, (UniversalStub,), {})


def _make_module_mock(name: str) -> MockModule:
    """Return a MockModule that pytest.importorskip will accept and satisfies GObject subclassing."""
    return MockModule(name)


def _inject_gi_mocks() -> list[str]:
    """Build a coherent mock hierarchy and inject it into sys.modules.

    Ensures that gi.repository.X attributes correctly resolve off the gi.repository mock,
    preventing TypeError metaclass conflicts when defining widgets or controllers with multi-inheritance.
    Standardized to be robust in both CI and local developer environments.
    """
    injected: list[str] = []
    _mock_gi = _make_module_mock("gi")
    _mock_repo = _make_module_mock("gi.repository")
    _mock_gi.repository = _mock_repo

    for _key in _GI_KEYS:
        if _key not in sys.modules:
            if _key == "gi":
                sys.modules[_key] = _mock_gi
            elif _key == "gi.repository":
                sys.modules[_key] = _mock_repo
            else:
                # e.g. "gi.repository.Gio" → attribute "Gio" on _mock_repo
                _leaf = _key.rsplit(".", 1)[-1]
                _leaf_mock = _make_module_mock(_key)
                setattr(_mock_repo, _leaf, _leaf_mock)
                sys.modules[_key] = _leaf_mock
            injected.append(_key)
    return injected


if _CI_MODE:
    _GI_INJECTED.extend(_inject_gi_mocks())


# ---------------------------------------------------------------------------
# Pillar 5 — Loguru CI handler.
#
# In CI mode: replace the default stderr handler with a thread-safe,
# enqueue=True file handler.  This avoids conflicts with pytest's stderr
# capturer and ensures log output from singleton instances (AtomicTaskManager)
# is captured without I/O contention.
#
# Runs at module level (after gi stubs) so the handler is active before any
# fixture or test code runs — including code that calls logger at import time.
# ---------------------------------------------------------------------------
if _CI_MODE:
    try:
        from loguru import logger as _logger

        _logger.remove()  # Remove all default handlers (stderr)

        _ci_log_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "anura" / "logs"
        _ci_log_dir.mkdir(parents=True, exist_ok=True)
        _ci_log_file = _ci_log_dir / "anura_ci_test.log"

        _logger.add(
            str(_ci_log_file),
            level="DEBUG",
            format="{time:HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation=None,       # no rotation during a single test run
            enqueue=True,        # thread-safe async queue — no GLib event loop needed
            catch=True,
            encoding="utf-8",
            mode="w",            # fresh file per run
        )
    except Exception:
        pass  # Never let logging setup break the test suite


# ---------------------------------------------------------------------------
# Pillar 1 — Source-level detection helper (used by Pillar 3 hook).
# ---------------------------------------------------------------------------

def _module_needs_gi(fspath: object) -> bool:
    """Return True if the test module at *fspath* depends on gi.repository.

    Scans file content for the four canonical gi-dependency patterns.
    Intentionally side-effect-free: reads source once per call; caching is
    done at the call-site.
    """
    try:
        src = Path(str(fspath)).read_text(encoding="utf-8", errors="replace")
        return (
            'importorskip("gi")' in src
            or "importorskip('gi')" in src
            or "from gi.repository" in src
            or "gi.require_version" in src
        )
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Pillar 3 — Dynamic gtk marker + conditional skip in CI mode.
#
# Two behaviours depending on environment:
#
#   Real GTK available (ANURA_CI_TEST_MODE not set):
#     Tag gi-dependent tests with the `gtk` marker so they can be selectively
#     run or excluded.  No skipping.
#
#   ANURA_CI_TEST_MODE=1 (headless CI):
#     Tag AND skip all `gtk`-marked tests with an informative reason.
#     Skipped tests appear in the CI report as `s` — fully traceable, no
#     false failures.
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(items: list) -> None:
    """Tag gi-dependent tests; skip them in CI mode."""
    _gi_file_cache: dict[str, bool] = {}
    skip_marker = pytest.mark.skip(reason="gi/GTK not available in ANURA_CI_TEST_MODE=1")

    for item in items:
        fspath_str = str(item.fspath)

        if fspath_str not in _gi_file_cache:
            _gi_file_cache[fspath_str] = _module_needs_gi(item.fspath)

        needs_gtk = _gi_file_cache[fspath_str] or "gtk" in item.name.lower()

        if needs_gtk:
            item.add_marker(pytest.mark.gtk)
            if _CI_MODE:
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# Pillar 2 (fixture) — headless_gi_mocks.
#
# For tests that do NOT import gi at module level but need mock gi bindings
# inside test bodies or fixtures.  Declares the session-scoped stubs as
# already injected in CI mode (no-op) or injects them on demand otherwise.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def headless_gi_mocks():
    """Ensure MagicMock stubs for gi are present for the test session.

    In ANURA_CI_TEST_MODE=1 the stubs are already in sys.modules (inserted at
    conftest module load time above), so this fixture is a no-op.

    Outside CI mode, injects stubs only if gi is genuinely absent, so the
    fixture is safe to declare even in environments where real gi is installed.
    """
    if _CI_MODE:
        # Already injected at module level — nothing to do.
        yield
        return

    # Non-CI path: inject only if gi is missing (e.g. developer laptop without GTK).
    inserted: list[str] = []
    try:
        import gi  # noqa: F401
        yield
        return
    except ImportError:
        pass

    inserted = _inject_gi_mocks()
    yield
    for key in inserted:
        sys.modules.pop(key, None)


# ---------------------------------------------------------------------------
# Standard test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_tessdata(tmp_path):
    """Temporary tessdata directory with fake traineddata stubs."""
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "eng.traineddata").write_bytes(b"fake-model")
    (tessdata / "ita.traineddata").write_bytes(b"fake-model")
    return tessdata


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    """Isolate tests from the real user environment.

    Redirects XDG dirs to tmp_path so tests never touch ~/.local or ~/.cache.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("TESSDATA_PREFIX_SYSTEM", str(tmp_path / "system-tessdata"))


# ---------------------------------------------------------------------------
# Session teardown + os._exit() with Pillar 6 safe flush
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):
    """Coordinated session teardown with guaranteed loguru flush before exit.

    Sequence (order is critical):

      1. Shutdown application singletons (best-effort).
      2. Flush loguru enqueue handler via logger.complete() — this blocks
         until the async queue is drained, preventing log loss on os._exit().
      3. Force-print the pytest summary line (it would be suppressed by
         os._exit() otherwise).
      4. os._exit(exitstatus) — bypasses Python's non-daemon thread join
         (the 74-second hang from GLib/GTK orphan threads).

    Pillar 6 note: os._exit() skips all atexit handlers and __del__ finalizers.
    logger.complete() MUST be called before os._exit() when enqueue=True is
    active; otherwise the enqueue thread's buffer is discarded mid-flight.
    """
    print("\nEnsuring clean session teardown...")

    # 1a. Shutdown AtomicTaskManager
    try:
        from anura.core.atomic_task_manager import get_atomic_manager
        get_atomic_manager().shutdown()
    except (ImportError, AttributeError, RuntimeError, ValueError):
        pass

    # 1b. Shutdown LanguageManager
    try:
        from anura.services.language_manager import get_language_manager
        get_language_manager().shutdown()
    except (ImportError, AttributeError, RuntimeError, ValueError):
        pass

    # 1c. Cleanup TTSService
    try:
        from anura.services.tts import get_tts_service
        get_tts_service().cleanup()
    except (ImportError, AttributeError, RuntimeError, ValueError):
        pass

    # 1d. Reset singletons
    try:
        from anura.utils.singleton import ThreadSafeSingleton
        ThreadSafeSingleton.reset_for_testing()
    except (ImportError, AttributeError):
        pass

    print("Teardown complete.")

    # 2. Pillar 6 — flush loguru enqueue queue BEFORE os._exit().
    #    logger.complete() is synchronous in loguru 0.7.x: it blocks until
    #    all enqueued records have been processed and written to disk.
    #    Wrapping in suppress because logger may already be torn down if
    #    pytest itself removed the handler.
    if _CI_MODE:
        try:
            from loguru import logger as _log
            _log.complete()
        except Exception:
            pass

    # 3. Force-print the summary line before os._exit() suppresses it.
    try:
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            # Verbose printing of test failure tracebacks since os._exit() suppresses standard reporting
            failed_reports = tr.stats.get('failed', [])
            for rep in failed_reports:
                print("\n" + "="*80)
                print(f"FAILURE IN {rep.nodeid}:")
                print("="*80)
                print(rep.longrepr)
                # Also print captured stdout/stderr
                for secname, secdata in rep.sections:
                    print(f"--- {secname} ---")
                    print(secdata)
                print("="*80 + "\n")
            tr.summary_stats()
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass

    # 3b. Forcefully terminate all child processes to prevent GHA from hanging on open pipes.
    try:
        import psutil
        current_process = psutil.Process()
        children = current_process.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except Exception:
                pass
    except Exception:
        pass

    # 4. Bypass Python's non-daemon-thread join (avoids 74-second CI hang).
    os._exit(int(exitstatus))
