# Skill: Testing Anura

Testing strategy and environment setup for Anura OCR.

## Environment Setup

### System Requirements (Ubuntu/Debian)
```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
    blueprint-compiler libportal-gtk4-dev \
    tesseract-ocr libxml2-utils \
    gstreamer1.0-plugins-good gstreamer1.0-pulseaudio
```

### Python Setup
```bash
uv sync --dev
```

## Running Tests

### Headless Tests (Business Logic & Security)
These tests do not require a display and are suitable for CI and rapid development.
```bash
uv run pytest tests/ -m "not gtk" -v
```

### GTK Integration Tests
These tests require a live display or a Flatpak environment.
```bash
./build-aux/setup-gschema.sh
./tests/setup_resources.sh
export GSETTINGS_SCHEMA_DIR="builddir"
uv run env PYTHONPATH="/usr/lib/python3/dist-packages:$PYTHONPATH" \
  GI_TYPELIB_PATH="/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0" \
  GSETTINGS_SCHEMA_DIR="builddir" \
  pytest tests/ -v
```

## Key Test Files
- `tests/test_gi_atomic_task_manager_unit.py`: Atomic task execution and versioning.
- `tests/test_security_hardening.py`: DoS prevention and URI validation.
- `tests/test_file_dialog_regressions.py`: GTK FileFilter stability.
- `tests/test_screenshot_service.py`: Screenshot capture and OCR pipeline.

## Best Practices
- **Mocking**: Use `unittest.mock` for GTK dependencies in unit tests.
- **Async**: Verify `AtomicTaskManager` behavior for background tasks.
- **Resource Cleanup**: Ensure temp files are removed in `finally` blocks.
- **Thread Safety**: Never emit GObject signals from secondary threads.
