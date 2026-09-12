# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
from gettext import gettext as _
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Any, ClassVar
from urllib.request import url2pathname

import gi

# Set GTK version requirements before imports
gi.require_version("Gio", "2.0")
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")

from gi.repository import Gio, GLib, GObject  # noqa: E402
from loguru import logger  # noqa: E402
from PIL import Image  # noqa: E402
import pytesseract  # noqa: E402

from anura.config import LANG_CODE_PATTERN  # noqa: E402
from anura.core.atomic_task_manager import get_atomic_manager  # noqa: E402
from anura.models.ocr import OcrResult  # noqa: E402
from anura.services.language_manager import get_tesseract_config  # noqa: E402
from anura.services.settings import settings  # noqa: E402
from anura.utils import mask_url, sanitize_text, validate_image_resource  # noqa: E402
from anura.utils.portal_advice import detect_portal_advice  # noqa: E402
from anura.utils.singleton import get_instance  # noqa: E402
from anura.utils.structural_reconstructor import get_structural_reconstructor  # noqa: E402
from anura.utils.text_preprocessor import get_text_preprocessor  # noqa: E402


def _is_flatpak_environment() -> bool:
    """Detect if running in Flatpak sandbox."""
    return Path("/.flatpak-info").exists() or "FLATPAK_ID" in os.environ


def _pipeline_detect_barcodes(img, start_time: float) -> tuple[bool, str | None, str | None, OcrResult | None, str] | None:
    """Stage 1: Barcode Detection"""
    from anura.utils.barcode_detector import detect_barcodes

    results = detect_barcodes(img)
    if results:
        raw_extracted = "\n".join([res.text for res in results])
        extracted = sanitize_text(raw_extracted)
        logger.info(f"Anura ZXing (Isolated): Code(s) detected in {time.time() - start_time:.3f}s")
        return True, extracted, None, None, ""
    return None


def _pipeline_enhance_image(img, preprocessing_mode: str, task_id, status_callback) -> Image.Image:
    """Stage 2: grayscale conversion + enhancement"""
    if img.mode != "L":
        img = img.convert("L")

    logger.debug("Isolated: Enhancing image...")
    if status_callback:
        status_callback(_("Enhancing image..."))
    preprocessor = get_text_preprocessor()
    enhanced_img = (
        preprocessor.enhance_image(img, task_id=task_id) if preprocessing_mode != "off" else img
    )
    return enhanced_img


def _pipeline_run_tesseract(enhanced_img, lang: str, task_id, status_callback) -> OcrResult:
    """Stage 3: Tesseract execution and OcrResult construction"""
    from pytesseract import Output

    logger.debug("Isolated: Running Tesseract OCR...")
    if status_callback:
        status_callback(_("Running Tesseract OCR..."))
    ocr_data = pytesseract.image_to_data(
        enhanced_img,
        lang=lang,
        config=get_tesseract_config(lang, task_id=task_id),
        output_type=Output.DICT,
    )
    return OcrResult.from_tesseract_dict(ocr_data)


def _pipeline_reconstruct(ocr_result: OcrResult, task_id, status_callback) -> tuple[str, float]:
    """Stage 4: Structural reconstruction"""
    logger.debug("Isolated: Reconstructing structure...")
    if status_callback:
        status_callback(_("Reconstructing structure..."))
    reconstructor = get_structural_reconstructor()
    return reconstructor.reconstruct(ocr_result, task_id=task_id)


def _pipeline_magic_process(ocr_result: OcrResult, task_id, status_callback) -> tuple[str, float, str]:
    """Stage 5: Magic processing — returns (processed_text, confidence, applied_name)."""
    from anura.transformers.magic_processor import get_magic_processor

    logger.debug("Isolated: Magic processing...")
    if status_callback:
        status_callback(_("Magic processing..."))
    magic_processor = get_magic_processor()
    processed_text, magic_conf, applied_name = magic_processor.process(ocr_result, task_id=task_id)
    return processed_text, magic_conf, applied_name


