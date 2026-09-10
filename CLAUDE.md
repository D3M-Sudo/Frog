# CLAUDE.md — Anura OCR Project Guide

> Rules for the AI agent. Automatically read at the start of each session.

## Tech Stack

- **Language**: Python 3.12+
- **Build**: Meson ≥ 1.5.0
- **Distribuzione**: Flatpak (`io.github.d3msudo.anura`)
- **UI**: GTK4 + Libadwaita + Blueprint Compiler 0.16.0
- **OCR**: pytesseract + Tesseract 5.3.4
- **QR/Barcode**: zxing-cpp 3.0.0 (replaces pyzbar)
- **Image Processing**: Leptonica 1.87.0
- **TTS**: gTTS + GStreamer playbin3
- **Screenshots**: Xdp.Portal (libportal) + fallback **scrot** (X11)
- **Settings**: GSettings singleton → `anura/services/settings.py`
- **Linter**: **ruff** solo — mai flake8, pylint o black

## Architecture

### Philosophy
- SOLID, KISS, DRY. Controller-based Composition over mixins for "God" classes (e.g., `AnuraWindow`).
- `AtomicTaskManager` for single-slot asynchronous execution with UUID versioning.
- Mandatory type hints on public functions.
- `validators.sanitize_text` for OCR output cleaning (Unicode control chars, Private Use/Surrogate categories).
- `uri_validator()` for centralized URI validation with homograph attack prevention.

### Project Structure
```
anura/
├── main.py              ← AnuraApplication (Adw.Application)
├── window.py            ← AnuraWindow (Controller Composition)
├── config.py            ← Constants, tessdata URL, lang_code validation
├── _release_notes.py    Auto-generated release notes (do not edit)
├── core/                ← atomic_task_manager, boot, logger, i18n, resources, dialogs, silent_runner
├── controllers/         ← ocr_controller, tts_controller, dnd_controller
├── services/            ← clipboard, screenshot, notification, tts, share, settings, language_manager
├── services/language/   ← cache_manager, download_manager, language_validator (specialized managers)
├── services/tts/        ← audio_player, language_mapper, pipeline_manager, service, speech_generator
├── services/screenshot/ ← base, factory, legacy_provider, portal_provider
├── models/              ← context, download_state, language_item, ocr (immutable dataclasses)
├── transformers/        ← magic_processor, base_transformers, email_transformer, url_transformer
├── utils/               ← barcode_detector, image_filters, structural_reconstructor, validators
└── widgets/             ← extracted_page, welcome_page, preferences, shortcuts_overlay
data/
├── ui/                  Blueprint files (.blp) → compiled to .ui
├── icons/               Scalable SVG icons + symbolic variants
├── screenshots/         Screenshots for Flathub/metainfo
└── *.xml                GResource, GSchema, desktop, metainfo files
build-aux/
├── release.sh           Release script (pin tessdata SHA, bump version)
├── generate_release_notes.py CHANGELOG.md parser → _release_notes.py
├── setup-gschema.sh     GSettings schema compilation for testing
└── meson/postinstall.py Post-install script
flatpak/
└── io.github.d3msudo.anura.json Flatpak manifest with all dependencies
po/                     Gettext translations (25+ languages)
tests/                  Unit, integration, security, and enterprise tests
```

## Code Rules — ABSOLUTE

### Thread Safety & Atomic Execution
- **NEVER** emit GObject signals or modify UI from secondary threads.
- **ALWAYS** use `AtomicTaskManager.execute()`.
- Automatic discard of obsolete results via task ID.
- `SignalManagerMixin` + `connect_tracked()` for automatic signal cleanup.

### Protected Files — NEVER MODIFY
- `po/*.po`
- `anura/_release_notes.py`
- `data/ui/*.ui` (generated from .blp files)
- `builddir/` (build artifacts)
- `CHANGELOG.md` (manutenzione via Keep a Changelog)

### Internationalization (i18n)
- `_("text {var}").format(var=value)` — NEVER `_(f"...")`.
- `ngettext()` for plurals.
- After new UI strings → `cd po && ./update_potfiles.sh`.

### Error Handling — Early Return Pattern
- Guards and validations at the beginning. Happy path at the end.
- No generic `except Exception` that silences bugs.

### Dependencies
- **`uv` exclusive**: `uv add`, `uv sync`. Never `pip` or `poetry`.

## Development Commands

### Setup & Build
```bash
uv sync --dev
uv run meson setup builddir
uv run meson compile -C builddir
GSETTINGS_SCHEMA_DIR=builddir/data python3 -m anura.main
```

### Testing
```bash
# Headless
uv run pytest tests/ -v -m "not gtk"
# Full (requires display)
./build-aux/setup-gschema.sh && ./tests/setup_resources.sh
export GSETTINGS_SCHEMA_DIR="builddir"
uv run pytest tests/ -v
```

## Security & Privacy
- **DoS**: `MAX_IMAGE_SIZE_BYTES` validation before loading.
- **Sanitization**: Removal of Unicode control characters from OCR.
- **Validation**: Strict URI check before `UriLauncher`.
- **Zero Telemetry**: No tracking or analytics.
