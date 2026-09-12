# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

"""Headless regression tests for PreferencesGeneralPage __init__ resilience.

Regression (History V1): a failure in `_setup_tts_language()` (e.g. the
pre-ad5f49d `get_supported_gtts_languages()` AttributeError) used to abort
`__init__` before `_setup_history()` ran, leaving the `history-enabled`
switch unbound to GSettings and its value never persisted.

The __init__ must therefore isolate the TTS-dependent setup so that the
history settings binding always executes.
"""

from unittest.mock import MagicMock


class FakeSettings:
    """Records GSettings calls made by the page under test."""

    def __init__(self):
        self.bound_keys: list[str] = []

    def bind(self, key, *_args, **_kwargs):
        self.bound_keys.append(key)

    def get_int(self, key):
        if key != "history-limit":
            raise KeyError(key)
        return 50

    def set_int(self, _key, _value):
        pass

    def get_string(self, _key):
        return ""

    def get_double(self, _key):
        return 0.5


def _make_page(monkeypatch, tts_raises: Exception | None):
    """Build the page with mocked collaborators; returns (page, settings)."""
    import anura.widgets.preferences_general_page as mod

    fake_settings = FakeSettings()
    monkeypatch.setattr(mod, "settings", fake_settings)

    fake_lang_manager = MagicMock()
    monkeypatch.setattr(mod, "get_language_manager", lambda: fake_lang_manager)

    if tts_raises is not None:
        def _boom():
            raise tts_raises

        monkeypatch.setattr(mod, "get_tts_service", _boom)

    page = mod.PreferencesGeneralPage()
    return page, fake_settings


def test_history_bound_when_tts_language_fails(monkeypatch, headless_gi_mocks):
    """A TTS setup failure must not prevent the history GSettings binding."""
    _page, fake_settings = _make_page(monkeypatch, tts_raises=AttributeError("boom"))

    assert "history-enabled" in fake_settings.bound_keys


def test_init_completes_normally(monkeypatch, headless_gi_mocks):
    """Happy path: all expected keys are bound when TTS setup succeeds."""
    _page, fake_settings = _make_page(monkeypatch, tts_raises=None)

    assert "autocopy" in fake_settings.bound_keys
    assert "history-enabled" in fake_settings.bound_keys


def test_history_limit_changed_persists(monkeypatch, headless_gi_mocks):
    """The SpinRow change handler persists the limit as an int."""
    page, _fake_settings = _make_page(monkeypatch, tts_raises=None)

    spin_row = MagicMock()
    spin_row.get_value.return_value = 120.0
    persisted: list[tuple[str, int]] = []

    class RecordingSettings(FakeSettings):
        def set_int(self, key, value):
            persisted.append((key, value))

    recording = RecordingSettings()
    page.settings = recording
    page._on_history_limit_changed(spin_row, None)

    assert persisted == [("history-limit", 120)]
