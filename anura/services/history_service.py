# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

import json
import logging
import os
from pathlib import Path
import time

from anura.config import XDG_DATA_HOME
from anura.models.history import HistoryEntry

logger = logging.getLogger(__name__)

DEFAULT_HISTORY_LIMIT = 50


class HistoryService:
    """
    Simple synchronous local history persistence (JSON file).

    Stores OCR results newest-first in
    ``$XDG_DATA_HOME/anura/history/history.json`` with atomic writes and
    corruption recovery. No threading, no database — integration concerns
    are deferred to later phases.
    """

    def __init__(
        self,
        base_dir: Path | str | None = None,
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> None:
        if base_dir is None:
            base_dir = Path(XDG_DATA_HOME) / "anura" / "history"
        self._base_dir = Path(base_dir)
        self._history_file = self._base_dir / "history.json"
        self._limit = limit
        self._entries: list[HistoryEntry] | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def record(
        self,
        text: str,
        language: str,
        applied_name: str = "",
        conf: float = 0.0,
    ) -> HistoryEntry:
        """Create a new entry, insert it newest-first, enforce the limit and persist."""
        entry = HistoryEntry(text=text, language=language, applied_name=applied_name, conf=conf)
        entries = self._load()
        entries.insert(0, entry)
        self._entries = entries[: self._limit]
        self._persist()
        return entry

    def get_entries(self, limit: int | None = None) -> list[HistoryEntry]:
        """Return stored entries newest-first. The returned list is a copy."""
        entries = self._load()
        if limit is not None:
            return entries[:limit]
        return list(entries)

    def clear(self) -> None:
        """Remove all entries and persist the empty history."""
        self._entries = []
        self._persist()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _load(self) -> list[HistoryEntry]:
        """Lazily load entries from disk, handling corruption defensively."""
        if self._entries is not None:
            return self._entries

        entries: list[HistoryEntry] = []
        if self._history_file.exists():
            try:
                raw = self._history_file.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, list):
                    for item in data:
                        entry = HistoryEntry.from_dict(item)
                        if entry is not None:
                            entries.append(entry)
                else:
                    self._quarantine_corrupted()
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                self._quarantine_corrupted()
                entries = []

        self._entries = entries[: self._limit]
        return self._entries

    def _quarantine_corrupted(self) -> None:
        """Rename the corrupted file instead of deleting it; never crash."""
        quarantine = self._base_dir / f"history.json.corrupt-{int(time.time())}"
        try:
            os.replace(self._history_file, quarantine)
            logger.warning("Corrupted history file quarantined: %s", quarantine)
        except OSError:
            logger.exception("Failed to quarantine corrupted history file")

    def _persist(self) -> None:
        """Atomically write the history file (temp file + os.replace)."""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps([e.to_dict() for e in self._entries or []], ensure_ascii=False, indent=2)
        tmp_path = self._base_dir / f"history.json.tmp-{os.getpid()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._history_file)
        except OSError:
            logger.exception("Failed to persist history")
            tmp_path.unlink(missing_ok=True)
            raise
