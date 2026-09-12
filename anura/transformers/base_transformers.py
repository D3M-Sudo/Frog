# base_transformers.py
#
# Copyright 2026 D3M-Sudo (Anura fork and modifications)
#
# MIT License

from anura.transformers.models import OcrResult, TransformerProtocol


class SingleLineTransformer(TransformerProtocol):
    def score(self, ocr_result: OcrResult) -> float:
        if not ocr_result.words:
            return 0
        return 50 if ocr_result.num_lines == 1 else 0

    def transform(self, ocr_result: OcrResult) -> list[str]:
        return [ocr_result.add_linebreaks(line_sep=" ")]


class MultiLineTransformer(TransformerProtocol):
    def score(self, ocr_result: OcrResult) -> float:
        if ocr_result.num_lines > 1 and ocr_result.num_blocks == 1 and ocr_result.num_pars == 1:
            return 60.0
        return 0

    def transform(self, ocr_result: OcrResult) -> list[str]:
        return [ocr_result.add_linebreaks()]


class ParagraphTransformer(TransformerProtocol):
    def score(self, ocr_result: OcrResult) -> float:
        if not ocr_result.words:
            return 0
        breaks = ocr_result.num_blocks + ocr_result.num_pars - 1
        if breaks <= 1:
            return 0
        # Keep Paragraph above MultiLine (60.0) / SingleLine (50.0)
        # for any result with multiple paragraphs/blocks.
        return 60.0 + (40.0 * (1.0 - (1.0 / (breaks + 0.05))))

    def transform(self, ocr_result: OcrResult) -> list[str]:
        return [ocr_result.add_linebreaks(block_sep="\n", line_sep=" ")]
