# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import contextlib
from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk
from loguru import logger

from anura.config import RESOURCE_PREFIX
from anura.services.language_manager import get_language_manager
from anura.services.settings import settings
from anura.services.tts import get_tts_service
from anura.utils.signal_manager import SignalManagerMixin


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/preferences_general.ui")
class PreferencesGeneralPage(Adw.PreferencesPage, SignalManagerMixin):
    __gtype_name__ = "PreferencesGeneralPage"

    color_scheme_combo: Adw.ComboRow = Gtk.Template.Child()
    extra_language_combo: Adw.ComboRow = Gtk.Template.Child()
    magic_processor_switch: Adw.SwitchRow = Gtk.Template.Child()
    autocopy_switch: Adw.SwitchRow = Gtk.Template.Child()
    autolinks_switch: Adw.SwitchRow = Gtk.Template.Child()
    volume_row: Adw.SpinRow = Gtk.Template.Child()
    tts_language_combo: Adw.ComboRow = Gtk.Template.Child()
    history_switch: Adw.SwitchRow = Gtk.Template.Child()
    history_limit_row: Adw.SpinRow = Gtk.Template.Child()
    editor_line_numbers_switch: Adw.SwitchRow = Gtk.Template.Child()
    editor_highlight_line_switch: Adw.SwitchRow = Gtk.Template.Child()
    editor_wrap_mode_combo: Adw.ComboRow = Gtk.Template.Child()

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        self.settings = settings

        self.settings.bind("autocopy", self.autocopy_switch, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind("autolinks", self.autolinks_switch, "active", Gio.SettingsBindFlags.DEFAULT)
        self.settings.bind(
            "magic-processor-enabled", self.magic_processor_switch, "active", Gio.SettingsBindFlags.DEFAULT
        )
        self.settings.bind(
            "editor-show-line-numbers", self.editor_line_numbers_switch, "active", Gio.SettingsBindFlags.DEFAULT
        )
        self.settings.bind(
            "editor-highlight-current-line",
            self.editor_highlight_line_switch,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        self._setup_color_scheme()
        self._setup_editor_wrap_mode()
        self._setup_extra_languages()

        self.connect_tracked(get_language_manager(), "downloaded", self._on_language_changed)
        self.connect_tracked(get_language_manager(), "removed", self._on_language_changed)

        self._setup_tts_volume()
        # TTS language setup depends on the (possibly network-backed) TTS
        # service; a failure there must not abort __init__ or any later
        # settings binding (e.g. history-enabled would never be bound).
        with contextlib.suppress(Exception):
            self._setup_tts_language()
        self._setup_history()

    def _setup_history(self) -> None:
        """Initialize History settings (enabled switch + size limit spin row)."""
        self.settings.bind("history-enabled", self.history_switch, "active", Gio.SettingsBindFlags.DEFAULT)

        # SpinRow works with doubles; the GSettings key is an integer (entries count)
        self.history_limit_row.set_value(float(self.settings.get_int("history-limit")))
        self.connect_tracked(self.history_limit_row, "notify::value", self._on_history_limit_changed)

    def _on_history_limit_changed(self, spin_row: Adw.SpinRow, _param: object) -> None:
        """Persist the history size limit as integer, clamped to the schema range."""
        value = int(spin_row.get_value())
        self.settings.set_int("history-limit", value)
        logger.debug(f"Anura: History size limit set to {value}")

    def _setup_editor_wrap_mode(self) -> None:
        from gettext import pgettext

        modes = [
            pgettext("wrap-mode", "Words"),
            pgettext("wrap-mode", "Characters"),
            pgettext("wrap-mode", "Disabled"),
        ]
        self.editor_wrap_mode_combo.set_model(Gtk.StringList.new(modes))
        mode = self.settings.get_string("editor-wrap-mode")
        mapping = {"word": 0, "char": 1, "none": 2}
        idx = mapping.get(mode, 0)
        self.editor_wrap_mode_combo.set_selected(idx)
        self.connect_tracked(self.editor_wrap_mode_combo, "notify::selected", self._on_editor_wrap_mode_changed)

    def _on_editor_wrap_mode_changed(self, combo: Adw.ComboRow, _param: object) -> None:
        idx = combo.get_selected()
        mapping = {0: "word", 1: "char", 2: "none"}
        mode = mapping.get(idx, "word")
        self.settings.set_string("editor-wrap-mode", mode)

    def _setup_color_scheme(self) -> None:
        """Initialize color scheme selector from settings."""
        from gettext import pgettext
        qualities = [
            pgettext("color-scheme", "System"),
            pgettext("color-scheme", "Light"),
            pgettext("color-scheme", "Dark"),
        ]
        self.color_scheme_combo.set_model(Gtk.StringList.new(qualities))

        scheme = self.settings.get_string("color-scheme")
        mapping = {"default": 0, "force-light": 1, "force-dark": 2}
        idx = mapping.get(scheme, 0)
        self.color_scheme_combo.set_selected(idx)

        self.connect_tracked(self.color_scheme_combo, "notify::selected", self._on_color_scheme_changed)

    def _on_color_scheme_changed(self, combo: Adw.ComboRow, _param: object) -> None:
        idx = combo.get_selected()
        mapping = {0: "default", 1: "force-light", 2: "force-dark"}
        scheme = mapping.get(idx, "default")
        logger.debug(f"Anura: Color scheme preference changed to {scheme}")
        self.settings.set_string("color-scheme", scheme)

    def _setup_extra_languages(self) -> None:
        downloaded_langs = get_language_manager().get_downloaded_languages()
        self.extra_language_combo.set_model(Gtk.StringList.new(downloaded_langs))

        if not downloaded_langs:
            return

        # Connect the signal ALWAYS, regardless of current extra language setting
        self.connect_tracked(self.extra_language_combo, "notify::selected-item", self._on_extra_language_changed)

        current_extra = self.settings.get_string("extra-language")

        # Guard against empty/unset extra-language
        if not current_extra:
            # No extra language configured - leave combo at default (index 0)
            return

        current_name = get_language_manager().get_language(current_extra)

        try:
            index = downloaded_langs.index(current_name)
            self.extra_language_combo.set_selected(index)
        except ValueError:
            logger.warning(f"Anura: Extra language '{current_name}' not found among installed models.")

    def _on_extra_language_changed(self, combo_row: Adw.ComboRow, _param: object) -> None:
        selected_item = combo_row.get_selected_item()
        if not selected_item:
            return
        lang_name = selected_item.get_string()
        lang_code = get_language_manager().get_language_code(lang_name)
        logger.debug(f"Anura: Extra language set to {lang_name} ({lang_code})")
        self.settings.set_string("extra-language", lang_code)

    def _on_language_changed(self, _sender: object, code: str) -> None:
        """Refresh the extra-language combo when models are installed or removed."""
        # If the removed language was the current extra-language, reset it
        current_extra = self.settings.get_string("extra-language")
        if current_extra == code:
            logger.info(f"Anura: Active extra-language '{code}' removed, resetting preference.")
            self.settings.set_string("extra-language", "")

        # Disconnect old combo handler via SignalManagerMixin tracking to avoid
        # stale IDs accumulating in _signal_connections (BUG-4 fix).
        emitter = self.extra_language_combo
        if emitter in self._signal_connections:
            for hid in list(self._signal_connections[emitter]):
                with contextlib.suppress(TypeError, RuntimeError):
                    emitter.disconnect(hid)
            self._signal_connections[emitter].clear()
        self._setup_extra_languages()

    def _setup_tts_volume(self) -> None:
        """Setup TTS volume spin row with percentage display (0-100)."""
        volume_normalized = self.settings.get_double("tts-volume")
        self.volume_row.set_value(volume_normalized * 100)

        # Update subtitle to show current value with %
        self._update_volume_subtitle(volume_normalized * 100)

        # Connect to changes and convert back to 0.0-1.0 for GSettings
        self.connect_tracked(self.volume_row, "notify::value", self._on_volume_changed)

    def _update_volume_subtitle(self, percentage: float) -> None:
        """Update the volume row subtitle to show the percentage."""
        self.volume_row.set_subtitle(_("TTS playback volume level: {percentage:.0f}%").format(percentage=percentage))

    def _on_volume_changed(self, spin_row: Adw.SpinRow, _param: object) -> None:
        """Convert percentage (0-100) to normalized value (0.0-1.0) for GSettings."""
        percentage = spin_row.get_value()
        normalized = percentage / 100.0
        self.settings.set_double("tts-volume", normalized)
        self._update_volume_subtitle(percentage)
        logger.debug(f"Anura: TTS volume set to {percentage:.0f}% ({normalized:.2f})")

    def _setup_tts_language(self) -> None:
        """Populate TTS language combo with gTTS supported languages."""
        supported = get_tts_service().get_supported_languages()

        # Create list: "Auto (follow OCR)" + all supported languages
        lang_names = [_("Auto (follow OCR language)"), *list(supported.values())]
        self.tts_language_combo.set_model(Gtk.StringList.new(lang_names))

        # Select current setting
        current = self.settings.get_string("tts-language")
        if current:
            try:
                idx = list(supported.keys()).index(current) + 1  # +1 for "Auto"
                self.tts_language_combo.set_selected(idx)
            except ValueError:
                self.tts_language_combo.set_selected(0)  # Auto
        else:
            self.tts_language_combo.set_selected(0)  # Auto

        self.connect_tracked(self.tts_language_combo, "notify::selected", self._on_tts_language_changed)

    def _on_tts_language_changed(self, combo: Adw.ComboRow, _param: object) -> None:
        idx = combo.get_selected()
        if idx == 0:
            self.settings.set_string("tts-language", "")  # Auto
        else:
            supported = get_tts_service().get_supported_languages()
            supported_keys = list(supported.keys())
            # Bounds check to prevent IndexError
            if idx - 1 < len(supported_keys):
                lang_code = supported_keys[idx - 1]  # -1 for "Auto"
                self.settings.set_string("tts-language", lang_code)
                logger.debug(f"Anura: TTS language set to {lang_code}")
            else:
                logger.warning(f"Anura: TTS language index {idx} out of bounds, falling back to Auto")
                self.settings.set_string("tts-language", "")

    def do_destroy(self) -> None:
        """Clean up all tracked signal handlers to prevent memory leaks."""
        self.teardown_all()
        super().do_destroy()
