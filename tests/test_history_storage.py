# This file is part of Anura.
# Copyright (C) 2026 D3M-Sudo (Anura)
#
# SPDX-License-Identifier: MIT

from dataclasses import FrozenInstanceError
import json

import pytest

from anura.models.history import HistoryEntry
from anura.services.history_service import HistoryService

# ---------------------------------------------------------------------- #
# HistoryEntry
# ---------------------------------------------------------------------- #


def test_entry_create_defaults():
    entry = HistoryEntry(text="hello", language="eng")
    assert entry.text == "hello"
    assert entry.language == "eng"
    assert entry.id
    assert entry.timestamp
    assert entry.applied_name == ""
    assert entry.conf == 0.0


def test_entry_frozen():
    entry = HistoryEntry(text="hello", language="eng")
    with pytest.raises(FrozenInstanceError):
        entry.text = "changed"  # type: ignore[misc]


def test_entry_serialize_roundtrip():
    entry = HistoryEntry(text="ciao", language="ita", applied_name="Magic", conf=91.5)
    data = entry.to_dict()
    restored = HistoryEntry.from_dict(data)
    assert restored == entry


def test_entry_deserialize_defensive():
    assert HistoryEntry.from_dict(None) is None
    assert HistoryEntry.from_dict("nope") is None
    assert HistoryEntry.from_dict({}) is None
    assert HistoryEntry.from_dict({"text": "x"}) is None  # missing fields
    # Partially valid data with wrong types
    assert HistoryEntry.from_dict({"text": "x", "language": 1, "timestamp": "t", "id": "i"}) is None


# ---------------------------------------------------------------------- #
# Persistence
# ---------------------------------------------------------------------- #


def test_empty_history(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    assert service.get_entries() == []


def test_record_and_read(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("first", "eng")
    service.record("second", "eng")
    entries = service.get_entries()
    assert [e.text for e in entries] == ["second", "first"]


def test_data_survives_reopen(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    entry = service.record("persisted", "ita", applied_name="Magic", conf=88.0)
    reopened = HistoryService(base_dir=tmp_path)
    entries = reopened.get_entries()
    assert len(entries) == 1
    assert entries[0] == entry


def test_newest_first(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    for i in range(5):
        service.record(f"text-{i}", "eng")
    entries = service.get_entries()
    assert [e.text for e in entries] == [f"text-{i}" for i in (4, 3, 2, 1, 0)]


def test_limit_evicts_oldest(tmp_path):
    service = HistoryService(base_dir=tmp_path, limit=50)
    for i in range(51):
        service.record(f"text-{i}", "eng")
    entries = service.get_entries()
    assert len(entries) == 50
    assert entries[0].text == "text-50"
    assert entries[-1].text == "text-1"  # text-0 evicted


def test_get_entries_explicit_limit(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    for i in range(20):
        service.record(f"text-{i}", "eng")
    entries = service.get_entries(limit=10)
    assert len(entries) == 10
    assert entries[0].text == "text-19"


def test_clear(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("something", "eng")
    service.clear()
    assert service.get_entries() == []
    # Persisted too
    assert HistoryService(base_dir=tmp_path).get_entries() == []


# ---------------------------------------------------------------------- #
# Atomic write
# ---------------------------------------------------------------------- #


def test_atomic_write_no_temp_files(tmp_path):
    service = HistoryService(base_dir=tmp_path)
    service.record("atomic", "eng")
    history_file = tmp_path / "history.json"
    assert history_file.exists()
    data = json.loads(history_file.read_text(encoding="utf-8"))
    assert data[0]["text"] == "atomic"
    leftovers = [p for p in tmp_path.iterdir() if p.name != "history.json"]
    assert leftovers == []


# ---------------------------------------------------------------------- #
# Corruption recovery
# ---------------------------------------------------------------------- #


def test_corrupted_file_recovered(tmp_path):
    (tmp_path / "history.json").write_text("{ this is not valid json", encoding="utf-8")
    service = HistoryService(base_dir=tmp_path)
    assert service.get_entries() == []
    quarantined = list(tmp_path.glob("history.json.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{ this is not valid json"


def test_service_survives_quarantine_failure(tmp_path):
    history_file = tmp_path / "history.json"
    history_file.write_text("not json", encoding="utf-8")
    # Make the file undeletable/renamable to force the fallback path
    tmp_path.chmod(0o555)
    try:
        service = HistoryService(base_dir=tmp_path)
        assert service.get_entries() == []  # must not crash
    finally:
        tmp_path.chmod(0o755)
