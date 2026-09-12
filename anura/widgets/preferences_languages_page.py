# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk
from loguru import logger

from anura.config import RESOURCE_PREFIX
from anura.models.language_item import LanguageItem
from anura.services.language_manager import get_language_manager
from anura.services.settings import settings
from anura.utils.signal_manager import SignalManagerMixin
from anura.widgets.language_row import LanguageRow


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/preferences_languages.ui")
class PreferencesLanguagesPage(Adw.PreferencesPage, SignalManagerMixin):
    __gtype_name__ = "PreferencesLanguagesPage"

    banner: Adw.Banner = Gtk.Template.Child()
    views: Gtk.Stack = Gtk.Template.Child()
    search_bar: Gtk.SearchBar = Gtk.Template.Child()
    language_search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    list_view: Gtk.ListView = Gtk.Template.Child()
    model: Gtk.FilterListModel = Gtk.Template.Child()
    list_store: Gio.ListStore = Gtk.Template.Child()
    revealer: Gtk.Revealer = Gtk.Template.Child()
    model_quality_combo: Adw.ComboRow = Gtk.Template.Child()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        self.settings = settings

        # Dynamic language store initialization - use centralized get_language_item pattern
        for lang_code in get_language_manager().get_available_codes():
            item = get_language_manager().get_language_item(lang_code)
            if item is not None:
                self.list_store.append(item)

        # Signals for dynamic model updates (tracked for automatic cleanup)
        self.connect_tracked(get_language_manager(), "added", self.on_language_added)
        self.connect_tracked(get_language_manager(), "downloaded", self.on_language_added)
        self.connect_tracked(get_language_manager(), "removed", self.on_language_removed)

        # UI signal connections (tracked for automatic cleanup)
        self.connect_tracked(self.language_search_entry, "search-changed", self.on_language_search)
        self.connect_tracked(self.language_search_entry, "stop-search", self.on_language_search_stop)
        self.connect_tracked(self.search_bar, "notify::search-mode-enabled", self.on_search_mode_enabled)

        # Bind model quality setting
        self._setup_model_quality()

        self.load_languages()
        self.activate_filter()
        self.check_connection()

    def check_connection(self) -> None:
        """Asynchronously checks network reachability for OCR model downloads."""
        monitor = Gio.NetworkMonitor.get_default()
        address = Gio.NetworkAddress.new("google.com", 443)
        monitor.can_reach_async(address, None, self._on_connection_checked)

    def _on_connection_checked(self, monitor: Gio.NetworkMonitor, result: Gio.AsyncResult) -> None:
        try:
            reachable = monitor.can_reach_finish(result)
        except (GLib.Error, OSError):
            reachable = False

        if not reachable:
            self.banner.set_title(_("OCR models unreachable. Please check your internet connection."))
            self.banner.set_revealed(True)
            return

        if monitor.get_network_metered():
            self.banner.set_title(_("Metered connection detected. Model downloads may incur data costs."))
            self.banner.set_revealed(True)
            return

        self.banner.set_revealed(False)

    @Gtk.Template.Callback()
    def _on_banner_clicked(self, _: object) -> None:
        self.check_connection()

    @Gtk.Template.Callback()
    def _on_item_setup(self, _factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
        item.set_child(LanguageRow())

    @Gtk.Template.Callback()
    def _on_item_bind(self, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        row: LanguageRow = list_item.get_child()
        item: LanguageItem = list_item.get_item()
        row.item = item  # type: ignore[method-assign]

    @Gtk.Template.Callback()
    def _on_add_language(self, _sender: Gtk.Widget) -> None:
        if not self.is_search_mode:
            self.deactivate_filter()
            self.search_bar.set_search_mode(True)
            # Use safe idle wrapper to ensure grab_focus succeeds after layout/mapping
            # Wrapped with lambda returning False (GLib.SOURCE_REMOVE) to prevent infinite reschedule loop if grab_focus returns True.
            GLib.idle_add(lambda: (self.language_search_entry.grab_focus(), GLib.SOURCE_REMOVE)[1])
        else:
            self.activate_filter()
            self.search_bar.set_search_mode(False)

    def load_languages(self) -> None:
        """Load all available languages into the list store."""
        self.list_store.remove_all()
        existing_codes = set()
        for lang_code in get_language_manager().get_available_codes():
            item = get_language_manager().get_language_item(lang_code)
            if item is not None and item.code not in existing_codes:
                self.list_store.append(item)
                existing_codes.add(item.code)

    @property
    def is_search_mode(self) -> bool:
        """Check if search mode is currently active."""
        return self.search_bar.get_search_mode()

    def activate_filter(self, search_text: str | None = None) -> None:
        """Activate search filter with the given text."""
        _filter = Gtk.CustomFilter.new(PreferencesLanguagesPage.filter_func, search_text)
        self.model.set_filter(_filter)
        self.toggle_empty_state(not self.model.get_n_items())

    def deactivate_filter(self) -> None:
        """Deactivate search filter and show all items."""
        self.model.set_filter(None)

    def on_language_search(self, entry: Gtk.SearchEntry, _user_data: object = None) -> None:
        """Handle language search text changes."""
        self.activate_filter(entry.get_text())

    def on_language_search_stop(self, entry: Gtk.SearchEntry) -> None:
        """Handle language search stop event."""
        entry.set_text("")
        self.search_bar.set_search_mode(False)
        self.revealer.set_reveal_child(True)
        self.activate_filter()

    def on_search_mode_enabled(self, _searchbar: object, _enabled: bool) -> None:
        """Handle search mode enabled/disabled event."""
        if not self.search_bar.get_search_mode():
            self.activate_filter()

    @staticmethod
    def filter_func(item: LanguageItem, user_data: str) -> bool:
        """Filter function for language search."""
        if user_data:
            return user_data.lower() in item.title.lower()
        return item.code in get_language_manager().get_downloaded_codes()

    def on_language_added(self, _sender: object, code: str | None = None) -> None:
        """Handle language added event."""
        # Idempotent: only add if not already in the list
        if code is not None:
            existing_codes = {item.code for item in self.list_store}
            if code not in existing_codes:
                item = get_language_manager().get_language_item(code)
                if item is not None:
                    self.list_store.append(item)
        if not self.search_bar.get_search_mode():
            self.activate_filter()

    def on_language_removed(self, _sender: object, _code: str) -> None:
        """Handle language removed event."""
        if not self.search_bar.get_search_mode():
            self.activate_filter()

    def toggle_empty_state(self, is_empty: bool = False) -> None:
        """Toggle between empty and languages state views."""
        state = "empty_state" if is_empty else "languages_state"
        self.views.set_visible_child_name(state)

    def _setup_model_quality(self) -> None:
        """Setup model quality combo box."""
        # Populate the model quality combo box
        qualities = [_("Fast"), _("Standard"), _("Best")]
        self.model_quality_combo.set_model(Gtk.StringList.new(qualities))

        current = self.settings.get_string("tessdata-model")
        mapping = {"fast": 0, "standard": 1, "best": 2}
        self.model_quality_combo.set_selected(mapping.get(current, 0))

        self.connect_tracked(self.model_quality_combo, "notify::selected", self._on_model_quality_changed)

    def _on_model_quality_changed(self, combo: Adw.ComboRow, _param: object) -> None:
        idx = combo.get_selected()
        mapping = {0: "fast", 1: "standard", 2: "best"}
        model = mapping.get(idx, "fast")
        self.settings.set_string("tessdata-model", model)
        logger.debug(f"Anura: Tesseract model quality set to {model}")
        self.load_languages()

    def do_destroy(self) -> None:
        """Clean up all tracked signal handlers to prevent memory leaks."""
        self.teardown_all()
        super().do_destroy()
