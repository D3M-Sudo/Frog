# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import contextlib
import html
import os
from pathlib import Path
import sys

# Bootstrap hardware and logging as early as possible
from anura.core.boot import boot_audit
from anura.core.logger import setup_logging

boot_audit()
setup_logging()

from anura.core.i18n import setup_i18n

setup_i18n()

from gettext import gettext as _

import gi

# Set GTK version requirements before imports
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Notify", "0.7")
gi.require_version("Xdp", "1.0")
gi.require_version("Gst", "1.0")

from gi.repository import Adw, Gio, GLib
from loguru import logger

from anura.config import APP_ID
from anura.core.resources import load_gresource_bundle

# Load GResource before importing any widgets
if not load_gresource_bundle():
    logger.critical("GResource bundle is required to run Anura. The application cannot start.")
    sys.exit(1)

from anura.core.action_registry import ActionRegistry
from anura.core.dialogs import DialogManager
from anura.core.silent_runner import SilentRunner
from anura.services.clipboard_service import get_clipboard_service
from anura.services.language_manager import get_language_manager
from anura.services.notification_service import (
    HAS_LIBNOTIFY,
    NotificationService,
)
from anura.services.screenshot_service import ScreenshotService, get_screenshot_service
from anura.services.settings import settings
from anura.utils import cleanup_orphaned_resources
from anura.utils.signal_manager import SignalManagerMixin
from anura.utils.validators import launch_uri
from anura.window import AnuraWindow


