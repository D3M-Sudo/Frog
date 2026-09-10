# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

"""Focused headless tests for the History V1 page (HistoryPage).

Uses the repository's headless gi-mock convention: widgets are constructed
with `headless_gi_mocks` and gi-dependent modules are imported inside the
test functions. Behaviour is asserted on the template-child mocks.
"""

from unittest.mock import MagicMock

from anura.services.history_service import HistoryService


class FakeSettings:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def get_boolean(self, key: str) -> bool:
        if key != "history-enabled":
            raise KeyError(key)
        return self.enabled


def _make_page(headless_gi_mocks, service: HistoryService | None = None, enabled: bool = True):
    """Import and build the HistoryPage under headless gi stubs."""
    from anura.widgets.history_page import HistoryPage

    page = HistoryPage()
    # Under headless stubs, template children are shared class-level mocks;
    # give this instance fresh isolated mocks so call counts don't leak.
    page.history_stack = MagicMock()
    page.history_list = MagicMock()
    page.clear_button = MagicMock()
    page.settings = FakeSettings(enabled)
    if service is not None:
        page.setup(service)
    return page


# ---------------------------------------------------------------------- #
# Empty history / disabled state
# ---------------------------------------------------------------------- #


def test_empty_enabled_history_shows_empty_state(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    page = _make_page(headless_gi_mocks, service, enabled=True)

    page.history_stack.set_visible_child_name.assert_called_with("empty")


def test_disabled_history_shows_disabled_state(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    page = _make_page(headless_gi_mocks, service, enabled=False)

    page.history_stack.set_visible_child_name.assert_called_with("disabled")


def test_disabled_history_does_not_delete_existing_entries(headless_gi_mocks, tmp_path):
    """history-enabled=false must NOT clear persisted history."""
    service = HistoryService(base_dir=tmp_path)
    service.record("kept", "eng")
    _make_page(headless_gi_mocks, service, enabled=False)

    assert len(service.get_entries()) == 1


# ---------------------------------------------------------------------- #
# Entries display
# ---------------------------------------------------------------------- #


def test_one_entry_displayed(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("hello world", "eng", applied_name="Magic", conf=91.0)
    page = _make_page(headless_gi_mocks, service)

    page.history_stack.set_visible_child_name.assert_called_with("entries")
    assert page.history_list.append.call_count == 1


def test_multiple_entries_newest_first(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("first", "eng")
    service.record("second", "eng")
    service.record("third", "eng")
    page = _make_page(headless_gi_mocks, service)

    assert page.history_list.append.call_count == 3
    # Service API already guarantees newest-first; the page must not reorder.
    assert service.get_entries()[0].text == "third"


def test_long_text_does_not_break_page(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("x" * 10_000, "eng")
    page = _make_page(headless_gi_mocks, service)

    page.history_stack.set_visible_child_name.assert_called_with("entries")
    assert page.history_list.append.call_count == 1

# ---------------------------------------------------------------------- #
# Malformed entry / defensive formatting
# ---------------------------------------------------------------------- #


def test_malformed_entry_does_not_crash(headless_gi_mocks):
    """Defensive formatting must survive incomplete/garbage field values."""
    from anura.models.history import HistoryEntry
    from anura.widgets.history_page import (
        format_entry_subtitle,
        format_entry_timestamp,
        format_entry_title,
    )

    entry = HistoryEntry(text="ok", language="eng", applied_name="", conf=-1.0)
    subtitle = format_entry_subtitle(entry)
    assert isinstance(subtitle, str)
    assert "eng" in subtitle

    # Garbage timestamp → raw fallback, no exception
    entry_bad_ts = HistoryEntry(text="ok", language="eng", timestamp="not-a-date")
    assert format_entry_timestamp("not-a-date") == "not-a-date"
    assert format_entry_subtitle(entry_bad_ts).startswith("not-a-date")

    # Empty/None-ish text handling
    assert format_entry_title("") == ""
    assert format_entry_title(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------- #
# Clear action
# ---------------------------------------------------------------------- #


def test_clear_action_refreshes_page(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("doomed", "eng")
    page = _make_page(headless_gi_mocks, service)

    dialog = MagicMock()
    page._on_clear_response(dialog, "clear")
    dialog.force_close.assert_called_once()

    assert service.get_entries() == []


def test_clear_cancelled_keeps_entries(headless_gi_mocks, tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("safe", "eng")
    page = _make_page(headless_gi_mocks, service)

    page._on_clear_response(MagicMock(), "cancel")

    assert len(service.get_entries()) == 1


def test_clear_io_failure_does_not_crash(headless_gi_mocks, tmp_path, monkeypatch):
    service = HistoryService(base_dir=tmp_path)
    service.record("entry", "eng")
    page = _make_page(headless_gi_mocks, service)

    def failing_clear():
        raise OSError("disk full")

    monkeypatch.setattr(service, "clear", failing_clear)
    # Must not raise
    page._on_clear_response(MagicMock(), "clear")


# ---------------------------------------------------------------------- #
# Wiring (window-level, verified statically — window construction
# requires the full GTK template)
# ---------------------------------------------------------------------- #


def test_window_wires_history_page_and_navigation():
    from pathlib import Path

    window_src = (Path(__file__).resolve().parents[1] / "anura" / "window.py").read_text()
    assert "self.history_page.setup(self.history_service)" in window_src
    assert 'self.navigation_view.push_by_tag("history")' in window_src

    window_blp = (Path(__file__).resolve().parents[1] / "data" / "ui" / "window.blp").read_text()
    assert "$HistoryPage history_page {" in window_blp
    assert 'tag: "history";' in window_blp

    welcome_blp = (Path(__file__).resolve().parents[1] / "data" / "ui" / "welcome_page.blp").read_text()
    assert '"win.show-history"' in welcome_blp