def _pipeline_select_and_clean(
    spatially_reconstructed: str,
    recon_conf: float,
    processed_text: str,
    magic_conf: float,
    preprocessing_mode: str,
    preprocessor,
) -> str:
    """Stage 6+7: Selection and cleanup"""
    # 6. Selection
    if spatially_reconstructed.strip() and (
        (len(spatially_reconstructed) > len(processed_text) * 1.2 and recon_conf >= magic_conf * 0.95)
        or recon_conf > magic_conf
    ):
        processed_text = spatially_reconstructed

    # 7. Final Cleanup
    if preprocessing_mode == "full":
        cleaned_text = preprocessor.clean_extracted_text(processed_text)
    elif preprocessing_mode == "image-only":
        cleaned_text = sanitize_text(processed_text)
    else:
        cleaned_text = processed_text.strip()

    return sanitize_text(cleaned_text)


def run_ocr_pipeline(
    lang: str,
    file_path: str,
    preprocessing_mode: str,
    task_id: str | None = None,
    status_callback: Callable | None = None,
) -> tuple[bool, str | None, str | None, OcrResult | None, str]:
    """
    Isolated OCR pipeline to bypass Python's GIL.
    Runs in a separate process via ProcessPoolExecutor.
    """
    import tempfile

    # Configure Tesseract path in the child process
    _configure_tesseract_path()

    try:
        from PIL import Image

        from anura.utils.text_preprocessor import get_text_preprocessor

        if not Path(file_path).exists() or Path(file_path).stat().st_size == 0:
            return False, "", _("The selected image file is empty."), None, ""

        start_time = time.time()

        # Transactional I/O: Create a temporary directory for all worker artifacts
        with tempfile.TemporaryDirectory(prefix="anura-worker-") as tmp_dir:
            # Point Tesseract-related env vars to the transactional directory so
            # any .tmp or log files created by Tesseract are automatically cleaned
            # up when the context manager exits.
            #
            # BUG-003 fix: ProcessPoolExecutor reuses worker processes across tasks,
            # so mutations to os.environ persist into future invocations.  Save the
            # original values and restore them in a finally block to keep the worker
            # environment clean for the next task (or for any other code that reads
            # TMPDIR/TEMP/TMP in the same process).
            # BUG-003: save original env values; restore in finally so the
            # reused worker process is not contaminated for future tasks.
            _ENV_KEYS = ("TMPDIR", "TEMP", "TMP")
            _saved_env = {k: os.environ.get(k) for k in _ENV_KEYS}
            try:
                for k in _ENV_KEYS:
                    os.environ[k] = tmp_dir

                with Image.open(file_path) as img:  # type: ignore[assignment]
                    # 1. Barcode Detection
                    barcode_result = _pipeline_detect_barcodes(img, start_time)
                    if barcode_result:
                        return barcode_result

                    # 2. Pre-processing
                    enhanced_img = _pipeline_enhance_image(
                        img, preprocessing_mode, task_id, status_callback
                    )

                    # 3. Tesseract OCR
                    ocr_result = _pipeline_run_tesseract(enhanced_img, lang, task_id, status_callback)

                    # 4. Reconstruction
                    spatially_reconstructed, recon_conf = _pipeline_reconstruct(
                        ocr_result, task_id, status_callback
                    )

                    # 5. Magic Processing
                    # FIX BUG-H-003: capture applied_name so callers don't need to re-run
                    # MagicProcessor on the raw OcrResult (which would bypass pipeline
                    # selection logic and double the processing cost on the main thread).
                    processed_text, magic_conf, applied_name = _pipeline_magic_process(
                        ocr_result, task_id, status_callback
                    )

                    # 6+7. Selection and Cleanup
                    preprocessor = get_text_preprocessor()
                    cleaned_text = _pipeline_select_and_clean(
                        spatially_reconstructed,
                        recon_conf,
                        processed_text,
                        magic_conf,
                        preprocessing_mode,
                        preprocessor,
                    )

                    logger.info(f"Anura OCR (Isolated): Completed in {time.time() - start_time:.3f}s")
                    return True, cleaned_text, None, ocr_result, applied_name

            finally:
                # Restore original env values so the reused worker process
                # is not contaminated for subsequent OCR tasks.
                for k, v in _saved_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

                # FIX BUG-H-007: remove the task-isolated tessdata pool subdirectory
                # created by get_tesseract_config() for multi-language OCR.
                # Previously these accumulated for the entire session (cleanup was
                # startup-only).  We clean up eagerly here — still inside the isolated
                # worker — so no disk bloat occurs during long batch sessions.
                if task_id:
                    from anura.config import TESSDATA_POOL_DIR
                    pool_task_dir = Path(TESSDATA_POOL_DIR) / task_id
                    if pool_task_dir.is_dir():
                        import contextlib
                        with contextlib.suppress(OSError):
                            shutil.rmtree(pool_task_dir)
                            logger.debug(
                                f"Anura OCR (Isolated): Cleaned up tessdata pool dir for task {task_id}"
                            )

    except InterruptedError:
        return False, None, None, None, ""
    except (OSError, RuntimeError, TypeError, AttributeError) as e:
        logger.exception(f"Anura OCR (Isolated) Error: {e}")
        return False, "", _("Failed to process image in isolated process."), None, ""


