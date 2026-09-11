# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import contextlib
from gettext import gettext as _
from io import BytesIO
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gi

# Set GTK version requirements before imports
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk  # noqa: E402
from loguru import logger  # noqa: E402

from anura.config import APP_ID, RESOURCE_PREFIX  # noqa: E402
from anura.controllers.dnd_controller import DndController  # noqa: E402
from anura.controllers.ocr_controller import OcrController  # noqa: E402
from anura.controllers.tts_controller import TtsController  # noqa: E402
from anura.core.atomic_task_manager import get_atomic_manager  # noqa: E402
from anura.models.context import get_app_context  # noqa: E402
from anura.services.clipboard_service import get_clipboard_service  # noqa: E402
from anura.services.history_service import HistoryService  # noqa: E402
from anura.services.language_manager import get_language_manager  # noqa: E402
from anura.services.screenshot_service import ScreenshotService, get_screenshot_service  # noqa: E402
from anura.services.share_service import get_share_service  # noqa: E402
from anura.utils import validate_image_resource  # noqa: E402
from anura.utils.signal_manager import SignalManagerMixin  # noqa: E402
from anura.widgets.extracted_page import ExtractedPage  # noqa: E402
from anura.widgets.history_page import HistoryPage  # noqa: E402
from anura.widgets.preferences_dialog import PreferencesDialog  # noqa: E402
from anura.widgets.welcome_page import WelcomePage  # noqa: E402

