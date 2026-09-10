# Contributing to Anura OCR

> This file is read by AI coding agents (Cascade, Claude Code, Cursor, Aider).
> It complements AGENTS.md with workflow-specific guidelines.

## Quick Start

```bash
# 1. Clone and enter the repo
git clone https://github.com/d3msudo/anura && cd anura

# 2. Setup environment and install dev tools
uv sync --dev

# 3. Install system dependencies (Ubuntu/Debian)
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
    blueprint-compiler libportal-gtk4-dev \
    tesseract-ocr libxml2-utils scrot \
    gstreamer1.0-plugins-good gstreamer1.0-pulseaudio

# 4. Build with Meson
uv run meson setup builddir
uv run meson compile -C builddir

# 5. Run from source (no install needed)
GSETTINGS_SCHEMA_DIR=builddir/data python3 -m anura.main
```

## Running Tests

History V1 behaviour is covered by `tests/test_history_storage.py`,
`tests/test_history_controller_integration.py`, `tests/test_history_ui.py`,
and `tests/test_history_settings.py` (GTK-marked). See
[docs/history-v1.md](docs/history-v1.md) for the current History V1 reference.

### Test Categories

Anura has two main categories of tests:

1. **Unit & Security Tests** - Logic without GTK dependencies (headless tests)
2. **Integration Tests** - Require GTK/GLib environment

### 🚀 QUICK START - Daily Development

```bash
# Run unit tests (ALWAYS use this for daily development)
uv run pytest tests/ -m "not gtk" -v
```

### 📋 COMPLETE TEST COMMANDS

#### **Unit Tests (No GTK Required)**
```bash
# All headless unit tests
uv run pytest tests/ -m "not gtk" -v

# Run specific unit test files
uv run pytest tests/test_gi_atomic_task_manager_unit.py -v
uv run pytest tests/test_security_hardening.py -v
uv run pytest tests/test_history_storage.py -v
```

#### **GTK Tests (Requires display/sandbox)**

```bash
# 1. Setup GSettings schema and resources
./build-aux/setup-gschema.sh
./tests/setup_resources.sh

# 2. Run GTK service tests
export GSETTINGS_SCHEMA_DIR="builddir"
uv run env PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" \
  GI_TYPELIB_PATH="/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0" \
  GSETTINGS_SCHEMA_DIR="builddir" \
  pytest tests/ -v
```

### ⚠️ IMPORTANT - WHAT NOT TO DO

```bash
# ❌ NEVER run this without a display or proper setup
uv run pytest tests/ -v
# Result: will fail — many GTK tests require a live display/Wayland session
```

## Linting

```bash
# Strict enforcement of Ruff (E402, I001)
uv run ruff check anura/

# Format according to project style
uv run ruff format anura/
```

## Branch & Commit Conventions

- **Branch names**: `feature/short-description`, `fix/short-description`
- **Base branch for integration work**: `testing` (Dependabot and FEDC automation target `testing`; see [docs/dependencies.md](docs/dependencies.md))
- **Commit messages**: Use [Conventional Commits](https://www.conventionalcommits.org/).
- Every change should be documented in `CHANGELOG.md` under `[Unreleased]`.

## Security Checklist (before every PR)

- [ ] **DoS Prevention**: Image size validated with `MAX_IMAGE_SIZE_BYTES`.
- [ ] **Text Sanitization**: OCR output passed through `validators.sanitize_text`.
- [ ] **URI Validation**: URLs checked with `uri_validator()` before launch.
- [ ] **Pango Markup Prevention**: User input in notifications sanitized against markup injection.
- [ ] **Thread Safety**: No UI modifications from secondary threads; use `AtomicTaskManager`.
- [ ] **Signal Lifecycle**: Use `SignalManagerMixin` for automated cleanup.
- [ ] **No Telemetry**: Absolute privacy maintained.
- [ ] **Fallback Security**: `scrot` fallback only active on X11; Wayland relies on Portals.