def _configure_tesseract_path() -> None:
    """Configure Tesseract command path for Flatpak environment."""
    is_flatpak = _is_flatpak_environment()
    flatpak_tess_bin = "/app/bin/tesseract"

    if is_flatpak and Path(flatpak_tess_bin).exists():
        # Force Tesseract to use Flatpak path
        os.environ["TESSERACT_CMD"] = flatpak_tess_bin
        pytesseract.pytesseract.tesseract_cmd = flatpak_tess_bin
        logger.info(f"Anura OCR: Using Flatpak Tesseract at {flatpak_tess_bin}")
    else:
        # Use system Tesseract from PATH.
        # NEW-012: Only clear the override if it was specifically set to the Flatpak path.
        # This preserves user-defined TESSERACT_CMD environment variables.
        if os.environ.get("TESSERACT_CMD") == flatpak_tess_bin:
            os.environ.pop("TESSERACT_CMD", None)

        # Update pytesseract.tesseract_cmd but respect existing ENV if set
        pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD", "tesseract")
        logger.debug(f"Anura OCR: Using Tesseract at '{pytesseract.pytesseract.tesseract_cmd}'")

    # Final validation: check if tesseract binary is actually reachable
    tess_bin = pytesseract.pytesseract.tesseract_cmd
    if not shutil.which(tess_bin):
        logger.error(f"Anura OCR: Tesseract binary '{tess_bin}' not found in PATH or configured location")


