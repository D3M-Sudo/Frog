# This file is part of Anura.
# Copyright (C) 2022-2025 Andrey Maksimov (Frog)
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from gettext import gettext as _
import re
from typing import ClassVar

from anura.config import LANG_CODE_PATTERN
from anura.models.language_item import LanguageItem


class LanguageValidator:
    """
    Validates language codes and provides language metadata.
    Handles ISO 639-2 mapping and validation.
    """

    # Full ISO 639-2 mapping (Tesseract compatible)
    _languages: ClassVar[dict[str, str]] = {
        "afr": _("Afrikaans"),
        "amh": _("Amharic"),
        "ara": _("Arabic"),
        "asm": _("Assamese"),
        "aze": _("Azerbaijani"),
        "aze_cyrl": _("Azerbaijani - Cyrillic"),
        "bel": _("Belarusian"),
        "ben": _("Bengali"),
        "bod": _("Tibetan"),
        "bos": _("Bosnian"),
        "bre": _("Breton"),
        "bul": _("Bulgarian"),
        "cat": _("Catalan"),
        "ceb": _("Cebuano"),
        "ces": _("Czech"),
        "chi_sim": _("Chinese - Simplified"),
        "chi_sim_vert": _("Chinese - Simplified (vertical)"),
        "chi_tra": _("Chinese - Traditional"),
        "chi_tra_vert": _("Chinese - Traditional (vertical)"),
        "chr": _("Cherokee"),
        "cos": _("Corsican"),
        "cym": _("Welsh"),
        "dan": _("Danish"),
        "deu": _("German"),
        "deu_latf": _("German - Fraktur"),
        "dzo": _("Dzongkha"),
        "ell": _("Greek"),
        "eng": _("English"),
        "enm": _("English, Middle"),
        "epo": _("Esperanto"),
        "est": _("Estonian"),
        "eus": _("Basque"),
        "fao": _("Faroese"),
        "fas": _("Persian"),
        "fil": _("Filipino"),
        "fin": _("Finnish"),
        "fra": _("French"),
        "frm": _("French, Middle"),
        "fry": _("Western Frisian"),
        "gla": _("Scottish Gaelic"),
        "gle": _("Irish"),
        "glg": _("Galician"),
        "grc": _("Greek, Ancient"),
        "guj": _("Gujarati"),
        "hat": _("Haitian"),
        "heb": _("Hebrew"),
        "hin": _("Hindi"),
        "hrv": _("Croatian"),
        "hun": _("Hungarian"),
        "hye": _("Armenian"),
        "iku": _("Inuktitut"),
        "ind": _("Indonesian"),
        "isl": _("Icelandic"),
        "ita": _("Italian"),
        "ita_old": _("Italian - Old"),
        "jav": _("Javanese"),
        "jpn": _("Japanese"),
        "jpn_vert": _("Japanese (vertical)"),
        "kan": _("Kannada"),
        "kat": _("Georgian"),
        "kat_old": _("Georgian - Old"),
        "kaz": _("Kazakh"),
        "khm": _("Central Khmer"),
        "kir": _("Kirghiz"),
        "kmr": _("Kurmanji"),
        "kor": _("Korean"),
        "kor_vert": _("Korean (vertical)"),
        "lao": _("Lao"),
        "lat": _("Latin"),
        "lav": _("Latvian"),
        "lit": _("Lithuanian"),
        "ltz": _("Luxembourgish"),
        "mal": _("Malayalam"),
        "mar": _("Marathi"),
        "mkd": _("Macedonian"),
        "mlt": _("Maltese"),
        "mon": _("Mongolian"),
        "mri": _("Maori"),
        "msa": _("Malay"),
        "mya": _("Burmese"),
        "nep": _("Nepali"),
        "nld": _("Dutch"),
        "nor": _("Norwegian"),
        "oci": _("Occitan"),
        "ori": _("Oriya"),
        "pan": _("Panjabi"),
        "pol": _("Polish"),
        "por": _("Portuguese"),
        "pus": _("Pushto"),
        "que": _("Quechua"),
        "ron": _("Romanian"),
        "rus": _("Russian"),
        "san": _("Sanskrit"),
        "sin": _("Sinhala"),
        "slk": _("Slovak"),
        "slv": _("Slovenian"),
        "snd": _("Sindhi"),
        "spa": _("Spanish"),
        "spa_old": _("Spanish - Old"),
        "sqi": _("Albanian"),
        "srp": _("Serbian"),
        "srp_latn": _("Serbian - Latin"),
        "sun": _("Sundanese"),
        "swa": _("Swahili"),
        "swe": _("Swedish"),
        "syr": _("Syriac"),
        "tam": _("Tamil"),
        "tat": _("Tatar"),
        "tel": _("Telugu"),
        "tgk": _("Tajik"),
        "tha": _("Thai"),
        "tir": _("Tigrinya"),
        "ton": _("Tonga"),
        "tur": _("Turkish"),
        "uig": _("Uighur"),
        "ukr": _("Ukrainian"),
        "urd": _("Urdu"),
        "uzb": _("Uzbek"),
        "uzb_cyrl": _("Uzbek - Cyrillic"),
        "vie": _("Vietnamese"),
        "yid": _("Yiddish"),
        "yor": _("Yoruba"),
    }

    @classmethod
    def is_valid_code(cls, code: str) -> bool:
        """Check if a language code is valid.

        Args:
            code: Language code to validate

        Returns:
            True if valid, False otherwise
        """
        if not code or not re.match(LANG_CODE_PATTERN, code):
            return False
        return code in cls._languages

    @classmethod
    def is_valid_code_format(cls, code: str) -> bool:
        """Check if a language code has valid format (regex only).

        Use this for operations like remove_language() where the file on disk
        is the source of truth, not the static language map.

        Args:
            code: Language code to validate

        Returns:
            True if format is valid, False otherwise
        """
        return bool(code and re.match(LANG_CODE_PATTERN, code))

    @classmethod
    def is_safe_filename(cls, filename: str) -> bool:
        """Check if a filename is safe (prevents path traversal).

        Args:
            filename: Filename to validate

        Returns:
            True if safe, False otherwise
        """
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", filename))

    @classmethod
    def get_language_name(cls, code: str) -> str:
        """Returns the human-readable language name for a given ISO code.

        Args:
            code: Language code

        Returns:
            Human-readable name, or the code itself if not found
        """
        return cls._languages.get(code, code)

    @classmethod
    def get_language_item(cls, code: str) -> LanguageItem | None:
        """Create a LanguageItem for a given code.

        Args:
            code: Language code

        Returns:
            LanguageItem if code is valid, None otherwise
        """
        if code not in cls._languages:
            return None
        return LanguageItem(code=code, title=cls._languages[code])

    @classmethod
    def get_available_codes(cls) -> list[str]:
        """Returns all ISO codes supported by Tesseract.

        Returns:
            Sorted list of language codes
        """
        return sorted(cls._languages.keys())

    @classmethod
    def get_language_code(cls, name: str) -> str:
        """Reverse lookup: from name to ISO code.

        Args:
            name: Human-readable language name

        Returns:
            Language code, or 'eng' as default if not found
        """
        for code, lang_name in cls._languages.items():
            if lang_name == name:
                return code
        return "eng"