class AnuraApplication(Adw.Application, SignalManagerMixin):
    __gtype_name__ = "AnuraApplication"

    def __init__(self, version: str | None = None) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)  # type: ignore[call-arg]
        SignalManagerMixin.__init__(self)
        self.backend: ScreenshotService | None = None
        self.version = version
        self.settings = settings
        self.notification_service = NotificationService(APP_ID)
        self._setup_options()

    def _setup_options(self) -> None:
        self.add_main_option(
            "extract_to_clipboard",
            ord("e"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Extract directly into the clipboard"),
            None,
        )
        self.add_main_option(
            "file",
            ord("f"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.FILENAME,
            _("Process image file for OCR"),
            None,
        )
        self.add_main_option(
            "silent",
            ord("s"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            _("Run OCR without UI (copy result to clipboard)"),
            None,
        )

    def do_startup(self, *args: object, **kwargs: object) -> None:
        Adw.init()
        Adw.Application.do_startup(self)

        self._apply_color_scheme()
        self.settings.connect("changed::color-scheme", self._on_color_scheme_changed)

        active_lang = self.settings.get_string("active-language")
        cleanup_orphaned_resources(active_lang)

        self.backend = get_screenshot_service()
        # Signals are now coordinated via OcrController in AnuraWindow for GUI mode.
        # on_decoded and on_error are maintained for Headless/Silent mode entry points.
        self.connect_tracked(self.backend, "decoded", self.on_decoded)
        self.connect_tracked(self.backend, "error", self.on_error)

        get_language_manager().init_tessdata()
        get_clipboard_service().init()

        ActionRegistry(self).setup_actions()

        GLib.set_application_name("Anura OCR")
        GLib.set_prgname(APP_ID)

    def do_shutdown(self, *args: object, **kwargs: object) -> None:
        if self.backend:
            with contextlib.suppress(Exception):
                self.backend.do_destroy()

        self._cleanup_services()
        self.teardown_all()
        try:
            get_language_manager().shutdown()
        except (AttributeError, RuntimeError) as e:
            logger.debug(f"Failed to shutdown LanguageManager: {e}")

        from anura.core.atomic_task_manager import get_atomic_manager

        get_atomic_manager().shutdown()

        Adw.Application.do_shutdown(self)

    def _cleanup_services(self) -> None:
        if hasattr(self, "notification_service") and self.notification_service:
            self.notification_service.cleanup()
            try:
                if HAS_LIBNOTIFY:
                    from gi.repository import Notify

                    if Notify.is_initted():
                        Notify.uninit()
            except (AttributeError, RuntimeError) as e:
                logger.error(f"Failed to uninitialize Notify service: {e}")

        with contextlib.suppress(Exception):
            get_clipboard_service().cancel_pending_operations()

        with contextlib.suppress(Exception):
            from anura.services.tts import get_tts_service

            get_tts_service().cleanup()

    def do_activate(self) -> None:
        win = self.props.active_window
        if not win:
            if self.backend is None:
                self.backend = get_screenshot_service()
            win = AnuraWindow(application=self, backend=self.backend)
            self._setup_window_signals(win)
        win.present()

    def _apply_color_scheme(self) -> None:
        """Apply color scheme preference using Adw.StyleManager."""
        scheme = self.settings.get_string("color-scheme")
        style_manager = Adw.StyleManager.get_default()

        if scheme == "force-light":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        elif scheme == "force-dark":
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        logger.debug(f"Anura: Applied color scheme '{scheme}'")

    def _on_color_scheme_changed(self, _settings: Gio.Settings, _key: str) -> None:
        self._apply_color_scheme()

    def _setup_window_signals(self, win: AnuraWindow) -> None:
        """Wire up event-driven service integration via OcrController signals."""
        controller = win.ocr_controller
        self.connect_tracked(controller, "text-extracted", self._on_text_extracted)
        self.connect_tracked(controller, "uri-detected", self._on_uri_detected)
        # NOTE: "error-occurred" is intentionally NOT connected here.
        # AnuraWindow._on_ocr_error (handler connected in window.py) already
        # handles this signal with show_toast() + UI cleanup. Connecting it
        # again here caused a double-notification burst confirmed by debug log
        # (handler_id=1493 from window.py + handler_id=1505 from main.py both
        # firing for every single emit("error-occurred")).
        # Fatal-dialog logic for missing portal/fallback has been moved into
        # AnuraWindow._on_ocr_error where the window context is always available.

    def _on_text_extracted(self, _controller, text: str, copy_requested: bool) -> None:
        is_window_active = bool(self.get_active_window())
        win = self.get_active_window()

        if self.settings.get_boolean("autocopy") or copy_requested:
            get_clipboard_service().set(text)
            if win:
                win.show_toast(_("Text copied to clipboard"))
            if not is_window_active:
                self.notification_service.show_notification(
                    title=_("Anura OCR"), body=_("Text extracted and copied to clipboard.")
                )
        else:
            if not is_window_active:
                self.notification_service.show_notification(
                    title=_("Anura OCR"), body=_("Text extracted successfully.")
                )

    def _on_uri_detected(self, _controller, url: str, copy_requested: bool) -> None:
        win = self.get_active_window()

        if self.settings.get_boolean("autolinks"):
            launch_uri(url, window=win, error_callback=lambda msg: win.show_toast(msg) if win else None)
            if win:
                win.show_toast(_("URL opened automatically"))
        else:
            target = GLib.Variant("s", url)
            self.notification_service.send_notification_with_action(
                notification_id="qr-url",
                title=_("QR Code URL Detected"),
                body=url,
                action_id="app.open-qr-url",
                action_target=target,
                priority="high",
            )

        # Handle URL Clipboard (respecting global autocopy or explicit request)
        if self.settings.get_boolean("autocopy") or copy_requested:
            get_clipboard_service().set(url)
            if win and not self.settings.get_boolean("autolinks"):
                win.show_toast(_("URL copied to clipboard"))

    def _on_error_occurred(self, _controller, message: str) -> None:
        win = self.get_active_window()
        if win:
            # Check for total capture failure (no primary, no fallback)
            if "Screenshot failed" in message.lower() and not getattr(self.backend, "fallback_provider", None):
                error_body = _(
                    "Anura could not capture a screenshot because no suitable "
                    "portal backend or fallback tool was found."
                )
                DialogManager.show_fatal_error(win, _("Capture Failed"), error_body)
            else:
                win.show_toast(message)
        else:
            self.notification_service.show_notification(title=_("Anura OCR"), body=message)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict().end().unpack()

        if "extract_to_clipboard" in options:
            return self._handle_extract_to_clipboard()
        if "file" in options:
            return self._handle_file_option(options["file"], "silent" in options)

        self.activate()
        return 0

    def _handle_extract_to_clipboard(self) -> int:
        if self.backend:
            self.backend.capture(self.settings.get_string("active-language"), copy=True)
            return 0
        return 1

    def _handle_file_option(self, file_path: str, is_silent: bool) -> int:
        try:
            _exists = Path(file_path).exists()
        except PermissionError:
            # Path.exists() raises PermissionError when the *parent directory*
            # is not readable (e.g. /root/ on a non-root CI runner).
            # Treat this as inaccessible rather than letting the exception
            # propagate to the caller.
            _exists = False
        if _exists and os.access(file_path, os.R_OK):
            if is_silent:
                return SilentRunner(self, file_path).run()
            self.activate()
            if self.props.active_window:
                self.props.active_window.process_file(file_path)
            return 0

        if not is_silent:
            self.activate()
            if self.props.active_window:
                self.props.active_window.open_image()
            return 0
        return 1

    def _decode_image_synchronously(self, file_path: str):
        if self.backend:
            return self.backend.decode_image_sync(self.settings.get_string("active-language"), file_path)
        return False, None, "Backend not initialized", None, ""

    def _get_release_notes(self) -> str:
        """Get release notes from generated _release_notes module.

        Adw.AboutDialog parses the value as AppStream/Pango markup and rejects
        bare text (libxml: "The document must start with an element"). Wrap any
        non-element-leading content in <p> as a safety net so the Novità window
        always opens, even with stale or empty release notes.
        """
        notes: str | None = None
        try:
            from anura._release_notes import get_release_notes

            notes = get_release_notes()
        except (ImportError, AttributeError, RuntimeError) as e:
            logger.debug(f"Could not load release notes: {e}")

        if not notes or not notes.strip():
            notes = _("Bug fixes and improvements.")

        stripped = notes.lstrip()
        if not stripped.startswith("<"):
            # Bare text — wrap so libxml accepts it as a valid document
            notes = f"<p>{html.escape(notes)}</p>"
        return notes

    def on_preferences(self, *_) -> None:
        DialogManager.show_preferences(self.get_active_window())

    def on_about(self, *_) -> None:
        DialogManager.show_about(self.get_active_window(), self.version)

    def on_github_star(self, *_) -> None:
        launch_uri("https://github.com/D3M-Sudo/Anura", window=self.props.active_window)

    def on_report_issue(self, *_) -> None:
        launch_uri("https://github.com/D3M-Sudo/Anura/issues", window=self.props.active_window)

    def on_shortcuts(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.show_shortcuts()

    def on_copy_to_clipboard(self, _, variant: GLib.Variant | None) -> None:
        win = self.get_active_window()
        if not win:
            return

        text = variant.get_string() if variant else ""
        if text:
            get_clipboard_service().set(text)
            win.show_toast(_("Text copied to clipboard"))
        elif hasattr(win, "_do_copy_to_clipboard"):
            win._do_copy_to_clipboard()

    def on_find(self, *_) -> None:
        win = self.get_active_window()
        if win and hasattr(win, "show_search"):
            win.show_search()

    def on_open_external_editor(self, *_) -> None:
        win = self.get_active_window()
        if win and hasattr(win, "open_in_external_editor"):
            win.open_in_external_editor()

    def get_screenshot(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.get_screenshot()

    def get_screenshot_and_copy(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.get_screenshot(copy=True)

    def open_image(self, *_) -> None:
        win = self.get_active_window()
        if win and hasattr(win, "ocr_controller"):
            win.ocr_controller.open_image()

    _last_paste_time: float = 0

    def on_paste_from_clipboard(self, *_) -> None:
        now = GLib.get_monotonic_time() / 1_000_000
        if now - self._last_paste_time < 0.5:
            logger.debug("Anura: Debouncing clipboard paste")
            return
        self._last_paste_time = now

        win = self.props.active_window
        if win and hasattr(win, "welcome_page"):
            win.welcome_page.show_spinner()
        get_clipboard_service().read_texture()

    def _on_open_qr_notification(self, _, parameter: GLib.Variant | None) -> None:
        if parameter:
            launch_uri(parameter.get_string().strip(), window=self.get_active_window())

    def on_decoded(self, _sender, text: str, copy: bool, ocr_result: object, applied_name: str = "") -> None:
        win = self.get_active_window()
        if win:
            # When UI is present, OcrController handles it via signals
            # connected in _setup_window_signals.
            return

        # Headless/Silent mode: perform direct dispatching
        from anura.models.ocr import OcrResult
        from anura.services.result_dispatcher import get_result_dispatcher

        result = get_result_dispatcher().dispatch(text, ocr_result if isinstance(ocr_result, OcrResult) else None)

        if not result.text:
            self.notification_service.show_notification(title=_("Anura OCR"), body=_("No text found."))
            return

        if self.settings.get_boolean("autocopy") or copy:
            get_clipboard_service().set(result.text)
            self.notification_service.show_notification(title=_("Anura OCR"), body=_("Text copied to clipboard."))
        else:
            self.notification_service.show_notification(title=_("Anura OCR"), body=_("Text extracted."))

    def on_error(self, _sender, message: str) -> None:
        # When a window is present, OcrController._on_shot_error already
        # handles this signal and shows the notification via AnuraWindow.
        # Firing here too produces a duplicate burst (confirmed by debug log:
        # handler_id=103 from main.py fires alongside handler_id=1484 from
        # ocr_controller.py for every emit("error"), multiplying the
        # notification count by 2+ per event).
        if self.get_active_window():
            return
        if message and message != _("Cancelled"):
            GLib.idle_add(
                lambda: (
                    self.notification_service.show_notification(title=_("Anura OCR"), body=message)
                    or GLib.SOURCE_REMOVE
                )
            )

    def on_listen(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.on_listen()

    def on_listen_cancel(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.on_listen_cancel()

    def on_listen_pause(self, *_) -> None:
        win = self.get_active_window()
        if win:
            win.on_listen_pause()


def main(version: str) -> int:
    app = AnuraApplication(version)
    return app.run(sys.argv)
