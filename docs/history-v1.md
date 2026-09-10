# Anura — Extraction History V1 (current behaviour on `testing`)

This document is the **normative** reference for the completed History V1
integration. The pre-implementation plan is preserved as historical material in
[planning/history-v1-plan.md](planning/history-v1-plan.md) and must not be
treated as current guidance.

## What History V1 provides

- Opt-in local history of recent OCR extractions, newest-first.
- Read-only history page (`HistoryPage`, `data/ui/history_page.blp`) with
  empty/disabled/entries states and a destructive clear action with
  confirmation (`Adw.MessageDialog`).
- Navigation entry via the `win.show-history` action from the welcome page.
- History preferences in `PreferencesGeneralPage` (`Save Extraction History`
  switch + `History Size` spin row).

What History V1 does **not** provide: search, thumbnails, image archiving,
SQLite/database storage, cloud sync, export/import, tags/folders, editing of
historical entries, or OCR result versioning.

## Persistence

- Backend: `anura/services/history_service.py` (`HistoryService`).
- Store: `$XDG_DATA_HOME/anura/history/history.json` (synchronous local JSON).
- Writes are atomic (temp file + `os.replace` with `fsync`); no temp files are
  left behind.
- Corruption recovery: an unreadable/non-list JSON file is quarantined as
  `history.json.corrupt-<epoch>` instead of being deleted, and loading
  continues with an empty history. Structurally invalid entries are skipped via
  defensive `HistoryEntry.from_dict()` deserialization.
- History recording never breaks OCR: persistence failures (`OSError`) are
  caught and logged in `OcrController._record_history()`.

## Recorded fields

`anura/models/history.py` (`HistoryEntry`, frozen dataclass):

| Field | Source |
| --- | --- |
| `text` | Extracted text at OCR completion |
| `language` | Active OCR language (`AnuraWindow.get_language()`) |
| `applied_name` | Transformer name selected by the OCR pipeline |
| `conf` | Average OCR confidence (`OcrResult.avg_confidence`) |
| `timestamp` | UTC ISO-8601 timestamp (auto-generated) |
| `id` | UUID (auto-generated) |

Recording rules (see `anura/controllers/ocr_controller.py`):

- Only successful extractions are recorded (empty text is never stored).
- Recording happens only when `history-enabled` is `true`.
- `AnuraWindow` wires a single shared `HistoryService` with the configured
  limit and injects it into both `OcrController` and `HistoryPage`.

## Settings (GSettings)

Defined in `data/io.github.d3msudo.anura.gschema.xml`:

| Key | Type | Default | Range |
| --- | --- | --- | --- |
| `history-enabled` | boolean | `false` | — |
| `history-limit` | int | `50` | `1`–`500` |

Notes:

- `history-enabled=false` disables recording but does **not** delete already
  stored history.
- `history-limit` is applied both when entries are recorded (oldest evicted)
  and when entries are loaded.
- Changing the limit requires an application restart to re-wire the shared
  `HistoryService` (the limit is read once at window construction).

## UI behaviour

- `HistoryPage.refresh()` reloads entries from the injected service.
- Disabled recording with no entries shows the `disabled` state; enabled
  recording with no entries shows the `empty` state; otherwise the `entries`
  list is shown newest-first.
- Row title: first line of the extracted text (capped at 200 chars).
- Row subtitle: `timestamp · language · applied_name · confidence%`, skipping
  empty fields.
- Malformed timestamps fall back to the raw string; formatting never crashes.
- Clear action removes all entries through the service and refreshes the page.

## Lifecycle and boundaries

- `HistoryService` is synchronous and runs on the GTK main thread; this is
  acceptable for the small bounded JSON writes of V1.
- No threading, no database, no image/thumbnail lifecycle in V1.
- Storage boundary: local user data only (`$XDG_DATA_HOME/anura/history/`),
  consistent with the zero-telemetry privacy model.

## Tests

| File | Coverage |
| --- | --- |
| `tests/test_history_storage.py` | Entry model, persistence, newest-first order, limit eviction, atomic writes, corruption recovery |
| `tests/test_history_controller_integration.py` | Enabled/disabled recording, field wiring, failure isolation, window wiring |
| `tests/test_history_ui.py` | Page states, entry display order, defensive formatting, clear action |
| `tests/test_history_settings.py` (`@pytest.mark.gtk`) | GSettings defaults, ranges, read/write |

## Limitations

- No search or filtering.
- No thumbnails or source-image retention.
- Limit changes require restart.
- Synchronous I/O on the main thread (bounded by the entry limit).
