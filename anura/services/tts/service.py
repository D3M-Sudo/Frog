# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from typing import ClassVar

import gi

# Set GTK version requirements before imports
gi.require_version("GLib", "2.0")
gi.require_version("GObject", "2.0")

from gi.repository import GObject  # noqa: E402
from loguru import logger  # noqa: E402

from anura.services.settings import settings  # noqa: E402
from anura.services.tts.pipeline_manager import PipelineManager  # noqa: E402
from anura.utils.singleton import get_instance  # noqa: E402


class TTSService(GObject.GObject):
    """
    Service responsible for converting text to speech and managing audio playback.
    Delegates to specialized managers for generation, playback, and language mapping.
    """

    __gtype_name__ = "TTSService"

    __gsignals__: ClassVar[dict[str, tuple]] = {
        "speak": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "stop": (GObject.SignalFlags.RUN_LAST, None, (bool,)),
        "paused": (GObject.SignalFlags.RUN_LAST, None, (bool,)),
        "error": (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__()
        logger.debug("Anura TTSService: Initializing TTS service singleton")

        self._pipeline = PipelineManager()

        # Connect pipeline signals to forward them
        self._pipeline.connect("speak", self._on_speak)
        self._pipeline.connect("stop", self._on_stop)
        self._pipeline.connect("paused", self._on_paused)
        self._pipeline.connect("error", self._on_error)

        logger.debug("Anura TTSService: TTS service initialization complete")

    def _on_speak(self, _pipeline: PipelineManager, filepath: str) -> None:
        """Forward speak signal from PipelineManager."""
        self.emit("speak", filepath)

    def _on_stop(self, _pipeline: PipelineManager, completed: bool) -> None:
        """Forward stop signal from PipelineManager."""
        self.emit("stop", completed)

    def _on_paused(self, _pipeline: PipelineManager, is_paused: bool) -> None:
        """Forward paused signal from PipelineManager."""
        self.emit("paused", is_paused)

    def _on_error(self, _pipeline: PipelineManager, error_msg: str) -> None:
        """Forward error signal from PipelineManager."""
        self.emit("error", error_msg)

    def get_supported_languages(self) -> dict:
        """Fetch available languages supported by gTTS (cached, via LanguageMapper).

        Pass-through to PipelineManager on purpose: callers must not reach
        into self._pipeline directly, and the legacy uncached gtts.lang.tts_langs()
        call must not be re-exposed here (synchronous network fetch per call).
        """
        return self._pipeline.get_supported_languages()

    def get_effective_language(self, ocr_lang: str) -> str | None:
        """Return TTS language: user preference or fallback to OCR language."""
        tts_lang = settings.get_string("tts-language")
        if tts_lang:
            return tts_lang
        # Fallback: map OCR language to TTS
        return self._pipeline.map_language(ocr_lang)

    def generate(self, text: str, lang: str = "en") -> str:
        """Generate speech file (for compatibility with existing code)."""
        return self._pipeline.generate_speech_file(text, lang)

    def play(self, speech_file: str) -> None:
        """Play a speech file (for compatibility with existing code)."""
        volume = max(0.0, min(1.0, settings.get_double("tts-volume")))
        self._pipeline.play_speech_file(speech_file, volume)

    def stop_speaking(self) -> None:
        """Stop playback."""
        self._pipeline.stop()

    def pause(self) -> None:
        """Pause playback."""
        self._pipeline.pause()

    def resume(self) -> None:
        """Resume playback."""
        self._pipeline.resume()

    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._pipeline.is_playing()

    def is_paused(self) -> bool:
        """Check if currently paused.

        Pass-through to PipelineManager on purpose: the controller must not
        access the underlying GStreamer element (self._pipeline._player.player).
        """
        return self._pipeline.is_paused()

    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self._pipeline.toggle_pause()

    def cleanup(self) -> None:
        """Complete cleanup for shutdown."""
        self._pipeline.cleanup()


# Thread-safe singleton instance for global app access
def get_tts_service() -> TTSService:
    """Get thread-safe TTS service singleton."""
    return get_instance(TTSService)
