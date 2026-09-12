# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _
from gettext import ngettext
from gettext import pgettext as C_
from typing import ClassVar

import gi

# Set GTK version requirements before imports
gi.require_version("Adw", "1")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gtk", "4.0")
gi.require_version("GtkSource", "5")

from gi.repository import Adw, Gio, GLib, GObject, Gtk, GtkSource  # noqa: E402
from loguru import logger  # noqa: E402

from anura.config import RESOURCE_PREFIX  # noqa: E402
from anura.services.settings import settings  # noqa: E402
from anura.services.share_service import get_share_service  # noqa: E402
from anura.utils.signal_manager import SignalManagerMixin  # noqa: E402
from anura.widgets.share_row import ShareRow  # noqa: E402


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/extracted_page.ui")
class ExtractedPage(Adw.NavigationPage, SignalManagerMixin):
    __gtype_name__ = "ExtractedPage"

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "go-back": (GObject.SignalFlags.RUN_LAST, None, (int,)),
        "on-listen-start": (GObject.SignalFlags.RUN_LAST, None, ()),
        "on-listen-stop": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    stats_label: Gtk.Label = Gtk.Template.Child()
    transformer_label: Gtk.Label = Gtk.Template.Child()
    share_list_box: Gtk.ListBox = Gtk.Template.Child()
    grab_btn: Gtk.Button = Gtk.Template.Child()
    text_copy_btn: Gtk.Button = Gtk.Template.Child()
    listen_stack: Gtk.Stack = Gtk.Template.Child()
    listen_btn: Gtk.Button = Gtk.Template.Child()
    listen_pause_btn: Gtk.Button = Gtk.Template.Child()
    listen_spinner: Gtk.Spinner = Gtk.Template.Child()
    share_button: Gtk.MenuButton = Gtk.Template.Child()
    text_view: GtkSource.View = Gtk.Template.Child()
    buffer: GtkSource.Buffer = Gtk.Template.Child()
    search_button: Gtk.ToggleButton = Gtk.Template.Child()
    search_bar: Gtk.SearchBar = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    search_count_label: Gtk.Label = Gtk.Template.Child()
    search_case_btn: Gtk.ToggleButton = Gtk.Template.Child()
    search_prev_btn: Gtk.Button = Gtk.Template.Child()
    search_next_btn: Gtk.Button = Gtk.Template.Child()
    undo_btn: Gtk.Button = Gtk.Template.Child()
    redo_btn: Gtk.Button = Gtk.Template.Child()

    def __init__(self, **kwargs: object) -> None:
        # Pre-initialize attributes to avoid AttributeError during failed template init
        self.settings = settings
        self._share_service = None

        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        self.search_settings = GtkSource.SearchSettings.new()
        self.search_context = GtkSource.SearchContext.new(self.buffer, self.search_settings)

        if self.search_bar and self.search_entry:
            self.search_bar.connect_entry(self.search_entry)
            self.search_bar.set_key_capture_widget(self.text_view)
            if self.search_button:
                self.search_bar.bind_property(
                    "search-mode-enabled",
                    self.search_button,
                    "active",
                    GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
                )

            self.connect_tracked(self.search_entry, "search-changed", self._on_search_text_changed)
            self.connect_tracked(self.search_entry, "activate", self._on_search_next)
            self.connect_tracked(self.search_case_btn, "notify::active", self._on_case_sensitivity_changed)
            self.connect_tracked(self.search_prev_btn, "clicked", self._on_search_prev)
            self.connect_tracked(self.search_next_btn, "clicked", self._on_search_next)
            if self.search_context:
                self.connect_tracked(
                    self.search_context, "notify::occurrences-count", self._on_search_occurrences_changed
                )

        # Defensive check: ensure critical template components are loaded
        if not self.share_list_box:
            logger.error("ExtractedPage: share_list_box not found in template")
        else:
            self._share_service = get_share_service()
            for provider in self._share_service.providers():
                self.share_list_box.append(ShareRow(provider))
            # Connect to share signal to automatically popdown the menu
            self.connect_tracked(self._share_service, "share", self._on_share_finished)

        self.connect_tracked(self.buffer, "changed", self._on_buffer_changed)
        self.connect_tracked(self.buffer, "mark-set", self._on_mark_set)

        if self.text_view:
            self.settings.bind(
                "editor-show-line-numbers", self.text_view, "show-line-numbers", Gio.SettingsBindFlags.DEFAULT
            )
            self.settings.bind(
                "editor-highlight-current-line",
                self.text_view,
                "highlight-current-line",
                Gio.SettingsBindFlags.DEFAULT,
            )
            self._apply_wrap_mode()
            self.connect_tracked(self.settings, "changed::editor-wrap-mode", self._on_wrap_mode_setting_changed)

        # Accessibility: set tooltip for the stats label
        self.stats_label.set_tooltip_text(
            _("Shows character and word count. If text is selected, shows selection stats.")
        )

        self.buffer.set_enable_undo(True)

        # Undo/Redo buttons: sensitivity driven by the buffer undo stack
        if self.undo_btn and self.redo_btn:
            self.buffer.bind_property(
                "can-undo", self.undo_btn, "sensitive", GObject.BindingFlags.SYNC_CREATE
            )
            self.buffer.bind_property(
                "can-redo", self.redo_btn, "sensitive", GObject.BindingFlags.SYNC_CREATE
            )
            self.connect_tracked(self.undo_btn, "clicked", self._on_undo)
            self.connect_tracked(self.redo_btn, "clicked", self._on_redo)

    def _apply_wrap_mode(self) -> None:
        mode_str = self.settings.get_string("editor-wrap-mode")
        mapping = {
            "word": Gtk.WrapMode.WORD,
            "char": Gtk.WrapMode.CHAR,
            "none": Gtk.WrapMode.NONE,
        }
        wrap_enum = mapping.get(mode_str, Gtk.WrapMode.WORD)
        if self.text_view:
            self.text_view.set_wrap_mode(wrap_enum)

    def _on_wrap_mode_setting_changed(self, _settings: object, _key: str) -> None:
        self._apply_wrap_mode()

    def _on_undo(self, *_args: object) -> None:
        """Undo the last user edit in the buffer."""
        if self.buffer and self.buffer.can_undo():
            self.buffer.undo()

    def _on_redo(self, *_args: object) -> None:
        """Redo the last undone edit in the buffer."""
        if self.buffer and self.buffer.can_redo():
            self.buffer.redo()

    def _on_buffer_changed(self, buffer: GtkSource.Buffer) -> None:
        """Update action sensitivities when buffer changes."""
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        has_text = bool(text.strip()) if text else False

        # Update action sensitivity based on text presence
        if self.text_copy_btn:
            self.text_copy_btn.set_sensitive(has_text)
        if self.share_button:
            self.share_button.set_sensitive(has_text)
        if self.listen_btn:
            self.listen_btn.set_sensitive(has_text)

        self._update_stats_label()

    def _on_mark_set(self, _buffer: Gtk.TextBuffer, _location: Gtk.TextIter, mark: Gtk.TextMark) -> None:
        """Update stats label when selection changes."""
        # We only care about the selection bound or the insert mark which define the selection
        if mark.get_name() in ["selection_bound", "insert"]:
            self._update_stats_label()

    def _update_stats_label(self) -> None:
        """Update character and word count in the status bar label, considering selection."""
        selection = self.buffer.get_selection_bounds()
        if selection:
            start, end = selection
            text = self.buffer.get_text(start, end, False)
            # Use a prefix to indicate these are selection stats
            prefix = _("Selection: ")
        else:
            text = self.extracted_text
            prefix = ""

        char_count = len(text) if text else 0
        word_count = len(text.split()) if text else 0

        words_text = ngettext("{n} word", "{n} words", word_count).format(n=word_count)
        chars_text = ngettext("{n} character", "{n} characters", char_count).format(n=char_count)

        # Construct the stats label using a single translatable string
        stats = _("{words} | {chars}").format(words=words_text, chars=chars_text)
        self.stats_label.set_text(f"{prefix}{stats}")

        self._update_action_tooltips(bool(selection))

    def _update_action_tooltips(self, has_selection: bool) -> None:
        """Update tooltips and accessibility labels based on whether text is selected."""
        if has_selection:
            copy_tooltip = C_("Extracted screen", "Copy Selected Text to Clipboard (Ctrl+C)")
            listen_tooltip = C_("Extracted screen", "Listen to Selected Text (Ctrl+L)")
            share_tooltip = C_("Extracted screen", "Share Selection To")
        else:
            copy_tooltip = C_("Extracted screen", "Copy Extracted Text to Clipboard (Ctrl+C)")
            listen_tooltip = C_("Extracted screen", "Listen to Text (Ctrl+L)")
            share_tooltip = C_("Extracted screen", "Share To")

        if self.text_copy_btn:
            self.text_copy_btn.set_tooltip_text(copy_tooltip)
            self.text_copy_btn.update_property([Gtk.AccessibleProperty.LABEL], [copy_tooltip])

        if self.listen_btn:
            self.listen_btn.set_tooltip_text(listen_tooltip)
            self.listen_btn.update_property([Gtk.AccessibleProperty.LABEL], [listen_tooltip])

        if self.share_button:
            self.share_button.set_tooltip_text(share_tooltip)
            self.share_button.update_property([Gtk.AccessibleProperty.LABEL], [share_tooltip])

    def show_copy_feedback(self) -> None:
        """Temporarily change the copy button icon, tooltip and accessible label for UX feedback."""
        if not self.text_copy_btn:
            return

        # Defensive: if already showing feedback, don't nested-capture the checkmark
        if self.text_copy_btn.get_icon_name() == "emblem-ok-symbolic":
            return

        # Store original icon and switch to checkmark
        original_icon = self.text_copy_btn.get_icon_name()
        self.text_copy_btn.set_icon_name("emblem-ok-symbolic")

        # Temporarily update tooltip and screen reader accessible label
        copied_text = C_("Extracted screen", "Copied to clipboard!")
        self.text_copy_btn.set_tooltip_text(copied_text)
        self.text_copy_btn.update_property([Gtk.AccessibleProperty.LABEL], [copied_text])

        GLib.timeout_add_seconds(2, self._reset_copy_icon, original_icon)

    def _reset_copy_icon(self, icon_name: str) -> bool:
        """Helper to reset copy button icon, tooltip and accessible label."""
        try:
            if self.text_copy_btn and self.text_copy_btn.get_icon_name() == "emblem-ok-symbolic":
                # Only reset if it's still showing the checkmark (don't overwrite newer state)
                self.text_copy_btn.set_icon_name(icon_name)
                # Restore original tooltip and accessibility label based on the active selection state
                has_selection = bool(self.buffer.get_selection_bounds()) if self.buffer else False
                self._update_action_tooltips(has_selection)
        except (AttributeError, RuntimeError, TypeError) as e:
            logger.exception(f"Anura: Failed to reset copy icon: {e}")
        return GLib.SOURCE_REMOVE

    def do_hiding(self) -> None:
        """Handle widget hiding event."""
        self.buffer.set_text("")
        self.emit("go-back", 1)

    def do_unmap(self) -> None:
        """Handle widget unmapping."""
        Gtk.Widget.do_unmap(self)

    def do_dispose(self) -> None:
        """Handle widget disposal."""
        # SignalManagerMixin handles all disconnects via do_destroy or explicit teardown_all
        super().do_dispose()

    @GObject.Property(type=str)
    def extracted_text(self) -> str:
        """Get the extracted text from the buffer."""
        return self.buffer.get_text(
            start=self.buffer.get_start_iter(),
            end=self.buffer.get_end_iter(),
            include_hidden_chars=False,
        )

    @extracted_text.setter  # type: ignore[no-redef]
    def extracted_text(self, text: str) -> None:
        self.set_extracted_text(text)

    def set_extracted_text(self, text: str, transformer_name: str = "") -> None:
        """Set the extracted text and optionally show the applied transformer."""
        GLib.idle_add(self._set_text_internal, text, transformer_name)

    def _set_text_internal(self, text: str, transformer_name: str) -> bool:
        """Atomic UI update for extracted text."""
        try:
            self.buffer.set_text(text)
            if transformer_name:
                self.transformer_label.set_text(_("Smart Parse: {name}").format(name=transformer_name))
                self.transformer_label.set_visible(True)
            else:
                self.transformer_label.set_visible(False)
        except (GLib.Error, ValueError) as e:
            logger.error(f"Error setting extracted text: {e}")
        return GLib.SOURCE_REMOVE

    def toggle_search(self) -> None:
        """Toggle search bar visibility and focus entry."""
        if not self.search_bar:
            return
        is_active = not self.search_bar.get_search_mode()
        self.search_bar.set_search_mode(is_active)
        if is_active:
            selection = self.buffer.get_selection_bounds()
            if selection:
                start, end = selection
                text = self.buffer.get_text(start, end, False)
                if text and "\n" not in text:
                    self.search_entry.set_text(text)
            self.search_entry.grab_focus()

    def _on_search_text_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text()
        if text:
            self.search_settings.set_search_text(text)
            self.search_context.set_highlight(True)
            self._navigate_search(forward=True, wrap=True)
        else:
            self.search_settings.set_search_text(None)
            self.search_context.set_highlight(False)
            if self.search_count_label:
                self.search_count_label.set_text("")

    def _on_case_sensitivity_changed(self, btn: Gtk.ToggleButton, _param: object) -> None:
        self.search_settings.set_case_sensitive(btn.get_active())

    def _on_search_occurrences_changed(self, search_context: GtkSource.SearchContext, _param: object) -> None:
        if not self.search_count_label or not self.search_settings.get_search_text():
            return
        count = search_context.get_occurrences_count()
        if count == -1:
            self.search_count_label.set_text(_("Searching…"))
        elif count == 0:
            self.search_count_label.set_text(_("No matches"))
        else:
            self.search_count_label.set_text(ngettext("{n} match", "{n} matches", count).format(n=count))

    def _on_search_next(self, *_args: object) -> None:
        self._navigate_search(forward=True, wrap=True)

    def _on_search_prev(self, *_args: object) -> None:
        self._navigate_search(forward=False, wrap=True)

    def _navigate_search(self, forward: bool = True, wrap: bool = True) -> None:
        if not self.search_settings.get_search_text() or not self.search_context:
            return

        selection = self.buffer.get_selection_bounds()
        if selection:
            start_iter = selection[1] if forward else selection[0]
        else:
            start_iter = self.buffer.get_iter_at_mark(self.buffer.get_insert())

        found = False
        match_start = None
        match_end = None

        if hasattr(self.search_context, "forward2") and forward:
            res = self.search_context.forward2(start_iter)
            if res and res[0]:
                found, match_start, match_end = res[0], res[1], res[2]
        elif hasattr(self.search_context, "backward2") and not forward:
            res = self.search_context.backward2(start_iter)
            if res and res[0]:
                found, match_start, match_end = res[0], res[1], res[2]

        if found and match_start and match_end:
            self.buffer.select_range(match_start, match_end)
            self.text_view.scroll_to_iter(match_start, 0.1, False, 0.0, 0.0)

    def get_active_text(self) -> str:
        """Get selected text if available, otherwise the full text."""
        selection = self.buffer.get_selection_bounds()
        if selection:
            start, end = selection
            return self.buffer.get_text(start, end, False)
        return self.extracted_text

    def _on_share_finished(self, _service: object, _success: bool) -> None:
        """Handle share completion - close the popover."""
        popover = self.share_button.get_popover()
        if popover:
            popover.popdown()

    def update_tts_state(self, state: str) -> None:
        """Update the TTS UI state (called from TtsController via AnuraWindow)."""
        if state == "generating":
            self.swap_controls(True)
            if self.listen_stack:
                self.listen_stack.set_visible_child_name("spinner")
            if self.listen_spinner:
                self.listen_spinner.start()
            if self.listen_btn:
                self.listen_btn.update_state([Gtk.AccessibleState.PRESSED], [False])
        elif state == "playing":
            self.swap_controls(True)
            if self.listen_stack:
                self.listen_stack.set_visible_child_name("pause")
            if self.listen_spinner:
                self.listen_spinner.stop()
            if self.listen_pause_btn:
                self.listen_pause_btn.set_icon_name("media-playback-pause-symbolic")
                self.listen_pause_btn.update_state([Gtk.AccessibleState.PRESSED], [True])
                self.listen_pause_btn.set_tooltip_text(C_("Extracted screen", "Pause listening (Ctrl+Alt+L)"))
                self.listen_pause_btn.update_property([Gtk.AccessibleProperty.LABEL], [C_("Extracted screen", "Pause listening")])
        elif state == "paused":
            self.swap_controls(True)
            if self.listen_stack:
                self.listen_stack.set_visible_child_name("pause")
            if self.listen_pause_btn:
                self.listen_pause_btn.set_icon_name("media-playback-start-symbolic")
                self.listen_pause_btn.update_state([Gtk.AccessibleState.PRESSED], [False])
                self.listen_pause_btn.set_tooltip_text(C_("Extracted screen", "Resume listening (Ctrl+Alt+L)"))
                self.listen_pause_btn.update_property([Gtk.AccessibleProperty.LABEL], [C_("Extracted screen", "Resume listening")])
        else:  # idle
            self.swap_controls(False)
            if self.listen_stack:
                self.listen_stack.set_visible_child_name("button")
            if self.listen_spinner:
                self.listen_spinner.stop()
            if self.listen_btn:
                self.listen_btn.update_state([Gtk.AccessibleState.PRESSED], [False])

    def swap_controls(self, locked: bool) -> None:
        """Enable or disable interactive controls during TTS playback."""
        if self.grab_btn:
            self.grab_btn.set_sensitive(not locked)
        if self.text_copy_btn:
            self.text_copy_btn.set_sensitive(not locked)

    def do_destroy(self) -> None:
        """Clean up signal handlers to prevent memory leaks."""
        # do_dispose() already handles TTS and share service cleanup
        super().do_destroy()
