# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import sys
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("gi")

# Mock missing components
import gi

try:
    from gi.repository import Gio  # noqa: F401
except ImportError:
    mock_gio = MagicMock()
    sys.modules["gi.repository.Gio"] = mock_gio
    gi.repository.Gio = mock_gio

try:
    from gi.repository import GLib  # noqa: F401
except ImportError:
    mock_glib = MagicMock()
    sys.modules["gi.repository.GLib"] = mock_glib
    gi.repository.GLib = mock_glib

try:
    from gi.repository import Xdp  # noqa: F401
except ImportError:
    mock_xdp = MagicMock()
    sys.modules["gi.repository.Xdp"] = mock_xdp
    gi.repository.Xdp = mock_xdp

try:
    from gi.repository import GObject  # noqa: F401
except ImportError:
    mock_gobject = MagicMock()

    class MockGObject:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def emit(*args, **kwargs):
            pass

    mock_gobject.GObject = MockGObject
    sys.modules["gi.repository.GObject"] = mock_gobject
    gi.repository.GObject = mock_gobject

# Now import the service
from anura.services.screenshot_service import ScreenshotService


class TestScreenshotServiceEnterprise:
    """
    Enterprise-grade unit tests for ScreenshotService.
    Focuses on logic paths and fallbacks safe for VM/headless.
    """

    @pytest.fixture
    def service(self):
        with patch("anura.services.screenshot_service._configure_tesseract_path"):
            # Minimal init to satisfy the tests
            # We want to use the real class logic but avoid GObject issues
            class PseudoService:
                pass

            s = PseudoService()
            s.provider = MagicMock()
            s.fallback_provider = MagicMock()
            s._is_capturing = False
            s._current_task_id = None
            s._emit_decode_error = MagicMock()
            s._log_portal_environment = MagicMock()
            s._emit_portal_failure = MagicMock()
            return s

    def test_validate_decode_inputs(self, service):
        """Test language code validation."""
        valid, _, _, _, _ = ScreenshotService._validate_decode_inputs(service, "eng")
        assert valid is True

        invalid, _, err, _, _ = ScreenshotService._validate_decode_inputs(service, "invalid-code!!")
        assert invalid is False
        assert "Invalid language code" in err

    def test_screenshot_fallback_logic_generic_dbus_error(self, service):
        """BUG-004: a real portal error that does NOT contain 'screenshot failed'
        (e.g. a localized GDBus UnknownMethod) must still trigger the fallback."""
        def _mock_capture(lang, copy, callback):
            callback(
                False,
                None,
                "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
                "No such interface 'org.freedesktop.portal.Screenshot'",
            )

        service.provider.capture = MagicMock(side_effect=_mock_capture)
        service._is_capturing = False
        ScreenshotService.capture(service, "eng", False)

        service.fallback_provider.capture.assert_called_once()

    def test_screenshot_fallback_logic_exact_screenshot_failed(self, service):
        """The historical exact string 'screenshot failed' still triggers the fallback."""
        def _mock_capture(lang, copy, callback):
            callback(False, None, "screenshot failed")

        service.provider.capture = MagicMock(side_effect=_mock_capture)
        service._is_capturing = False
        ScreenshotService.capture(service, "eng", False)

        service.fallback_provider.capture.assert_called_once()

    def test_screenshot_fallback_user_cancellation_does_not_trigger(self, service):
        """BUG-004: error=None (user cancellation) must NOT trigger the fallback."""
        def _mock_capture(lang, copy, callback):
            callback(False, None, None)

        service.provider.capture = MagicMock(side_effect=_mock_capture)
        service._is_capturing = False
        ScreenshotService.capture(service, "eng", False)

        service.fallback_provider.capture.assert_not_called()
        assert service._is_capturing is False

    def test_screenshot_fallback_unavailable_emits_portal_failure(self, service):
        """No fallback_provider available: the portal-failure path (banner + desktop
        advice) runs instead of a generic fallback-error; no exception is raised."""
        service.fallback_provider = None

        def _mock_capture(lang, copy, callback):
            callback(
                False,
                None,
                "GDBus.Error:org.freedesktop.DBus.Error.UnknownMethod: "
                "No such interface 'org.freedesktop.portal.Screenshot'",
            )

        service.provider.capture = MagicMock(side_effect=_mock_capture)
        service._is_capturing = False
        ScreenshotService.capture(service, "eng", False)  # must not raise

        service._log_portal_environment.assert_called_once()
        service._emit_portal_failure.assert_called_once()
        service._emit_decode_error.assert_not_called()
        assert service._is_capturing is False

    def test_screenshot_fallback_failure_does_not_recurse(self, service):
        """BUG-004 safeguard: when the fallback itself fails with a real error, the
        service must NOT trigger the fallback again (no infinite loop) and must emit
        the generic error exactly once."""
        def _mock_capture(lang, copy, callback):
            callback(False, None, "The portal host does not support screenshot capture")

        service.provider.capture = MagicMock(side_effect=_mock_capture)

        def _mock_fallback_capture(lang, copy, callback):
            callback(False, None, "scrot not found")

        service.fallback_provider.capture = MagicMock(side_effect=_mock_fallback_capture)
        service._is_capturing = False
        ScreenshotService.capture(service, "eng", False)

        assert service.provider.capture.call_count == 1
        assert service.fallback_provider.capture.call_count == 1
        service._emit_decode_error.assert_called_once()
        assert service._is_capturing is False

    def test_format_decode_result(self, service):
        """Test result formatting for various OCR outcomes."""
        # Success
        s, t, e, _, _aname = ScreenshotService._format_decode_result(service, "Extracted Text", None)
        assert s is True
        assert t == "Extracted Text"
        assert e is None

        # Explicit Error
        s, t, e, _, _aname = ScreenshotService._format_decode_result(service, None, "Fatal Error")
        assert s is False
        assert t == ""
        assert e == "Fatal Error"

        # No Text Found
        s, t, e, _, _aname = ScreenshotService._format_decode_result(service, None, None)
        assert s is False
        assert "No text found" in e

    def test_cleanup_temporary_file(self, service, tmp_path):
        """Test cleanup logic for source files."""
        temp_file = tmp_path / "shot.png"
        temp_file.touch()

        # Case: remove_source=True
        ScreenshotService._cleanup_temporary_file(service, str(temp_file), True, True)
        assert not temp_file.exists()

        # Case: remove_source=False
        temp_file.touch()
        ScreenshotService._cleanup_temporary_file(service, str(temp_file), True, False)
        assert temp_file.exists()
