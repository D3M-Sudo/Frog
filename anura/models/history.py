# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid


def _utc_now_iso() -> str:
    """Current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """Immutable record of a single OCR result, persisted to local history."""

    text: str
    language: str
    applied_name: str = ""
    conf: float = 0.0
    timestamp: str = None  # type: ignore[assignment]
    id: str = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.timestamp:
            object.__setattr__(self, "timestamp", _utc_now_iso())
        if not self.id:
            object.__setattr__(self, "id", str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "text": self.text,
            "language": self.language,
            "timestamp": self.timestamp,
            "applied_name": self.applied_name,
            "conf": self.conf,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "HistoryEntry | None":
        """
        Defensively deserialize a dictionary into a HistoryEntry.

        Returns None for any structurally invalid input, so a corrupted
        history file never crashes the application on load.
        """
        if not isinstance(data, dict):
            return None

        text = data.get("text")
        language = data.get("language")
        if not isinstance(text, str) or not isinstance(language, str):
            return None

        timestamp = data.get("timestamp")
        if not isinstance(timestamp, str):
            return None

        entry_id = data.get("id")
        if not isinstance(entry_id, str):
            return None

        applied_name = data.get("applied_name")
        if not isinstance(applied_name, str):
            applied_name = ""

        try:
            conf = float(data.get("conf", 0.0))
        except (TypeError, ValueError):
            conf = 0.0

        return cls(
            text=text,
            language=language,
            timestamp=timestamp,
            id=entry_id,
            applied_name=applied_name,
            conf=conf,
        )