class ScreenshotService(GObject.GObject):
    """
    Service responsible for capturing screenshots via XDG Portals
    and processing them for OCR or QR code decoding.
    """

    __gtype_name__ = "ScreenshotService"

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "error": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "decoded": (GObject.SignalFlags.RUN_FIRST, None, (str, bool, object, str)),
        # Emitted when the host's xdg-desktop-portal screenshot backend is
        # missing/broken (libportal generic-failure pattern). Consumers
        # typically use this to reveal a persistent install hint banner;
        # the user-facing toast is still emitted via "error".
        "portal-backend-missing": (GObject.SignalFlags.RUN_FIRST, None, ()),
        # Emitted during various stages of OCR processing to provide user feedback.
        "status-changed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self) -> None:
        GObject.GObject.__init__(self)
        logger.debug("ScreenshotService: Initializing singleton")

        from anura.services.screenshot.factory import ScreenshotProviderFactory

        self.provider = ScreenshotProviderFactory.get_provider()
        self.fallback_provider = ScreenshotProviderFactory.get_fallback_provider()

        self._cancellable_lock = threading.Lock()
        with self._cancellable_lock:
            self.cancelable: Gio.Cancellable = Gio.Cancellable.new()
        self._env_diagnostics_logged = False
        self._is_capturing = False

        # Configure Tesseract path for Flatpak environment
        _configure_tesseract_path()

    @GObject.Property(type=bool, default=False)
    def is_busy(self) -> bool:
        """Indicates if a capture is currently in progress."""
        return self._is_capturing

    @GObject.Property(type=str)
    def current_task_id(self) -> str | None:
        """Return the ID of the current active task (NEW-008)."""
        return getattr(self, "_current_task_id", None)

    def cancel(self) -> None:
        """Cancel any in-progress capture operation."""
        if not self._is_capturing:
            return

        logger.info("Anura Screenshot: Cancelling active capture...")
        if self.provider:
            self.provider.cancel()
        if self.fallback_provider:
            self.fallback_provider.cancel()
        self._is_capturing = False

    def capture(self, lang: str, copy: bool = False) -> None:
        """Requests a screenshot from the primary provider."""
        # Prevent concurrent capture requests
        if self._is_capturing:
            logger.warning("Anura Screenshot: Capture already in progress, ignoring request.")
            return

        self._is_capturing = True

        def _on_capture_result(success, uri, error, already_attempted_fallback=False):
            # Track the most recent task ID for navigation interlock (NEW-008).
            # This is cleared when the capture finishes or fails.
            self._current_task_id = None
            if success and uri:
                # Move URI parsing and file existence check to background thread
                task_id = get_atomic_manager().execute(
                    self._handle_portal_uri_background, (lang, uri, copy), pass_task_id=True
                )
                self._current_task_id = task_id
                self._is_capturing = False
            elif error:
                # Log full error context
                logger.error(f"Anura Screenshot: Capture failed: {error}")

                # BUG-004 FIX: we deliberately NO LONGER pattern-match the error text
                # ("screenshot failed") to decide whether to fall back. That textual
                # gate was fragile — a portal error with different wording (e.g. a
                # localized GDBus "UnknownMethod") silently skipped the fallback. The
                # only trusted signal is `error is None`, which providers use for user
                # cancellation, so any real (non-None) error from the primary provider
                # is fallback-eligible. The fallback is attempted at most once
                # (`already_attempted_fallback`) so the fallback's own failure cannot
                # recurse into an infinite loop.
                if self.fallback_provider and not already_attempted_fallback:
                    logger.info("Anura Screenshot: Attempting fallback capture...")
                    # FIX BUG-H-002: wrap symmetrically with primary provider call to
                    # guarantee _is_capturing is reset even if the fallback raises before
                    # its callback is ever scheduled.
                    try:
                        self.fallback_provider.capture(
                            lang, copy, lambda s, u, e: _on_capture_result(s, u, e, True)
                        )
                    except (GLib.Error, RuntimeError, AttributeError) as e:
                        self._is_capturing = False
                        logger.error(f"Anura Screenshot: Fallback provider raised: {e}")
                        self._emit_decode_error(
                            _("Screenshot failed: {reason}").format(reason=str(e))
                        )
                else:
                    self._is_capturing = False
                    if not self.fallback_provider:
                        # True portal-missing case: keep the environment diagnostic dump
                        # and the desktop-specific advice banner/error message.
                        self._log_portal_environment()
                        self._emit_portal_failure()
                    else:
                        # The fallback was attempted and failed with a real error of its
                        # own (no further fallback possible).
                        self._emit_decode_error(_("Screenshot failed: {reason}").format(reason=error))
            else:
                # Cancelled by user (providers signal this with error=None)
                self._is_capturing = False

        try:
            self.provider.capture(lang, copy, _on_capture_result)
        except (GLib.Error, RuntimeError) as e:
            self._is_capturing = False
            logger.error(f"Anura Screenshot: Provider capture call failed: {e}")
            self._emit_decode_error(_("Failed to initiate screenshot capture."))

    def _handle_portal_uri_background(self, lang: str, uri: str, copy: bool, task_id: str | None = None) -> bool:
        """Background worker to parse Portal URI and trigger OCR."""
        try:
            if uri.startswith("file://") and len(uri) > len("file://"):
                filename = url2pathname(uri[len("file://") :])
            else:
                filename = GLib.Uri.unescape_string(uri)
        except (ValueError, GLib.Error) as e:
            logger.error(f"Anura Screenshot: Failed to parse URI '{mask_url(uri)}': {e}")
            self._emit_decode_error(_("Can't take a screenshot."))
            return False

        # Check for cancellation before I/O
        if task_id and get_atomic_manager().is_cancelled(task_id):
            return False

        # Validate the extracted filename before processing (on background thread)
        if not filename or not Path(filename).exists():
            logger.error(f"Anura Screenshot: Invalid or non-existent file path: {filename}")
            self._emit_decode_error(_("Can't take a screenshot."))
            return False

        return self.decode_image(lang, filename, copy, remove_source=True, task_id=task_id)

    def _emit_decode_error(self, message: str) -> None:
        """Helper to emit error signal on the main thread."""

        def _on_error_idle():
            try:
                self.emit("error", message)
            except (RuntimeError, TypeError) as e:
                logger.exception(f"Anura: Failed to emit error: {message} ({e})")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_on_error_idle, priority=GLib.PRIORITY_DEFAULT)

    def _emit_decoded(self, text: str, copy: bool, ocr_result: OcrResult | None, applied_name: str) -> None:
        """Helper to emit decoded signal on the main thread."""

        def _on_decoded_idle():
            try:
                self.emit("decoded", text, copy, ocr_result, applied_name)
            except (RuntimeError, TypeError) as e:
                logger.exception(f"Anura: Failed to emit decoded signal: {e}")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_on_decoded_idle, priority=GLib.PRIORITY_DEFAULT)

    def _emit_status(self, status_msg: str) -> None:
        """Helper to emit status-changed signal on the main thread."""

        def _on_status_idle():
            try:
                self.emit("status-changed", status_msg)
            except (RuntimeError, TypeError) as e:
                logger.debug(f"Failed to emit status-changed: {e}")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_on_status_idle)

    def _decode_image_isolated(
        self,
        lang: str,
        file: str,
        copy: bool = False,
        remove_source: bool = False,
    ) -> None:
        """Triggers isolated OCR pipeline execution to bypass GIL."""
        mode = settings.get_string("ocr-preprocessing")
        self._emit_status(_("Extracting text..."))

        def _on_isolated_complete(result_tuple):
            # FIX BUG-H-003: unpack 5-tuple — run_ocr_pipeline now returns applied_name
            # to avoid re-running MagicProcessor in OcrController._on_shot_done.
            success, extracted, error_message, ocr_result, applied_name = (
                result_tuple if len(result_tuple) == 5 else (*result_tuple, "")
            )
            if success:
                self._emit_decoded(extracted, copy, ocr_result, applied_name)
            elif error_message:
                self._emit_decode_error(error_message)
            else:
                self._emit_decode_error("")

            if remove_source:
                get_atomic_manager().execute(Path(file).unlink, ())

        def _on_isolated_error(error, _traceback_str):
            logger.error(f"Anura OCR (Isolated): Process error: {error}")
            self._emit_decode_error(_("OCR processing failed. Please try again."))

        def _on_isolated_status(status_msg):
            self._emit_status(status_msg)

        # BUG-nav-block: clear _current_task_id now so backend.current_task_id returns
        # None, causing _navigate_to_extracted_page to skip the guard and
        # open ExtractedPage correctly after a successful scrot capture.
        self._current_task_id = None

        get_atomic_manager().execute_isolated(
            run_ocr_pipeline,
            (lang, file, mode),
            callback=_on_isolated_complete,
            errorback=_on_isolated_error,
            status_callback=_on_isolated_status,
        )

    # Environment variables surfaced when the portal screenshot fails. These
    # tell us which desktop/session backend should be answering the portal
    # request, which is the single most useful piece of triage data when a
    # screenshot fails with a generic libportal error.
    _PORTAL_DIAGNOSTIC_ENV_KEYS = (
        "XDG_CURRENT_DESKTOP",
        "XDG_SESSION_TYPE",
        "XDG_SESSION_DESKTOP",
        "DESKTOP_SESSION",
        "GDMSESSION",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "FLATPAK_ID",
        "container",
    )

    def _log_portal_environment(self) -> None:
        """Dump host environment context once on portal failure.

        Captures the XDG/Flatpak environment variables that determine which
        xdg-desktop-portal backend handles the request. Logged at most once
        per process so repeated failures don't flood the log.
        """
        if self._env_diagnostics_logged:
            return
        self._env_diagnostics_logged = True

        snapshot = ", ".join(f"{key}={os.environ.get(key) or '<unset>'}" for key in self._PORTAL_DIAGNOSTIC_ENV_KEYS)
        in_flatpak = _is_flatpak_environment()
        logger.debug(
            f"Anura Screenshot diagnostics: in_flatpak={in_flatpak}, {snapshot}",
        )

    def _emit_portal_failure(self) -> None:
        """Emit the user-facing failure UI for a missing portal backend.

        Centralised so both portal and fallback can call it consistently.
        Uses desktop-aware advice based on XDG_CURRENT_DESKTOP.
        """
        advice = detect_portal_advice()
        user_message = advice.long_message

        def _on_failure_idle():
            try:
                self.emit("portal-backend-missing")
                self.emit("error", user_message)
            except (RuntimeError, TypeError) as e:
                logger.exception(f"Anura: Failed to emit portal failure signals: {e}")
            return GLib.SOURCE_REMOVE

        GLib.idle_add(_on_failure_idle)

    def decode_image_sync(
        self,
        lang: str,
        file: str | Image.Image | object,
        remove_source: bool = False,
        task_id: str | None = None,
    ) -> tuple[bool, str | None, str | None, OcrResult | None, str]:
        """
        Synchronously decodes the image to find QR codes or extract text using Tesseract OCR.
        Supports file paths (str) and binary streams (BytesIO).
        """
        validation_result = self._validate_decode_inputs(lang)
        if not validation_result[0]:
            return validation_result

        is_physical_file = self._determine_file_type(file, remove_source)

        if not isinstance(file, Image.Image):
            is_valid, _size, error = validate_image_resource(file)
            if not is_valid:
                logger.error(f"Anura OCR: {error}")
                return False, "", _(error) if error else _("Invalid image file"), None, ""

        start_time = time.time()

        try:
            extracted, error_message, ocr_result, applied_name = self._process_image_decode(
                file, lang, start_time, task_id=task_id
            )
        except InterruptedError:
            logger.debug(f"Anura OCR: Task {task_id} was cancelled during processing.")
            return False, None, None, None, ""
        except (OSError, RuntimeError, TypeError, AttributeError) as e:
            extracted, error_message = self._handle_decode_exception(e)
            ocr_result = None
            applied_name = ""
        finally:
            self._cleanup_temporary_file(file, is_physical_file, remove_source)

        return self._format_decode_result(extracted, error_message, ocr_result, applied_name)

    def _validate_decode_inputs(self, lang: str) -> tuple[bool, str | None, str | None, OcrResult | None, str]:
        """Validate language code for OCR processing."""
        if not lang or not re.match(LANG_CODE_PATTERN, lang):
            logger.error(f"Anura: Invalid language code '{lang}' for OCR")
            return (False, "", _("Invalid language code specified."), None, "")
        return (True, None, None, None, "")

    def _determine_file_type(self, file: str | Image.Image | object, _remove_source: bool) -> bool:
        """Determine if file is a physical file."""
        return isinstance(file, str) and Path(file).exists()

    def _process_image_decode(
        self,
        file: str | Image.Image | object,
        lang: str,
        start_time: float,
        task_id: str | None = None,
    ) -> tuple[str | None, str | None, OcrResult | None, str]:
        """Process image for QR code detection and OCR.

        Returns:
            (extracted_text, error_message, ocr_result, applied_name)
        """
        extracted = None
        error_message = None
        ocr_result = None
        applied_name = ""

        if isinstance(file, str) and Path(file).exists() and Path(file).stat().st_size == 0:
            logger.error(f"Anura OCR: Attempted to process 0-byte image file: {file}")
            return None, _("The selected image file is empty."), None, ""

        import contextlib
        img_context: Any
        if isinstance(file, Image.Image):
            img_context = contextlib.nullcontext(file)
        else:
            img_context = Image.open(file)  # type: ignore[arg-type]

        with img_context as img:
            image_size = img.size
            logger.debug(f"Anura OCR: Processing image size: {image_size[0]}x{image_size[1]}")

            extracted = self._try_barcode_detection(img, start_time)

            if extracted is None:
                if task_id and get_atomic_manager().is_cancelled(task_id):
                    raise InterruptedError(f"Task {task_id} was cancelled before OCR")

                if img.mode != "L":
                    img = img.convert("L")  # type: ignore[assignment]
                extracted, ocr_result, applied_name = self._try_ocr_extraction(
                    img, lang, start_time, task_id=task_id
                )

        return extracted, error_message, ocr_result, applied_name

    def _try_barcode_detection(self, img: Image.Image, start_time: float) -> str | None:
        """Try to detect and decode QR codes and Barcodes from image using zxing-cpp."""
        try:
            from anura.utils.barcode_detector import detect_barcodes

            results = detect_barcodes(img)
            if results:
                raw_extracted = "\n".join([res.text for res in results])
                extracted = sanitize_text(raw_extracted)
                duration = time.time() - start_time
                logger.info(f"Anura ZXing: Code(s) detected in {duration:.3f}s")
                return extracted
        except (ImportError, RuntimeError, ValueError) as e:
            logger.debug(f"Anura ZXing: Detection failed: {e}")
        return None

    def _try_ocr_extraction(
        self, img: Image.Image, lang: str, start_time: float, task_id: str | None = None
    ) -> tuple[str | None, OcrResult | None, str]:
        """Try to extract text using Tesseract OCR with preprocessing and Magic Transformers.

        Returns:
            (cleaned_text, ocr_result, applied_name) — applied_name is the MagicProcessor
            transformer that was selected (empty string when magic-processing is disabled or
            when the reconstructor won the selection contest).  Surfaced here so callers can
            forward it via the 'decoded' signal without re-running MagicProcessor a second
            time on the main thread (FIX BUG-H-003).
        """
        try:
            from pytesseract import Output

            from anura.transformers.magic_processor import get_magic_processor

            mode = settings.get_string("ocr-preprocessing")

            preprocessor = get_text_preprocessor()
            enhanced_img = preprocessor.enhance_image(img, task_id=task_id) if mode != "off" else img

            if task_id and get_atomic_manager().is_cancelled(task_id):
                raise InterruptedError(f"Task {task_id} was cancelled before Tesseract")

            ocr_data = pytesseract.image_to_data(
                enhanced_img,
                lang=lang,
                config=get_tesseract_config(lang, task_id=task_id),
                output_type=Output.DICT,
            )

            ocr_result = OcrResult.from_tesseract_dict(ocr_data)

            if task_id and get_atomic_manager().is_cancelled(task_id):
                raise InterruptedError(f"Task {task_id} was cancelled before Reconstruction")

            reconstructor = get_structural_reconstructor()
            spatially_reconstructed, recon_conf = reconstructor.reconstruct(ocr_result, task_id=task_id)

            magic_processor = get_magic_processor()
            processed_text, magic_conf, applied_name = magic_processor.process(ocr_result, task_id=task_id)

            if spatially_reconstructed.strip() and (
                (len(spatially_reconstructed) > len(processed_text) * 1.2 and recon_conf >= magic_conf * 0.95)
                or recon_conf > magic_conf
            ):
                processed_text = spatially_reconstructed
                # Reconstructor won: the magic-transformer name is no longer representative
                applied_name = ""

            if mode == "full":
                cleaned_text = preprocessor.clean_extracted_text(processed_text)
            elif mode == "image-only":
                cleaned_text = sanitize_text(processed_text)
            else:
                cleaned_text = processed_text.strip()

            cleaned_text = sanitize_text(cleaned_text)

            duration = time.time() - start_time
            logger.info(f"Anura OCR: Text extraction and Magics completed in {duration:.3f}s")

            return cleaned_text, ocr_result, applied_name
        except InterruptedError:
            logger.debug("Anura OCR: Cancellation intercepted, re-raising InterruptedError")
            raise
        except (OSError, RuntimeError, TypeError, AttributeError) as e:
            logger.debug(f"Anura OCR: OCR extraction or Magic processing failed: {e}")
            return None, None, ""

    def _handle_decode_exception(self, e: Exception) -> tuple[str | None, str | None]:
        """Handle exceptions during image decoding."""
        extracted = None
        error_message = None

        if isinstance(e, OSError):
            logger.exception(f"Anura OCR/QR File Error: {e}")
            error_message = _("Failed to read image file.")
        elif isinstance(e, (pytesseract.TesseractError, pytesseract.TesseractNotFoundError)):
            logger.exception(f"Anura OCR Error: Tesseract failed: {e}")
            error_message = _("OCR engine failed to process image.")
        elif isinstance(e, (Image.DecompressionBombError, Image.UnidentifiedImageError)):
            logger.exception(f"Anura OCR/QR Error: {type(e).__name__}: {e}")
            error_message = _("Failed to decode data.")
        elif isinstance(e, (SystemExit, KeyboardInterrupt)):
            raise
        else:
            logger.exception(f"Anura OCR/QR Error: {type(e).__name__}: {e}")
            error_message = _("Failed to decode data.")

        return extracted, error_message

    def _cleanup_temporary_file(
        self,
        file: str | Image.Image | object,
        is_physical_file: bool,
        remove_source: bool,
    ) -> None:
        """Clean up temporary files if requested."""
        if remove_source and is_physical_file:
            try:
                Path(file).unlink()  # type: ignore[arg-type]
                logger.debug(f"Anura OCR: Cleaned up temporary file: {file}")
            except (OSError, PermissionError) as e:
                logger.warning(f"Anura OCR: Could not delete {file}: {e}")

    def _format_decode_result(
        self,
        extracted: str | None,
        error_message: str | None,
        ocr_result: OcrResult | None = None,
        applied_name: str = "",
    ) -> tuple[bool, str | None, str | None, OcrResult | None, str]:
        """Format the final decode result — returns a 5-tuple including applied_name."""
        if extracted:
            return (True, extracted, None, ocr_result, applied_name)
        elif error_message:
            return (False, "", error_message, None, "")
        else:
            return (False, "", _("No text found."), None, "")

    def decode_image(
        self,
        lang: str,
        file: str | Image.Image | object,
        copy: bool = False,
        remove_source: bool = False,
        task_id: str | None = None,
    ) -> bool:
        """
        Asynchronously decodes the image and emits GObject signals.
        Wraps decode_image_sync() for use with GUI mode.
        """
        # Validate language code before processing
        if not lang or not re.match(LANG_CODE_PATTERN, lang):
            logger.error(f"Anura: Invalid language code '{lang}' for OCR")
            self._emit_decode_error(_("Invalid language code specified."))
            return False

        # If it's a physical file, we can use process isolation to bypass the GIL
        if isinstance(file, str) and Path(file).exists():
            self._decode_image_isolated(lang, file, copy, remove_source)
            return True

        success, extracted, error_message, ocr_result, applied_name = self.decode_image_sync(
            lang, file, remove_source, task_id=task_id
        )

        if success:
            if extracted is not None:
                self._emit_decoded(extracted, copy, ocr_result, applied_name)
            else:
                self._emit_decode_error(_("No text found."))
        else:
            if error_message is not None:
                self._emit_decode_error(error_message)
            else:
                self._emit_decode_error(_("Failed to decode image."))

        return False

    def do_destroy(self) -> None:
        """Clean up cancellable to prevent leaks."""
        with self._cancellable_lock:
            if self.cancelable is not None:
                if not self.cancelable.is_cancelled():
                    self.cancelable.cancel()
                self.cancelable = None


def get_screenshot_service() -> ScreenshotService:
    """Get thread-safe screenshot service singleton."""
    return get_instance(ScreenshotService)
