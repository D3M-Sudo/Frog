# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_extracted_page_ui_reflow_properties() -> None:
    """
    Verifies that the generated extracted_page.ui contains the correct properties
    to enable dynamic text reflow as specified in the resolution methodology.

    This test compiles the .blp file to .ui on-the-fly since .ui files are
    no longer tracked in git (they are build artifacts from blueprint-compiler).
    """
    blp_file = PROJECT_ROOT / "data" / "ui" / "extracted_page.blp"
    assert blp_file.exists(), "extracted_page.blp must exist"

    # Check if blueprint-compiler is available
    try:
        subprocess.run(
            ["blueprint-compiler", "--version"],
            check=True,
            capture_output=True,
            text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("blueprint-compiler not available, skipping .ui compilation test")

    # Compile .blp to .ui in a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        ui_file = Path(tmpdir) / "extracted_page.ui"

        subprocess.run(
            ["blueprint-compiler", "compile", str(blp_file), "--output", str(ui_file)],
            check=True,
            capture_output=True,
            text=True
        )

        assert ui_file.exists(), "extracted_page.ui must be generated from blueprint-compiler"

        tree = ET.parse(ui_file)
        root = tree.getroot()

        # Check ScrolledWindow (text_scrollview)
        scrollview = None
        for obj in root.iter("object"):
            if obj.get("id") == "text_scrollview" and obj.get("class") == "GtkScrolledWindow":
                scrollview = obj
                break

        assert scrollview is not None, "GtkScrolledWindow with id 'text_scrollview' not found"

        width_request = None
        hscrollbar_policy = None
        propagate_natural_width = None
        for prop in scrollview.findall("property"):
            if prop.get("name") == "width-request":
                width_request = prop.text
            if prop.get("name") == "hscrollbar-policy":
                hscrollbar_policy = prop.text
            if prop.get("name") == "propagate-natural-width":
                propagate_natural_width = prop.text

        assert width_request == "150", "text_scrollview must have width-request set to 150"
        assert hscrollbar_policy == "2", "text_scrollview must have hscrollbar-policy set to GTK_POLICY_NEVER (2)"
        assert propagate_natural_width == "false", "text_scrollview must have propagate-natural-width set to false"

        # Check TextView (text_view)
        textview = None
        for obj in root.iter("object"):
            if obj.get("id") == "text_view" and obj.get("class") == "GtkTextView":
                textview = obj
                break

        assert textview is not None, "GtkTextView with id 'text_view' not found"

        wrap_mode = None
        left_margin = None
        right_margin = None
        tv_width_request = None
        tv_vexpand = None
        for prop in textview.findall("property"):
            if prop.get("name") == "wrap-mode":
                wrap_mode = prop.text
            if prop.get("name") == "left-margin":
                left_margin = prop.text
            if prop.get("name") == "right-margin":
                right_margin = prop.text
            if prop.get("name") == "width-request":
                tv_width_request = prop.text
            if prop.get("name") == "vexpand":
                tv_vexpand = prop.text

        assert wrap_mode == "2", "text_view must have wrap-mode set to GTK_WRAP_WORD (2)"
        assert left_margin == "14", "text_view must have left-margin set to 14"
        assert right_margin == "14", "text_view must have right-margin set to 14"
        assert tv_width_request == "100", "text_view must have width-request set to 100 to constrain minimum width"
        assert tv_vexpand == "true", "text_view must have vexpand set to true for vertical expansion"
