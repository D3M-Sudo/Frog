#!/usr/bin/env python3
# tests/test_tessdata_consistency.py
"""Tests for build-aux/check_tessdata_consistency.py

Verifies that the tessdata consistency checker correctly detects:
- Case A: Consistent state (PASS)
- Case B: config.py different (FAIL)
- Case C: Main manifest different (FAIL)
- Case D: Local manifest different (FAIL)
- Case E: Unrelated structural differences (PASS)
"""

import json
from pathlib import Path
import sys

import pytest

# Import the checker module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build-aux"))
import check_tessdata_consistency as checker

# Valid test commit SHAs (40 hex chars)
VALID_SHA = "923915d4ced2a7235221788285785a29c4a42d4a"
DIFFERENT_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    """Create a temporary config.py with tessdata URLs."""
    config = tmp_path / "config.py"
    config.write_text(
        f'# tessdata configuration\n'
        f'TESSDATA_BEST_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/{VALID_SHA}/"\n'
    )
    return config


@pytest.fixture
def temp_manifest(tmp_path: Path) -> Path:
    """Create a temporary Flatpak manifest with tessdata module."""
    manifest = tmp_path / "manifest.json"
    data = {
        "app-id": "io.github.d3msudo.anura",
        "modules": [
            {
                "name": "tessdata",
                "buildsystem": "simple",
                "build-commands": [
                    "install -Dm0644 eng.traineddata /app/share/tessdata/eng.traineddata"
                ],
                "sources": [
                    {
                        "type": "file",
                        "url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{VALID_SHA}/eng.traineddata",
                        "sha256": "abc123"
                    }
                ]
            }
        ]
    }
    manifest.write_text(json.dumps(data, indent=4))
    return manifest


class TestExtractShaFromConfig:
    """Tests for extract_sha_from_config function."""

    def test_valid_config(self, temp_config: Path) -> None:
        """Extract SHA from a valid config file."""
        sha = checker.extract_sha_from_config(temp_config)
        assert sha == VALID_SHA

    def test_missing_tessdata_url(self, tmp_path: Path) -> None:
        """Return None when TESSDATA_BEST_URL is missing."""
        config = tmp_path / "config.py"
        config.write_text("# No tessdata URL here\n")
        sha = checker.extract_sha_from_config(config)
        assert sha is None

    def test_malformed_url(self, tmp_path: Path) -> None:
        """Return None when URL doesn't match expected pattern."""
        config = tmp_path / "config.py"
        config.write_text('TESSDATA_BEST_URL = "https://example.com/invalid/"\n')
        sha = checker.extract_sha_from_config(config)
        assert sha is None


class TestExtractShasFromManifest:
    """Tests for extract_shas_from_manifest function."""

    def test_valid_manifest(self, temp_manifest: Path) -> None:
        """Extract SHAs from a valid manifest."""
        shas = checker.extract_shas_from_manifest(temp_manifest)
        assert shas == [VALID_SHA]

    def test_multiple_sources(self, tmp_path: Path) -> None:
        """Extract multiple SHAs from tessdata module."""
        manifest = tmp_path / "manifest.json"
        data = {
            "modules": [
                {
                    "name": "tessdata",
                    "sources": [
                        {"url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{VALID_SHA}/eng.traineddata"},
                        {"url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{VALID_SHA}/ita.traineddata"}
                    ]
                }
            ]
        }
        manifest.write_text(json.dumps(data))
        shas = checker.extract_shas_from_manifest(manifest)
        assert shas == [VALID_SHA, VALID_SHA]

    def test_no_tessdata_module(self, tmp_path: Path) -> None:
        """Return empty list when no tessdata module exists."""
        manifest = tmp_path / "manifest.json"
        data = {"modules": [{"name": "other-module"}]}
        manifest.write_text(json.dumps(data))
        shas = checker.extract_shas_from_manifest(manifest)
        assert shas == []


