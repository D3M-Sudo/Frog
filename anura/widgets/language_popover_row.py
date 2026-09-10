# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _

from gi.repository import GObject, Gtk

from anura.config import RESOURCE_PREFIX
from anura.models.language_item import LanguageItem


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/language_popover_row.ui")
class LanguagePopoverRow(Gtk.ListBoxRow):
    __gtype_name__ = "LanguagePopoverRow"

    lang: LanguageItem

    # Widgets
    title: Gtk.Label = Gtk.Template.Child()
    selection: Gtk.Image = Gtk.Template.Child()
    selection_revealer: Gtk.Revealer = Gtk.Template.Child()

    def __init__(self, lang: LanguageItem) -> None:
        super().__init__()
        self.lang = lang
        self.title.set_label(self.lang.title)

        self.lang.bind_property(
            "selected",
            self.selection_revealer,
            "reveal-child",
            GObject.BindingFlags.SYNC_CREATE,
        )

        # ARIA: Keep the SELECTED state, tooltip, and accessible label in sync
        self._selected_handler_id = self.lang.connect("notify::selected", self._on_selected_changed)
        self._update_accessibility_metadata()

    def _update_accessibility_metadata(self) -> None:
        """Update tooltip, accessible label and SELECTED state based on active selection state."""
        is_selected = self.lang.selected if self.lang else False
        if is_selected:
            tooltip = _("{language} (active language)").format(language=self.lang.title)
        else:
            tooltip = _("Select {language}").format(language=self.lang.title)

        self.set_tooltip_text(tooltip)
        self.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])
        self.update_state([Gtk.AccessibleState.SELECTED], [is_selected])

    def _on_selected_changed(self, _obj: GObject.GObject, _pspec: GObject.ParamSpec) -> None:
        self._update_accessibility_metadata()

    def do_dispose(self) -> None:
        """Disconnect notification signals during dispose to prevent memory leaks."""
        if hasattr(self, "_selected_handler_id") and self._selected_handler_id and self.lang:
            self.lang.disconnect(self._selected_handler_id)
            self._selected_handler_id = 0
        super().do_dispose()
