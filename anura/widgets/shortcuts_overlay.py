# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

"""
Keyboard shortcuts overlay widget for Anura OCR.
Provides an elegant cheat sheet with all available keyboard shortcuts.
"""

from gettext import gettext as _
from typing import ClassVar

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GLib, GObject, Gtk  # noqa: E402

from anura.config import RESOURCE_PREFIX  # noqa: E402


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/shortcuts_overlay.ui")
class ShortcutsOverlay(Adw.Window):
    """Elegant keyboard shortcuts overlay window."""

    __gtype_name__ = "ShortcutsOverlay"

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "closed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    shortcuts_list: Gtk.ListBox = Gtk.Template.Child()
    stack: Gtk.Stack = Gtk.Template.Child()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)

        # Title, modal, default size, etc. are declared in shortcuts_overlay.blp.

        self._setup_shortcuts_data()
        self._populate_shortcuts_list()
        self._connect_signals()

        self.add_css_class("anura-fade-in")
        self.add_css_class("anura-card")

    def _setup_shortcuts_data(self) -> None:
        """Define all keyboard shortcuts with descriptions.

        Note: ``key`` strings must follow Gtk.accelerator_parse() format
        (e.g. ``<Control>g``) so Gtk.ShortcutLabel can render them.
        """
        self.shortcuts_data = [
            # Screenshot & OCR
            {
                "category": _("Screenshot & OCR"),
                "shortcuts": [
                    {"key": "<Control>g", "description": _("Take screenshot")},
                    {"key": "<Control><Shift>g", "description": _("Take screenshot and copy to clipboard")},
                    {"key": "<Control>o", "description": _("Open image file")},
                    {"key": "<Control>v", "description": _("Paste image from clipboard")},
                ],
            },
            # Editor (native GtkSourceView bindings — no GAction behind them)
            {
                "category": _("Editor"),
                "shortcuts": [
                    {"key": "<Control>a", "description": _("Select all text (in editor)")},
                    {"key": "<Control>c", "description": _("Copy text to clipboard")},
                    {"key": "<Control>z", "description": _("Undo (in editor)")},
                    {"key": "<Control><Shift>z", "description": _("Redo (in editor)")},
                    {"key": "<Control>f", "description": _("Search text")},
                    {"key": "<Control><Shift>e", "description": _("Open in external editor")},
                ],
            },
            # Text-to-Speech
            {
                "category": _("Text-to-Speech"),
                "shortcuts": [
                    {"key": "<Control>l", "description": _("Listen to text")},
                    {"key": "<Control><Alt>l", "description": _("Pause/resume listening")},
                    {"key": "<Control><Shift>l", "description": _("Stop listening")},
                ],
            },
            # Application
            {
                "category": _("Application"),
                "shortcuts": [
                    {"key": "<Control>comma", "description": _("Open preferences")},
                    {"key": "<Control>h", "description": _("Show keyboard shortcuts")},
                    {"key": "<Control>q", "description": _("Quit application")},
                ],
            },
            # Navigation
            {
                "category": _("Navigation"),
                "shortcuts": [
                    {"key": "Escape", "description": _("Clear search / go back")},
                ],
            },
        ]

    def _populate_shortcuts_list(self) -> None:
        """Populate the shortcuts list with categorized shortcuts."""
        # Track (group, [rows]) pairs explicitly. Iterating a Gtk.ListBox in
        # GTK4 yields the auto-generated Gtk.ListBoxRow wrappers (not the
        # PreferencesGroup we appended), and iterating an Adw.PreferencesGroup
        # yields its internal Gtk.Box — so isinstance() checks against
        # Adw.PreferencesGroup / Adw.ActionRow during iteration always fail
        # and the search filter would silently do nothing without this.
        self._groups: list[tuple[Adw.PreferencesGroup, list[Adw.ActionRow]]] = []

        for category_data in self.shortcuts_data:
            group = Adw.PreferencesGroup()
            # Adw.PreferencesGroup titles are parsed as Pango markup, so any
            # literal ``&`` (e.g. "Screenshot & OCR") must be escaped.
            group.set_title(GLib.markup_escape_text(category_data["category"]))
            rows: list[Adw.ActionRow] = []

            for shortcut in category_data["shortcuts"]:
                row = Adw.ActionRow()
                row.set_title(shortcut["description"])

                shortcut_label = Gtk.ShortcutLabel()
                shortcut_label.set_accelerator(shortcut["key"])
                shortcut_label.set_valign(Gtk.Align.CENTER)

                row.add_suffix(shortcut_label)
                group.add(row)
                rows.append(row)

            self.shortcuts_list.append(group)
            self._groups.append((group, rows))

    def _connect_signals(self) -> None:
        """Connect signals for search and window events."""
        self._search_handler_id = self.search_entry.connect("search-changed", self._on_search_changed)

        self._close_handler_id = self.connect("close-request", self._on_close_request)

        # Use CAPTURE phase so Escape closes the window even when focus is in
        # the SearchEntry (which would otherwise consume the key event via its
        # built-in stop-search handling).
        self._key_controller = Gtk.EventControllerKey()
        self._key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._key_pressed_handler_id = self._key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(self._key_controller)

    def do_destroy(self) -> None:
        """Clean up signal handlers to prevent memory leaks."""
        import contextlib

        if getattr(self, "_search_handler_id", None) is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self.search_entry.disconnect(self._search_handler_id)
            self._search_handler_id = None
        if getattr(self, "_close_handler_id", None) is not None:
            with contextlib.suppress(TypeError, RuntimeError):
                self.disconnect(self._close_handler_id)
            self._close_handler_id = None

        if getattr(self, "_key_controller", None) is not None:
            if getattr(self, "_key_pressed_handler_id", None) is not None:
                with contextlib.suppress(TypeError, RuntimeError):
                    self._key_controller.disconnect(self._key_pressed_handler_id)
                self._key_pressed_handler_id = None
            self.remove_controller(self._key_controller)
            self._key_controller = None

        super().do_destroy()

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Handle search entry changes."""
        query = entry.get_text().lower()
        any_visible = False

        for group, rows in self._groups:
            visible_count = 0
            for child_row in rows:
                title = child_row.get_title().lower()
                if not query or query in title:
                    child_row.set_visible(True)
                    visible_count += 1
                else:
                    child_row.set_visible(False)

            group.set_visible(visible_count > 0)
            if visible_count > 0:
                any_visible = True

        if any_visible:
            self.stack.set_visible_child_name("results")
        else:
            self.stack.set_visible_child_name("no_results")

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        """Handle window close request."""
        self.emit("closed")
        return False

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        """Handle key press events from the EventControllerKey."""
        if keyval == Gdk.KEY_Escape:
            if self.search_entry.get_text():
                self.search_entry.set_text("")
                self.search_entry.emit("search-changed")
                return True
            self.close()
            return True
        return False


def show_shortcuts_overlay(parent_window: Gtk.Window) -> None:
    """Show the keyboard shortcuts overlay."""
    try:
        overlay = ShortcutsOverlay(transient_for=parent_window)
        overlay.present()
    except (AttributeError, RuntimeError, TypeError, GLib.Error) as e:
        from loguru import logger

        logger.error(f"Failed to show shortcuts overlay: {e}")
