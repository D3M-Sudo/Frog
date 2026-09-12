# models.py
#
# Copyright 2026 D3M-Sudo (Anura fork and modifications)
#
# MIT License
"""Models for the Magic Transformer pattern."""

from dataclasses import dataclass, field
import enum
from functools import cached_property
from typing import Any, Protocol


class TransformerType(enum.StrEnum):
    SINGLE_LINE = "SINGLE_LINE"
    MULTI_LINE = "MULTI_LINE"
    PARAGRAPH = "PARAGRAPH"
    MAIL = "MAIL"
    URL = "URL"


@dataclass
class OcrResult:
    """Encapsulate recognized text and layout information from image_to_data."""

    words: list[Any]
    text: str = ""
    transformer_scores: dict[TransformerType, float] = field(default_factory=dict)
    parsed: list[str] = field(default_factory=list)

    @cached_property
    def _layout_stats(self) -> dict[str, int]:
        """
        Calculate layout statistics in a single pass and cache the result.
        Reduces complexity from up to 6*O(N) down to 1*O(N) for Magic processing.
        """
        blocks: set[Any] = set()
        pars: set[tuple[Any, Any]] = set()
        lines: set[tuple[Any, Any, Any]] = set()

        if self.words:
            first = self.words[0]
            if isinstance(first, dict):
                for w in self.words:
                    b = w.get("block_num")
                    p = w.get("par_num")
                    ln = w.get("line_num")
                    blocks.add(b)
                    pars.add((b, p))
                    lines.add((b, p, ln))
            else:
                for w in self.words:
                    b = getattr(w, "block_num", None)
                    p = getattr(w, "par_num", None)
                    ln = getattr(w, "line_num", None)
                    blocks.add(b)
                    pars.add((b, p))
                    lines.add((b, p, ln))

        return {
            "block_num": len(blocks),
            "par_num": len(pars),
            "line_num": len(lines),
        }

    @property
    def num_lines(self) -> int:
        return self._layout_stats["line_num"]

    @property
    def num_pars(self) -> int:
        return self._layout_stats["par_num"]

    @property
    def num_blocks(self) -> int:
        return self._layout_stats["block_num"]

    def add_linebreaks(
        self,
        block_sep: str = "\n\n",
        par_sep: str = "\n",
        line_sep: str = "\n",
        word_sep: str = " ",
    ) -> str:
        if not self.words:
            return ""

        last_block_num = None
        last_par_num = None
        last_line_num = None
        text_parts = []

        # Optimization: Check if the first word is a dictionary or an object
        # to avoid dynamic _get_val calls within the hot loop.
        first = self.words[0]
        if isinstance(first, dict):
            for word in self.words:
                # Skip empty entries often returned by Tesseract for layout markers
                text = word.get("text")
                if not text or not text.strip():
                    continue

                block_num = word.get("block_num")
                par_num = word.get("par_num")
                line_num = word.get("line_num")

                if last_block_num is not None and block_num != last_block_num:
                    text_parts.append(block_sep)
                elif last_par_num is not None and par_num != last_par_num:
                    text_parts.append(par_sep)
                elif last_line_num is not None and line_num != last_line_num:
                    text_parts.append(line_sep)
                elif last_line_num is not None:
                    text_parts.append(word_sep)

                text_parts.append(text)

                last_block_num = block_num
                last_par_num = par_num
                last_line_num = line_num
        else:
            for word in self.words:
                # Skip empty entries often returned by Tesseract for layout markers
                text = getattr(word, "text", None)
                if not text or not text.strip():
                    continue

                block_num = getattr(word, "block_num", None)
                par_num = getattr(word, "par_num", None)
                line_num = getattr(word, "line_num", None)

                if last_block_num is not None and block_num != last_block_num:
                    text_parts.append(block_sep)
                elif last_par_num is not None and par_num != last_par_num:
                    text_parts.append(par_sep)
                elif last_line_num is not None and line_num != last_line_num:
                    text_parts.append(line_sep)
                elif last_line_num is not None:
                    text_parts.append(word_sep)

                text_parts.append(text)

                last_block_num = block_num
                last_par_num = par_num
                last_line_num = line_num

        return "".join(text_parts).strip()


class ITransformer(Protocol):
    """Protocol for OCR result transformers."""

    def score(self, ocr_result: OcrResult) -> float:
        """Calculate a score (0.0 to 1.0) indicating how well this transformer fits the result."""
        ...

    def transform(self, ocr_result: OcrResult) -> list[str]:
        """Transform the OCR result into a list of strings."""
        ...


# Compatibility alias
TransformerProtocol = ITransformer
