<h1 align="center">Anura</h1>

<p align="center">
  Jumping from pixels to text in a single leap
</p>

<p align="center">
  <strong>Intuitive text extraction for the Linux desktop.</strong><br>
  OCR · QR/Barcode Decoding · Privacy-first · Native GTK4
</p>

<p align="center">
  <img src="data/screenshots/anura-window-dark.png" alt="Anura Screenshot" width="800" />
</p>

<p align="center">
  <a href="https://github.com/D3M-Sudo/Anura/releases/latest">
    <img src="https://img.shields.io/github/v/release/D3M-Sudo/Anura?color=4A90D9&logo=github&label=release&style=flat-square" alt="Latest Release" />
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-22c55e?style=flat-square" alt="License: MIT" />
  </a>
  <a href="https://hosted.weblate.org/engage/anura/">
    <img src="https://img.shields.io/badge/translations-Weblate-orange?style=flat-square" alt="Translation status" />
  </a>
  <a href="https://github.com/D3M-Sudo/Anura/releases/latest">
    <img src="https://img.shields.io/badge/distribution-Flatpak-4A90D9?style=flat-square&logo=flatpak" alt="Flatpak" />
  </a>
</p>

---

Anura lets you capture any region of your screen and instantly extract the text inside — from videos, screencasts, PDFs, webpages, or photos. The result lands straight in your clipboard, ready to paste.

It also decodes **QR codes and Barcodes** in a single click using **zxing-cpp**, with full system integration on modern GTK-based Linux desktops.

---

## Features

| | |
| --- | --- |
| 📷 **Instant OCR** | Select a screen region — text is copied automatically |
| 🔲 **QR & Barcode Decoding** | Robust recognition via `zxing-cpp` (QR, DataMatrix, UPC, etc.) |
| 🌍 **Multi-language** | Supports 100+ Tesseract models with pooling for simultaneous multi-lang OCR |
| 🔊 **Text-to-Speech** | Read extracted text aloud via gTTS + GStreamer `playbin3` |
| 🎨 **Theme Selector** | Choose between System, Light, or Dark theme via Adw.StyleManager |
| ✏️ **Selection-Aware Actions** | Text statistics and actions based on selection in OCR results |
| ↩️ **Undo/Redo** | Full undo/redo support in ExtractedPage for text editing workflow |
| 🔒 **Privacy-first** | All processing happens locally — no telemetry or tracking |
| 🎨 **Native GTK4** | Designed for GNOME, built with Libadwaita and Blueprint |
| 🚀 **Async D&D** | Smooth, non-blocking asynchronous drag-and-drop |
| ♿ **Enhanced Accessibility** | Improved keyboard navigation, tooltips, and screen reader support |
| ✨ **Smart OCR Cleanup** | Adaptive image enhancement and structural layout reconstruction |
| 🛡️ **Architectural Security** | Transactional worker isolation and OOM prevention guards |
| 📜 **Offline Rotary Logs** | Secure, zero-telemetry local logging system |
| ⌨️ **Keyboard Shortcuts** | Modern shortcut overlay with categorized searchable cheat sheet |
| 🔗 **Share Anywhere** | Share to Telegram, Reddit, Mastodon, X, Email, Bluesky, Discord, LinkedIn, Threads |
| 🕘 **Extraction History** | Opt-in local history of recent extractions (JSON, newest-first, with clear action) — see [docs/history-v1.md](docs/history-v1.md) |

---

## Architecture

As of **v0.1.5**, Anura features an **Enterprise Clean Architecture** focused on event-driven decoupling and memory safety:

- **Core Services (`anura/core/`)**: Pure infrastructure logic. Includes `boot` (capability audit), `logger` (rotary logging), `atomic_task_manager` (isolated worker pool), and `resources`.
- **Business Services (`anura/services/`)**: High-level I/O and resource management. Includes `language_manager` (Tessdata coordination), specialized language managers (DownloadManager, CacheManager, LanguageValidator), `screenshot` (multi-provider capture factory), `history_service` (opt-in local JSON history, see [docs/history-v1.md](docs/history-v1.md)), and `settings`.
- **Event-Driven Controllers (`anura/controllers/`)**: Logic-only components that emit GLib signals. `OcrController` (OCR + history recording gate), `TtsController`, and `DndController` are fully decoupled from UI side-effects, which are handled by the main application coordinator.
- **Semantic Transformers (`anura/transformers/`)**: Implements the **Chain of Responsibility** pattern. The `MagicProcessor` dynamically selects the best `ITransformer` for structured data extraction.
- **Memory Safety**: Uses `weakref.proxy` for View-Controller relationships and asynchronous native Gio APIs for non-blocking I/O.

---

## Installation

