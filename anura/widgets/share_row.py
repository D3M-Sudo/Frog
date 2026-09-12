# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _

from gi.repository import GLib, Gtk

from anura.config import RESOURCE_PREFIX


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/share_row.ui")
class ShareRow(Gtk.ListBoxRow):
    __gtype_name__ = "ShareRow"

    box: Gtk.Box = Gtk.Template.Child()
    image: Gtk.Image = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    provider_name: str = "email"

    def __init__(self, provider_name: str) -> None:
        super().__init__()

        self.provider_name = provider_name or "email"
        display_name = provider_name.capitalize()
        tooltip = _("Share via {name}").format(name=display_name)

        self.set_tooltip_text(tooltip)
        self.update_property([Gtk.AccessibleProperty.LABEL], [tooltip])

        self.label.set_label(display_name)
        self.image.set_from_icon_name(f"share-{self.provider_name.lower()}-symbolic")

    @Gtk.Template.Callback()
    def _on_released(self, *_args: object) -> None:
        self.activate_action(
            "win.share",
            GLib.Variant.new_string(self.provider_name),
        )