class TestConsistencyScenarios:
    """Integration tests for the full consistency check.

    These tests use monkeypatching to point the checker at temporary files.
    """

    def test_case_a_consistent(
        self,
        temp_config: Path,
        temp_manifest: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Case A: All references consistent -> PASS."""
        monkeypatch.setattr(checker, "CONFIG_PY", temp_config)
        monkeypatch.setattr(checker, "MANIFEST_MAIN", temp_manifest)
        monkeypatch.setattr(checker, "MANIFEST_LOCAL", temp_manifest)

        result = checker.main()
        assert result == 0

    def test_case_b_config_different(
        self,
        tmp_path: Path,
        temp_manifest: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Case B: config.py has different SHA -> FAIL."""
        config = tmp_path / "config.py"
        config.write_text(
            f'TESSDATA_BEST_URL = "https://github.com/tesseract-ocr/tessdata_best/raw/{DIFFERENT_SHA}/"\n'
        )
        monkeypatch.setattr(checker, "CONFIG_PY", config)
        monkeypatch.setattr(checker, "MANIFEST_MAIN", temp_manifest)
        monkeypatch.setattr(checker, "MANIFEST_LOCAL", temp_manifest)

        result = checker.main()
        assert result == 1

    def test_case_c_main_manifest_different(
        self,
        tmp_path: Path,
        temp_config: Path,
        temp_manifest: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Case C: Main manifest has different SHA -> FAIL."""
        different_manifest = tmp_path / "different_manifest.json"
        data = {
            "modules": [
                {
                    "name": "tessdata",
                    "sources": [
                        {
                            "url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{DIFFERENT_SHA}/eng.traineddata"
                        }
                    ],
                }
            ]
        }
        different_manifest.write_text(json.dumps(data))

        monkeypatch.setattr(checker, "CONFIG_PY", temp_config)
        monkeypatch.setattr(checker, "MANIFEST_MAIN", different_manifest)
        monkeypatch.setattr(checker, "MANIFEST_LOCAL", temp_manifest)

        result = checker.main()
        assert result == 1

    def test_case_d_local_manifest_different(
        self,
        tmp_path: Path,
        temp_config: Path,
        temp_manifest: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Case D: Local manifest has different SHA -> FAIL."""
        different_manifest = tmp_path / "different_manifest.json"
        data = {
            "modules": [
                {
                    "name": "tessdata",
                    "sources": [
                        {
                            "url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{DIFFERENT_SHA}/eng.traineddata"
                        }
                    ],
                }
            ]
        }
        different_manifest.write_text(json.dumps(data))

        monkeypatch.setattr(checker, "CONFIG_PY", temp_config)
        monkeypatch.setattr(checker, "MANIFEST_MAIN", temp_manifest)
        monkeypatch.setattr(checker, "MANIFEST_LOCAL", different_manifest)

        result = checker.main()
        assert result == 1

    def test_case_e_unrelated_differences_pass(
        self,
        tmp_path: Path,
        temp_config: Path,
        temp_manifest: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Case E: Unrelated structural differences -> PASS.

        Differences in other modules should not cause false positives.
        """
        modified_manifest = tmp_path / "modified_manifest.json"
        data = {
            "modules": [
                {
                    "name": "leptonica",
                    "sources": [
                        {"type": "archive", "url": "https://example.com/leptonica.tar.gz"}
                    ],
                },
                {
                    "name": "tessdata",
                    "sources": [
                        {
                            "url": f"https://github.com/tesseract-ocr/tessdata_fast/raw/{VALID_SHA}/eng.traineddata"
                        }
                    ],
                },
                {
                    "name": "extra-module",
                    "sources": [
                        {"type": "archive", "url": "https://example.com/extra.tar.gz"}
                    ],
                },
            ]
        }
        modified_manifest.write_text(json.dumps(data))

        monkeypatch.setattr(checker, "CONFIG_PY", temp_config)
        monkeypatch.setattr(checker, "MANIFEST_MAIN", modified_manifest)
        monkeypatch.setattr(checker, "MANIFEST_LOCAL", temp_manifest)

        result = checker.main()
        assert result == 0
