# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT


from gi.repository import Gio, GLib
from loguru import logger


class ActionRegistry:
    """Centralized registry for application actions and shortcuts."""

    def __init__(self, app):
        self.app = app

    def setup_actions(self):
        """Register all application actions."""
        # Main actions
        self._create_action("get_screenshot", self.app.get_screenshot, ["<primary>g"])
        self._create_action("get_screenshot_and_copy", self.app.get_screenshot_and_copy, ["<primary><shift>g"])
        self._create_action("copy_to_clipboard", self.app.on_copy_to_clipboard, ["<primary>c"])
        self._create_action("open_image", self.app.open_image, ["<primary>o"])
        self._create_action("paste_from_clipboard", self.app.on_paste_from_clipboard, ["<primary>v"])
        self._create_action("find", self.app.on_find, ["<primary>f"])
        self._create_action("open_external_editor", self.app.on_open_external_editor, ["<primary><shift>e"])
        self._create_action("listen", self.app.on_listen, ["<primary>l"])
        self._create_action("listen_pause", self.app.on_listen_pause, ["<primary><alt>l"])
        self._create_action("listen_cancel", self.app.on_listen_cancel, ["<primary><shift>l"])
        self._create_action("shortcuts", self.app.on_shortcuts, ["<primary>h"])
        self._create_action("quit", lambda *_: self.app.quit(), ["<primary>q"])
        self._create_action("preferences", self.app.on_preferences, ["<primary>comma"])
        self._create_action("about", self.app.on_about)
        self._create_action("github_star", self.app.on_github_star)
        self._create_action("report_issue", self.app.on_report_issue)

        # Specialized actions
        open_qr_action = Gio.SimpleAction.new("open-qr-url", GLib.VariantType.new("s"))
        open_qr_action.connect("activate", self.app._on_open_qr_notification)
        self.app.add_action(open_qr_action)

        logger.debug("ActionRegistry: All actions registered.")

    def _create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.app.add_action(action)
        if shortcuts:
            self.app.set_accels_for_action(f"app.{name}", shortcuts)