### Flatpak — Stable Release

Download the `.flatpak` bundle from the [Releases](https://github.com/D3M-Sudo/Anura/releases/latest) page, then install:

```bash
flatpak install --user ~/Downloads/io.github.d3msudo.anura.flatpak
```

### Runtime requirements

Anura captures screenshots through the **XDG Desktop Portal**. The portal frontend is shipped with `xdg-desktop-portal`, but it needs a *backend* matching your desktop session.

| Desktop session | Install command (Ubuntu 24.04+) | Notes |
| --- | --- | --- |
| GNOME / Ubuntu Desktop | already installed | Uses `xdg-desktop-portal-gnome` |
| KDE Plasma / Kubuntu | already installed | Uses `xdg-desktop-portal-kde` |
| **LXQt / Lubuntu** | `sudo apt install xdg-desktop-portal-gtk` | Uses `xdg-desktop-portal-gtk` (legacy) or `xdg-desktop-portal-kde` |
| Xfce / MATE | `sudo apt install xdg-desktop-portal-gnome` | Backend needed for Screenshot interface |
| wlroots (Sway, Hyprland) | `sudo apt install xdg-desktop-portal-wlr` | Requires screencast support |

#### Host screenshot fallback (Flatpak + X11 only)

On **X11 sessions**, if the portal fails, Anura automatically falls back to a **bundled `scrot`** inside the sandbox. This is self-contained and requires no host tools.

---

## Troubleshooting

### Debug Logging

Anura supports configurable logging levels via the `ANURA_LOG_LEVEL` environment variable:

```bash
ANURA_LOG_LEVEL=DEBUG flatpak run io.github.d3msudo.anura
```

Valid levels: `TRACE`, `DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`

---

## Building from Source

### Prerequisites

| Tool | Version |
| ---- | ------- |
| Meson | ≥ 1.5.0 |
| Python | ≥ 3.12 |
| GTK4 + Libadwaita | latest |
| Tesseract OCR | 5.3.4 |
| zxing-cpp | 3.0.0 |
| Leptonica | 1.87.0 |
| Blueprint Compiler | ≥ 0.16.0 |
| gettext | latest |
| uv | latest |

**Ubuntu / Linux Mint / Debian:**

```bash
sudo apt install meson gettext python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
    tesseract-ocr blueprint-compiler libxml2-utils \
    leptonica-progs liblibleptonica-dev
```

---

### Meson *(manual)*

```bash
git clone https://github.com/D3M-Sudo/Anura.git
cd Anura

# Setup and build using uv
uv sync --dev
uv run meson setup builddir
uv run meson compile -C builddir

# Run without installing
GSETTINGS_SCHEMA_DIR=builddir/data python3 -m anura.main
```

---

## Code Quality

Anura uses **Ruff** for linting and **pytest** for testing, managed via **uv**.

```bash
# Run headless unit/security tests
uv run pytest tests/ -m "not gtk" -v

# Run full suite (requires GTK environment)
./build-aux/setup-gschema.sh
./tests/setup_resources.sh
export GSETTINGS_SCHEMA_DIR="builddir"
uv run pytest tests/ -v
```

The test suite includes headless unit tests (logic without GTK dependencies), integration tests (GTK/GLib environment), security/hardening tests (DoS prevention, URI validation, sanitization), and reliability/enterprise tests (performance benchmarks, concurrency, lifecycle). History V1 behaviour is covered by `tests/test_history_storage.py`, `tests/test_history_controller_integration.py`, `tests/test_history_ui.py`, and `tests/test_history_settings.py` (GTK-marked).

---

## Documentation

- [docs/README.md](docs/README.md) — documentation index
- [docs/history-v1.md](docs/history-v1.md) — Extraction History V1 (current behaviour)
- [docs/dependencies.md](docs/dependencies.md) — Python/Flatpak dependency workflow (uv.lock, sync, FEDC/certifi)
- [AGENTS.md](AGENTS.md) — canonical AI-assistant and architecture guide
- [CONTRIBUTING.md](CONTRIBUTING.md) — contributor and development workflow

---

## Localization

Anura is translated via [Weblate](https://hosted.weblate.org/engage/anura/).

Contributions in any language are welcome.


<p align="center">
 <a href="https://hosted.weblate.org/engage/anura/">
  <img src="https://hosted.weblate.org/widgets/anura/-/horizontal-auto.svg" alt="Translation status" />
 </a>
</p>

**For maintainers** — update translatable strings:

```bash
cd po
./update_potfiles.sh
for f in *.po; do msgmerge -U "$f" io.github.d3msudo.anura.pot --backup=none; done
```

---

## License

Released under the **MIT** license. See [`LICENSE`](LICENSE) for details.
