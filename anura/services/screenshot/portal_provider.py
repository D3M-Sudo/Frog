# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from collections.abc import Callable
import contextlib
import threading

from gi.repository import Gio, GLib, Xdp
from loguru import logger

from .base import ScreenshotProvider


class PortalProvider(ScreenshotProvider):
    """Screenshot provider using XDG Desktop Portal."""

    def __init__(self) -> None:
        self.portal = Xdp.Portal()
        self._cancellable: Gio.Cancellable | None = None
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        # Portals are the primary method in Flatpak and modern desktops
        return True

    def cancel(self) -> None:
        """Cancel any in-flight portal request."""
        with self._lock:
            if self._cancellable is not None and not self._cancellable.is_cancelled():
                self._cancellable.cancel()
                logger.debug("PortalProvider: Cancelled in-flight portal request.")
            self._cancellable = None

    def capture(self, lang: str, copy: bool, callback: Callable) -> None:
        # Cancel any previous in-flight request before starting a new one
        self.cancel()

        cancellable = Gio.Cancellable.new()
        with self._lock:
            self._cancellable = cancellable

        try:
            self.portal.take_screenshot(
                None,
                Xdp.ScreenshotFlags.INTERACTIVE,
                cancellable,
                self._on_finish,
                (lang, copy, callback),
            )
        except (GLib.Error, RuntimeError) as e:
            logger.error(f"PortalProvider: Call failed: {e}")
            with self._lock:
                self._cancellable = None
            callback(False, None, str(e))

    def _on_finish(self, _source_object: object, res: Gio.AsyncResult, user_data: tuple) -> None:
        _lang, _copy, callback = user_data

        # Clear saved cancellable — this request is done
        with self._lock:
            self._cancellable = None

        try:
            try:
                uri = self.portal.take_screenshot_finish(res)
                if uri:
                    callback(True, uri, None)
                else:
                    # Cancelled by user (portal returned empty URI)
                    callback(False, None, None)
            except GLib.Error as e:
                if e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                    callback(False, None, None)
                else:
                    # Log full error context (domain + code + message)
                    logger.error(
                        "PortalProvider: Portal failed to provide a screenshot "
                        f"(domain={e.domain}, code={e.code}): {e.message}",
                    )

                    is_known_backend_missing = (
                        e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.FAILED)
                        and (e.message or "").strip().lower() == "screenshot failed"
                    )

                    if is_known_backend_missing:
                        logger.warning(
                            "PortalProvider: xdg-desktop-portal screenshot backend failed (code=0). "
                            "This is often caused by missing portal backends or an unavailable "
                            "session bus. Try installing one of: "
                            "xdg-desktop-portal-gnome, xdg-desktop-portal-gtk, "
                            "xdg-desktop-portal-kde.",
                        )
                    else:
                        logger.warning(
                            "PortalProvider: unexpected portal error "
                            f"(domain={e.domain}, code={e.code}): {e.message} — "
                            "screenshot will use fallback if available.",
                        )

                    callback(False, None, e.message)
            except RuntimeError as e:
                logger.error(f"PortalProvider: Unexpected error: {e}")
                callback(False, None, str(e))
        except (AttributeError, RuntimeError, TypeError) as e:
            # BUG-031: Ensure callback is ALWAYS invoked to prevent ScreenshotService deadlock
            logger.exception(f"PortalProvider: Fatal error in callback wrapper: {e}")
            with contextlib.suppress(Exception):
                callback(False, None, str(e))
