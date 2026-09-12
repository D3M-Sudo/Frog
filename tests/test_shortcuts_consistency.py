#!/usr/bin/env python3
# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

"""
Anti-drift consistency test: the ShortcutsOverlay cheat sheet and the
accelerators actually registered via ActionRegistry must stay in sync.

- Every overlay entry backed by a GAction must match a registered accelerator.
- Every registered accelerator must be documented in the overlay.
- Entries backed by native widget behaviour (no GAction) are whitelisted.

Headless-safe: uses the system gi binding pattern documented in
docs/dependencies.md ("GTK (PyGObject) and the development venv").
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gio, GLib, Gtk

    HAS_GI = True
except (ImportError, ValueError):
    HAS_GI = False

pytestmark = pytest.mark.skipif(not HAS_GI, reason="GTK environment (gi) not available")

# Native widget bindings with no GAction behind them (documented behaviour).
NATIVE_WHITELIST = {
    "<Control>a": "GtkTextView select-all",
    "<Control>z": "GtkSourceBuffer undo",
    "<Control><Shift>z": "GtkSourceBuffer redo",
    "Escape": "EventControllerKey / GtkSearchBar",
}


@pytest.fixture(scope="module")
def registered_accels():
    """Canonical accelerators registered by ActionRegistry, via a stub app."""

    class StubApp:
        def __init__(self):
            self.accels = {}

        def add_action(self, action):
            pass

        def set_accels_for_action(self, action, accels):
            self.accels.setdefault(action, []).extend(accels)

        def __getattr__(self, name):
            return lambda *a, **k: None

    from anura.core.action_registry import ActionRegistry

    stub = StubApp()
    ActionRegistry(stub).setup_actions()

    result = {}  # (keyval, mods) -> action
    for action, accels in stub.accels.items():
        for accel in accels:
            ok, keyval, mods = Gtk.accelerator_parse(accel)
            assert ok, f"Unparseable accelerator registered: {accel}"
            result[(keyval, mods)] = action
    return result


def _register_gresource():
    path = os.path.join(
        os.path.dirname(__file__), "..", "builddir", "data", "io.github.d3msudo.anura.gresource"
    )
    if not os.path.exists(path):
        pytest.skip("Compiled GResource not found (run meson build first)")
    with open(path, "rb") as f:
        Gio.Resource.new_from_data(GLib.Bytes.new(f.read()))._register()


def _overlay_entries():
    _register_gresource()
    from anura.widgets.shortcuts_overlay import ShortcutsOverlay

    dummy = SimpleNamespace()
    ShortcutsOverlay._setup_shortcuts_data(dummy)
    entries = []  # (canonical_name, (keyval, mods), key_string, description)
    for category in dummy.shortcuts_data:
        for shortcut in category["shortcuts"]:
            ok, keyval, mods = Gtk.accelerator_parse(shortcut["key"])
            assert ok, f"Unparseable accelerator in overlay: {shortcut['key']}"
            name = Gtk.accelerator_name(keyval, mods)
            entries.append((name, (keyval, mods), shortcut["key"], shortcut["description"]))
    return entries


class TestShortcutsConsistency:
    def test_overlay_entries_are_unique(self):
        """No two overlay entries may use the same accelerator."""
        entries = _overlay_entries()
        seen = {}
        for name, combo, key, _desc in entries:
            assert combo not in seen, f"Duplicate overlay accelerator {name}: {seen[combo]} vs {key}"
            seen[combo] = key

    def test_overlay_entries_have_unique_descriptions(self):
        """No two overlay entries may describe the same function (dedup rule)."""
        entries = _overlay_entries()
        descriptions = [desc for _n, _c, _k, desc in entries]
        assert len(descriptions) == len(set(descriptions))

    def test_overlay_gaction_entries_match_registry(self, registered_accels):
        """Overlay entries with a GAction must match registered accelerators."""
        for name, combo, key, _desc in _overlay_entries():
            if key in NATIVE_WHITELIST:
                continue
            action = registered_accels.get(combo)
            assert action is not None, (
                f"Overlay documents {name} but no GAction accelerator matches it "
                f"(not in NATIVE_WHITELIST either)"
            )

    def test_registered_accels_are_documented(self, registered_accels):
        """Every registered accelerator must be documented in the overlay."""
        overlay_combos = {combo for _n, combo, _k, _d in _overlay_entries()}
        for combo, action in registered_accels.items():
            name = Gtk.accelerator_name(*combo)
            assert combo in overlay_combos, f"Registered accelerator {name} ({action}) missing from overlay"

    def test_native_whitelist_entries_exist(self):
        """Whitelisted native bindings must actually be documented in the overlay."""
        keys = {key for _n, _c, key, _d in _overlay_entries()}
        for key in NATIVE_WHITELIST:
            assert key in keys, f"Whitelisted native binding {key} not documented in overlay"
