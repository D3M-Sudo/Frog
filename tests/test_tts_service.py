# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import pytest

pytest.importorskip("gi")

from unittest.mock import MagicMock, patch

from anura.services.tts import TTSService
from anura.services.tts.language_mapper import LanguageMapper


class TestTTSServiceEnterprise:
    """
    Enterprise-grade unit tests for TTSService.
    """

    @pytest.fixture
    def service(self):
        with patch("gi.repository.Gst.init"):
            return TTSService()

    def test_map_tesseract_to_gtts_happy_path(self):
        """Test mapping of Tesseract codes to gTTS codes."""
        assert LanguageMapper.map_tesseract_to_gtts("eng") == "en"
        assert LanguageMapper.map_tesseract_to_gtts("ita") == "it"
        assert LanguageMapper.map_tesseract_to_gtts("jpn_vert") == "ja"
        assert LanguageMapper.map_tesseract_to_gtts("chi_sim") == "zh-CN"

    def test_map_tesseract_to_gtts_fallbacks(self):
        """Test fallback behavior for unknown or invalid codes."""
        assert LanguageMapper.map_tesseract_to_gtts(None) == "en"
        # Unknown codes now return None (no fallback to "en")
        assert LanguageMapper.map_tesseract_to_gtts("unknown") is None

        # Test 2-char prefix matching
        with patch.object(LanguageMapper, "get_supported_gtts_languages", return_value={"fr": "French"}):
            assert LanguageMapper.map_tesseract_to_gtts("fra-new") == "fr"

    def test_generate_empty_text(self, service):
        """Test generate with empty or whitespace text."""
        assert service.generate("") == ""
        assert service.generate("   ") == ""
        assert service.generate(None) == ""

    @patch("gtts.gTTS")
    @patch("os.makedirs")
    def test_generate_save_error(self, mock_makedirs, mock_gtts, service):
        """Test error handling during speech file generation."""
        mock_tts_instance = mock_gtts.return_value
        mock_tts_instance.save.side_effect = OSError("Disk full")

        with patch("loguru.logger.error") as mock_log:
            result = service.generate("hello", "en")
            assert result == ""
            mock_log.assert_called()

    def test_get_effective_language(self, service):
        """Test determination of the effective TTS language."""
        # Case 1: User has set a specific TTS language
        with patch("anura.services.settings.settings.get_string", return_value="de"):
            assert service.get_effective_language("eng") == "de"

        # Case 2: No user preference, fallback to OCR mapping
        with patch("anura.services.settings.settings.get_string", return_value=""):
            assert service.get_effective_language("ita") == "it"

    def test_is_playing_states(self, service):
        """Test is_playing reporting based on GStreamer state."""
        assert service.is_playing() is False

        service._pipeline._player = MagicMock()

        # Mock is_playing on the player
        service._pipeline._player.is_playing.return_value = True
        assert service.is_playing() is True

        service._pipeline._player.is_playing.return_value = False
        assert service.is_playing() is False

    def test_stop_speaking_cleanup(self, service):
        """Test that stop_speaking cleans up resources and files."""
        service._pipeline._player = MagicMock()
        service._pipeline._generator = MagicMock()

        service.stop_speaking()
        service._pipeline._player.stop.assert_called_once()
        service._pipeline._generator.clear_current_file.assert_called_once()

    def test_referential_transparency_mapping(self):
        """Test that language mapping is pure."""
        code = "eng"
        assert LanguageMapper.map_tesseract_to_gtts(code) == LanguageMapper.map_tesseract_to_gtts(code)

    def test_get_supported_languages_delegates_to_cached_mapper(self, service):
        """TTSService.get_supported_languages must delegate to the cached
        LanguageMapper (via PipelineManager), never to an uncached network call."""
        cached = {"fr": "French", "it": "Italian"}
        with patch.object(LanguageMapper, "get_supported_gtts_languages", return_value=cached):
            result = service.get_supported_languages()
        assert result == cached

    def test_is_paused_delegates_to_pipeline(self, service):
        """TTSService.is_paused must be a pass-through to PipelineManager."""
        service._pipeline._player = MagicMock()
        service._pipeline._player.is_paused.return_value = True
        assert service.is_paused() is True

        service._pipeline._player.is_paused.return_value = False
        assert service.is_paused() is False
