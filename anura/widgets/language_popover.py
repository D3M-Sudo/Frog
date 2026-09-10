# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _
from gettext import ngettext
from typing import ClassVar

from gi.repository import Gdk, Gio, GLib, GObject, Gtk
from loguru import logger

from anura.config import RESOURCE_PREFIX
from anura.models.language_item import LanguageItem
from anura.services.language_manager import get_language_manager
from anura.services.settings import settings
from anura.utils.signal_manager import SignalManagerMixin
from anura.widgets.language_popover_row import LanguagePopoverRow


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/language_popover.ui")
class LanguagePopover(Gtk.Popover, SignalManagerMixin):
    __gtype_name__ = "LanguagePopover"

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "language-changed": (GObject.SignalFlags.RUN_LAST, None, (LanguageItem,)),
    }

    views: Gtk.Stack = Gtk.Template.Child()
    search_box: Gtk.Box = Gtk.Template.Child()
    entry: Gtk.SearchEntry = Gtk.Template.Child()
    list_view: Gtk.ListBox = Gtk.Template.Child()

    lang_list: Gio.ListStore = Gio.ListStore(item_type=LanguageItem)
    filter_list: Gtk.FilterListModel
    filter: Gtk.CustomFilter

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        self.settings = settings

        self.connect_tracked(get_language_manager(), "downloaded", self._on_language_downloaded)
        self.connect_tracked(get_language_manager(), "removed", self._on_language_removed)

        self._active_language = self.settings.get_string("active-language")

        self.bind_model()

        # Keyboard navigation: Allow Down arrow in search entry to focus the language list
        self._key_controller = Gtk.EventControllerKey()
        self._key_controller.connect("key-pressed", self._on_entry_key_pressed)
        self.entry.add_controller(self._key_controller)

    def bind_model(self) -> None:
        """Bind the language model to the filter."""
        self.filter = Gtk.CustomFilter()
        self.filter.set_filter_func(self._on_language_filter)
        self.filter_list = Gtk.FilterListModel.new(self.lang_list, self.filter)
        self.list_view.bind_model(self.filter_list, LanguagePopoverRow)

    @GObject.Property(type=str)
    def active_language(self) -> str:
        """Get the currently active language."""
        return self._active_language

    @active_language.setter  # type: ignore[no-redef]
    def active_language(self, lang_code: str) -> None:
        self._active_language = lang_code

    def _on_entry_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        """Handle Down arrow key in search entry to navigate into the language list."""
        if keyval in (Gdk.KEY_Down, Gdk.KEY_KP_Down) and self.filter_list.get_n_items() > 0:
            first_row = self.list_view.get_row_at_index(0)
            if first_row:
                first_row.grab_focus()
                return True
        return False

    def _on_language_filter(self, proposal: LanguageItem, text: str | None = None) -> bool:
        if not text:
            return True
        return text.lower() in proposal.title.lower()

    def _on_language_downloaded(self, _sender: GObject.GObject, _lang_code: str) -> None:
        self.populate_model(force=True)

    def _on_language_removed(self, _sender: GObject.GObject, _lang_code: str) -> None:
        self.populate_model(force=True)

    @Gtk.Template.Callback()
    def _on_search_activate(self, entry: Gtk.SearchEntry) -> None:
        if self.filter_list.get_n_items() > 0:
            first_row = self.list_view.get_row_at_index(0)
            if first_row:
                self._on_language_activate(self.list_view, first_row)

    @Gtk.Template.Callback()
    def _on_language_activate(self, _: Gtk.ListBox, row: LanguagePopoverRow) -> None:
        item: LanguageItem = row.lang
        self.emit("language-changed", item)
        self.active_language = item.code  # type: ignore[method-assign]
        get_language_manager().active_language = item  # type: ignore[method-assign]

        self.settings.set_string("active-language", item.code)
        logger.debug(f"Anura: OCR language changed to '{item.code}'")
        self.popdown()

    @Gtk.Template.Callback()
    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text().strip()
        self.filter.set_filter_func(self._on_language_filter, query)
        count = self.filter_list.get_n_items()
        self.toggle_empty_state(not count)

        if not query:
            label = _("Language list")
        elif count == 0:
            label = _("Language list — No matching languages found")
        else:
            label = ngettext(
                "Language list ({n} matching language)",
                "Language list ({n} matching languages)",
                count,
            ).format(n=count)

        self.list_view.update_property([Gtk.AccessibleProperty.LABEL], [label])

    @Gtk.Template.Callback()
    def _on_stop_search(self, _entry: Gtk.SearchEntry) -> None:
        self.popdown()

    @Gtk.Template.Callback()
    def _on_popover_show(self, _: object) -> None:
        self.populate_model(force=False)
        self.entry.grab_focus()

    @Gtk.Template.Callback()
    def _on_popover_closed(self, *_args: object) -> None:
        self.entry.set_text("")
        self.list_view.update_property([Gtk.AccessibleProperty.LABEL], [_("Language list")])

    @Gtk.Template.Callback()
    def _on_add_clicked(self, _: Gtk.Widget) -> None:
        self.activate_action("app.preferences")
        self.popdown()

    def populate_model(self, force: bool = False) -> None:
        """Populate the language model with available languages."""
        try:
            downloaded_codes = get_language_manager().get_downloaded_codes(force=force)

            # BUG-042: UI Flickering Risk.
            # Compare current model with new codes to avoid full remove_all() if unchanged.
            current_codes = [self.lang_list.get_item(i).code for i in range(self.lang_list.get_n_items())]

            if set(current_codes) != set(downloaded_codes) or force:
                self.lang_list.remove_all()
                for code in downloaded_codes:
                    title = get_language_manager().get_language(code)
                    selected = self.active_language == code
                    self.lang_list.append(LanguageItem(code=code, title=title, selected=selected))
            else:
                # Only update 'selected' status if set of languages is the same
                for i in range(self.lang_list.get_n_items()):
                    item = self.lang_list.get_item(i)
                    item.selected = self.active_language == item.code

            # Fallback to English if current language was removed, emitting only on actual change
            current_code = self.active_language
            if current_code not in downloaded_codes:
                new_item = get_language_manager().get_language_item("eng")
                if new_item and self.active_language != "eng":  # emit only if language actually changed
                    self.active_language = "eng"  # type: ignore[method-assign]
                    self.settings.set_string("active-language", "eng")
                    self.emit("language-changed", new_item)

        except (AttributeError, RuntimeError, TypeError, GLib.Error) as e:
            logger.error(f"Failed to populate language model: {e}")
            # Ensure UI doesn't remain empty
            self.toggle_empty_state(True)

    def toggle_empty_state(self, is_empty: bool = False) -> None:
        """Toggle between empty and languages state views."""
        if is_empty:
            self.views.set_visible_child_name("empty_page")
        else:
            self.views.set_visible_child_name("languages_page")

    def do_destroy(self) -> None:
        """Clean up all tracked signal handlers to prevent memory leaks."""
        if hasattr(self, "_key_controller") and self._key_controller:
            self.entry.remove_controller(self._key_controller)
            self._key_controller = None
        self.teardown_all()
        super().do_destroy()
