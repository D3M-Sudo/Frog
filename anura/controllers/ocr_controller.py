# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _
from gettext import ngettext
from typing import TYPE_CHECKING, ClassVar
import weakref

from gi.repository import Adw, Gio, GLib, GObject, Gtk
from loguru import logger

from anura.services.history_service import HistoryService
from anura.services.notification_service import get_notification_service
from anura.services.result_dispatcher import get_result_dispatcher
from anura.utils import uri_validator
from anura.utils.portal_advice import detect_portal_advice
from anura.utils.signal_manager import SignalManagerMixin

if TYPE_CHECKING:
    from anura.models.ocr import ExtractionResult, OcrResult
    from anura.window import AnuraWindow


class OcrController(GObject.GObject, SignalManagerMixin):
    """
    Decoupled controller for OCR operations.
    Manages coordination between the Window UI and the ScreenshotService.
    Emits GLib signals for detected text and errors to allow event-driven service integration.
    """

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "text-extracted": (GObject.SignalFlags.RUN_LAST, None, (str, bool)),
        "uri-detected": (GObject.SignalFlags.RUN_LAST, None, (str, bool)),
        "error-occurred": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "extraction-completed": (GObject.SignalFlags.RUN_LAST, None, (str, str)),  # text, applied_name
        "status-changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "capture-portal-missing": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "navigation-requested": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(
        self,
        window: "AnuraWindow",
        history_service: HistoryService | None = None,
    ) -> None:
        GObject.GObject.__init__(self)
        SignalManagerMixin.__init__(self)

        self._window = weakref.proxy(window)
        # weakref.proxy is transparent for Python attribute access, but PyGObject's
        # C-level type check in dialog.open() rejects proxies.  Keep a plain
        # weakref.ref for the one call-site that needs the real GObject.
        self._window_ref = weakref.ref(window)
        self._dispatcher = get_result_dispatcher()
        self._notification_service = get_notification_service()
        # History V1: injected by the application wiring (AnuraWindow) so the
        # configured history-limit is honoured.  None disables history recording.
        self._history_service = history_service

        # Register for automatic teardown
        if hasattr(window, "register_controller"):
            window.register_controller(self)

        # Connect to window signals and backend
        self._setup_connections()
        logger.debug("OcrController: Initialized and connected to AnuraWindow")

    def teardown(self) -> None:
        """Unified teardown called by SignalManagerMixin."""
        # BUG-039: Cleanup logic consolidated in teardown() to eliminate redundancy.
        try:
            self.disconnect_all_signals()
        except (TypeError, RuntimeError) as e:
            logger.debug(f"Signal disconnection failed during teardown: {e}")
        self._window = None  # type: ignore[assignment]
        logger.debug("OcrController: Torn down and disconnected")

    def _setup_connections(self) -> None:
        backend = self._window.backend
        self.connect_tracked(backend, "decoded", self._on_shot_done)
        self.connect_tracked(backend, "error", self._on_shot_error)
        self.connect_tracked(backend, "status-changed", self._on_status_changed)
        self.connect_tracked(backend, "portal-backend-missing", self._on_portal_backend_missing)

        self.connect_tracked(self._window.portal_banner, "button-clicked", self._on_portal_banner_dismissed)

    def _on_shot_done(
        self,
        _sender: GObject.GObject,
        text: str,
        copy: bool,
        ocr_result: "OcrResult",
        applied_name: str,
    ) -> None:
        """Handle successful screenshot capture and OCR processing.

        FIX BUG-H-003: applied_name is now forwarded from the OCR pipeline (service layer)
        so MagicProcessor is NOT run a second time here.  The pipeline already selected the
        best text and cleaned it; re-processing the raw OcrResult on the main thread would
        both waste CPU and potentially produce a different (worse) result.
        """
        if not text:
            self.emit("error-occurred", _("No text found. Try to grab another region."))
            return

        # History V1: persist the extraction only when the user opted in.
        # Runs on the GTK main thread (decoded is emitted via GLib.idle_add),
        # so the small synchronous JSON write of HistoryService is acceptable.
        self._record_history(text, applied_name, ocr_result)

        try:
            self.emit("extraction-completed", text, applied_name)
            extraction_result = self._dispatcher.dispatch(text, ocr_result)
            self._handle_extraction_result(extraction_result, copy)

            if self._notification_service.is_available():
                body = text[:80] + "…" if len(text) > 80 else text
                self._notification_service.show(title=_("Text extracted"), body=body, priority="normal")

            # NEW-003 / NEW-008: Navigate only for the current active task
            # backend.current_task_id is now a public GObject property.
            _current_id = self._window.backend.current_task_id
            GLib.idle_add(self._navigate_to_extracted_page, _current_id)
        except ReferenceError:
            logger.debug("OcrController: Window was already destroyed, skipping _on_shot_done processing.")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.error(f"OcrController: Error in _on_shot_done: {e}")

    def _record_history(self, text: str, applied_name: str, ocr_result: "OcrResult | None") -> None:
        """Record a successful extraction in the local history, if enabled.

        Never raises: a persistence failure must not break the OCR flow.
        """
        if self._history_service is None:
            return
        try:
            settings = self._window.settings
            if not settings.get_boolean("history-enabled"):
                return

            # Only data genuinely available at this point is recorded:
            # text (mandatory), the current OCR language, the transformer
            # name chosen by the pipeline and the average OCR confidence.
            conf = ocr_result.avg_confidence if ocr_result is not None else 0.0
            self._history_service.record(
                text=text,
                language=self._window.get_language(),
                applied_name=applied_name,
                conf=conf,
            )
            logger.debug("OcrController: Extraction recorded in history")
        except ReferenceError:
            logger.debug("OcrController: Window was already destroyed, skipping history record.")
        except OSError:
            logger.exception("OcrController: Failed to record extraction in history")

    def _handle_extraction_result(self, result: "ExtractionResult", copy_requested: bool) -> None:
        """Handle the extraction result, emitting signals for side effects."""
        if result.is_primary_url:
            url = result.urls[0].strip()
            if uri_validator(url):
                self.emit("uri-detected", url, copy_requested)
            else:
                self.emit("text-extracted", url, copy_requested)
        else:
            self.emit("text-extracted", result.text, copy_requested)

            try:
                # Show toasts for other structured data found in text
                if result.emails:
                    count = len(result.emails)
                    self._window.show_toast(
                        ngettext("{n} email found in text", "{n} emails found in text", count).format(n=count)
                    )

                if result.phone_numbers:
                    count = len(result.phone_numbers)
                    self._window.show_toast(
                        ngettext("{n} phone number found in text", "{n} phone numbers found in text", count).format(n=count)
                    )
            except ReferenceError:
                logger.debug("OcrController: Window was already destroyed, skipping toasts.")

    def _on_status_changed(self, _sender: GObject.GObject, status_msg: str) -> None:
        """Handle status updates from backend to prevent Zombie UI."""
        self.emit("status-changed", status_msg)

    def _on_shot_error(self, _sender: GObject.GObject, message: str) -> None:
        """Handle screenshot capture errors."""
        if message:
            # BUG-3a: Defer error emission to allow window manager to process
            # window restoration and grant focus, ensuring get_active_window()
            # in main.py returns the correct window for toast display.
            GLib.idle_add(self.emit, "error-occurred", message)

    def _on_portal_backend_missing(self, _sender: GObject.GObject) -> None:
        """Reveal the persistent install hint banner."""
        try:
            advice = detect_portal_advice()
            self.emit("capture-portal-missing", advice.short_message)
        except (AttributeError, RuntimeError) as e:
            logger.error(f"OcrController: Error handling portal backend missing: {e}")

    def _on_portal_banner_dismissed(self, _banner: Adw.Banner) -> None:
        try:
            self._window.portal_banner.set_revealed(False)
        except ReferenceError:
            logger.debug("OcrController: Window was already destroyed, skipping portal banner dismissal.")

    def _navigate_to_extracted_page(self, task_id: str | None = None) -> int:
        # NEW-003: Validate task ID before navigation to prevent jumps during rapid captures
        if task_id:
            from anura.core.atomic_task_manager import get_atomic_manager

            if get_atomic_manager().is_cancelled(task_id):
                logger.debug(f"OcrController: Ignoring navigation for cancelled task {task_id}")
                return GLib.SOURCE_REMOVE

        self.emit("navigation-requested", "extracted")
        return GLib.SOURCE_REMOVE

    def open_image(self) -> None:
        """Open file dialog to select an image for OCR processing."""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Choose an image for extraction"))

        all_img_filter = Gtk.FileFilter()
        all_img_filter.set_name(_("All supported images"))

        all_extensions = [
            "png",
            "jpg",
            "jpeg",
            "jpe",
            "jfif",
            "webp",
            "avif",
            "avifs",
            "tif",
            "tiff",
            "bmp",
            "dib",
            "gif",
        ]

        for ext in all_extensions:
            all_img_filter.add_pattern(f"*.{ext}")
            all_img_filter.add_pattern(f"*.{ext.upper()}")

        def _make_format_filter(display_name: str, extensions: list[str]) -> Gtk.FileFilter:
            filt = Gtk.FileFilter()
            filt.set_name(display_name)
            for ext in extensions:
                filt.add_pattern(f"*.{ext}")
                filt.add_pattern(f"*.{ext.upper()}")
            return filt

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(all_img_filter)
        filters.append(_make_format_filter(_("PNG images (*.png)"), ["png"]))
        filters.append(_make_format_filter(_("JPEG images (*.jpg)"), ["jpg", "jpeg", "jpe", "jfif"]))
        filters.append(_make_format_filter(_("WebP images (*.webp)"), ["webp"]))
        filters.append(_make_format_filter(_("AVIF images (*.avif)"), ["avif", "avifs"]))
        filters.append(_make_format_filter(_("TIFF images (*.tif)"), ["tif", "tiff"]))
        filters.append(_make_format_filter(_("BMP images (*.bmp)"), ["bmp", "dib"]))
        filters.append(_make_format_filter(_("GIF images (*.gif)"), ["gif"]))

        all_files_filter = Gtk.FileFilter()
        all_files_filter.set_name(_("All files (*)"))
        all_files_filter.add_pattern("*")
        filters.append(all_files_filter)

        dialog.set_filters(filters)
        dialog.set_default_filter(all_img_filter)

        def _on_open_image_result(dialog: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
            try:
                file = dialog.open_finish(result)
                if file:
                    self._window.process_file(file.get_path())
            except ReferenceError:
                logger.debug("OcrController: Window was already destroyed, skipping file processing.")
            except (GLib.Error, RuntimeError) as e:
                logger.warning(f"Image selection failed or aborted: {e}")

        # Resolve the real GObject: weakref.proxy is opaque to PyGObject's C-level
        # isinstance check inside Gtk.FileDialog.open(), causing a TypeError.
        # self._window_ref() returns the live window or None if already destroyed.
        _win = self._window_ref()
        if _win is None:
            logger.warning("OcrController.open_image: window was destroyed, aborting")
            return

        dialog.open(_win, None, _on_open_image_result)
