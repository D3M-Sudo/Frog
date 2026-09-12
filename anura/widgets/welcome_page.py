# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _
from mimetypes import guess_type
from pathlib import Path

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from loguru import logger

from anura.config import RESOURCE_PREFIX
from anura.models.language_item import LanguageItem
from anura.services.language_manager import get_language_manager
from anura.services.settings import settings
from anura.utils import mask_url
from anura.utils.signal_manager import SignalManagerMixin
from anura.widgets.language_popover import LanguagePopover


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/welcome_page.ui")
class WelcomePage(Adw.NavigationPage, SignalManagerMixin):
    __gtype_name__ = "WelcomePage"

    spinner: Gtk.Spinner = Gtk.Template.Child()
    welcome: Adw.StatusPage = Gtk.Template.Child()
    screenshot_button: Gtk.Button = Gtk.Template.Child()
    lang_combo: Gtk.MenuButton = Gtk.Template.Child()
    language_popover: LanguagePopover = Gtk.Template.Child()
    drop_button: Gtk.Button = Gtk.Template.Child()
    drop_area: Gtk.Box = Gtk.Template.Child()
    drop_revealer: Gtk.Revealer = Gtk.Template.Child()
    drop_area_label: Gtk.Label = Gtk.Template.Child()

    _language_changed_handler_id: int | None = None
    _drop_button_handler_id: int | None = None

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        self.settings = settings

        self.connect_tracked(self.language_popover, "language-changed", self._on_language_changed)

        current_lang_code = self.settings.get_string("active-language")
        self.lang_combo.set_label(
            get_language_manager().get_language(current_lang_code),
        )

        self.connect_tracked(self.drop_button, "clicked", self._on_drop_button_clicked)
        self._setup_drop_target()

        # Initialize drop_button's accessibility expanded state to False
        if self.drop_button:
            self.drop_button.update_state([Gtk.AccessibleState.EXPANDED], [False])

        # Keyboard support: Add key controller to drop_area to collapse on Escape
        self._drop_key_ctrl = Gtk.EventControllerKey()
        self._drop_key_ctrl.connect("key-pressed", self._on_drop_area_key_pressed)
        self.drop_area.add_controller(self._drop_key_ctrl)

    def _on_drop_area_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        """Collapse the drop area when user presses Escape inside it."""
        if keyval == Gdk.KEY_Escape and self.drop_revealer.get_reveal_child():
            self.drop_revealer.set_reveal_child(False)
            self.drop_button.remove_css_class("suggested-action")
            self.drop_button.set_tooltip_text(_("Drop image here"))
            self.drop_button.update_state([Gtk.AccessibleState.EXPANDED], [False])
            self.drop_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Drop image here")])
            GLib.idle_add(lambda: (self.drop_button.grab_focus(), GLib.SOURCE_REMOVE)[1])
            return True
        return False

    def _setup_drop_target(self) -> None:
        """Configure drop target with DropTargetAsync and explicit text/uri-list.

        We deliberately request only 'text/uri-list' and NOT Gdk.FileList.

        Why: including Gdk.FileList causes GTK to prefer
        'application/vnd.portal.filetransfer' as transfer channel. In VirtualBox
        guests with non-GNOME sessions (LXQt, XFCE, LXDE), xdg-desktop-portal is
        not available — the portal call hangs silently and the callback is NEVER
        invoked (no GLib.Error is raised, making it impossible to detect or recover).

        By requesting 'text/uri-list' exclusively, GDK uses the raw Xdnd protocol
        which PCManFM, Thunar and all standard file managers provide directly,
        bypassing the portal entirely.

        The stream read is fully asynchronous (read_bytes_async) so the GTK
        main loop is never blocked.
        """
        formats = Gdk.ContentFormats.new(["text/uri-list"])
        self._drop_target = Gtk.DropTargetAsync(
            formats=formats,
            actions=Gdk.DragAction.COPY,
        )
        self._drop_cancellable: Gio.Cancellable | None = None

        self.connect_tracked(self._drop_target, "drop", self._on_dnd_drop)
        self.connect_tracked(self._drop_target, "drag-enter", self._on_dnd_enter)
        self.connect_tracked(self._drop_target, "drag-leave", self._on_dnd_leave)

        self.add_controller(self._drop_target)

    def _on_drop_button_clicked(self, _button: Gtk.Button) -> None:
        """Toggle the visibility of the dedicated drop area."""
        try:
            is_revealed = self.drop_revealer.get_reveal_child()
            new_revealed = not is_revealed
            self.drop_revealer.set_reveal_child(new_revealed)
            if new_revealed:
                self.drop_button.add_css_class("suggested-action")
                self.drop_button.set_tooltip_text(_("Hide drop area"))
                self.drop_button.update_state([Gtk.AccessibleState.EXPANDED], [True])
                self.drop_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Hide drop area")])
                # Shift focus directly to the revealed drop area for accessible navigation asynchronously
                GLib.idle_add(lambda: (self.drop_area.grab_focus(), GLib.SOURCE_REMOVE)[1])
            else:
                self.drop_button.remove_css_class("suggested-action")
                self.drop_button.set_tooltip_text(_("Drop image here"))
                self.drop_button.update_state([Gtk.AccessibleState.EXPANDED], [False])
                self.drop_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Drop image here")])
                # Shift focus back to the toggle button asynchronously
                GLib.idle_add(lambda: (self.drop_button.grab_focus(), GLib.SOURCE_REMOVE)[1])
        except Exception as e:
            logger.exception(f"Anura: Failed to handle drop button click: {e}")

    def _on_dnd_enter(self, _target: Gtk.DropTargetAsync, _drop: Gdk.Drop, _x: float, _y: float) -> Gdk.DragAction:
        """Visual feedback when drag enters the drop area."""
        try:
            self.drop_revealer.set_reveal_child(True)
            self.drop_area.add_css_class("drag-hover")
            self.welcome.set_description(_("Drop image to extract text"))
        except (AttributeError, RuntimeError) as e:
            logger.exception(f"Anura: Failed to handle DnD enter: {e}")
        return Gdk.DragAction.COPY

    def _on_dnd_leave(self, _target: Gtk.DropTargetAsync, _drop: Gdk.Drop) -> None:
        """Remove visual feedback when drag leaves the drop area."""
        try:
            self.drop_area.remove_css_class("drag-hover")
            # Only hide if it wasn't already revealed (user clicked button)
            if not self.drop_button.has_css_class("suggested-action"):
                self.drop_revealer.set_reveal_child(False)
            self.welcome.set_description(_("Extract text from anywhere"))
        except (AttributeError, RuntimeError) as e:
            logger.exception(f"Anura: Failed to handle DnD leave: {e}")

    def _on_dnd_drop(self, _target: Gtk.DropTargetAsync, drop: Gdk.Drop, _x: float, _y: float) -> bool:
        """Handle drop signal. Initiates a fully async stream read of text/uri-list.

        We always read text/uri-list (never Gdk.FileList) to bypass the
        xdg-desktop-portal which is unavailable in VirtualBox/non-GNOME guests.
        drop.finish() MUST be called in the final callback (Xdnd protocol requirement).
        """
        self.drop_area.remove_css_class("drag-hover")

        if self._drop_cancellable:
            self._drop_cancellable.cancel()
        self._drop_cancellable = Gio.Cancellable()

        drop.read_async(
            ["text/uri-list"],
            GLib.PRIORITY_DEFAULT,
            self._drop_cancellable,
            self._on_drop_stream_ready,
            drop,
        )
        return True  # Accept the drop; finish() will be called in _on_drop_bytes_ready

    def _on_drop_stream_ready(
        self,
        source_object: Gdk.Drop,
        result: Gio.AsyncResult,
        drop: Gdk.Drop,
    ) -> None:
        """Called when the Xdnd stream is ready. Starts async byte read.

        source_object is the Gdk.Drop that initiated read_async (not an InputStream).
        We immediately start read_bytes_async — no blocking calls here.
        """
        try:
            input_stream, _mime_type = source_object.read_finish(result)
        except GLib.Error as e:
            logger.error(f"DnD: Failed to open drop stream: {e}")
            drop.finish(Gdk.DragAction.COPY)  # Always finish, even on error
            return

        input_stream.read_bytes_async(
            65536,  # 64 KB — more than enough for any URI list
            GLib.PRIORITY_DEFAULT,
            self._drop_cancellable,
            self._on_drop_bytes_ready,
            (input_stream, drop),
        )

    def _on_drop_bytes_ready(
        self,
        input_stream: Gio.InputStream,
        result: Gio.AsyncResult,
        user_data: tuple,
    ) -> None:
        """Called when bytes are available. Parses URIs and triggers OCR.

        This is the end of the async chain. We call drop.finish() here (required),
        then process the first valid local image path.
        """
        stream, drop = user_data

        try:
            gbytes = stream.read_bytes_finish(result)
        except GLib.Error as e:
            logger.error(f"DnD: Failed to read drop bytes: {e}")
            drop.finish(Gdk.DragAction.COPY)
            return
        finally:
            self._drop_cancellable = None

        # Xdnd protocol: always call finish BEFORE processing
        drop.finish(Gdk.DragAction.COPY)

        raw = gbytes.get_data() if gbytes else None
        if not raw:
            logger.error("DnD: Received empty data from drop stream")
            self._show_error_toast(_("No file data received from drop"))
            return

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")

        # Parse text/uri-list: skip comment lines (#) and empty lines
        uris = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]

        if not uris:
            logger.error("DnD: No valid URIs found in drop data")
            self._show_error_toast(_("No valid file found in drop"))
            return

        # Anura processes one image at a time — take the first URI
        gfile = Gio.File.new_for_uri(uris[0])
        local_path = gfile.get_path()

        if not local_path:
            logger.error(f"DnD: URI has no local path: {mask_url(uris[0])}")
            self._show_error_toast(_("Only local files can be dropped"))
            return

        self._process_dropped_path(local_path)

    def _process_dropped_path(self, local_path: str) -> None:
        """Common logic for processing a verified local path from any DnD format."""
        if not Path(local_path).exists():
            logger.error(f"DnD: File not accessible: {local_path}")
            self._show_error_toast(_("File not accessible. Ensure Anura has permission to access this location."))
            return

        (mimetype, _encoding) = guess_type(local_path)
        logger.debug(f"DnD: Dropped file ({mimetype}): {local_path}")

        if not mimetype or not mimetype.startswith("image"):
            self._show_error_toast(_("Only images can be processed that way."))
            return

        window = self.get_root()
        if not window or not hasattr(window, "dnd_controller"):
            logger.error("DnD: Root window missing process_dnd_file_sync")
            self._show_error_toast(_("Failed to process dropped file"))
            return

        self._set_drop_area_processing_state(True)
        self.show_spinner()
        window.dnd_controller.process_dnd_file_sync(local_path)

    def _show_error_toast(self, message: str) -> None:
        """Show error toast to user."""
        window = self.get_root()
        if window and hasattr(window, "show_toast"):
            window.show_toast(message)
        self._set_drop_area_processing_state(False)
        self.hide_spinner()

    def _set_drop_area_processing_state(self, processing: bool) -> None:
        """Set the drop area visual state to indicate processing (OCR in progress)."""
        if processing:
            self.drop_area.add_css_class("drag-processing")
            if self.drop_area_label:
                self.drop_area_label.set_label(_("Processing..."))
            self.drop_area.update_property([Gtk.AccessibleProperty.LABEL], [_("Image drop zone: Processing...")])
        else:
            self.drop_area.remove_css_class("drag-processing")
            if self.drop_area_label:
                self.drop_area_label.set_label(_("Drop image file here"))
            self.drop_area.update_property([Gtk.AccessibleProperty.LABEL], [_("Image drop zone")])

    def reset_drop_area_state(self) -> None:
        """Reset the drop area to its initial state (called after OCR completes)."""
        self._set_drop_area_processing_state(False)
        self.hide_spinner()
        self.drop_revealer.set_reveal_child(False)
        self.drop_button.remove_css_class("suggested-action")
        self.drop_button.set_tooltip_text(_("Drop image here"))
        self.drop_button.update_state([Gtk.AccessibleState.EXPANDED], [False])
        self.drop_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Drop image here")])
        self.welcome.set_description(_("Extract text from anywhere"))

    def set_status(self, status_msg: str) -> None:
        """Update the status label during processing."""
        if self.drop_area_label:
            self.drop_area_label.set_label(status_msg)

    def hide_spinner(self) -> None:
        """Stop and hide the spinner."""
        self.spinner.stop()
        self.spinner.set_visible(False)

    def show_spinner(self) -> None:
        """Start and show the spinner."""
        self.spinner.set_visible(True)
        self.spinner.start()

    def _on_language_changed(self, _: LanguagePopover, language: LanguageItem) -> None:
        self.lang_combo.set_label(language.title)
        self.settings.set_string("active-language", language.code)

    def do_destroy(self) -> None:
        """Clean up signal handlers to prevent memory leaks."""
        # BUG-041: Automated signal teardown via SignalManagerMixin
        self.teardown_all()

        # Cancel any in-flight drop operation
        drop_cancellable = getattr(self, "_drop_cancellable", None)
        if drop_cancellable:
            drop_cancellable.cancel()
            self._drop_cancellable = None

        # Remove key controller
        if hasattr(self, "_drop_key_ctrl") and self._drop_key_ctrl:
            self.drop_area.remove_controller(self._drop_key_ctrl)
            self._drop_key_ctrl = None

        # Remove drop target controller
        if hasattr(self, "_drop_target") and self._drop_target:
            self.remove_controller(self._drop_target)
            self._drop_target = None

        super().do_destroy()
