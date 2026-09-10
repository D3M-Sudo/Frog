# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import pytest

pytest.importorskip("gi")

from gi.repository import Gio, GLib

from anura.services.settings import Settings

pytestmark = pytest.mark.gtk


@pytest.fixture
def gsettings():
    """Fresh GSettings instance with history keys reset to defaults."""
    s = Settings()
    yield s
    s.reset("history-enabled")
    s.reset("history-limit")


class TestHistorySettings:
    """Focused tests for the History V1 GSettings keys."""

    def test_history_enabled_default_false(self, gsettings):
        assert gsettings.get_boolean("history-enabled") is False
        assert gsettings.get_default_value("history-enabled").get_boolean() is False

    def test_history_limit_default_50(self, gsettings):
        assert gsettings.get_int("history-limit") == 50
        assert gsettings.get_default_value("history-limit").unpack() == 50

    def test_history_enabled_read_write(self, gsettings):
        gsettings.set_boolean("history-enabled", True)
        assert gsettings.get_boolean("history-enabled") is True
        gsettings.set_boolean("history-enabled", False)
        assert gsettings.get_boolean("history-enabled") is False

    def test_history_limit_read_write(self, gsettings):
        gsettings.set_int("history-limit", 120)
        assert gsettings.get_int("history-limit") == 120

    def test_history_limit_respects_schema_range(self, gsettings):
        schema = Gio.SettingsSchemaSource.get_default().lookup("io.github.d3msudo.anura", True)
        key = schema.get_key("history-limit")
        value_type = key.get_value_type()
        assert value_type.equal(GLib.VariantType.new("i"))
        min_v, max_v = key.get_range().unpack()[1]
        assert min_v == 1
        assert max_v == 500