if TYPE_CHECKING:
    pass


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/window.ui")
class AnuraWindow(Adw.ApplicationWindow, SignalManagerMixin):
    __gtype_name__ = "AnuraWindow"

    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    navigation_view: Adw.NavigationView = Gtk.Template.Child()
    welcome_page: WelcomePage = Gtk.Template.Child()
    extracted_page: ExtractedPage = Gtk.Template.Child()
    history_page: HistoryPage = Gtk.Template.Child()
    portal_banner: Adw.Banner = Gtk.Template.Child()

    settings: Gio.Settings
    share_service: Any
    backend: ScreenshotService
    ocr_controller: OcrController
    tts_controller: TtsController
    dnd_controller: DndController
    history_service: HistoryService
    _clipboard_service: Any | None
    _screenshot_timeout_id: int | None

    def __init__(self, backend: ScreenshotService | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        SignalManagerMixin.__init__(self)

        app = Gtk.Application.get_default()
        if app is None:
            raise RuntimeError("Cannot get default application")
        self.settings = app.settings

        # Defensive: validate language from settings, fallback to English if corrupted
        lang_code: str = self.settings.get_string("active-language")
        language_manager_instance = get_language_manager()
        item = language_manager_instance.get_language_item(lang_code)
        if item is None:
            item = language_manager_instance.get_language_item("eng")
        if item is None:
            # Ultimate fallback - should never happen for built-in languages
            from anura.models.language_item import LanguageItem

            item = LanguageItem(code="eng", title=_("English"))
        language_manager_instance.active_language = item  # type: ignore[method-assign]

        self._setup_geometry()
        self._apply_capability_constraints()
        self.set_icon_name(APP_ID)

        # Safety timeout for portal screenshot (prevents hidden window on D-Bus hang)
        self._screenshot_timeout_id = None

        # Use shared singleton instance
        self.share_service = get_share_service()
        share_action = Gio.SimpleAction.new("share", GLib.VariantType.new("s"))
        self.connect_tracked(share_action, "activate", self._on_share)
        self.add_action(share_action)

        self.backend = backend  # type: ignore[assignment]
        # History V1: one HistoryService wired once with the configured limit;
        # recording itself is gated by the history-enabled setting at OCR time.
        self.history_service = HistoryService(limit=self.settings.get_int("history-limit"))
        self.history_page.setup(self.history_service)
        self.ocr_controller = OcrController(self, history_service=self.history_service)

        show_history_action = Gio.SimpleAction.new("show-history", None)
        self.connect_tracked(show_history_action, "activate", self._on_show_history)
        self.add_action(show_history_action)
        self.tts_controller = TtsController(self)
        self.dnd_controller = DndController(self)

        self._setup_controller_signals()

        if backend is None:
            self.backend = get_screenshot_service()
        else:
            self.backend = backend

        self.connect_tracked(self.extracted_page, "go-back", self.show_welcome_page)  # type: ignore[arg-type]
        self._clipboard_service = None
        try:
            self._clipboard_service = get_clipboard_service()
            self.connect_tracked(
                self._clipboard_service,
                "paste_from_clipboard",
                self._on_paste_from_clipboard_texture,
            )
            self.connect_tracked(
                self._clipboard_service,
                "error",
                self._on_clipboard_error,
            )
        except RuntimeError as e:
            logger.warning(f"Clipboard service unavailable: {e}")

    def _setup_geometry(self) -> None:
        width: int = max(400, self.settings.get_int("window-width"))  # Min 400px
        height: int = max(300, self.settings.get_int("window-height"))  # Min 300px
        self.set_default_size(width, height)

        # Connect to surface scale changes to handle multi-monitor DPI scaling.
        # FIX BUG-H-006: use connect_tracked (not plain connect) so teardown_all()
        # explicitly disconnects this handler. GTK4 auto-disconnects self-signals on
        # destroy, but consistent use of connect_tracked enforces the pattern uniformly.
        self.connect_tracked(self, "notify::scale-factor", self._on_scale_factor_changed)

    def _apply_capability_constraints(self) -> None:
        """Apply UI sensitivity constraints based on the boot-time capability audit."""
        ctx = get_app_context()

        # If OCR is missing, disable core capture actions
        if not ctx.has_ocr:
            logger.warning("Anura: OCR capability missing. Disabling capture UI.")
            self.welcome_page.screenshot_button.set_sensitive(False)
            self.welcome_page.screenshot_button.set_tooltip_text(_("Tesseract OCR not found on system"))

        # If TTS is missing, disable listen button on extracted page
        if not ctx.has_tts:
            logger.warning("Anura: TTS capability missing. Disabling Listen UI.")
            self.extracted_page.listen_btn.set_sensitive(False)
            self.extracted_page.listen_btn.set_tooltip_text(_("TTS dependencies (gTTS/GStreamer) missing"))

    def _on_scale_factor_changed(self, _window: Gtk.Window, _pspec: GObject.ParamSpec) -> None:
        scale: int = self.get_scale_factor()
        logger.debug(f"Anura: Window scale factor changed to {scale}")
        # Ensure the window is properly resized/redrawn if needed
        self.queue_resize()

    def get_language(self) -> str:
        """Get current language code from settings or language manager."""
        language_manager_instance = get_language_manager()
        lang_setting: str = self.settings.get_string("active-language")
        return lang_setting or language_manager_instance.active_language.code

    def _on_screenshot_timeout(self) -> bool:
        """Restore window if portal screenshot doesn't respond within 30s."""
        self._screenshot_timeout_id = None
        # BUG-031: Cancel active capture to prevent UI interference and reset state
        if self.backend:
            self.backend.cancel()
        self.present()
        self.show_toast(_("Screenshot timed out. Please try again."))
        logger.warning("Anura: Screenshot portal timeout — restoring window.")
        return GLib.SOURCE_REMOVE

    def get_screenshot(self, copy: bool = False) -> None:
        """Capture screenshot and process it for OCR."""
        lang: str = self.get_language()

        # Check if backend is already capturing BEFORE hiding the window
        # BUG-040: Use public is_busy property instead of private _is_capturing
        if self.backend.is_busy:
            logger.warning("Anura: Capture already in progress.")
            self.show_toast(_("Capture already in progress"))
            return

        self.hide()

        # Safety timeout: if portal doesn't respond within 30s, restore window
        if self._screenshot_timeout_id is not None:
            GLib.source_remove(self._screenshot_timeout_id)
            self._screenshot_timeout_id = None  # prevent double source_remove on early return path

        self._screenshot_timeout_id = GLib.timeout_add_seconds(30, self._on_screenshot_timeout)

        try:
            self.backend.capture(lang, copy)
        except (GLib.Error, RuntimeError, OSError) as e:
            # Clean up timeout and restore window on error
            if self._screenshot_timeout_id is not None:
                GLib.source_remove(self._screenshot_timeout_id)
                self._screenshot_timeout_id = None
            self.present()
            logger.error(f"Anura: Screenshot capture failed: {e}")
            self.show_toast(_("Failed to capture screenshot"))

    def process_file(self, file_path: str) -> None:
        """Process an image file asynchronously."""
        if not file_path:
            return

        gfile: Gio.File = Gio.File.new_for_path(file_path)
        self.welcome_page.show_spinner()

        def _on_contents_loaded(gfile: Gio.File, result: Gio.AsyncResult) -> None:
            try:
                ok, contents, _etag = gfile.load_contents_finish(result)
                if ok:
                    is_valid, _size, error = validate_image_resource(contents)
                    if not is_valid:
                        self.welcome_page.spinner.set_visible(False)
                        self.show_toast(_(error) if error else _("Invalid image file"))
                        return

                    get_atomic_manager().execute(self.backend.decode_image, (self.get_language(), BytesIO(contents)))
                else:
                    self.welcome_page.hide_spinner()
                    self.show_toast(_("Failed to load image file"))
            except (GLib.Error, RuntimeError) as e:
                logger.error(f"Anura Window: Async load failed: {e}")
                self.welcome_page.hide_spinner()
                self.show_toast(_("Error loading file"))

        gfile.load_contents_async(None, _on_contents_loaded)

    def _do_copy_to_clipboard(self) -> None:
        text: str = self.extracted_page.get_active_text()
        if text:
            selection = self.extracted_page.buffer.get_selection_bounds()
            get_clipboard_service().set(text)
            if selection:
                self.show_toast(_("Selection copied to clipboard"))
            else:
                self.show_toast(_("Text copied to clipboard"))
            self.extracted_page.show_copy_feedback()
        else:
            self.show_toast(_("No text to copy"))

    def _on_paste_from_clipboard_texture(self, _service: GObject.GObject, texture: Gdk.Texture) -> None:
        self.welcome_page.show_spinner()
        png_bytes: BytesIO = BytesIO(texture.save_to_png_bytes().get_data())
        get_atomic_manager().execute(self.backend.decode_image, (self.get_language(), png_bytes))

    def _on_clipboard_error(self, _service: GObject.GObject, message: str) -> None:
        """Handle clipboard service errors."""
        self.welcome_page.spinner.set_visible(False)
        if message:
            self.show_toast(message)

    def do_close_request(self) -> bool:
        """Handle window close request and save window state."""
        width: int = self.get_width()
        height: int = self.get_height()
        self.settings.set_int("window-width", width)
        self.settings.set_int("window-height", height)
        return False

    def do_destroy(self) -> None:
        """Clean up signal handlers and timeouts to prevent memory leaks."""
        if self._screenshot_timeout_id is not None:
            GLib.source_remove(self._screenshot_timeout_id)
            self._screenshot_timeout_id = None

        clipboard_service_instance = get_clipboard_service()
        clipboard_service_instance.cancel_pending_operations()

        # Note: self.teardown_all() is now called automatically by SignalManagerMixin
        # via the 'destroy' signal connection established during __init__.

        super().do_destroy()

    def show_preferences(self) -> None:
        """Show the preferences dialog for application settings."""
        self.set_focus(None)
        dialog: PreferencesDialog = PreferencesDialog()
        dialog.present(self)

    def show_shortcuts(self) -> None:
        """Show the keyboard shortcuts overlay."""
        self.set_focus(None)
        try:
            from anura.widgets.shortcuts_overlay import show_shortcuts_overlay

            show_shortcuts_overlay(self)
        except (ImportError, RuntimeError) as e:
            logger.error(f"Failed to show shortcuts overlay: {e}")

    def show_search(self) -> None:
        """Toggle search bar on the extracted page."""
        self.navigation_view.push_by_tag("extracted")
        self.extracted_page.toggle_search()

    def open_in_external_editor(self) -> None:
        """Export current extracted text to temporary file and launch external editor."""
        text = self.extracted_page.get_active_text()
        if not text:
            self.show_toast(_("No text to open in external editor"))
            return

        try:
            runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
            import tempfile

            base_dir = (
                Path(runtime_dir) / "anura" / "exports"
                if runtime_dir
                else Path(tempfile.gettempdir()) / "anura_exports"
            )
            base_dir.mkdir(parents=True, exist_ok=True)

            temp_file = base_dir / f"extracted_{GLib.get_monotonic_time()}.txt"
            temp_file.write_text(text, encoding="utf-8")

            gfile = Gio.File.new_for_path(str(temp_file))
            launcher = Gtk.FileLauncher.new(gfile)
            launcher.launch(self, None, self._on_external_editor_launched)
        except (OSError, RuntimeError, GLib.Error) as e:
            logger.error(f"Failed to export or launch external editor: {e}")
            self.show_toast(_("Failed to open external editor"))

    def _on_external_editor_launched(self, launcher: Gtk.FileLauncher, result: Gio.AsyncResult) -> None:
        try:
            success = launcher.launch_finish(result)
            if success:
                self.show_toast(_("Opened in external editor"))
        except (GLib.Error, RuntimeError) as e:
            logger.warning(f"External editor launch cancelled or failed: {e}")
            self.show_toast(_("Could not launch external editor"))

    def show_welcome_page(self, *_args: object) -> None:
        """Show the welcome page and hide the extracted content."""
        self.navigation_view.pop_to_tag("welcome")
        self.tts_controller.stop()

    def show_history_page(self, *_args: object) -> None:
        """Show the History page, reloading its entries from the service."""
        self.history_page.refresh()
        self.navigation_view.push_by_tag("history")

    def _on_show_history(self, _action: Gio.SimpleAction, _parameter: object) -> None:
        """Activate the win.show-history action."""
        self.show_history_page()

    def _setup_controller_signals(self) -> None:
        """Connect to controller signals to mediate UI updates."""
        # OCR Controller signals
        self.connect_tracked(self.ocr_controller, "extraction-completed", self._on_extraction_completed)
        self.connect_tracked(self.ocr_controller, "error-occurred", self._on_ocr_error)
        self.connect_tracked(self.ocr_controller, "status-changed", self._on_ocr_status_changed)
        self.connect_tracked(self.ocr_controller, "capture-portal-missing", self._on_portal_missing)
        self.connect_tracked(self.ocr_controller, "navigation-requested", self._on_navigation_requested)

        # DnD Controller signals
        self.connect_tracked(self.dnd_controller, "error-occurred", self._on_dnd_error)

        # TTS Controller signals
        self.connect_tracked(self.tts_controller, "state-changed", self._on_tts_state_changed)
        self.connect_tracked(self.tts_controller, "error-occurred", self._on_tts_error)

    def _on_extraction_completed(self, _controller: OcrController, text: str, applied_name: str) -> None:
        """Mediate OCR result to the UI."""
        self._cleanup_screenshot_state()
        self.welcome_page.reset_drop_area_state()
        self.extracted_page.set_extracted_text(text, applied_name)

    def _on_ocr_error(self, _controller: OcrController, message: str) -> None:
        """Handle OCR error signal."""
        self._cleanup_screenshot_state()
        self.welcome_page.reset_drop_area_state()
        if not message:
            return
        # For total capture failure with no fallback available, show a fatal
        # error dialog instead of a toast (previously handled in
        # AnuraApplication._on_error_occurred; moved here to avoid the double
        # notification burst caused by connecting error-occurred twice).
        from anura.services.screenshot_service import get_screenshot_service
        backend = get_screenshot_service()
        if "screenshot failed" in message.lower() and not getattr(backend, "fallback_provider", None):
            from anura.core.dialogs import DialogManager
            error_body = _(
                "Anura could not capture a screenshot because no suitable "
                "portal backend or fallback tool was found."
            )
            DialogManager.show_fatal_error(self, _("Capture Failed"), error_body)
        else:
            self.show_toast(message)

    def _on_ocr_status_changed(self, _controller: OcrController, status_msg: str) -> None:
        """Update UI status during OCR."""
        self.welcome_page.set_status(status_msg)

    def _on_portal_missing(self, _controller: OcrController, message: str) -> None:
        """Show the portal missing banner."""
        self.portal_banner.set_title(message)
        self.portal_banner.set_revealed(True)

    def _on_navigation_requested(self, _controller: OcrController, tag: str) -> None:
        """Handle navigation requests from controllers."""
        if tag == "extracted":
            self.navigation_view.push_by_tag("extracted")
            self.extracted_page.text_view.grab_focus()

    def _on_dnd_error(self, _controller: DndController, message: str) -> None:
        """Handle DnD error signal."""
        self.welcome_page.reset_drop_area_state()
        if message:
            self.show_toast(message)

    def _on_tts_state_changed(self, _controller: TtsController, state: str) -> None:
        """Mediate TTS state to the UI."""
        self.extracted_page.update_tts_state(state)

    def _on_tts_error(self, _controller: TtsController, message: str) -> None:
        """Handle TTS error signal."""
        if message:
            self.show_toast(message)

    def _cleanup_screenshot_state(self) -> None:
        """Restore window state after screenshot attempt."""
        if self._screenshot_timeout_id is not None:
            GLib.source_remove(self._screenshot_timeout_id)
            self._screenshot_timeout_id = None
        self.present()

    def _on_share(self, _action: Gio.SimpleAction, variant: GLib.Variant) -> None:
        """Dispatch share action to the correct provider."""
        provider: str = variant.get_string()
        text: str = self.extracted_page.get_active_text()
        if not text:
            self.show_toast(_("No text to share."))
            return
        self.share_service.share(provider, text)

    def show_toast(self, title: str, priority: Adw.ToastPriority = Adw.ToastPriority.NORMAL) -> None:
        """Show a toast notification to the user."""
        self.toast_overlay.add_toast(Adw.Toast(title=title, priority=priority))

    def _launch_uri(self, url: str) -> None:
        """Open a URI in the default system browser."""
        from anura.utils.validators import launch_uri

        launch_uri(url, window=self, error_callback=lambda msg: self.show_toast(msg))

    def on_listen(self) -> None:
        """Trigger TTS playback."""
        text = self.extracted_page.get_active_text()
        self.tts_controller.request_listen(text)

    def on_listen_cancel(self) -> None:
        """Cancel TTS playback."""
        self.tts_controller.stop()

    def on_listen_pause(self) -> None:
        """Toggle TTS pause/resume."""
        self.tts_controller.toggle_pause()

    def close_popovers(self) -> None:
        """Close all open popovers."""
        try:
            share_popover: Gtk.Popover = self.extracted_page.share_button.get_popover()
            if share_popover and share_popover.get_visible():
                share_popover.popdown()
        except (AttributeError, RuntimeError, TypeError):
            pass

        for page in (self.welcome_page, self.extracted_page):
            if page:
                self._close_page_menu_popovers(page)

    def _close_page_menu_popovers(self, page: Adw.NavigationPage) -> None:
        child: Gtk.Widget | None = page.get_first_child()
        while child is not None:
            if isinstance(child, Adw.ToolbarView):
                self._close_toolbar_view_popovers(child)
                return
            child = child.get_next_sibling()

    def _close_toolbar_view_popovers(self, toolbar_view: Adw.ToolbarView) -> None:
        child: Gtk.Widget | None = toolbar_view.get_first_child()
        while child is not None:
            if isinstance(child, Adw.HeaderBar):
                self._close_header_bar_popovers(child)
                return
            child = child.get_next_sibling()

    def _close_header_bar_popovers(self, headerbar: Adw.HeaderBar) -> None:
        child: Gtk.Widget | None = headerbar.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.MenuButton):
                with contextlib.suppress(AttributeError, RuntimeError, TypeError):
                    popover: Gtk.Popover = child.get_popover()
                    if popover and popover.get_visible():
                        popover.popdown()
            child = child.get_next_sibling()
