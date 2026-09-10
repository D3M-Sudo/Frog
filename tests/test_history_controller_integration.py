# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from unittest.mock import MagicMock

import pytest

from anura.models.ocr import OcrResult
from anura.services.history_service import HistoryService


class MockWindow:
    """Minimal window stand-in matching the OcrController contract."""

    def __init__(self, enabled: bool = True, limit: int = 50):
        self.backend = MagicMock()
        self.portal_banner = MagicMock()
        self.settings = MagicMock()
        self.settings.get_boolean.return_value = enabled
        self.settings.get_int.return_value = limit

    def register_controller(self, ctrl) -> None:
        pass

    def get_language(self) -> str:
        return "ita"


def _ocr_result(conf: float = 88.5) -> OcrResult:
    return OcrResult(words=(), raw_text="hello world", avg_confidence=conf)


def _make_controller(window: MockWindow, service: HistoryService | None):
    from anura.controllers.ocr_controller import OcrController

    return OcrController(window, history_service=service)


# ---------------------------------------------------------------------- #
# History disabled / enabled
# ---------------------------------------------------------------------- #


def test_history_disabled_records_nothing(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    window = MockWindow(enabled=False)
    ctrl = _make_controller(window, service)

    ctrl._on_shot_done(MagicMock(), "secret text", False, _ocr_result(), "Magic")

    assert service.get_entries() == []


def test_history_enabled_records_entry(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    window = MockWindow(enabled=True)
    ctrl = _make_controller(window, service)

    ctrl._on_shot_done(MagicMock(), "hello world", False, _ocr_result(), "Magic")

    entries = service.get_entries()
    assert len(entries) == 1
    assert entries[0].text == "hello world"


# ---------------------------------------------------------------------- #
# Field availability
# ---------------------------------------------------------------------- #


def test_history_entry_language_from_window(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    window = MockWindow(enabled=True)
    ctrl = _make_controller(window, service)

    ctrl._on_shot_done(MagicMock(), "ciao", False, _ocr_result(), "Magic")

    entries = service.get_entries()
    assert entries[0].language == "ita"
    assert entries[0].applied_name == "Magic"
    assert entries[0].conf == pytest.approx(88.5)


def test_history_skipped_without_service(headless_gi_mocks):
    """Backwards compatibility: no injected service → no crash, nothing stored."""
    window = MockWindow(enabled=True)
    ctrl = _make_controller(window, None)
    ctrl._on_shot_done(MagicMock(), "text", False, _ocr_result(), "Magic")
    assert ctrl._history_service is None


def test_history_error_never_breaks_ocr_flow(headless_gi_mocks):
    """A persistence failure is swallowed and must not raise."""

    class FailingService:
        def record(self, **_kwargs):
            raise OSError("disk full")

    window = MockWindow(enabled=True)
    ctrl = _make_controller(window, FailingService())
    # Must not raise
    ctrl._on_shot_done(MagicMock(), "text", False, _ocr_result(), "Magic")


# ---------------------------------------------------------------------- #
# Limit wiring (window-level, verified statically — window construction
# requires the full GTK template; the limit behaviour itself is covered
# by tests/test_history_storage.py)
# ---------------------------------------------------------------------- #


def test_window_wires_history_service_with_configured_limit():
    from pathlib import Path

    window_src = (Path(__file__).resolve().parents[1] / "anura" / "window.py").read_text()
    assert 'HistoryService(limit=self.settings.get_int("history-limit"))' in window_src
    assert "OcrController(self, history_service=self.history_service)" in window_src
